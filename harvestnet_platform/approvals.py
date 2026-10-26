"""Version-bound human decisions and household pickup emails. Neither n8n nor this store commits produce."""
import hashlib
import html
import math
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from urllib.error import HTTPError, URLError
from .transport import canonical, terms_hash
from .http import JsonHandler, request_json, serve
from .roster import APPROVERS

MAX_LINK_TTL_SECONDS = 86400


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


class ApprovalStore:
    def __init__(self, path=':memory:', clock=time.time):
        if path != ':memory:':
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock, self.clock = threading.RLock(), clock
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS drafts(event TEXT PRIMARY KEY, version INTEGER, terms TEXT, digest TEXT);
            CREATE TABLE IF NOT EXISTS links(token_hash TEXT PRIMARY KEY, event TEXT, version INTEGER,
                organization TEXT, digest TEXT, expires REAL, decision TEXT, receipt_id TEXT);
        ''')
        # SMS replies are retired (pickup messages are emails with links): drop any old
        # reply bindings, which held keyed hashes of household phone numbers.
        self.db.execute('DROP TABLE IF EXISTS reply_bindings')

    @staticmethod
    def token_hash(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def _link(self, event, version, org, digest, terms, ttl):
        token = secrets.token_urlsafe(32)
        expires = self.clock() + ttl
        self.db.execute('INSERT INTO links VALUES (?,?,?,?,?,?,NULL,NULL)',
                        (self.token_hash(token), event, version, org, digest, expires))
        return {'organization_id': org, 'lot_id': event, 'version': version,
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
        if any(org not in APPROVERS for org in organizations):
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
        return {'lot_id': event, 'version': version, 'organization_id': org,
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


def approval_subject(link):
    return f"HarvestNet: review draft version {link['version']} for lot {link['lot_id']}"


# --- Household pickup emails ---------------------------------------------------------------
# Decided (user, October 11, 2026): pickup messages go by email through n8n's Send Email
# (SMTP) node and Amazon SES, not SMS. Each email has a subject and a plain-text body, and a
# "Can't make it" link to the household page, which calls the core's release_pickup. There
# is nothing to reply to, so no phone number, reply binding or inbound message is kept here.

_LOCAL = re.compile(r"^[A-Za-z0-9.!#$%&*+/=?^_`{|}~-]{1,64}$")
_LABEL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_TLD = re.compile(r"^[A-Za-z]{2,63}$")


def email_address(raw):
    """A plain address, or ``ValueError`` that never repeats it (so it never reaches a log)."""
    value = raw.strip() if isinstance(raw, str) else ''
    if not value or len(value) > 254 or value.count('@') != 1:
        raise ValueError('A pickup email needs a valid "to" address')
    local, domain = value.split('@')
    labels = domain.split('.')
    if (not _LOCAL.match(local) or local.startswith('.') or local.endswith('.') or '..' in local
            or len(labels) < 2 or not all(_LABEL.match(label) for label in labels) or not _TLD.match(labels[-1])):
        raise ValueError('A pickup email needs a valid "to" address')
    return f'{local}@{domain.lower()}'


def one_line(value, field):
    """A value for a subject or a line of its own: no line breaks, so no header injection."""
    if not isinstance(value, str) or not value.strip() or any(c in value for c in '\r\n\x00'):
        raise ValueError(f'Pickup notice requires a one-line {field}')
    return value.strip()


# The household's pickup email, in its own language (ticket #6). Numbers, names, times and
# the code come only from the core's notice.
PICKUP_EMAIL = {
    'en': {
        'item': '{lb} lb {name}', 'and': 'and',
        'subject': {'pickup_ready': 'HarvestNet: your produce is ready at {food_bank}',
                    'pickup_changed': 'HarvestNet: your pickup changed',
                    'pickup_released': 'HarvestNet: thanks for telling us'},
        'opening': {'pickup_ready': 'Your produce is ready at {food_bank}.',
                    'pickup_changed': 'Your pickup changed. It is now at {food_bank}.'},
        'not_chosen': "This isn't a food bank you chose. If you can't go there, use the link below and your portion goes to another family.",
        'what': 'What: {items}', 'when': 'When: {when}', 'code': 'Your code: {code} (show it at pickup)',
        'wash': 'Please wash produce before eating.',
        'release': "Can't make it? Open this link and tap \"Can't make it\". Your portion goes to another family:",
        'coming': "If you're coming, you don't need to do anything.",
        'released': 'Thanks for telling us. Your portion will go to another family.',
        'tip': 'Market Match tip: ask {market} about its verified CalFresh produce match. {url}',
        'footer': ('HarvestNet. This address is used only for pickup messages and is deleted with your request '
                   'after 7 days. Replies to this email are not read.'),
        'range': '{start} to {end}', 'dated': '{day}, {range}', 'am': 'am', 'pm': 'pm',
        'weekdays': ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'),
        'months': ('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September',
                   'October', 'November', 'December'),
        'day': '{weekday}, {month} {date}',
    },
    'es': {
        'item': '{lb} lb de {name}', 'and': 'y',
        'subject': {'pickup_ready': 'HarvestNet: sus productos están listos en {food_bank}',
                    'pickup_changed': 'HarvestNet: su recogida cambió',
                    'pickup_released': 'HarvestNet: gracias por avisarnos'},
        'opening': {'pickup_ready': 'Sus productos están listos en {food_bank}.',
                    'pickup_changed': 'Su recogida cambió. Ahora es en {food_bank}.'},
        'not_chosen': 'Este no es un banco de alimentos que eligió. Si no puede ir, use el enlace de abajo y su porción pasará a otra familia.',
        'what': 'Qué: {items}', 'when': 'Cuándo: {when}', 'code': 'Su código: {code} (muéstrelo al recoger)',
        'wash': 'Por favor lave los productos antes de comerlos.',
        'release': '¿No puede ir? Abra este enlace y toque "No puedo ir". Su porción pasará a otra familia:',
        'coming': 'Si va a venir, no tiene que hacer nada.',
        'released': 'Gracias por avisarnos. Su porción pasará a otra familia.',
        'tip': 'Consejo de Market Match: pregunte en {market} por su programa verificado que iguala sus dólares de CalFresh para frutas y verduras. {url}',
        'footer': ('HarvestNet. Esta dirección solo se usa para avisos de recogida y se borra con su solicitud '
                   'después de 7 días. No leemos las respuestas a este correo.'),
        'range': 'de {start} a {end}', 'dated': '{day}, {range}', 'am': 'a. m.', 'pm': 'p. m.',
        'weekdays': ('lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'),
        'months': ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre',
                   'octubre', 'noviembre', 'diciembre'),
        'day': '{weekday} {date} de {month}',
    },
}
NOTICE_KINDS = ('pickup_ready', 'pickup_changed', 'pickup_released')


def _clock(moment, words):
    hour = moment.hour % 12 or 12
    minutes = f':{moment.minute:02d}' if moment.minute else ''
    return f"{hour}{minutes} {words['pm'] if moment.hour >= 12 else words['am']}"


def pickup_when(window, words):
    """The pickup window as the household reads it, at the notice's own clock time.

    ISO times with an offset read "Tuesday, October 13, 6 pm to 8 pm"; plain clock times
    ("18:00") are shown as given.
    """
    try:
        start = datetime.fromisoformat(window['start'].replace('Z', '+00:00'))
        end = datetime.fromisoformat(window['end'].replace('Z', '+00:00'))
    except ValueError:
        return words['range'].format(start=window['start'].strip(), end=window['end'].strip())
    span = words['range'].format(start=_clock(start, words), end=_clock(end, words))
    day = words['day'].format(weekday=words['weekdays'][start.weekday()], month=words['months'][start.month - 1], date=start.day)
    return words['dated'].format(day=day, range=span)


def _items(items, words):
    parts = [words['item'].format(lb=f"{item['pounds']:g}", name=one_line(item['name'], 'produce name')) for item in items]
    return parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} {words['and']} {parts[-1]}"


def _market_tip(notice, words, now):
    """The Market Match tip: SNAP households only, and only a verified, nearby, recently
    checked market. Markets are trusted, verified records, never arbitrary model suggestions."""
    market = notice.get('market')
    if not (notice.get('snap') == 'yes' and market and market.get('verified') is True and market.get('nearby') is True
            and market.get('source_url') and market.get('verified_at')):
        return None
    from datetime import timedelta
    checked = datetime.fromisoformat(market['verified_at'].replace('Z', '+00:00'))
    current = now or datetime.now(timezone.utc)
    if checked.tzinfo is None:
        raise ValueError('Market verification timestamp requires timezone')
    if current - timedelta(days=30) <= checked <= current:
        return words['tip'].format(market=one_line(market['name'], 'market name'), url=one_line(market['source_url'], 'market link'))
    return None


def pickup_email(notice, *, now=None):
    """A household's pickup email: ``{to, kind, language, subject, text}``.

    ``kind`` is ``pickup_ready`` (the default), ``pickup_changed`` (a changed version moved
    the pickup) or ``pickup_released`` (the thank-you after "Can't make it"). Only households
    that gave an email get one, so ``to`` is required.
    """
    kind = notice.get('kind', 'pickup_ready')
    if kind not in NOTICE_KINDS:
        raise ValueError(f'Pickup notice kind must be one of {", ".join(NOTICE_KINDS)}')
    to = email_address(notice.get('to'))
    language = notice.get('language') if notice.get('language') in PICKUP_EMAIL else 'en'
    words = PICKUP_EMAIL[language]
    if kind == 'pickup_released':
        if notice.get('released') is not True or not notice.get('pickup_id'):
            raise ValueError('Send a release notice only after the core released the pickup')
        return {'to': to, 'kind': kind, 'language': language, 'subject': words['subject'][kind],
                'text': f"{words['released']}\n\n--\n{words['footer']}\n"}
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
    url = one_line(notice['release_url'], 'release_url')
    if not url.startswith(('https://', 'http://')):
        raise ValueError('Pickup notice requires an http(s) release_url')
    food_bank = one_line(notice['food_bank'], 'food bank')
    parts = [words['opening'][kind].format(food_bank=food_bank)]
    if kind == 'pickup_changed' and notice.get('reply_expected') is True:
        parts.append(words['not_chosen'])
    parts.append('\n'.join((words['what'].format(items=_items(notice['items'], words)),
                            words['when'].format(when=pickup_when(notice['window'], words)),
                            words['code'].format(code=one_line(notice['request_code'], 'request code')))))
    parts += [words['wash'], f"{words['release']}\n{url}", words['coming']]
    tip = _market_tip(notice, words, now)
    if tip:
        parts.append(tip)
    parts.append(f"--\n{words['footer']}")
    return {'to': to, 'kind': kind, 'language': language,
            'subject': words['subject'][kind].format(food_bank=food_bank), 'text': '\n\n'.join(parts) + '\n'}


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


def handler_for(store, core, events_token, public_url, *, approver_emails=None,
                approval_webhook=None, webhook_token=None, test_recipients=()):
    approver_emails=approver_emails or {}
    allowed={email.strip().lower() for email in test_recipients if email.strip()}
    if approval_webhook:
        parsed=urlsplit(approval_webhook)
        if not parsed.netloc or (parsed.scheme!='https' and not (parsed.scheme=='http' and parsed.hostname in ('localhost','127.0.0.1'))):
            raise ValueError('approval email webhook must use HTTPS')
    class Handler(JsonHandler):
        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path == '/health':
                return self.send_json(200, {'status': 'ok', 'approval_mode': 'live_core' if core.base_url else 'local_approval_fallback',
                                            'approval_email': 'configured' if approval_webhook and webhook_token and approver_emails and allowed else 'manual'})
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
                    links = store.request(data['lot_id'], data['version'], data['terms'], data['organizations'],
                                          ttl=data.get('ttl_seconds'), reissue=data.get('reissue') is True)
                    for link in links:
                        link['decision_url'] = public_url.rstrip('/') + '/human/review?token=' + link.pop('token')
                        link['message'] = approval_message(link)
                        link['subject'] = approval_subject(link)
                        address=approver_emails.get(link['organization_id'])
                        if not (address and approval_webhook and webhook_token):
                            link['email_delivery']='manual'
                        elif address.lower() not in allowed:
                            link['email_delivery']='outside_test_allowlist'
                        else:
                            # The link was already issued. A timeout may mean n8n sent the email;
                            # do not reissue automatically. The caller still gets the link for a
                            # deliberate manual fallback or an explicit reissue.
                            try:
                                result=request_json(approval_webhook,{
                                    'to':address,'lot_id':link['lot_id'],'version':link['version'],
                                    'decision_url':link['decision_url'],'subject':link['subject'],
                                    'message':link['message']},token=webhook_token)
                                link['email_delivery']='sent' if result.get('sent') is True else 'uncertain'
                            except (HTTPError,URLError,TimeoutError,OSError,ValueError):
                                link['email_delivery']='uncertain'
                    return self.send_json(201, {'status': 'awaiting_humans', 'committed': False, 'requests': links})
                if path == '/human/decision':
                    record = store.decide(data['token'], data['decision'], data['version'], data['terms_hash'], data.get('human_confirmed'))
                    return self.send_json(200, core.decision(record))
                if path == '/notifications/prepare':
                    # The core's trusted notice becomes one email for n8n; nothing is sent or kept here.
                    return self.send_json(200, {**pickup_email(data), 'mode': 'prepared_email', 'sent': False})
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
    store = ApprovalStore(os.getenv('APPROVALS_DB', 'runtime/approvals.sqlite'))
    public_url = os.getenv('APPROVAL_PUBLIC_URL', f'http://127.0.0.1:{args.port}')
    approver_emails=json.loads(os.getenv('APPROVER_EMAILS_JSON') or '{}')
    if not isinstance(approver_emails,dict) or any(k not in APPROVERS or not isinstance(v,str) for k,v in approver_emails.items()):
        raise ValueError('APPROVER_EMAILS_JSON must map organization IDs to email addresses')
    approver_emails={k:email_address(v) for k,v in approver_emails.items()}
    serve(handler_for(store, CoreAPI.from_env(), events_token, public_url,
                      approver_emails=approver_emails,
                      approval_webhook=os.getenv('N8N_APPROVAL_WEBHOOK_URL'),
                      webhook_token=os.getenv('N8N_WEBHOOK_TOKEN'),
                      test_recipients=os.getenv('SES_TEST_RECIPIENTS','').split(',')),args.port,args.host)


if __name__ == '__main__':
    main()
