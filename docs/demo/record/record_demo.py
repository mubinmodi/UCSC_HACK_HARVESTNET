"""Record the HarvestNet demo against the LOCAL stack (docs/demo/record/start_local_stack.sh up).

    uv run --with playwright python docs/demo/record/record_demo.py          # all clips
    uv run --with playwright python docs/demo/record/record_demo.py --only 5 # one moment (needs the earlier state)

One browser clip per moment, 1280x720, with an injected caption bar and a visible cursor. Clips go to
demo-video/clips/*.webm and demo-video/marks.json (timestamps the stitch step uses for the short cut).
Everything runs on 127.0.0.1 against synthetic fixtures. Test tokens come from demo-video/.local-env
(gitignored) and are never printed. No email is sent, no AWS or Claude call is made.

Where the real system sends an email (review links, pickup text), this local run has no email service.
The script plays the part of the email: it asks the local approvals service to issue the review links
(the same call the core and the cooler watcher make) and opens them as each organization's human.
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'demo-video'
CLIPS = OUT / 'clips'
BASE = 'http://127.0.0.1:8080'
SLIDES = (ROOT / 'docs/demo/slides.html').as_uri()
REPLAY = (ROOT / 'docs/demo/replay.html').as_uri()
STATE = OUT / 'run' / 'state.json'
MARKS = OUT / 'marks.json'
FOOTER = 'Synthetic data · local run of the same code'

# A first lot for the demo: the contract's example offer (docs/contracts/examples/public-api).
DEADLINE_LOCAL = '2026-10-13T15:00'
DROP_START_LOCAL, DROP_END_LOCAL = '2026-10-13T13:00', '2026-10-13T15:00'


# ---------------------------------------------------------------- local test credentials (never printed)

def load_env():
    env = {}
    for line in (OUT / '.local-env').read_text().splitlines():
        key, _, value = line.partition('=')
        env[key] = value.strip("'")
    return env


ENV = load_env()
STAFF = json.loads(ENV['HARVESTNET_STAFF_TOKENS'])


def http(method, url, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={'Content-Type': 'application/json', **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'{}')


def core(method, path, body=None, org=None):
    headers = {'Authorization': 'Bearer ' + STAFF[org]} if org else {}
    return http(method, BASE + '/api' + path, body, headers)


def issue_review_links(lot_id, version, terms, organizations, reissue=False):
    """Ask the local approvals service for each organization's review link (what the email would carry)."""
    body = {'lot_id': lot_id, 'version': version, 'terms': terms, 'organizations': organizations}
    if reissue:
        body['reissue'] = True
    headers = {'Authorization': 'Bearer ' + ENV['API_EVENTS_TOKEN']}
    status, out = http('POST', BASE + '/platform/approval-requests', body, headers)
    if status == 400 and not reissue:  # links already issued for this version (a re-run): replace them
        status, out = http('POST', BASE + '/platform/approval-requests', {**body, 'reissue': True}, headers)
    if status not in (200, 201):
        raise RuntimeError(f'approvals service refused the request ({status})')
    return {r['organization_id']: r['decision_url'] for r in out['requests']}


def save_state(**kw):
    data = json.loads(STATE.read_text()) if STATE.exists() else {}
    data.update(kw)
    STATE.write_text(json.dumps(data))


def load_state():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


# ---------------------------------------------------------------- on-screen helpers

