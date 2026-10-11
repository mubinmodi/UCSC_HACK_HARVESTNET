#!/usr/bin/env python3
"""Create or update the HarvestNet voice agent in ElevenLabs from the files in this folder.

    ELEVENLABS_API_KEY=... python3 integrations/elevenlabs/sync_agent.py            # create/update
    python3 integrations/elevenlabs/sync_agent.py --dry-run                         # no key, no network
    python3 integrations/elevenlabs/sync_agent.py --simulate "Hi, we are four people..."

Reads `tools.json` and `agent-prompt.md`. Matches existing tools and the agent by name, so
running it twice updates instead of duplicating. Writes the non-secret result to `agent.json`.
The API key comes only from the environment and is never printed or saved. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
API = "https://api.elevenlabs.io"
AGENT_NAME = "HarvestNet front desk"
TOOL_PREFIX = "harvestnet_"  # keeps the tools apart from anything else in the account

# Settings that are not in the repo's other files. Change here, then re-run.
LLM = "claude-sonnet-5-5"  # the front desk model named in docs/MVP_DESIGN.md
VOICE_ID = "cjVigY5qzO86Huf0OWal"  # the ElevenLabs API docs' default voice; change to taste
TTS_MODEL = "eleven_flash_v2_5"  # multilingual and fast, so Spanish works
MAX_CALL_SECONDS = 900
REQUEST_CODE_PLACEHOLDER = "not_saved_yet"  # until create_request returns the real code


def read_key() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        sys.exit("Set ELEVENLABS_API_KEY in the environment (or use --dry-run).")
    return key


# ---------------------------------------------------------------------------
# Build the payloads from the repo files (pure; no network)
# ---------------------------------------------------------------------------

def load_tools(folder: Path = HERE) -> dict:
    return json.loads((folder / "tools.json").read_text(encoding="utf-8"))


def parse_prompt_file(text: str) -> dict:
    """Pull the two first messages, the system prompt, and the Spanish fixed lines out of agent-prompt.md."""
    def quote_after(label: str) -> str:
        m = re.search(re.escape(label) + r"\*\*\s*\n\s*\n>\s*(.+)", text)
        if not m:
            raise ValueError(f"first message not found: {label}")
        return m.group(1).strip()

    en = quote_after("**English (default language):")
    es = quote_after("**Spanish (additional language override):")
    system = re.search(r"## System prompt\s*\n\s*```text\n(.*?)\n```", text, re.S)
    if not system:
        raise ValueError("system prompt block not found")
    rows = [r for r in re.findall(r"^\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$", text.split("## Spanish wording")[1], re.M)
            if r[0] != "English" and not r[0].startswith("---")]
    return {"first_message_en": en, "first_message_es": es, "system_prompt": system.group(1), "spanish_lines": rows}


def full_system_prompt(parsed: dict) -> str:
    lines = "\n".join(f'- "{en}" -> "{es}"' for en, es in parsed["spanish_lines"])
    return (
        parsed["system_prompt"].rstrip()
        + "\n\nSPANISH FIXED LINES\n"
        + "When the call is in Spanish, say these fixed lines in Spanish, in these words:\n"
        + lines
        + "\n"
    )


def _schema(spec: dict) -> dict:
    """One tool parameter in ElevenLabs' schema: the model fills it, a dynamic variable does, or it is a constant."""
    source = spec.get("source", "llm")
    out: dict = {"type": spec["type"]}
    if source == "dynamic_variable":
        out["dynamic_variable"] = spec["dynamic_variable"]
        return out
    if source == "constant":
        out["constant_value"] = spec["value"]
        return out
    out["description"] = spec.get("description") or "Value for this field."
    if "enum" in spec:
        out["enum"] = spec["enum"]
    if spec["type"] == "object":
        props = {k: _schema(v) for k, v in spec.get("properties", {}).items()}
        out["properties"] = props
        # A property whose description says "or null" may be left out.
        out["required"] = [k for k, v in spec.get("properties", {}).items() if "or null" not in v.get("description", "")]
    if spec["type"] == "array":
        out["items"] = _schema(spec["items"])
    return out


