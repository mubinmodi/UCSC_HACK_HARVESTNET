"""Version-bound human decisions. Neither n8n nor this store commits produce."""
import hashlib
import hmac
import html
import math
import json
import os
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, quote
from urllib.error import HTTPError, URLError
from .transport import canonical, terms_hash
from .http import JsonHandler, request_json, serve

APPROVERS = ('market', 'city', 'rural', 'eastside')
# The core's tests still invite the donor by role; the core maps it to the lot's donor.
LEGACY_APPROVERS = ('donor',)
MAX_LINK_TTL_SECONDS = 86400
CANT_MAKE_IT = ("can't make it", 'cant make it', 'cannot make it', "can't go", 'no puedo ir', 'no puedo')
YES = ('yes', 'y', 'si', 'sí', 'confirm', 'ok')


class StaleApproval(ValueError):
    pass


def iso(epoch):
    """Contract times are ISO 8601 with an offset (docs/contracts/README.md)."""
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


def link_ttl(value=None):
    raw = os.getenv('APPROVAL_LINK_TTL_SECONDS', '3600') if value is None else value
    if isinstance(raw, bool):
        raise ValueError('Approval link lifetime must be whole seconds')
    try:
        ttl = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError('Approval link lifetime must be whole seconds') from exc
    if not 1 <= ttl <= MAX_LINK_TTL_SECONDS:
        raise ValueError(f'Approval links expire within {MAX_LINK_TTL_SECONDS} seconds')
    return ttl


def same_hash(given, expected):
    """Accept the contract form (``sha256:<hex>``) and Lane C's earlier bare hex."""
    if isinstance(given, str) and len(given) == 64 and all(c in '0123456789abcdef' for c in given):
        given = 'sha256:' + given
    return given == expected


def phone_digits(phone):
    digits = ''.join(c for c in str(phone or '') if c.isdigit())
    if len(digits) == 10:  # a US number without its country code
        digits = '1' + digits
    if not 8 <= len(digits) <= 15:
        raise ValueError('A phone number is required')
    return digits