INIT_JS = """
(() => {
  const css = `
    #__hn_cap{position:fixed;left:0;right:0;bottom:0;z-index:2147483647;background:rgba(12,38,28,.95);color:#fff;
      font:15px/1.35 -apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;padding:9px 24px 8px;
      border-top:3px solid #7fcf9f;pointer-events:none;box-sizing:border-box}
    #__hn_cap .t{font-weight:700;font-size:12.5px;letter-spacing:.07em;text-transform:uppercase;color:#a8e6bf}
    #__hn_cap .l{font-size:17px;margin-top:2px}
    #__hn_cap .f{font-size:12px;opacity:.8;margin-top:3px}
    #__hn_dot{position:fixed;z-index:2147483646;width:18px;height:18px;border-radius:50%;background:rgba(235,64,52,.85);
      border:2px solid #fff;box-shadow:0 0 6px rgba(0,0,0,.5);pointer-events:none;transform:translate(-50%,-50%);left:-50px;top:-50px}
    .__hn_rip{position:fixed;z-index:2147483645;width:14px;height:14px;border-radius:50%;border:3px solid rgba(235,64,52,.9);
      pointer-events:none;transform:translate(-50%,-50%);animation:__hn_r .5s ease-out forwards}
    @keyframes __hn_r{to{width:54px;height:54px;opacity:0}}
    html{scroll-padding-bottom:130px}`;
  const ensure = () => {
    if (!document.documentElement) return;
    if (!document.getElementById('__hn_style')) {
      const s = document.createElement('style'); s.id = '__hn_style'; s.textContent = css; document.documentElement.appendChild(s);
    }
    let bar = document.getElementById('__hn_cap');
    if (!bar) {
      bar = document.createElement('div'); bar.id = '__hn_cap';
      bar.innerHTML = '<div class="t"></div><div class="l"></div><div class="f"></div>';
      document.documentElement.appendChild(bar);
    }
    let cap = {};
    try { cap = JSON.parse(window.name || '{}'); } catch (e) {}
    if (cap.t !== undefined) {
      bar.children[0].textContent = cap.t; bar.children[1].textContent = cap.l; bar.children[2].textContent = cap.f;
      bar.style.display = '';
    } else { bar.style.display = 'none'; }
    if (!document.getElementById('__hn_dot')) {
      const d = document.createElement('div'); d.id = '__hn_dot'; document.documentElement.appendChild(d);
    }
  };
  setInterval(ensure, 150);
  window.addEventListener('DOMContentLoaded', ensure);
  document.addEventListener('mousemove', e => {
    const d = document.getElementById('__hn_dot'); if (d) { d.style.left = e.clientX + 'px'; d.style.top = e.clientY + 'px'; }
  }, true);
  document.addEventListener('mousedown', e => {
    const r = document.createElement('div'); r.className = '__hn_rip'; r.style.left = e.clientX + 'px'; r.style.top = e.clientY + 'px';
    document.documentElement.appendChild(r); setTimeout(() => r.remove(), 600);
  }, true);
})();
"""


class Clip:
    """One recorded browser context (one video file)."""

    def __init__(self, pw, browser, name, marks):
        self.name, self.marks = name, marks
        self.context = browser.new_context(
            viewport={'width': 1280, 'height': 720}, record_video_dir=str(CLIPS / '_raw'),
            record_video_size={'width': 1280, 'height': 720}, timezone_id='America/Los_Angeles', locale='en-US')
        self.context.add_init_script(INIT_JS)
        self.page = self.context.new_page()
        self.t0 = time.monotonic()
        self.mouse = (640, 360)
        marks[name] = {}

    def mark(self, label):
        self.marks[self.name][label] = round(time.monotonic() - self.t0, 2)

    def caption(self, title, line):
        cap = json.dumps({'t': title, 'l': line, 'f': FOOTER})
        self.page.evaluate('c => { window.name = c; }', cap)
        self.page.wait_for_timeout(250)

    def pause(self, seconds):
        self.page.wait_for_timeout(int(seconds * 1000))

    def goto(self, url, wait=0.9):
        self.page.goto(url, wait_until='load')
        self.page.mouse.move(self.mouse[0], self.mouse[1])
        self.pause(wait)

    def move_to(self, locator):
        locator.scroll_into_view_if_needed()
        box = locator.bounding_box()
        # Keep targets above the caption bar.
        if box and box['y'] + box['height'] > 600:
            self.page.evaluate('y => window.scrollBy({top: y, behavior: "smooth"})', box['y'] + box['height'] - 520)
            self.pause(0.7)
            box = locator.bounding_box()
        x, y = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
        self.page.mouse.move(x, y, steps=22)
        self.mouse = (x, y)
        self.pause(0.25)

    def click(self, locator, after=0.5):
        self.move_to(locator)
        locator.click()
        self.pause(after)

    def type(self, locator, text, delay=45, after=0.4):
        self.move_to(locator)
        locator.click()
        locator.press_sequentially(text, delay=delay)
        self.pause(after)

    def scroll_to(self, y, seconds=1.5):
        self.page.evaluate(
            """([y, ms]) => new Promise(done => {
                const y0 = window.scrollY, t0 = performance.now();
                const step = now => { const k = Math.min(1, (now - t0) / ms), e = k < .5 ? 2*k*k : 1 - Math.pow(-2*k + 2, 2) / 2;
                  window.scrollTo(0, y0 + (y - y0) * e); k < 1 ? requestAnimationFrame(step) : done(); };
                requestAnimationFrame(step); })""", [y, int(seconds * 1000)])

    def scroll_by(self, dy, seconds=1.5):
        cur = self.page.evaluate('window.scrollY')
        self.scroll_to(max(0, cur + dy), seconds)

    def scroll_through(self, to_y, seconds, pause_end=1.0):
        self.scroll_to(to_y, seconds)
        self.pause(pause_end)

    def finish(self):
        video = self.page.video
        self.context.close()
        target = CLIPS / f'{self.name}.webm'
        target.unlink(missing_ok=True)
        Path(video.path()).rename(target)
        return target