def _required(params: dict) -> list[str]:
    return [k for k, v in params.items() if v.get("source", "llm") == "llm"]


def build_tool_config(tool: dict, base_url: str) -> dict:
    """The body for POST /v1/convai/tools: one HarvestNet operation as a webhook tool."""
    api_schema: dict = {"url": base_url.rstrip("/") + tool["path"], "method": tool["method"]}
    if tool.get("path_parameters"):
        api_schema["path_params_schema"] = {k: _schema(v) for k, v in tool["path_parameters"].items()}
    if tool.get("query_parameters"):
        q = tool["query_parameters"]
        api_schema["query_params_schema"] = {
            "properties": {k: _schema(v) for k, v in q.items()},
            "required": _required(q),
        }
    if tool.get("body_parameters"):
        b = tool["body_parameters"]
        api_schema["content_type"] = "application/json"
        api_schema["request_body_schema"] = {
            "type": "object",
            "description": "",
            "required": _required(b),
            "properties": {k: _schema(v) for k, v in b.items()},
        }
    config: dict = {
        "type": "webhook",
        "name": TOOL_PREFIX + tool["name"],
        "description": tool["description"],
        "response_timeout_secs": 30 if tool["name"] == "voice_intake" else 20,
        "api_schema": api_schema,
    }
    assignments = [
        {"dynamic_variable": var, "value_path": path, "source": "response"}
        for var, path in tool.get("assign_dynamic_variables", {}).items()
    ]
    if assignments:
        config["assignments"] = assignments
    return {"tool_config": config}


def system_tool(kind: str) -> dict:
    return {"type": "system", "name": kind, "description": "", "params": {"system_tool_type": kind}}


def build_agent_body(parsed: dict, tool_ids: list[str]) -> dict:
    """The body for POST /v1/convai/agents/create (and PATCH /v1/convai/agents/{id})."""
    return {
        "name": AGENT_NAME,
        "tags": ["harvestnet", "ticket-4"],
        "conversation_config": {
            "agent": {
                "language": "en",
                "first_message": parsed["first_message_en"],
                "dynamic_variables": {"dynamic_variable_placeholders": {"request_code": REQUEST_CODE_PLACEHOLDER}},
                "prompt": {
                    "prompt": full_system_prompt(parsed),
                    "llm": LLM,
                    "temperature": 0.2,
                    "tool_ids": tool_ids,
                    "built_in_tools": {
                        "language_detection": system_tool("language_detection"),
                        "end_call": system_tool("end_call"),
                    },
                },
            },
            "language_presets": {
                "es": {
                    "overrides": {
                        "agent": {"language": "es", "first_message": parsed["first_message_es"]},
                    }
                }
            },
            "tts": {"model_id": TTS_MODEL, "voice_id": VOICE_ID},
            "conversation": {"max_duration_seconds": MAX_CALL_SECONDS},
        },
    }


def build_plan(base_url: str, folder: Path = HERE) -> dict:
    """Everything sync would send, with placeholder tool ids. Used by --dry-run and the tests."""
    tools = load_tools(folder)
    parsed = parse_prompt_file((folder / "agent-prompt.md").read_text(encoding="utf-8"))
    tool_bodies = {t["name"]: build_tool_config(t, base_url) for t in tools["tools"]}
    ids = [f"<id:{TOOL_PREFIX}{name}>" for name in tool_bodies]
    return {"base_url": base_url, "tools": tool_bodies, "agent": build_agent_body(parsed, ids)}


# ---------------------------------------------------------------------------
# Talk to ElevenLabs
# ---------------------------------------------------------------------------

class ApiError(RuntimeError):
    pass


