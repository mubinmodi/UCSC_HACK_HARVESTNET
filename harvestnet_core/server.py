"""Local JSON HTTP server. Staff credentials are never returned or logged."""
import json
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .api import API
from .engine import Engine
from .records import Records


def make_server(api, host='127.0.0.1',port=8050):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_OPTIONS(self):
            self.send_response(204)
            self.cors()
            self.end_headers()
        def cors(self):
            self.send_header('Access-Control-Allow-Origin',os.environ.get('HARVESTNET_ALLOWED_ORIGIN','http://127.0.0.1:8040'))
            self.send_header('Access-Control-Allow-Headers','Content-Type, Authorization')
            self.send_header('Access-Control-Allow-Methods','GET, POST, PUT, OPTIONS')
        def handle_json(self):
            try:
                size=int(self.headers.get('Content-Length',0))
                if size<0 or size>262144: raise ValueError()
                body=json.loads(self.rfile.read(size)) if size else {}
                if not isinstance(body,dict): raise ValueError()
                auth=self.headers.get('Authorization','')
                token=auth[7:] if auth.startswith('Bearer ') else None
                status,data=api.call(self.command,self.path,body,token)
            except (ValueError,UnicodeDecodeError):
                status,data=400,{'error':{'code':'bad_request','message':'JSON object within size limit required'}}
            raw=json.dumps(data,allow_nan=False,ensure_ascii=False).encode()
            self.send_response(status); self.cors()
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Content-Length',str(len(raw)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.end_headers(); self.wfile.write(raw)
        do_GET=handle_json
        do_POST=handle_json
        do_PUT=handle_json
    return ThreadingHTTPServer((host,port),Handler)


if __name__=='__main__':
    Path('runtime').mkdir(exist_ok=True)
    fixture=json.loads(Path(os.environ.get('HARVESTNET_FIXTURE','docs/contracts/examples/scenario-normal-afternoon.json')).read_text())
    records=Records(os.environ.get('DATABASE_URL','runtime/core.sqlite'))
    engine=Engine(fixture,records)
    api=API(engine,staff_tokens=json.loads(os.environ.get('HARVESTNET_STAFF_TOKENS','{}')))
    make_server(api,port=int(os.environ.get('PORT','8050'))).serve_forever()