def text_of(locator):
    return locator.inner_text().strip()


# ---------------------------------------------------------------- the moments

def opening(clip):
    clip.goto(SLIDES + '#1', wait=0.3)
    clip.caption('Opening · slides 1 to 3',
                 'Good produce goes to waste every day, while families nearby could use it. Every donor and every food bank gets its own AI agent.')
    clip.mark('slide1'); clip.pause(5.5)
    clip.page.keyboard.press('ArrowRight'); clip.mark('slide2'); clip.pause(6)
    clip.caption('Opening · slides 1 to 3',
                 'The agents negotiate how each batch is shared. Nobody sits in the middle and decides. Every organization keeps its own keys.')
    clip.page.keyboard.press('ArrowRight'); clip.mark('slide3'); clip.pause(7)


def moment1_household(clip, state):
    t = 'Moment 1 · A household asks, in Spanish'
    line = ('A parent asks in Spanish: family of four near Watsonville, pickup after 6 pm, small fridge. The assistant reads it back and asks '
            'before saving. Voice line shown as the web form (text fallback).')
    p = clip.page
    clip.goto(BASE + '/household/', wait=0.3)
    clip.caption(t, line)
    clip.pause(1.5)
    clip.mark('form_start')
    clip.click(p.get_by_role('button', name='Español'), after=1.0)
    for _ in range(4):
        clip.click(p.locator('#size-more'), after=0.25)
    clip.pause(1.2)  # the fair share the calculator returns appears under the counter
    clip.click(p.locator('input[name="days"][value="weekdays"]').locator('..'))
    clip.click(p.locator('input[name="time"][value="evening"]').locator('..'))
    clip.click(p.locator('input[name="fridge"][value="yes"]').locator('..'))
    clip.type(p.locator('#neighborhood'), 'Watsonville')
    clip.click(p.locator('input[name="snap"][value="yes"]').locator('..'))
    clip.pause(0.6)
    clip.click(p.get_by_role('button', name='Revisar mis respuestas'), after=0.4)
    p.get_by_text('Lo que entendió HarvestNet').wait_for(timeout=20000)
    clip.pause(1.0)
    clip.mark('read_back')
    clip.scroll_by(420, 1.6)
    clip.pause(3.0)
    clip.click(p.get_by_role('button', name='Sí, guardar mis respuestas'), after=1.0)
    p.locator('.code-card .code').wait_for(timeout=20000)
    clip.mark('saved')
    state['household_code'] = text_of(p.locator('.code-card .code'))
    clip.scroll_to(0, 0.8)
    clip.pause(2.0)
    banks = p.locator('.bank-card')
    banks.first.wait_for(timeout=20000)
    for bank_id in ('rural', 'city'):
        clip.click(p.locator(f'.bank-card:has(#bank-{bank_id}) input[type=checkbox]'), after=0.5)
    clip.click(p.get_by_role('button', name='Continuar'), after=1.5)
    p.locator('.pickup-card').wait_for(timeout=20000)
    clip.scroll_to(0, 0.6)
    clip.mark('waiting')
    clip.pause(3.0)