def call(key: str, method: str, path: str, body: dict | None = None):
    req = urllib.request.Request(
        API + path,
        method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={"xi-api-key": key, "content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        # The error body never contains our key, but keep it short anyway.
        raise ApiError(f"{method} {path} -> HTTP {e.code}: {e.read().decode()[:500]}") from None


def upsert_tools(key: str, bodies: dict) -> dict[str, str]:
    existing = {}
    listing = call(key, "GET", "/v1/convai/tools?page_size=100")
    for t in listing.get("tools", []):
        cfg = t.get("tool_config") or t
        existing[cfg.get("name")] = t["id"]
    ids = {}
    for name, body in bodies.items():
        full = body["tool_config"]["name"]
        if full in existing:
            ids[name] = existing[full]
            call(key, "PATCH", f"/v1/convai/tools/{ids[name]}", body)
            print(f"updated tool {full}")
        else:
            ids[name] = call(key, "POST", "/v1/convai/tools", body)["id"]
            print(f"created tool {full}")
    return ids


def find_agent(key: str) -> str | None:
    from urllib.parse import quote
    listing = call(key, "GET", f"/v1/convai/agents?search={quote(AGENT_NAME)}&page_size=100")
    for a in listing.get("agents", []):
        if a.get("name") == AGENT_NAME:
            return a["agent_id"]
    return None


def upsert_agent(key: str, body: dict) -> str:
    agent_id = find_agent(key)
    if agent_id:
        call(key, "PATCH", f"/v1/convai/agents/{agent_id}", body)
        print(f"updated agent {AGENT_NAME}")
        return agent_id
    agent_id = call(key, "POST", "/v1/convai/agents/create", body)["agent_id"]
    print(f"created agent {AGENT_NAME}")
    return agent_id


def summary(plan: dict, agent_id: str, tool_ids: dict[str, str]) -> dict:
    """The non-secret record saved to agent.json."""
    cfg = plan["agent"]["conversation_config"]
    return {
        "synthetic": True,
        "note": "Written by sync_agent.py. No secrets. Tool ids and the agent id are identifiers, not credentials.",
        "agent_name": AGENT_NAME,
        "agent_id": agent_id,
        "tool_ids": tool_ids,
        "tools_base_url": plan["base_url"],
        "settings": {
            "llm": cfg["agent"]["prompt"]["llm"],
            "temperature": cfg["agent"]["prompt"]["temperature"],
            "default_language": cfg["agent"]["language"],
            "extra_languages": sorted(cfg["language_presets"]),
            "language_detection": "language_detection" in cfg["agent"]["prompt"]["built_in_tools"],
            "tts_model": cfg["tts"]["model_id"],
            "voice_id": cfg["tts"]["voice_id"],
            "max_call_seconds": cfg["conversation"]["max_duration_seconds"],
            "tools": {name: f"{b['tool_config']['api_schema']['method']} {b['tool_config']['api_schema']['url']}"
                      for name, b in plan["tools"].items()},
        },
    }


def simulate(key: str, agent_id: str, opening: str, language: str, turns: int) -> dict:
    return call(key, "POST", f"/v1/convai/agents/{agent_id}/simulate-conversation", {
        "simulation_specification": {"simulated_user_config": {"first_message": opening, "language": language}},
        "new_turns_limit": turns,
    })


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="print the payloads (no key, no network) and exit")
    ap.add_argument("--base-url", help="API the tools call (default: live_base_url in tools.json)")
    ap.add_argument("--skeleton", action="store_true", help="point the tools at the example-data skeleton (base_url)")
    ap.add_argument("--simulate", metavar="OPENING", help="after syncing, run one simulated call that opens with this line")
    ap.add_argument("--language", default="en", choices=["en", "es"], help="language of the simulated caller")
    ap.add_argument("--turns", type=int, default=12, help="turn limit for --simulate")
    args = ap.parse_args(argv)

    tools = load_tools()
    base = args.base_url or (tools["base_url"] if args.skeleton else tools["live_base_url"])
    plan = build_plan(base)

    if args.dry_run:
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return 0

    key = read_key()
    tool_ids = upsert_tools(key, plan["tools"])
    parsed = parse_prompt_file((HERE / "agent-prompt.md").read_text(encoding="utf-8"))
    agent_id = upsert_agent(key, build_agent_body(parsed, list(tool_ids.values())))
    (HERE / "agent.json").write_text(
        json.dumps(summary(plan, agent_id, tool_ids), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"agent_id {agent_id}; wrote integrations/elevenlabs/agent.json")

    if args.simulate:
        result = simulate(key, agent_id, args.simulate, args.language, args.turns)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ApiError as e:
        sys.exit(f"ElevenLabs refused: {e}")
