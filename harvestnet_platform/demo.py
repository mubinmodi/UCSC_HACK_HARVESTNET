"""One-command offline platform rehearsal; no sponsor accounts or live LLMs."""
import argparse
import json
import secrets
import uuid
from pathlib import Path
from urllib.parse import urlsplit
from .approvals import ApprovalStore, CoreAPI, handler_for as approvals_handler
from .directory import LocalDirectory
from .http import serve
from .roster import BANKS, DONOR
from .systems import Systems
from .transport import InProcess, Receiver, ORGANIZATIONS, role_of
from .voice import text_intake

DEMO_BANK = BANKS[0]  # the city food bank: the demo fails its cooler and asks it to approve

PAGE = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>HarvestNet platform rehearsal</title><style>body{font:17px system-ui;color:#18372c;background:#f4f8f3;max-width:980px;margin:2rem auto;padding:1rem}section{background:white;border:1px solid #cbd9cd;border-radius:12px;padding:1.2rem;margin:1rem 0}button,a.button{font:inherit;background:#235e43;color:white;border:0;border-radius:6px;padding:.7rem 1rem;cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px}.label{color:#795400}a{color:#235e43}input,select{font:inherit;padding:.4rem}</style>
<h1>HarvestNet platform rehearsal</h1><p class="label">Synthetic fixtures · Local Directory · In-process agents · Text intake · Local human approval</p>
<p>This exercises platform integrations. It has no real household records, live sponsor calls, or measured negotiation results.</p>
<section><h2>Cooler disruption and discovery</h2><button onclick="cooler(true)">Fail city cooler</button> <button onclick="cooler(false)">Reset city cooler</button><pre id="systems"></pre></section>
<section><h2>Agent communication</h2><button onclick="run('transport',{},'transport')">Run five organization turns</button><pre id="transport"></pre></section>
<section><h2>Human approval</h2><p>Sample terms: synthetic 200 lb romaine to city. Links display the complete version and terms. Each invited organization's human decides.</p><button onclick="approvals()">Create sample review requests</button><div id="links"></div><pre id="approvals"></pre></section>
<section><h2>Text instead of voice</h2><label>Household size <input id="size" type="number" min="1" max="30" value="4"></label> <label>Limited fridge <select id="fridge"><option value="yes">Yes</option><option value="no">No</option></select></label><p>Sample pickup window: 6–8 pm. Optional SNAP answer defaults to prefer not to say.</p><button onclick="intake()">Read back draft</button><pre id="intake"></pre></section>
<script>const token=location.hash.slice(1); history.replaceState(null,'',location.pathname); async function api(path,body){const r=await fetch('/demo/'+path,{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw new Error(data.error);return data;}async function run(path,body,id){try{const data=await api(path,body);document.getElementById(id).textContent=JSON.stringify(data,null,2);return data;}catch(e){document.getElementById(id).textContent=e.message;}}async function cooler(failed){await run('cooler',{failed},'systems');}async function approvals(){const data=await run('approvals',{},'approvals'); const div=document.getElementById('links');div.replaceChildren();if(data)for(const request of data.requests){const a=document.createElement('a');a.textContent='Review as '+request.organization_id+' (local fallback)';a.href=request.decision_url;a.target='_blank';a.rel='noopener';div.append(a,document.createElement('br'));}}async function intake(){await run('text-intake',{household_size:Number(document.getElementById('size').value),limited_fridge:document.getElementById('fridge').value==='yes',pickup_windows:[{start:'2026-10-13T18:00:00-07:00',end:'2026-10-13T20:00:00-07:00'}],snap:'not_said'},'intake');}run('cooler',{failed:false},'systems');</script></html>'''


def handler_for(systems, store, token, base):
    parent = approvals_handler(store,CoreAPI(),token,base)
    transport = InProcess({org:Receiver(org) for org in ORGANIZATIONS})
    directory = LocalDirectory(systems,{org:base for org in ORGANIZATIONS})
    class Handler(parent):
        def do_GET(self):
            if urlsplit(self.path).path != '/':
                return super().do_GET()
            raw = PAGE.encode()
            self.send_response(200)
            self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Content-Length',str(len(raw)))
            self.send_header('Cache-Control','no-store')
            self.send_header('Referrer-Policy','no-referrer')
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self):
            path = urlsplit(self.path).path
            if not path.startswith('/demo/'):
                return super().do_POST()
            if not self.authorized(token):
                return self.send_json(401,{'error':'Use the local rehearsal URL containing its session token'})
            try:
                data = self.read_json()
                if path == '/demo/cooler':
                    reading = systems.switch(DEMO_BANK,data['failed'])
                    result = {'reading':reading,'candidates':directory.search(min_cold_lb=100,pickup_at='2026-10-13T19:00:00-07:00')}
                elif path == '/demo/transport':
                    event = str(uuid.uuid4())
                    receipts = []
                    for seq,actor in enumerate(ORGANIZATIONS,1):
                        receipts.extend(transport.broadcast({'event_id':event,'sequence':seq,'turn':actor,
                            'input':{'role':role_of(actor),'draft':{'version':1,'terms':{}},'facts':{},
                                     'turn':{'organization_id':actor,'number':seq,'now':'2026-10-13T12:00:00-07:00','accepted_by':[]}}}))
                    result = {'mode':transport.mode,'policy':'synthetic_stand_in','receipts':receipts,'committed':False}
                elif path == '/demo/approvals':
                    event = 'synthetic-'+str(uuid.uuid4())
                    links = store.request(event,1,{'items':[{'profile_id':'romaine','pounds':200,'food_bank':DEMO_BANK,'mover':DEMO_BANK}],
                                                 'synthetic':True},[DONOR,DEMO_BANK])
                    for link in links:
                        link['decision_url'] = base+'/human/review?token='+link.pop('token')
                    result = {'mode':'local_approval_fallback','requests':links,'committed':False}
                elif path == '/demo/text-intake':
                    result = text_intake(data)
                else:
                    return self.send_json(404,{'error':'Not found'})
                self.send_json(200,result)
            except (ValueError,KeyError,TypeError) as exc:
                self.send_json(400,{'error':str(exc)})
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8040)
    parser.add_argument('--write-url',default='runtime/demo-url.txt')
    args = parser.parse_args()
    token = secrets.token_urlsafe(32)
    base = f'http://127.0.0.1:{args.port}'
    url_file = Path(args.write_url)
    url_file.parent.mkdir(parents=True,exist_ok=True)
    url_file.write_text(base+'/#'+token)
    print(f'Local synthetic rehearsal URL saved to {url_file.resolve()}',flush=True)
    serve(handler_for(Systems(),ApprovalStore('runtime/demo-approvals.sqlite'),token,base),args.port)


if __name__ == '__main__':
    main()