def moment2_3_donor(clip, state):
    p = clip.page
    t2 = 'Moment 2 · The farmers market reports surplus'
    l2 = 'At closing time the market has 300 lb of apples, 200 lb of romaine and 400 lb of potatoes, to be gone by 3 pm. It can drop some off.'
    clip.goto(BASE + '/donor-dashboard/', wait=0.3)
    clip.caption(t2, l2)
    clip.mark('donor_start')
    clip.pause(1.5)
    # Staff sign-in for the market: a throwaway local test token, typed into a password field (shown as dots).
    clip.click(p.get_by_role('button', name='Settings').first, after=0.8)
    field = p.locator('input[type=password]').first
    clip.move_to(field)
    field.click()
    field.press_sequentially(STAFF['market'], delay=25)
    clip.pause(0.5)
    clip.click(p.get_by_role('button', name='Save for this tab').first, after=1.0)
    clip.click(p.get_by_role('button', name='Report surplus').first, after=1.0)
    p.get_by_role('form', name='Report surplus produce').wait_for(timeout=20000)

    rows = p.locator('fieldset.item-row')
    clip.type(rows.nth(0).get_by_label('Quantity'), '300')
    clip.click(p.get_by_role('button', name='Add another item'))
    rows.nth(1).get_by_label('Produce').select_option(label='Romaine lettuce')
    clip.pause(0.4)
    clip.type(rows.nth(1).get_by_label('Quantity'), '200')
    clip.click(p.get_by_role('button', name='Add another item'))
    rows.nth(2).get_by_label('Produce').select_option(label='Potatoes')
    clip.pause(0.4)
    rows.nth(2).get_by_label('Unit').select_option('sack')
    clip.type(rows.nth(2).get_by_label('Quantity'), '8')
    clip.type(rows.nth(2).get_by_label('Pounds in each sack'), '50')
    clip.move_to(p.get_by_label('Must be gone by'))
    p.get_by_label('Must be gone by').fill(DEADLINE_LOCAL)
    clip.pause(0.8)
    drop = p.locator('.choices.transport button').first
    clip.click(drop, after=0.6)
    p.get_by_label('Earliest drop-off').fill(DROP_START_LOCAL)
    p.get_by_label('Latest drop-off').fill(DROP_END_LOCAL)
    clip.type(p.get_by_label('Vehicle can carry (lb)'), '700')
    clip.click(p.get_by_label('Rural food bank'), after=0.3)
    clip.click(p.get_by_label('Eastside food bank'), after=0.6)
    clip.mark('offer_ready')
    clip.click(p.get_by_role('button', name='Offer this surplus'), after=0.5)
    notice = p.locator('.notice-card')
    notice.wait_for(timeout=60000)
    clip.pause(0.5)
    clip.move_to(notice)
    state['lot_id'] = re.search(r'Lot (lot-[0-9a-f]+)', text_of(notice)).group(1)
    clip.mark('offered')
    clip.pause(3.0)

    t3 = 'Moment 3 · The agents negotiate'
    l3 = ('The food banks bid item by item. Every change is a new version, with a reason. The advocate can propose but cannot vote. '
          'There is no central decider.')
    clip.caption(t3, l3)
    clip.click(p.get_by_role('button', name='See this lot’s status'), after=1.5)
    p.locator('.version-list').wait_for(timeout=30000)
    clip.mark('versions')
    clip.pause(2.5)
    clip.scroll_to(300, 1.5)
    clip.pause(2.0)
    height = p.evaluate('document.documentElement.scrollHeight')
    # Read down the version history slowly, then show the current version and who still has to approve.
    versions_top = p.evaluate("document.querySelector('.versions').getBoundingClientRect().top + window.scrollY")
    clip.scroll_to(max(0, versions_top - 80), 1.5)
    clip.pause(2.5)
    end = max(0, height - 640)
    clip.scroll_to(end, min(24.0, 3 + 0.012 * max(0, end - versions_top)))
    clip.mark('versions_end')
    clip.pause(3.0)


