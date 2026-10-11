"""Local JSON HTTP server. Staff credentials are never returned or logged."""
import json
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .api import API
from .email_delivery import EmailDispatcher
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


def bind_address(environ=None):
    """HOST defaults to 127.0.0.1; a container sets HOST=0.0.0.0 to accept its network."""
    environ=os.environ if environ is None else environ
    return environ.get('HOST','127.0.0.1'), int(environ.get('PORT','8050'))


if __name__=='__main__':
    Path('runtime').mkdir(exist_ok=True)
    fixture=json.loads(Path(os.environ.get('HARVESTNET_FIXTURE','docs/contracts/examples/scenario-normal-afternoon.json')).read_text())
    records=Records(os.environ.get('DATABASE_URL','runtime/core.sqlite'))
    engine=Engine(fixture,records)
    pickup_webhook=os.environ.get('N8N_PICKUP_WEBHOOK_URL')
    release_webhook=os.environ.get('N8N_RELEASE_WEBHOOK_URL')
    token=os.environ.get('N8N_WEBHOOK_TOKEN')
    email_enabled=bool(pickup_webhook or release_webhook)
    if email_enabled and not (pickup_webhook and release_webhook and token):
        raise ValueError('both pickup webhooks and N8N_WEBHOOK_TOKEN are required for email notices')
    page_url=os.environ.get('HARVESTNET_HOUSEHOLD_URL') if email_enabled else None
    if email_enabled and not page_url:
        raise ValueError('HARVESTNET_HOUSEHOLD_URL is required for email notices')
    from .voice import extractor_from_env
    # Voice intake: a Claude extractor under a hard spending cap only when a key and a cap are set; else the API answers 503.
    api=API(engine,staff_tokens=json.loads(os.environ.get('HARVESTNET_STAFF_TOKENS','{}')),
            household_page_url=page_url,extractor=extractor_from_env())
    if email_enabled:
        allowed=os.environ.get('SES_TEST_RECIPIENTS','')
        dispatcher=EmailDispatcher(api,pickup_webhook=pickup_webhook,release_webhook=release_webhook,
                                   token=token,allowed_recipients=allowed.split(','))
        import threading
        worker=threading.Thread(target=dispatcher.run_forever,daemon=True,name='household-email-outbox')
        worker.start()
        api.email_dispatcher_thread=worker
    host,port=bind_address()
    make_server(api,host=host,port=port).serve_forever()
