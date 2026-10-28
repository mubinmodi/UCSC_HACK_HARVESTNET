"""Per-sender authentication for organization turn messages. Standard library only.

Every sender has its own key: the turn publisher (``core``, the process that publishes
the negotiation's turns) and each organization. A message is signed with HMAC-SHA256
over a canonical body: sender, recipient, timestamp, nonce and the whole envelope
(event, sequence, turn and input). The recipient checks the claimed sender's key, its
own name as the recipient, the timestamp window and that the nonce is new.

Keys are pairwise. A sender keeps its own key and derives one key per recipient
(``pair_key``). A recipient is given only the keys derived for itself, so it can check
a message addressed to it but cannot forge one from that sender to anyone else. That is
what a shared token could not do: with one token, any organization could speak as any
other.

Who may publish a turn: the turn publisher may publish any organization's turn. An
organization may publish only its own turn (sender and turn must match), and only under
an event ID that starts with its own name and a colon, so it can never step into the
publisher's events. Today the organization hosts only receive; their signing keys are
there for organization-to-organization messages.

Receipts that come back on the same HTTP exchange are not signed here; the publisher
chose the endpoint and checks the receipt's organization, event and sequence.
"""
import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from pathlib import Path

from .roster import ORGANIZATIONS

TURN_PUBLISHER = 'core'
SENDERS = (TURN_PUBLISHER, *ORGANIZATIONS)
SCHEME = 'harvestnet-hmac-sha256-v1'
MAX_SKEW_SECONDS = 120
_NONCE = re.compile(r'^[A-Za-z0-9_-]{16,64}$')
_HEX = re.compile(r'^[0-9a-f]{64}$')


class AuthError(ValueError):
    """A message that is not authentic, not for this recipient, stale or replayed."""


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def pair_key(sender_key, recipient):
    """The key ``sender`` uses for messages to ``recipient``, derived from the sender's own key."""
    if not isinstance(sender_key, str) or len(sender_key) < 32:
        raise ValueError('A transport key needs at least 32 characters')
    if recipient not in SENDERS:
        raise ValueError('Unknown transport recipient')
    return hmac.new(sender_key.encode(), f'{SCHEME}|recipient|{recipient}'.encode(), hashlib.sha256).hexdigest()


def signing_body(sender, recipient, timestamp, nonce, envelope):
    return _canonical({'scheme': SCHEME, 'sender': sender, 'recipient': recipient,
                       'timestamp': timestamp, 'nonce': nonce, 'envelope': envelope}).encode()


def strip_auth(message):
    """The envelope without its ``auth`` block (what the receiver and its receipts see)."""
    return {key: value for key, value in message.items() if key != 'auth'}


class Signer:
    """Signs messages from one sender with that sender's own key."""

    def __init__(self, sender, key, clock=time.time):
        if sender not in SENDERS:
            raise ValueError('Unknown transport sender')
        pair_key(key, TURN_PUBLISHER)  # validates the key
        self.sender, self.key, self.clock = sender, key, clock

    @classmethod
    def from_env(cls, sender=None, environ=None):
        environ = os.environ if environ is None else environ
        sender = sender or environ.get('TRANSPORT_SENDER', TURN_PUBLISHER)
        key = environ.get('TRANSPORT_SIGNING_KEY')
        if not key:
            raise ValueError('TRANSPORT_SIGNING_KEY is required to send organization messages')
        return cls(sender, key)

    def sign(self, envelope, recipient):
        if not isinstance(envelope, dict) or 'auth' in envelope:
            raise ValueError('Sign an unsigned envelope object')
        timestamp, nonce = int(self.clock()), secrets.token_urlsafe(18)
        signature = hmac.new(pair_key(self.key, recipient).encode(),
                             signing_body(self.sender, recipient, timestamp, nonce, envelope), hashlib.sha256).hexdigest()
        return {**envelope, 'auth': {'scheme': SCHEME, 'sender': self.sender, 'recipient': recipient,
                                     'timestamp': timestamp, 'nonce': nonce, 'signature': signature}}


