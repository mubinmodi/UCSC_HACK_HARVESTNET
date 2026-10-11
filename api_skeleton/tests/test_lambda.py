"""The Lambda Function URL handler uses the same router. Recorded payload v2.0 events."""

import json

import pytest

from conftest import EVENTS, load
from harvestnet_api_skeleton import lambda_function
from harvestnet_api_skeleton.lambda_function import lambda_handler


def event(name):
    return load(EVENTS / f"{name}.json")


def body_of(result):
    assert result["isBase64Encoded"] is False
    return json.loads(result["body"]) if result["body"] else None


def test_get_health():
    result = lambda_handler(event("get_health"), None)
    assert result["statusCode"] == 200
    assert body_of(result)["status"] == "ok"
    assert result["headers"]["Content-Type"] == "application/json; charset=utf-8"
    assert result["headers"]["Access-Control-Allow-Origin"] == "*"


def test_get_with_query_and_path_value():
    result = lambda_handler(event("get_request_with_query"), None)
    assert result["statusCode"] == 200
    assert body_of(result)["request_code"] == "K7P4"


def test_post_json_body():
    result = lambda_handler(event("post_request"), None)
    assert result["statusCode"] == 201
    assert body_of(result)["fair_share_lb"] == 12


def test_post_base64_body():
    result = lambda_handler(event("post_approval_base64"), None)
    assert result["statusCode"] == 200
    assert body_of(result)["status"] == "approval_recorded"


def test_put_body():
    result = lambda_handler(event("put_food_banks"), None)
    assert result["statusCode"] == 200
    assert body_of(result)["chosen_food_bank_ids"] == ["rural", "city"]


def test_preflight():
    result = lambda_handler(event("options_preflight"), None)
    assert result["statusCode"] == 204
    assert result["body"] == ""
    assert "PUT" in result["headers"]["Access-Control-Allow-Methods"]


def test_unknown_route():
    result = lambda_handler(event("unknown_route"), None)
    assert result["statusCode"] == 404
    assert body_of(result)["error"]["code"] == "not_found"


def test_bad_json():
    result = lambda_handler(event("post_bad_json"), None)
    assert result["statusCode"] == 400


@pytest.mark.parametrize("value", ["url", "URL", "function_url"])
def test_cors_can_be_left_to_the_function_url(monkeypatch, value):
    # When CORS is configured on the Function URL, Lambda adds the headers itself, and
    # headers from the function too would be duplicated on GET and POST.
    monkeypatch.setenv("HARVESTNET_CORS", value)
    result = lambda_handler(event("get_health"), None)
    assert "Access-Control-Allow-Origin" not in result["headers"]


def test_cors_from_function_by_default(monkeypatch):
    monkeypatch.delenv("HARVESTNET_CORS", raising=False)
    assert lambda_function.cors_from_function() is True
