"""Local development server for the public API skeleton (stdlib ``http.server``).

    uv run python -m harvestnet_api_skeleton.server            # http://127.0.0.1:8040
    uv run python -m harvestnet_api_skeleton.server --port 9000 --host 0.0.0.0

Serves the agreed example responses with open CORS, so a browser page on any local port
can call it. All routing is in ``routes.py``.
"""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .routes import CORS_HEADERS, handle

MAX_BODY_BYTES = 1_000_000


class SkeletonHandler(BaseHTTPRequestHandler):
    server_version = "HarvestNetSkeleton/0.1"
    protocol_version = "HTTP/1.1"

    def _respond(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            raw = b'{"mode": "example", "error": {"code": "too_large", "message": "The body must be at most 1 MB."}}'
            self._send(413, {"Content-Type": "application/json; charset=utf-8", **CORS_HEADERS, "Connection": "close"}, raw)
            self.close_connection = True
            return
        body = self.rfile.read(length) if length else None
        resp = handle(self.command, self.path, body)
        self._send(resp.status, resp.headers, resp.body)

    def _send(self, status: int, headers: dict[str, str], body: bytes) -> None:
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _respond

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        # Paths can hold request codes; keep them out of logs.
        pass


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="HarvestNet public API skeleton (example data only)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8040)
    args = parser.parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), SkeletonHandler)
    print(f"HarvestNet API skeleton (example data) on http://{args.host}:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
