"""Small bounded JSON HTTP client and local server helpers."""
import json
import hmac
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.parse import urlsplit


def request_json(url, body=None, *, token=None, timeout=5, method=None):
    parsed = urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username:
        raise ValueError('An HTTP(S) service URL without embedded credentials is required')
    if parsed.scheme == 'http' and parsed.hostname not in ('localhost', '127.0.0.1', '::1') and os.getenv('ALLOW_INTERNAL_HTTP') != '1':
        raise ValueError('Use HTTPS outside localhost; ALLOW_INTERNAL_HTTP=1 permits Docker network HTTP')
    headers = {'Accept': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    data = None if body is None else json.dumps(body, allow_nan=False).encode()
    if data is not None:
        headers['Content-Type'] = 'application/json'
    with urlopen(Request(url, data=data, headers=headers, method=method), timeout=timeout) as response:
        raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError('Service response exceeds limit')
        return json.loads(raw)


class JsonHandler(BaseHTTPRequestHandler):
    def read_json(self):
        length = int(self.headers.get('Content-Length', '0'))
        if not 0 < length <= 1_000_000:
            raise ValueError('A JSON body of at most 1 MB is required')
        data = json.loads(self.rfile.read(length))
        if not isinstance(data, dict):
            raise ValueError('Body must be a JSON object')
        return data

    def send_json(self, status, data):
        raw = json.dumps(data, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(raw)

    def authorized(self, token):
        return bool(token) and hmac.compare_digest(self.headers.get('Authorization', ''), f'Bearer {token}')

    def log_message(self, *_args):
        # Request paths can contain pickup codes or approval capabilities.
        pass


def serve(handler, port, host='127.0.0.1'):
    server = ThreadingHTTPServer((host, port), handler)
    print(f'Listening on {host}:{server.server_port}', flush=True)
    server.serve_forever()