class Verifier:
    """Checks messages addressed to one recipient. ``keys`` maps sender to its pair key for us."""

    def __init__(self, recipient, keys, db_path=':memory:', clock=time.time, max_skew=MAX_SKEW_SECONDS):
        if recipient not in SENDERS:
            raise ValueError('Unknown transport recipient')
        if not isinstance(keys, dict) or not keys or any(
                sender not in SENDERS or not isinstance(key, str) or not _HEX.match(key) for sender, key in keys.items()):
            raise ValueError('Verification keys must map known senders to derived 64-hex keys')
        self.recipient, self.keys, self.clock, self.max_skew = recipient, dict(keys), clock, max_skew
        if db_path != ':memory:':
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        # Seen nonces survive a restart when the receipts database is on disk.
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS transport_nonces (nonce TEXT PRIMARY KEY, expires REAL)')
        self.db.commit()
        self.lock = threading.Lock()

    @classmethod
    def from_env(cls, recipient, db_path=':memory:', environ=None):
        environ = os.environ if environ is None else environ
        raw = environ.get('TRANSPORT_VERIFY_KEYS')
        if not raw:
            raise ValueError('TRANSPORT_VERIFY_KEYS is required: a JSON map of sender to the key derived for this host '
                             '(python -m harvestnet_platform.transport_auth generates them)')
        try:
            keys = json.loads(raw)
        except ValueError as exc:
            raise ValueError('TRANSPORT_VERIFY_KEYS must be a JSON object') from exc
        return cls(recipient, keys, db_path)

    def verify(self, message):
        """The authenticated envelope without ``auth``, or ``AuthError``. Records the nonce."""
        if not isinstance(message, dict) or not isinstance(message.get('auth'), dict):
            raise AuthError('A signed organization message is required')
        auth, envelope = message['auth'], strip_auth(message)
        sender, recipient, timestamp, nonce = (auth.get(k) for k in ('sender', 'recipient', 'timestamp', 'nonce'))
        signature = auth.get('signature')
        if auth.get('scheme') != SCHEME or type(timestamp) is not int or not isinstance(nonce, str) or not _NONCE.match(nonce) \
                or not isinstance(signature, str):
            raise AuthError('Malformed message signature')
        if sender not in self.keys:
            raise AuthError('Unknown sender')
        if recipient != self.recipient:
            raise AuthError('Message is addressed to another recipient')
        expected = hmac.new(self.keys[sender].encode(), signing_body(sender, recipient, timestamp, nonce, envelope),
                            hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise AuthError('Signature does not match the claimed sender')
        now = self.clock()
        if abs(now - timestamp) > self.max_skew:
            raise AuthError('Stale or future-dated message')
        turn, event = envelope.get('turn'), envelope.get('event_id')
        if sender != TURN_PUBLISHER:
            if turn != sender:
                raise AuthError('An organization may publish only its own turn')
            if not isinstance(event, str) or not event.startswith(sender + ':'):
                raise AuthError("An organization's own events are named '<organization>:...'")
        elif isinstance(event, str) and event.split(':', 1)[0] in ORGANIZATIONS and ':' in event:
            raise AuthError("The turn publisher does not use an organization's event names")
        with self.lock:
            self.db.execute('DELETE FROM transport_nonces WHERE expires < ?', (now,))
            try:
                self.db.execute('INSERT INTO transport_nonces VALUES (?, ?)', (f'{sender}:{nonce}', now + 2 * self.max_skew))
            except sqlite3.IntegrityError:
                self.db.rollback()
                raise AuthError('Replayed message') from None
            self.db.commit()
        return envelope


def generate_keys():
    """New random sending keys, one per sender."""
    return {sender: secrets.token_hex(32) for sender in SENDERS}


def host_env(transport_keys):
    """Per-host settings derived from the senders' keys.

    ``TRANSPORT_SIGNING_KEY_<SENDER>`` is that sender's own key; ``TRANSPORT_VERIFY_KEYS_<HOST>``
    holds only the keys derived for that host. Give each host only its own two values.
    """
    if not isinstance(transport_keys, dict) or set(transport_keys) != set(SENDERS):
        raise ValueError(f'TRANSPORT_KEYS must hold one key for each of: {", ".join(SENDERS)}')
    env = {}
    for sender in SENDERS:
        env[f'TRANSPORT_SIGNING_KEY_{sender.upper()}'] = transport_keys[sender]
    for host in SENDERS:
        env[f'TRANSPORT_VERIFY_KEYS_{host.upper()}'] = _canonical(
            {sender: pair_key(key, host) for sender, key in transport_keys.items() if sender != host})
    return env


def main():
    parser = argparse.ArgumentParser(description='Write new per-sender transport keys and the per-host settings '
                                                 'derived from them to a private env file. Values are never printed.')
    parser.add_argument('--output', required=True, help='env file to write (mode 0600); it must not exist yet')
    args = parser.parse_args()
    keys = generate_keys()
    lines = [f"TRANSPORT_KEYS='{_canonical(keys)}'"] + [f"{k}='{v}'" for k, v in host_env(keys).items()]
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        parser.error(f'{path} exists; new keys go to a new file (delete the old one to rotate every key)')
    with os.fdopen(descriptor, 'w') as stream:
        stream.write('\n'.join(lines) + '\n')
    print(f'Transport keys for {", ".join(SENDERS)} written to {path}; values are not printed.')


if __name__ == '__main__':
    main()