class ApprovalStore:
    def __init__(self, path=':memory:', clock=time.time, reply_key=None):
        if path != ':memory:':
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock, self.clock = threading.RLock(), clock
        # Phones are never stored: a reply is matched on a keyed hash of its number.
        # Without a configured key, bindings last only as long as this process.
        self.reply_key = (reply_key.encode() if isinstance(reply_key, str) else reply_key) or secrets.token_bytes(32)
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS drafts(event TEXT PRIMARY KEY, version INTEGER, terms TEXT, digest TEXT);
            CREATE TABLE IF NOT EXISTS links(token_hash TEXT PRIMARY KEY, event TEXT, version INTEGER,
                organization TEXT, digest TEXT, expires REAL, decision TEXT, receipt_id TEXT);
            CREATE TABLE IF NOT EXISTS reply_bindings(phone_key TEXT, pickup_id TEXT, request_code TEXT,
                release_token TEXT, food_bank TEXT, window_start TEXT, window_end TEXT, created REAL, expires REAL,
                PRIMARY KEY(phone_key, pickup_id));
        ''')

    @staticmethod
    def token_hash(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def _link(self, event, version, org, digest, terms, ttl):
        token = secrets.token_urlsafe(32)
        expires = self.clock() + ttl
        self.db.execute('INSERT INTO links VALUES (?,?,?,?,?,?,NULL,NULL)',
                        (self.token_hash(token), event, version, org, digest, expires))
        # event_id is Lane C's name for the same lot (README decision 7).
        return {'organization_id': org, 'lot_id': event, 'event_id': event, 'version': version,
                'terms_hash': digest, 'terms': terms, 'token': token, 'expires_at': iso(expires)}

    def request(self, event, version, terms, organizations, ttl=None, reissue=False):
        """Issue one review link per named organization for this exact version.

        A repeat of the same request (a webhook retry) is refused, so no extra links
        appear. ``reissue=True`` replaces a lost or expired link for the same version:
        the organization's old link stops working. A decided link can't be reissued.
        """
        if not isinstance(event, str) or not event or len(event) > 100 or type(version) is not int or version < 1:
            raise ValueError('Lot and positive draft version required')
        if not isinstance(terms, dict) or not terms or not organizations or len(set(organizations)) != len(organizations):
            raise ValueError('Exact complete terms and distinct approving organizations required')
        if any(org not in APPROVERS + LEGACY_APPROVERS for org in organizations):
            raise ValueError('Only named donor/food bank humans may approve')
        ttl = link_ttl(ttl)
        digest = terms_hash(terms)
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                current = self.db.execute('SELECT version,digest FROM drafts WHERE event=?', (event,)).fetchone()
                if current and (version < current[0] or (version == current[0] and digest != current[1])):
                    raise StaleApproval('Draft terms changed without a new version, or version is stale')
                if current and version == current[0]:
                    if not reissue:
                        # A webhook retry must not create additional vote links.
                        raise ValueError('Approval request already exists; reissue explicitly to replace a lost link')
                    links = []
                    for org in organizations:
                        decided = self.db.execute('SELECT 1 FROM links WHERE event=? AND version=? AND organization=? AND decision IS NOT NULL',
                                                  (event, version, org)).fetchone()
                        if decided:
                            raise ValueError(f'{org} already decided this version; a change needs a new version')
                        self.db.execute('UPDATE links SET expires=-1 WHERE event=? AND version=? AND organization=?', (event, version, org))
                        links.append(self._link(event, version, org, digest, terms, ttl))
                else:
                    self.db.execute('INSERT OR REPLACE INTO drafts VALUES (?,?,?,?)', (event,version,canonical(terms),digest))
                    links = [self._link(event, version, org, digest, terms, ttl) for org in organizations]
                self.db.commit()
                return links
            except Exception:
                self.db.rollback()
                raise

    def _view(self, token):
        row = self.db.execute('SELECT l.event,l.version,l.organization,l.digest,l.expires,l.decision,l.receipt_id,d.version,d.digest,d.terms FROM links l JOIN drafts d ON d.event=l.event WHERE l.token_hash=?', (self.token_hash(token),)).fetchone()
        if not row:
            raise ValueError('Unknown decision link')
        event, version, org, digest, expires, decision, receipt, current_version, current_hash, terms = row
        if expires < 0:
            raise StaleApproval('This link was replaced by a newer one; use the latest link sent to you')
        if expires <= self.clock():
            raise StaleApproval('Decision link expired; ask the organization for a new request')
        if (version, digest) != (current_version, current_hash):
            raise StaleApproval('Old version rejected; approve the new complete terms')
        return {'lot_id': event, 'event_id': event, 'version': version, 'organization_id': org,
                'terms_hash': digest, 'terms': json.loads(terms), 'decision': decision,
                'receipt_id': receipt, 'expires_at': iso(expires)}

    def view(self, token):
        with self.lock:
            return self._view(token)

    def decide(self, token, decision, version, digest, human_confirmed):
        if human_confirmed is not True or decision not in ('approve', 'decline'):
            raise ValueError('An explicit human approve/decline decision is required')
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                record = self._view(token)
                if version != record['version'] or not same_hash(digest, record['terms_hash']):
                    raise StaleApproval('Human decision does not match the displayed version and terms')
                if record['decision'] and record['decision'] != decision:
                    raise ValueError('Decision already recorded; change terms with a fresh version')
                if not record['decision']:
                    receipt = secrets.token_hex(16)
                    self.db.execute('UPDATE links SET decision=?,receipt_id=? WHERE token_hash=?',
                                    (decision,receipt,self.token_hash(token)))
                self.db.commit()
                return self._view(token)
            except Exception:
                self.db.rollback()
                raise

    def approved_organizations(self, event):
        with self.lock:
            rows = self.db.execute("SELECT organization FROM links l JOIN drafts d ON l.event=d.event AND l.version=d.version AND l.digest=d.digest WHERE l.event=? AND decision='approve' AND expires>?", (event,self.clock()))
            return sorted({row[0] for row in rows})

    # SMS replies: which pickup a text to this phone was about.

    def phone_key(self, phone):
        return hmac.new(self.reply_key, phone_digits(phone).encode(), hashlib.sha256).hexdigest()

    def bind_reply(self, notice, ttl=None):
        """Remember the pickup a text to this phone is about, so its reply acts on it."""
        ttl = int(os.getenv('REPLY_BINDING_TTL_SECONDS', '604800') if ttl is None else ttl)
        now = self.clock()
        with self.lock:
            self.db.execute('INSERT OR REPLACE INTO reply_bindings VALUES (?,?,?,?,?,?,?,?,?)', (
                self.phone_key(notice['to']), notice['pickup_id'], notice['request_code'], notice.get('release_token'),
                notice['food_bank'], notice['window']['start'], notice['window']['end'], now, now + ttl))
            self.db.commit()

    def reply_binding(self, phone):
        """The pickup in the last text sent to this phone, if it is still open."""
        with self.lock:
            row = self.db.execute('SELECT pickup_id,request_code,release_token,food_bank,window_start,window_end FROM reply_bindings '
                                  'WHERE phone_key=? AND expires>? ORDER BY created DESC, rowid DESC LIMIT 1',
                                  (self.phone_key(phone), self.clock())).fetchone()
        if not row:
            return None
        return dict(zip(('pickup_id', 'request_code', 'release_token', 'food_bank', 'window_start', 'window_end'), row))

    def unbind_reply(self, phone, pickup_id):
        with self.lock:
            self.db.execute('DELETE FROM reply_bindings WHERE phone_key=? AND pickup_id=?', (self.phone_key(phone), pickup_id))
            self.db.commit()


class CoreAPI:
    """The core's approval and release operations.

    ``token`` is each organization's own staff credential: a mapping of organization
    ID to token, in the same JSON shape as the core's ``HARVESTNET_STAFF_TOKENS``. A
    single string is sent for every organization, which only suits a one-organization client.
    """

    def __init__(self, base_url=None, token=None, decision_webhook=None, webhook_token=None):
        self.base_url = base_url.rstrip('/') if base_url else None
        if token is not None and not isinstance(token, (str, dict)):
            raise ValueError('Core credentials are a token or a mapping of organization to token')
        if isinstance(token, dict) and (any(not isinstance(v, str) or not v for v in token.values()) or len(set(token.values())) != len(token)):
            raise ValueError('Each organization needs its own nonempty core token')
        self.tokens = token
        self.decision_webhook, self.webhook_token = decision_webhook, webhook_token

    @classmethod
    def from_env(cls):
        """Per-organization tokens from ``CORE_API_TOKENS``, else the core's own
        ``HARVESTNET_STAFF_TOKENS`` (same JSON shape). A single legacy ``CORE_API_TOKEN``
        still works but only commits that one organization's decisions."""
        tokens = None
        for name in ('CORE_API_TOKENS', 'HARVESTNET_STAFF_TOKENS'):
            if os.getenv(name):
                tokens = json.loads(os.environ[name])
                if not isinstance(tokens, dict):
                    raise ValueError(f'{name} must be a JSON map of organization to token')
                break
        if tokens is None and os.getenv('CORE_API_TOKEN'):
            tokens = os.environ['CORE_API_TOKEN']
            print('Warning: one CORE_API_TOKEN for every organization; set CORE_API_TOKENS so each '
                  "organization's decisions use its own token", flush=True)
        if os.getenv('CORE_API_URL') and tokens is None:
            print('Warning: no core credentials; the core will refuse decisions (401) until CORE_API_TOKENS is set', flush=True)
        return cls(os.getenv('CORE_API_URL'), tokens, os.getenv('N8N_DECISION_WEBHOOK_URL'), os.getenv('N8N_WEBHOOK_TOKEN'))

    def token_for(self, organization):
        if isinstance(self.tokens, dict):
            if organization not in self.tokens:
                raise ValueError(f'No core credential configured for {organization}')
            return self.tokens[organization]
        return self.tokens

    def decision(self, record):
        if not self.base_url and not self.decision_webhook:
            return {'mode': 'local_approval_fallback', 'status': 'human_decision_recorded',
                    'committed': False, 'requires_core_validation': True, 'receipt_id': record['receipt_id']}
        # record_approval (docs/contracts/public-api.md; README decision 8).
        payload = {key: record[key] for key in ('lot_id', 'version', 'organization_id', 'terms_hash', 'decision', 'receipt_id')}
        if self.decision_webhook:
            if not self.webhook_token:
                raise ValueError('Authenticated n8n decision webhook token required')
            return request_json(self.decision_webhook, payload, token=self.webhook_token)
        return request_json(self.base_url + '/approvals', payload, token=self.token_for(record['organization_id']))

    def release(self, code, pickup_id, release_token=None):
        if not self.base_url:
            return {'mode': 'text_fallback', 'status': 'release_pending', 'released': False,
                    'reason': 'Core API unavailable; household portion has not been released'}
        # release_pickup: the request code ties the reply to its own pickup (README decision 9).
        # A pickup-scoped token is sent when the core issued one; never a staff token.
        return request_json(self.base_url + '/pickups/' + quote(pickup_id, safe='') + '/release',
                            {'request_code': code}, token=release_token)


def core_error(exc):
    """The core's own status and error, passed through rather than reported as an outage."""
    try:
        body = json.loads(exc.read() or b'{}')
    except (ValueError, OSError):
        body = {}
    if not isinstance(body, dict) or 'error' not in body:
        body = {'error': {'code': 'core_error', 'message': f'Core API returned {exc.code}'}}
    return exc.code, {**body, 'core_status': exc.code, 'committed': False}


def approval_message(link):
    return (f"HarvestNet: {link['organization_id']}, review draft version {link['version']} "
            f"for lot {link['lot_id']}. Exact terms: {canonical(link['terms'])}. "
            f"Review and choose Approve or Decline: {link['decision_url']}. No reply means no approval.")


def pickup_message(notice, *, now=None):
    if notice.get('committed') is not True:
        raise ValueError('Notify only produce with a recorded commitment')
    for field in ('food_bank', 'items', 'window', 'request_code', 'pickup_id', 'version', 'release_url'):
        if not notice.get(field):
            raise ValueError(f'Pickup notice requires {field}')
    if type(notice['version']) is not int or notice['version'] < 1:
        raise ValueError('Pickup notice requires a positive commitment version')
    if not isinstance(notice['window'], dict) or any(not isinstance(notice['window'].get(key), str) or not notice['window'][key].strip() for key in ('start', 'end')):
        raise ValueError('Pickup window requires start and end')
    if not isinstance(notice['items'], list) or any(not isinstance(item, dict) or not isinstance(item.get('name'), str) or not item['name'].strip() or type(item.get('pounds')) not in (int,float) or not math.isfinite(item['pounds']) or item['pounds'] <= 0 for item in notice['items']):
        raise ValueError('Pickup pounds must come from positive calculator results')
    words = PICKUP_TEXT.get(notice.get('language'), PICKUP_TEXT['en'])
    items = ', '.join(words['item'].format(lb=f"{item['pounds']:g}", name=item['name']) for item in notice['items'])
    message = words['body'].format(items=items, food_bank=notice['food_bank'], start=notice['window']['start'],
                                   end=notice['window']['end'], code=notice['request_code'], url=notice['release_url'])
    # The Market Match tip: SNAP households only, and only a verified, nearby, recently checked market.
    # Markets are trusted, verified records, never arbitrary model suggestions.
    market = notice.get('market')
    if notice.get('snap') == 'yes' and market and market.get('verified') is True and market.get('nearby') is True and market.get('source_url') and market.get('verified_at'):
        from datetime import timedelta
        checked = datetime.fromisoformat(market['verified_at'].replace('Z', '+00:00'))
        current = now or datetime.now(timezone.utc)
        if checked.tzinfo is None:
            raise ValueError('Market verification timestamp requires timezone')
        if current - timedelta(days=30) <= checked <= current:
            message += words['tip'].format(market=market['name'], url=market['source_url'])
    return message


# The household's pickup text, in its own language (ticket #6). The reply words match
# CANT_MAKE_IT and YES above. Numbers, names and times come only from the notice.
PICKUP_TEXT = {
    'en': {
        'item': '{lb} lb {name}',
        'body': ("HarvestNet: {items} at {food_bank}, {start} to {end}. Your code: {code}. "
                 "Wash before eating. Reply YES to confirm, or CAN'T MAKE IT to pass it to another family ({url})."),
        'tip': ' Market Match tip: ask {market} about its verified CalFresh produce match. {url}',
    },
    'es': {
        'item': '{lb} lb de {name}',
        'body': ('HarvestNet: {items} en {food_bank}, de {start} a {end}. Su código: {code}. '
                 'Lave los productos antes de comerlos. Responda SÍ para confirmar, o NO PUEDO IR para pasarla a otra familia ({url}).'),
        'tip': ' Consejo de Market Match: pregunte en {market} por su programa verificado que iguala sus dólares de CalFresh para frutas y verduras. {url}',
    },
}


def reply_words(data):
    text = data.get('text', data.get('Body'))
    return ' '.join(str(text or '').lower().replace('’', "'").strip().rstrip('.!').split())


def household_reply(store, core, data):
    """An SMS reply. YES confirms; CAN'T MAKE IT calls the core's release operation.

    The pickup is the one in the last text sent to the replying phone (recorded by
    ``/notifications/prepare``), or an explicit ``pickup_id`` and ``request_code`` from a
    trusted caller. Anything else gets the instructions back and changes nothing.
    """
    sender = data.get('from', data.get('From'))
    words = reply_words(data)
    if data.get('pickup_id') or data.get('request_code'):
        if not (data.get('pickup_id') and data.get('request_code')):
            raise ValueError('An explicit reply names both pickup_id and request_code')
        pickup = {'pickup_id': data['pickup_id'], 'request_code': data['request_code'],
                  'release_token': data.get('release_token'), 'food_bank': None}
    elif sender:
        pickup = store.reply_binding(sender)
    else:
        raise ValueError("A reply needs the sending phone, or the pickup it's about")
    base = {'to': sender, 'released': False}
    if pickup is None:
        return 200, {**base, 'status': 'no_open_pickup',
                     'message': "HarvestNet: we couldn't find an open pickup for this number. Nothing was changed."}
    if words in YES:
        where = f" at {pickup['food_bank']}, {pickup['window_start']} to {pickup['window_end']}" if pickup.get('food_bank') else ''
        return 200, {**base, 'status': 'confirmed', 'pickup_id': pickup['pickup_id'],
                     'message': f"HarvestNet: thanks, see you{where}. Your code: {pickup['request_code']}."}
    if words in CANT_MAKE_IT:
        result = core.release(pickup['request_code'], pickup['pickup_id'], pickup.get('release_token'))
        if result.get('released') is True and sender:
            store.unbind_reply(sender, pickup['pickup_id'])
        message = result.get('message') or ("HarvestNet: thanks for telling us. Your portion will go to another family."
                                            if result.get('released') else
                                            "HarvestNet: we got your reply but couldn't release the pickup yet. We'll try again.")
        return 200, {**result, 'to': sender, 'pickup_id': pickup['pickup_id'], 'message': message}
    return 200, {**base, 'status': 'ignored', 'pickup_id': pickup['pickup_id'],
                 'message': "HarvestNet: reply YES to confirm your pickup, or CAN'T MAKE IT to pass it to another family."}


def approval_page(record, token):
    terms = html.escape(json.dumps(record['terms'], indent=2))
    token_js = json.dumps(token)
    payload = canonical({'version': record['version'], 'terms_hash': record['terms_hash'], 'human_confirmed': True})
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
    <title>HarvestNet human approval</title><style>body{{font:18px system-ui;max-width:760px;margin:2rem auto;padding:1rem}}pre{{white-space:pre-wrap}}button{{font:inherit;padding:.8rem;margin:.5rem}}</style>
    <h1>Review draft version {record['version']}</h1><p>Organization: {html.escape(record['organization_id'])}</p>
    <p>Local approval fallback. This records your decision. The core must validate holds and every organization's approval before commitment.</p>
    <pre>{terms}</pre><p>Terms hash: {html.escape(record['terms_hash'])}</p><p>Link expires: {html.escape(record['expires_at'])}</p>
    <button onclick="decide('approve')">I approve these exact terms</button><button onclick="decide('decline')">Decline</button>
    <pre id="result"></pre><script>const token={token_js}; async function decide(decision){{
    const response=await fetch('/human/decision',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{...{payload},token,decision}})}});
    document.getElementById('result').textContent=JSON.stringify(await response.json(),null,2);}}</script></html>'''


