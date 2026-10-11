"""The pure router returns every documented example at its route (ticket #1)."""

import json
from urllib.parse import urlencode

import pytest

from conftest import api_example_files, load
from harvestnet_api_skeleton.routes import CORS_HEADERS, handle, load_routes


def call(e):
    req = e["example"]["request"]
    target = req["path"] + ("?" + urlencode(req["query"]) if req.get("query") else "")
    body = json.dumps(req["body"]).encode() if "body" in req else None
    return handle(e["method"], target, body)


@pytest.mark.parametrize("path", api_example_files(), ids=lambda p: p.stem)
def test_every_operation_returns_its_example(path):
    e = load(path)
    resp = call(e)
    assert resp.status == e["example"]["response"]["status"]
    assert json.loads(resp.body) == e["example"]["response"]["body"]
    assert resp.headers["Content-Type"] == "application/json; charset=utf-8"


def test_routes_cover_every_example_file():
    routes = load_routes()
    assert sorted(r.operation for r in routes) == sorted(p.stem for p in api_example_files())


def test_any_path_value_returns_the_example():
    resp = handle("GET", "/requests/ZZZZ")
    assert resp.status == 200
    assert json.loads(resp.body)["request_code"] == "K7P4"


def test_trailing_slash_and_query_are_ignored_for_matching():
    assert handle("GET", "/health/").status == 200
    assert handle("GET", "/fair-share?household_size=9").status == 200


def test_same_path_different_methods_pick_different_operations():
    listed = json.loads(handle("GET", "/approvals?organization_id=city").body)
    recorded = json.loads(handle("POST", "/approvals", b'{"decision": "approve"}').body)
    assert "approvals" in listed and recorded["status"] == "approval_recorded"


def test_unknown_route_is_404_with_error_shape():
    resp = handle("GET", "/nope")
    assert resp.status == 404
    body = json.loads(resp.body)
    assert body["error"]["code"] == "not_found" and body["mode"] == "example"


def test_known_path_with_wrong_method_is_405():
    resp = handle("DELETE", "/requests")
    assert resp.status == 405
    assert json.loads(resp.body)["error"]["code"] == "method_not_allowed"
    assert "POST" in resp.headers["Allow"]


def test_bad_json_body_is_400():
    resp = handle("POST", "/requests", b"{not json")
    assert resp.status == 400
    assert json.loads(resp.body)["error"]["code"] == "bad_request"


def test_body_must_be_a_json_object():
    assert handle("POST", "/requests", b"[1, 2]").status == 400


def test_empty_body_is_allowed_for_the_skeleton():
    assert handle("POST", "/requests", b"").status == 201


def test_preflight_returns_204_with_cors():
    resp = handle("OPTIONS", "/requests")
    assert resp.status == 204 and resp.body == b""
    assert resp.headers["Access-Control-Allow-Origin"] == "*"


def test_every_response_has_cors_headers_by_default():
    for resp in (handle("GET", "/health"), handle("GET", "/nope"), handle("POST", "/requests", b"{bad")):
        for k, v in CORS_HEADERS.items():
            assert resp.headers[k] == v


def test_cors_headers_can_be_left_to_the_host():
    resp = handle("GET", "/health", cors=False)
    assert "Access-Control-Allow-Origin" not in resp.headers


def test_root_lists_every_operation():
    body = json.loads(handle("GET", "/").body)
    assert body["mode"] == "example"
    assert {o["operation"] for o in body["operations"]} == {p.stem for p in api_example_files()}