def moment4_approvals(clip, state):
    p = clip.page
    t = 'Moment 4 · A live approval'
    lot_id = state['lot_id']
    status, approvals = core('GET', '/approvals?organization_id=market', org='market')
    mine = [a for a in approvals['approvals'] if a['lot_id'] == lot_id][0]
    orgs = ['market', 'city', 'rural', 'eastside']
    links = issue_review_links(lot_id, mine['version'], mine['terms'], orgs)
    state['v1_version'] = mine['version']

    first = True
    for org in orgs:
        clip.goto(links[org], wait=0.2)
        if first:
            clip.mark('first_review')
        line = (f'Each manager approves the exact version (version {mine["version"]}). Nothing is committed automatically, and any change '
                'voids old approvals. Email is not sent locally, so these are the local approvals service’s review links.')
        clip.caption(t + f' · as {org}', line)
        clip.pause(2.2 if first else 1.6)
        clip.scroll_by(400, 1.2)
        clip.pause(1.0)
        button = p.get_by_role('button', name='I approve these exact terms')
        clip.click(button, after=0.8)
        p.get_by_text('approval_recorded').wait_for(timeout=20000)
        clip.scroll_to(p.evaluate('document.documentElement.scrollHeight'), 1.0)
        clip.pause(2.0 if org != 'eastside' else 2.5)
        first = False
    clip.mark('all_approved')
    # The lot is now committed: show it on the donor page.
    clip.goto(BASE + '/donor-dashboard/', wait=0.4)
    clip.caption(t + ' · committed', 'All four named organizations approved the same version, so it is now a commitment, and not before.')
    clip.click(p.get_by_role('button', name='My lots').first, after=0.8)
    p.get_by_label('Lot ID').fill(lot_id)
    clip.click(p.get_by_role('button', name='Show'), after=1.5)
    p.get_by_text('committed', exact=False).first.wait_for(timeout=20000)
    clip.pause(3.5)


TERMINAL_HTML = """<!doctype html><meta charset=utf-8><title>operator terminal</title>
<style>html,body{margin:0;height:100%;background:#0f1914;color:#d7efe0;font:17px/1.55 'SF Mono',Menlo,Consolas,monospace}
.win{margin:48px 64px;border:1px solid #2f5a44;border-radius:10px;overflow:hidden;background:#0b130f}
.bar{background:#1d3a2b;padding:8px 14px;font:13px system-ui;color:#a8e6bf;letter-spacing:.04em}
pre{margin:0;padding:18px 22px;white-space:pre-wrap;word-break:break-word}.c{color:#7fcf9f}.d{color:#8aa598}</style>
<div class=win><div class=bar>Operator terminal · local run · synthetic</div><pre id=t></pre></div>"""