def handler_for(store, core, events_token, public_url):
    class Handler(JsonHandler):
        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path == '/health':
                return self.send_json(200, {'status': 'ok', 'approval_mode': 'live_core' if core.base_url else 'local_approval_fallback'})
            if parsed.path != '/human/review':
                return self.send_json(404, {'error': 'Not found'})
            try:
                token = parse_qs(parsed.query).get('token', [''])[0]
                record = store.view(token)
                raw = approval_page(record, token).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(raw)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.send_header('X-Frame-Options', 'DENY')
                self.end_headers()
                self.wfile.write(raw)
            except StaleApproval as exc:
                self.send_json(409, {'error': str(exc)})
            except ValueError as exc:
                self.send_json(400, {'error': str(exc)})

        def do_POST(self):
            path = urlsplit(self.path).path
            if path != '/human/decision' and not self.authorized(events_token):
                return self.send_json(401, {'error': 'Authenticated core event required'})
            try:
                data = self.read_json()
                if path == '/approval-requests':
                    # The core names the lot `lot_id`; its earlier change requests say `event_id`.
                    lot = data.get('lot_id', data.get('event_id'))
                    links = store.request(lot, data['version'], data['terms'], data['organizations'],
                                          ttl=data.get('ttl_seconds'), reissue=data.get('reissue') is True)
                    for link in links:
                        link['decision_url'] = public_url.rstrip('/') + '/human/review?token=' + link.pop('token')
                        link['message'] = approval_message(link)
                    return self.send_json(201, {'status': 'awaiting_humans', 'committed': False, 'requests': links})
                if path == '/human/decision':
                    record = store.decide(data['token'], data['decision'], data['version'], data['terms_hash'], data.get('human_confirmed'))
                    return self.send_json(200, core.decision(record))
                if path == '/notifications/prepare':
                    message = pickup_message(data)
                    if data.get('to'):
                        store.bind_reply(data)
                    return self.send_json(200, {'to': data['to'], 'message': message, 'mode': 'prepared_text', 'sent': False})
                if path == '/household/replies':
                    return self.send_json(*household_reply(store, core, data))
                self.send_json(404, {'error': 'Not found'})
            except StaleApproval as exc:
                self.send_json(409, {'error': str(exc)})
            except HTTPError as exc:
                # A 401 or 409 from the core is the core's answer, not an outage.
                self.send_json(*core_error(exc))
            except (ValueError, KeyError, TypeError) as exc:
                self.send_json(400, {'error': str(exc)})
            except (URLError, TimeoutError, OSError):
                self.send_json(503, {'error': 'Core API unavailable. Retry the same decision; nothing was committed by this adapter.'})
    return Handler


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8030)
    parser.add_argument('--host', default='127.0.0.1')
    args = parser.parse_args()
    events_token = os.getenv('API_EVENTS_TOKEN')
    store = ApprovalStore(os.getenv('APPROVALS_DB', 'runtime/approvals.sqlite'),
                          reply_key=os.getenv('REPLY_BINDING_KEY') or events_token)
    public_url = os.getenv('APPROVAL_PUBLIC_URL', f'http://127.0.0.1:{args.port}')
    serve(handler_for(store, CoreAPI.from_env(), events_token, public_url), args.port, args.host)


if __name__ == '__main__':
    main()
