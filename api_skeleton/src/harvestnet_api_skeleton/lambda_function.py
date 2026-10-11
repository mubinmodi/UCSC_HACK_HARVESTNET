"""AWS Lambda entry point for the public API skeleton, behind a Function URL.

Handler: ``harvestnet_api_skeleton.lambda_function.lambda_handler``. It reads the Function URL
payload format version 2.0 and uses the same routing as the local server (``routes.py``).

CORS: by default the function adds open CORS headers itself. If CORS is configured on the
Function URL instead, set ``HARVESTNET_CORS=url``: Lambda then adds the headers, and headers
from both would be duplicated on GET and POST, which browsers reject.
"""

from __future__ import annotations

import base64
import os
from typing import Any

from .routes import handle

__all__ = ["cors_from_function", "lambda_handler"]


def cors_from_function() -> bool:
    return os.environ.get("HARVESTNET_CORS", "function").strip().lower() not in {"url", "function_url"}


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    http = event.get("requestContext", {}).get("http", {})
    method = http.get("method", "GET")
    path = event.get("rawPath") or http.get("path") or "/"
    query = event.get("rawQueryString") or ""
    body = event.get("body")
    raw = None
    if body:
        raw = base64.b64decode(body) if event.get("isBase64Encoded") else body.encode("utf-8")

    resp = handle(method, path + (f"?{query}" if query else ""), raw, cors=cors_from_function())
    return {
        "statusCode": resp.status,
        "headers": resp.headers,
        "body": resp.body.decode("utf-8"),
        "isBase64Encoded": False,
    }