def moment5_cooler(clip, state):
    p = clip.page
    t = 'Moment 5 · The cooler fails'
    lot_id = state['lot_id']
    l_a = 'Now the city’s walk-in cooler fails. The operator flips the local city cooler switch (the demo switch in the organization systems service).'
    p.set_content(TERMINAL_HTML)
    clip.caption(t, l_a)
    clip.pause(1.0)
    clip.mark('terminal')
    cmd = ('$ # token comes from a local test file; it is not shown\n'
           '$ curl -sS -X POST -H "Authorization: Bearer $DEMO_SWITCH_TOKEN" -H "Content-Type: application/json" \\\n'
           f'    {BASE}/systems/demo/city/cooler -d \'{{"failed": true}}\'\n')
    p.evaluate('''async (cmd) => { const t = document.getElementById('t');
        for (const ch of cmd) { t.textContent += ch; await new Promise(r => setTimeout(r, 22)); } }''', cmd)
    clip.pause(0.8)
    status, reply = http('POST', BASE + '/systems/demo/city/cooler', {'failed': True}, {'Authorization': 'Bearer ' + ENV['DEMO_SWITCH_TOKEN']})
    if status != 200:
        raise RuntimeError(f'cooler switch refused ({status})')
    out = json.dumps(reply, indent=2)
    p.evaluate("o => { document.getElementById('t').textContent += '\\n' + o + '\\n'; }", out)
    clip.mark('flipped')
    clip.pause(5.0)

    clip.caption(t, 'The city’s own agent polls its own cooler. Nobody tells it. It reads its holding and runs the cooler-failure flow.')
    clip.goto(BASE + '/donor-dashboard/', wait=0.4)
    clip.click(p.get_by_role('button', name='Settings').first, after=0.8)
    # Food bank staff sign-in for the city (local test token, typed into a password field).
    field = p.locator('input[type=password]').nth(1)
    clip.move_to(field)
    field.click()
    field.press_sequentially(STAFF['city'], delay=25)
    clip.pause(0.4)
    clip.click(p.get_by_role('button', name='Save for this tab').nth(1), after=0.8)
    clip.click(p.get_by_role('button', name='Dashboard').first, after=1.0)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if p.get_by_role('heading', name='Disruptions').count():
            break
        clip.pause(1.5)
        clip.click(p.get_by_role('button', name='Dashboard').first, after=0.8)
    else:
        raise RuntimeError('the city dashboard never showed the cooler disruption (see demo-video/run/org-city.log)')
    clip.mark('disruption')
    clip.caption(t, 'It checks the produce profiles (romaine must stay cold, apples are fine), searches the Directory (the local fallback here) '
                    'for cold space, and writes a reason card for every food bank.')
    heading = p.get_by_role('heading', name='Disruptions')
    top = p.evaluate("el => el.getBoundingClientRect().top + window.scrollY", heading.element_handle())
    clip.scroll_to(top - 40, 1.5)
    clip.pause(3.0)
    clip.scroll_by(430, 2.0)
    clip.pause(3.5)
    clip.scroll_by(430, 2.0)
    clip.pause(4.0)
    clip.scroll_by(430, 2.0)
    clip.pause(3.0)
    clip.mark('reason_cards_end')

    # Fresh approvals for the new version: the review links the approvals service issues.
    entry = None
    for org in ('city',):
        watch = json.loads((OUT / 'run' / 'data' / f'cooler-watch-{org}.json').read_text())
        for e in (watch.get('episode') or {}).get('lots', {}).values():
            if e.get('approval_request'):
                entry = e['approval_request']
    if not entry:
        raise RuntimeError('no proposed cooler change found in the city watcher state')
    links = issue_review_links(entry['event_id'], entry['version'], entry['terms'], entry['organizations'], reissue=True)
    state['v2_version'] = entry['version']
    for org in entry['organizations']:
        clip.goto(links[org], wait=0.2)
        clip.caption(t + f' · fresh approval as {org}',
                     f'It is a new version (version {entry["version"]}), so both managers approve again. Earlier approvals do not carry over.')
        clip.pause(2.2)
        clip.scroll_by(400, 1.2)
        clip.pause(1.0)
        clip.click(p.get_by_role('button', name='I approve these exact terms'), after=0.8)
        p.get_by_text('approval_recorded').wait_for(timeout=20000)
        clip.scroll_to(p.evaluate('document.documentElement.scrollHeight'), 1.0)
        clip.pause(2.5)
    clip.mark('reapproved')


def moment6_pickup(clip, state):
    p = clip.page
    t = 'Moment 6 · The household’s pickup changes'
    line = ('The parent sees the changed pickup: which food bank, what time, what is in it, and their code. If they cannot make it, one tap '
            'passes it to the next family. (The local run has no email, so the pickup screen is shown.)')
    code = state['household_code']
    clip.goto(BASE + '/household/', wait=0.3)
    clip.caption(t, line)
    clip.click(p.get_by_role('button', name='Español'), after=0.8)
    clip.click(p.get_by_text('¿Ya tiene un código?'), after=0.6)
    clip.type(p.get_by_label('Su código'), code)
    clip.click(p.get_by_role('button', name='Ver mi recogida'), after=1.0)
    p.locator('section.pickup').first.wait_for(timeout=20000)
    clip.mark('pickup')
    clip.scroll_to(250, 1.4)
    clip.pause(4.0)
    button = p.get_by_role('button', name='No puedo ir')
    clip.click(button, after=1.0)
    clip.pause(2.0)
    clip.click(p.get_by_role('button', name='Sí, no puedo ir'), after=1.0)
    p.locator('.released-note').wait_for(timeout=20000)
    clip.mark('released')
    clip.pause(3.5)


