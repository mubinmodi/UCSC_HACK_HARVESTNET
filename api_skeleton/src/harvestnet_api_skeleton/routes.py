"""Route table and example lookup for the public API skeleton (ticket #1).

Pure: no sockets, no globals beyond a cached route table. Both entry points use it:
``server.py`` (stdlib ``http.server``, for local development) and ``lambda_function.py``
(AWS Lambda Function URL).

The routes come from the agreed example files in ``docs/contracts/examples/public-api/``,
one per operation. Each file names its method and path template, and the skeleton returns
that file's example response for any matching request. Real logic (Lane A, #9) replaces
this behind the same routes and shapes. Nothing here decides or stores anything.

Examples are found in this order: ``HARVESTNET_EXAMPLES_DIR`` if set; the copy packaged
inside the Lambda zip (``harvestnet_api_skeleton/examples/public-api/``); then the repo's
``docs/contracts/examples/public-api/``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

__all__ = ["CORS_HEADERS", "Response", "Route", "examples_source", "handle", "load_routes"]

CONTRACT_VERSION = "contract-v0.1"
_REPO_EXAMPLES = Path(__file__).resolve().parents[3] / "docs" / "contracts" / "examples" / "public-api"
_LABEL = {"mode": "example", "synthetic": True}

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, PUT, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Max-Age": "600",
}


@dataclass(frozen=True)
class Route:
    operation: str
    method: str
    path: str
    summary: str
    status: int
    body: dict[str, Any]
    segments: tuple[str, ...] = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "segments", _segments(self.path))

    def matches(self, segments: tuple[str, ...]) -> bool:
        if len(segments) != len(self.segments):
            return False
        return all(t.startswith("{") or t == s for t, s in zip(self.segments, segments))

    @property
    def literal_count(self) -> int:
        return sum(1 for t in self.segments if not t.startswith("{"))


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict[str, str]
    body: bytes


def examples_source() -> str:
    """Where the examples come from: ``env``, ``packaged``, or ``repo``."""
    if os.environ.get("HARVESTNET_EXAMPLES_DIR"):
        return "env"
    if _packaged().is_dir():
        return "packaged"
    return "repo"


def load_routes(examples_dir: str | Path | None = None) -> tuple[Route, ...]:
    """Every route, read from the example files. Literal paths sort before templates."""
    files = _example_files(examples_dir)
    routes = []
    for name, text in files:
        data = json.loads(text)
        response = data["example"]["response"]
        if data["operation"] != name:
            raise ValueError(f"{name}.json names operation {data['operation']!r}")
        routes.append(Route(data["operation"], data["method"], data["path"], data["summary"], int(response["status"]), response["body"]))
    if not routes:
        raise FileNotFoundError("no public API example files found")
    return tuple(sorted(routes, key=lambda r: (-r.literal_count, r.path, r.method)))


@lru_cache(maxsize=1)
def _default_routes() -> tuple[Route, ...]:
    return load_routes()


def handle(method: str, target: str, body: bytes | None = None, *, cors: bool = True, routes: Iterable[Route] | None = None) -> Response:
    """Answer one request. ``target`` is the path with an optional query string."""
    routes = tuple(routes) if routes is not None else _default_routes()
    method = method.upper()
    extra = dict(CORS_HEADERS) if cors else {}

    if method == "OPTIONS":
        return Response(204, extra, b"")

    segments = _segments(urlsplit(target).path)
    if not segments and method == "GET":
        return _json(200, {**_LABEL, "contract_version": CONTRACT_VERSION, "operations": [
            {"operation": r.operation, "method": r.method, "path": r.path, "summary": r.summary} for r in routes
        ]}, extra)

    matching = [r for r in routes if r.matches(segments)]
    if not matching:
        return _error(404, "not_found", f"No operation at {urlsplit(target).path}. GET / lists them.", extra)
    route = next((r for r in matching if r.method == method), None)
    if route is None:
        allowed = ", ".join(sorted({r.method for r in matching} | {"OPTIONS"}))
        return _error(405, "method_not_allowed", f"Use {allowed} here.", {**extra, "Allow": allowed})

    if body:
        try:
            parsed = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            return _error(400, "bad_request", "The body must be JSON.", extra)
        if not isinstance(parsed, dict):
            return _error(400, "bad_request", "The body must be a JSON object.", extra)

    return _json(route.status, route.body, extra)


def _json(status: int, data: dict[str, Any], extra: dict[str, str]) -> Response:
    raw = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", **extra}
    return Response(status, headers, raw)


def _error(status: int, code: str, message: str, extra: dict[str, str]) -> Response:
    return _json(status, {"mode": "example", "error": {"code": code, "message": message}}, extra)


def _segments(path: str) -> tuple[str, ...]:
    return tuple(s for s in path.strip("/").split("/") if s)


def _packaged():
    return resources.files(__package__).joinpath("examples", "public-api")


def _example_files(examples_dir: str | Path | None) -> list[tuple[str, str]]:
    chosen = examples_dir or os.environ.get("HARVESTNET_EXAMPLES_DIR")
    if chosen:
        folder = Path(chosen)
        return [(p.stem, p.read_text(encoding="utf-8")) for p in sorted(folder.glob("*.json"))]
    packaged = _packaged()
    if packaged.is_dir():
        entries = sorted((e for e in packaged.iterdir() if e.name.endswith(".json")), key=lambda e: e.name)
        return [(e.name[: -len(".json")], e.read_text(encoding="utf-8")) for e in entries]
    return [(p.stem, p.read_text(encoding="utf-8")) for p in sorted(_REPO_EXAMPLES.glob("*.json"))]
