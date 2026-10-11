"""The http.server entry point uses the same router. Driven in memory, with no sockets."""

import io
import json

from harvestnet_api_skeleton.server import SkeletonHandler


class FakeConnection:
    def __init__(self, raw: bytes):
        self._in = io.BytesIO(raw)
        self.sent = bytearray()

    def makefile(self, mode, *args, **kwargs):
        return self._in

    def sendall(self, data):
        self.sent += data


def request(raw: bytes):
    conn = FakeConnection(raw)
    SkeletonHandler(conn, ("127.0.0.1", 50000), server=None)
    head, _, body = bytes(conn.sent).partition(b"\r\n\r\n")
    lines = head.decode().split("\r\n")
    status = int(lines[0].split()[1])
    headers = dict(line.split(": ", 1) for line in lines[1:])
    return status, headers, body


def test_get_returns_the_example_with_cors():
    status, headers, body = request(b"GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n")
    assert status == 200
    assert headers["Access-Control-Allow-Origin"] == "*"
    assert json.loads(body)["status"] == "ok"


def test_post_reads_the_body():
    payload = b'{"household_size": 4, "consent": true}'
    raw = b"POST /requests HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: " + str(len(payload)).encode() + b"\r\n\r\n" + payload
    status, _, body = request(raw)
    assert status == 201
    assert json.loads(body)["request_code"] == "K7P4"


def test_put_and_options_work():
    payload = b'{"food_bank_ids": ["rural"]}'
    raw = b"PUT /requests/K7P4/food-banks HTTP/1.1\r\nContent-Length: " + str(len(payload)).encode() + b"\r\n\r\n" + payload
    assert request(raw)[0] == 200
    status, headers, body = request(b"OPTIONS /requests HTTP/1.1\r\nOrigin: http://localhost:5173\r\n\r\n")
    assert status == 204 and body == b""
    assert "POST" in headers["Access-Control-Allow-Methods"]


def test_oversized_body_is_refused():
    raw = b"POST /requests HTTP/1.1\r\nContent-Length: 2000000\r\n\r\n{}"
    status, _, body = request(raw)
    assert status == 413
    assert json.loads(body)["error"]["code"] == "too_large"
