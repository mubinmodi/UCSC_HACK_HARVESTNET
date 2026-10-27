"""Local stand-in for the AWS Caddy gateway (deploy/aws/Caddyfile), on 127.0.0.1 only.

One origin serves the built frontends (the landing page at / and each app at /<app>/) and proxies the same routes the real gateway does:
/api/* -> core, /platform/* and /human/* -> approvals, POST /systems/demo/<bank>/cooler -> systems.
Standard library only. It binds to localhost and refuses anything else.
"""
import argparse
import mimetypes
import re
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

COOLER = re.compile(r'^/systems/demo/(city|rural|eastside)/cooler$')


def make_handler(dist, core, approvals, systems):
    dist = Path(dist).resolve()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *args):
            pass

        def proxy(self, base, path):
            length = int(self.headers.get('Content-Length') or 0)
            body = self.rfile.read(length) if length else None
            req = urllib.request.Request(base + path, data=body, method=self.command)
            for name in ('Authorization', 'Content-Type', 'Accept'):
                if self.headers.get(name):
                    req.add_header(name, self.headers[name])
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    status, data, ctype = r.status, r.read(), r.headers.get('Content-Type', 'application/json')
            except urllib.error.HTTPError as e:
                status, data, ctype = e.code, e.read(), e.headers.get('Content-Type', 'application/json')
            except (urllib.error.URLError, OSError):
                status, data, ctype = 502, b'{"error":"upstream not reachable"}', 'application/json'
            self.send_response(status)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)

        def route(self):
            path = self.path
            if path.startswith('/api/') or path == '/api':
                return self.proxy(core, path[4:] or '/')
            if path.startswith('/platform/'):
                return self.proxy(approvals, path[len('/platform'):])
            if path.startswith('/human/'):
                return self.proxy(approvals, path)
            if self.command == 'POST' and COOLER.match(path.split('?')[0]):
                return self.proxy(systems, path[len('/systems'):])
            if self.command != 'GET':
                return self.send_error(405)
            return self.static(path.split('?')[0].split('#')[0])

        def static(self, path):
            # Like the AWS Caddyfile, the landing app answers "/" and anything no other app serves.
            target = (dist / path.lstrip('/')).resolve()
            if target.is_dir():
                target = target / 'index.html'
            if path == '/' or not target.is_file():
                target = (dist / 'landing' / path.lstrip('/')).resolve()
                if target.is_dir():
                    target = target / 'index.html'
            if dist not in target.parents or not target.is_file():
                return self.send_error(404)
            data = target.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_GET = do_POST = do_PUT = route

    return Handler


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--port', type=int, default=8080)
    p.add_argument('--dist', required=True, help='folder holding household/, donor-dashboard/, results-strip/ and landing/')
    p.add_argument('--core', default='http://127.0.0.1:8050')
    p.add_argument('--approvals', default='http://127.0.0.1:8030')
    p.add_argument('--systems', default='http://127.0.0.1:8010')
    a = p.parse_args()
    ThreadingHTTPServer(('127.0.0.1', a.port), make_handler(a.dist, a.core, a.approvals, a.systems)).serve_forever()


if __name__ == '__main__':
    main()
