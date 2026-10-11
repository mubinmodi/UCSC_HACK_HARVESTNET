"""Version-bound human decisions. Neither n8n nor this store commits produce."""
import hashlib
import html
import math
import json
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, quote
from urllib.error import URLError
from .transport import canonical, terms_hash
from .http import JsonHandler, request_json, serve


class StaleApproval(ValueError):
    pass


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

    @staticmethod
    def token_hash(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def request(self, event, version, terms, organizations, ttl=900):
        if not isinstance(event, str) or not event or len(event) > 100 or type(version) is not int or version < 1:
            raise ValueError('Event and positive draft version required')
        if not isinstance(terms, dict) or not terms or not organizations or len(set(organizations)) != len(organizations):
            raise ValueError('Exact complete terms and distinct approving organizations required')
        if any(org not in ('donor', 'city', 'rural', 'eastside') for org in organizations):
            raise ValueError('Only named donor/food bank humans may approve')
        if type(ttl) is not int or not 1 <= ttl <= 3600:
            raise ValueError('Approval links expire within one hour')
        digest = terms_hash(terms)
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                current = self.db.execute('SELECT version,digest FROM drafts WHERE event=?', (event,)).fetchone()
                if current and (version < current[0] or (version == current[0] and digest != current[1])):
                    raise StaleApproval('Draft terms changed without a new version, or version is stale')
                if current and version == current[0]:
                    # A webhook retry must not create additional vote links.
                    raise ValueError('Approval request already exists; use the original issued links')
                self.db.execute('INSERT OR REPLACE INTO drafts VALUES (?,?,?,?)', (event,version,canonical(terms),digest))
                links = []
                for org in organizations:
                    token = secrets.token_urlsafe(32)
                    self.db.execute('INSERT INTO links VALUES (?,?,?,?,?,?,NULL,NULL)',
                                    (self.token_hash(token),event,version,org,digest,self.clock()+ttl))
                    links.append({'organization_id': org, 'event_id': event, 'version': version,
                                  'terms_hash': digest, 'terms': terms, 'token': token, 'expires_at': self.clock()+ttl})
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
        if expires <= self.clock():
            raise StaleApproval('Decision link expired; ask the organization for a new request')
        if (version, digest) != (current_version, current_hash):
            raise StaleApproval('Old version rejected; approve the new complete terms')
        return {'event_id': event, 'version': version, 'organization_id': org,
                'terms_hash': digest, 'terms': json.loads(terms), 'decision': decision,
                'receipt_id': receipt, 'expires_at': expires}

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
                if (version, digest) != (record['version'], record['terms_hash']):
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
    def __init__(self, base_url=None, token=None, decision_webhook=None, webhook_token=None):
        self.base_url = base_url.rstrip('/') if base_url else None
        self.token = token
        self.decision_webhook, self.webhook_token = decision_webhook, webhook_token

    def decision(self, record):
        if not self.base_url and not self.decision_webhook:
            return {'mode': 'local_approval_fallback', 'status': 'human_decision_recorded',
                    'committed': False, 'requires_core_validation': True, 'receipt_id': record['receipt_id']}
        payload = {key: record[key] for key in ('event_id', 'version', 'organization_id', 'terms_hash', 'decision', 'receipt_id')}
        if self.decision_webhook:
            if not self.webhook_token:
                raise ValueError('Authenticated n8n decision webhook token required')
            return request_json(self.decision_webhook, payload, token=self.webhook_token)
        return request_json(self.base_url + '/approvals', payload, token=self.token)

    def release(self, code, pickup_id, release_token):
        if not self.base_url:
            return {'mode': 'text_fallback', 'status': 'release_pending', 'released': False,
                    'reason': 'Core API unavailable; household portion has not been released'}
        # Token belongs to this pickup/request, never the broad service token.
        return request_json(self.base_url + '/pickups/' + quote(pickup_id, safe='') + '/release',
                            {'request_code': code}, token=release_token)


def approval_message(link):
    return (f"HarvestNet: {link['organization_id']}, review draft version {link['version']} "
            f"for event {link['event_id']}. Exact terms: {canonical(link['terms'])}. "
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
    items = ', '.join(f"{item['pounds']:g} lb {item['name']}" for item in notice['items'])
    message = (f"HarvestNet: {items} at {notice['food_bank']}, {notice['window']['start']} to "
               f"{notice['window']['end']}. Your pickup code: {notice['request_code']}. "
               f"Wash before eating. Can't make it? Open {notice['release_url']}.")
    # Markets are trusted, verified records, never arbitrary model suggestions.
    market = notice.get('market')
    if notice.get('snap') == 'yes' and market and market.get('verified') is True and market.get('nearby') is True and market.get('source_url') and market.get('verified_at'):
        from datetime import datetime, timezone, timedelta
        checked = datetime.fromisoformat(market['verified_at'].replace('Z', '+00:00'))
        current = now or datetime.now(timezone.utc)
        if checked.tzinfo is None:
            raise ValueError('Market verification timestamp requires timezone')
        if current - timedelta(days=30) <= checked <= current:
            message += f" Market Match tip: ask {market['name']} about its verified CalFresh produce match. {market['source_url']}"
    return message


def approval_page(record, token):
    terms = html.escape(json.dumps(record['terms'], indent=2))
    token_js = json.dumps(token)
    payload = canonical({'version': record['version'], 'terms_hash': record['terms_hash'], 'human_confirmed': True})
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
    <title>HarvestNet human approval</title><style>body{{font:18px system-ui;max-width:760px;margin:2rem auto;padding:1rem}}pre{{white-space:pre-wrap}}button{{font:inherit;padding:.8rem;margin:.5rem}}</style>
    <h1>Review draft version {record['version']}</h1><p>Organization: {html.escape(record['organization_id'])}</p>
    <p>Local approval fallback. This records your decision. The core must validate holds and every organization's approval before commitment.</p>
    <pre>{terms}</pre><p>Terms hash: {html.escape(record['terms_hash'])}</p>
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
                    links = store.request(data['event_id'], data['version'], data['terms'], data['organizations'])
                    for link in links:
                        link['decision_url'] = public_url.rstrip('/') + '/human/review?token=' + link.pop('token')
                        link['message'] = approval_message(link)
                    return self.send_json(201, {'status': 'awaiting_humans', 'committed': False, 'requests': links})
                if path == '/human/decision':
                    record = store.decide(data['token'], data['decision'], data['version'], data['terms_hash'], data.get('human_confirmed'))
                    return self.send_json(200, core.decision(record))
                if path == '/notifications/prepare':
                    message = pickup_message(data)
                    return self.send_json(200, {'to': data['to'], 'message': message, 'mode': 'prepared_text', 'sent': False})
                if path == '/household/replies':
                    text = ' '.join(str(data['text']).lower().replace('’', "'").strip().split())
                    if text not in ("can't make it", 'cant make it', 'cannot make it', 'no puedo ir'):
                        return self.send_json(200, {'status': 'ignored', 'released': False})
                    if not data.get('release_token'):
                        raise ValueError('Pickup-bound release token required; a reply alone cannot release food')
                    return self.send_json(200, core.release(data['request_code'], data['pickup_id'], data['release_token']))
                self.send_json(404, {'error': 'Not found'})
            except StaleApproval as exc:
                self.send_json(409, {'error': str(exc)})
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
    store = ApprovalStore(os.getenv('APPROVALS_DB', 'runtime/approvals.sqlite'))
    core = CoreAPI(os.getenv('CORE_API_URL'), os.getenv('CORE_API_TOKEN'), os.getenv('N8N_DECISION_WEBHOOK_URL'), os.getenv('N8N_WEBHOOK_TOKEN'))
    public_url = os.getenv('APPROVAL_PUBLIC_URL', f'http://127.0.0.1:{args.port}')
    serve(handler_for(store, core, os.getenv('API_EVENTS_TOKEN'), public_url), args.port, args.host)


if __name__ == '__main__':
    main()