def moment7_results(clip, state):
    p = clip.page
    t = 'Moment 7 · The results strip'
    line = ('Same inputs, synthetic scenarios, four methods side by side. Numbers are read from the screen. LLM negotiators were not run '
            'for these results.')
    clip.goto(BASE + '/results-strip/', wait=0.3)
    clip.caption(t, line)
    p.locator('.run').first.wait_for(timeout=20000)
    clip.mark('results')
    clip.pause(4.5)
    clip.scroll_to(260, 2.0)
    clip.pause(7.0)
    clip.scroll_to(620, 2.0)
    clip.pause(5.0)
    clip.mark('results_end')
    clip.caption('Close · slide 16', 'Every organization keeps its own keys. The food still moves. Thank you.')
    clip.goto(SLIDES + '#16', wait=0.3)
    clip.caption('Close · slide 16', 'Every organization keeps its own keys. The food still moves. Thank you.')
    clip.mark('close')
    clip.pause(6.0)


def title_cards(browser):
    """Intro and outro stills, rendered here so the stitch step needs no font tools."""
    cards = {
        'intro': ('HarvestNet', 'End-to-end demo · Cisco “When AI Agents Disagree”, Level 3',
                  'A local run of the same code, on one Mac, with synthetic data only. No email, no live services, no paid model calls.'),
        'outro': ('That was a local run', 'Synthetic data · rules-based negotiators · email replaced by local review links',
                  'Recorded by docs/demo/record/record_demo.py. The live system runs the same code on AWS.'),
    }
    for name, (h, sub, small) in cards.items():
        page = browser.new_page(viewport={'width': 1280, 'height': 720})
        page.set_content(f"""<!doctype html><meta charset=utf-8><style>
        body{{margin:0;height:720px;background:linear-gradient(135deg,#123a2a,#1d6b49);color:#fff;display:flex;flex-direction:column;
        align-items:center;justify-content:center;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;text-align:center;padding:0 90px}}
        h1{{font-size:78px;margin:0 0 14px;letter-spacing:-.02em}}h2{{font-weight:500;font-size:28px;margin:0 0 30px;color:#c8f0d8}}
        p{{font-size:21px;max-width:900px;color:#e5f6ec;margin:0}}</style><h1>{h}</h1><h2>{sub}</h2><p>{small}</p>""")
        page.screenshot(path=str(CLIPS / f'{name}.png'))
        page.close()


MOMENTS = [
    ('00-opening', opening, False),
    ('01-household', moment1_household, True),
    ('02-donor-negotiation', moment2_3_donor, True),
    ('04-approvals', moment4_approvals, True),
    ('05-cooler', moment5_cooler, True),
    ('06-pickup', moment6_pickup, True),
    ('07-results', moment7_results, True),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', help='record only the clips whose name starts with this prefix (needs the earlier state)')
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    CLIPS.mkdir(parents=True, exist_ok=True)
    marks = json.loads(MARKS.read_text()) if MARKS.exists() and args.only else {}
    state = load_state() if args.only else {}
    if not args.only:
        STATE.unlink(missing_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed)
        title_cards(browser)
        for name, fn, uses_state in MOMENTS:
            if args.only and not name.startswith(args.only):
                continue
            print(f'recording {name} ...', flush=True)
            clip = Clip(pw, browser, name, marks)
            try:
                fn(clip, state) if uses_state else fn(clip)
            finally:
                path = clip.finish()
            save_state(**state)
            MARKS.write_text(json.dumps(marks, indent=1))
            print(f'  -> {path.name}', flush=True)
        browser.close()


if __name__ == '__main__':
    sys.exit(main())
