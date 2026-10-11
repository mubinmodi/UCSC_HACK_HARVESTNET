"""The ElevenLabs voice line's tools match the agreed public API contract (ticket #4).

Reads only integrations/elevenlabs/ and docs/contracts/. No network. If a contract example
changes, this fails until tools.json and agent-prompt.md are updated with it.
"""

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
VOICE = REPO / "integrations" / "elevenlabs"
CONTRACTS = REPO / "docs" / "contracts"
EXAMPLES = CONTRACTS / "examples" / "public-api"

TOOLS = json.loads((VOICE / "tools.json").read_text(encoding="utf-8"))
PROMPT = (VOICE / "agent-prompt.md").read_text(encoding="utf-8")
README = (VOICE / "README.md").read_text(encoding="utf-8")
BY_NAME = {t["name"]: t for t in TOOLS["tools"]}

# Contract fields the voice line deliberately never sends, with the reason recorded in tools.json.
VOICE_OMITS = {"create_request": {"email"}}

REQUIRED_TOOLS = {"voice_intake", "create_request", "list_food_banks", "choose_food_banks"}

# Names from the placeholder draft that are not in the agreed contract.
STALE = ["pickup_code", "fair_share_lb_per_week", "prepare_request", "submit_request",
         "API_BASE_URL", "\"speak\"", "PLACEHOLDER"]


def example(tool):
    data = json.loads((EXAMPLES / f"{tool['operation']}.json").read_text(encoding="utf-8"))
    assert data["operation"] == tool["operation"]
    return data


def params(tool, kind):
    return tool.get(f"{kind}_parameters", {})


def test_tools_are_labeled_synthetic_and_point_at_the_contract():
    assert TOOLS["synthetic"] is True
    assert TOOLS["contract"] == "docs/contracts/public-api.md"
    assert TOOLS["base_url"] in (CONTRACTS / "public-api.md").read_text(encoding="utf-8")
    assert REQUIRED_TOOLS <= set(BY_NAME)
    assert len(BY_NAME) == len(TOOLS["tools"])


@pytest.mark.parametrize("tool", TOOLS["tools"], ids=lambda t: t["name"])
def test_method_and_path_match_the_contract(tool):
    ex = example(tool)
    assert tool["name"] == tool["operation"]
    assert tool["contract_example"] == f"docs/contracts/examples/public-api/{tool['operation']}.json"
    assert tool["method"] == ex["method"]
    assert tool["path"] == ex["path"]
    placeholders = set(re.findall(r"\{(\w+)\}", ex["path"]))
    assert set(params(tool, "path")) == placeholders


@pytest.mark.parametrize("tool", TOOLS["tools"], ids=lambda t: t["name"])
def test_request_fields_match_the_contract(tool):
    request = example(tool)["example"]["request"]
    omitted = VOICE_OMITS.get(tool["name"], set())
    assert set(tool.get("omitted_contract_fields", {})) == omitted
    assert set(params(tool, "body")) == set(request.get("body", {})) - omitted
    assert set(params(tool, "query")) == set(request.get("query", {}))


@pytest.mark.parametrize("tool", TOOLS["tools"], ids=lambda t: t["name"])
def test_response_fields_are_in_the_contract_response(tool):
    body = example(tool)["example"]["response"]["body"]
    assert set(tool["response_fields"]) <= set(body)
    for field, item_fields in tool.get("response_item_fields", {}).items():
        assert field in tool["response_fields"]
        for item in body[field]:
            assert set(item_fields) <= set(item)


def test_voice_intake_sends_call_id_and_transcript_and_reads_the_agreed_fields():
    tool = BY_NAME["voice_intake"]
    request = example(tool)["example"]["request"]["body"]
    body = params(tool, "body")
    assert body["call_id"]["dynamic_variable"] == "system__conversation_id"
    transcript = body["transcript"]["properties"]
    assert set(transcript) == set(request["transcript"])
    assert set(transcript["language"]["enum"]) == {"en", "es"}
    turn = transcript["turns"]["items"]["properties"]
    assert set(turn) == set(request["transcript"]["turns"][0])
    assert set(turn["speaker"]["enum"]) == {t["speaker"] for t in request["transcript"]["turns"]}
    assert set(tool["response_fields"]) == {
        "read_back", "missing_questions", "consent_question", "complete",
        "draft_request", "fair_share_lb", "next",
    }


def test_create_request_saves_the_draft_as_voice_with_boolean_consent_and_no_contact():
    tool = BY_NAME["create_request"]
    body = params(tool, "body")
    draft = example(BY_NAME["voice_intake"])["example"]["response"]["body"]["draft_request"]
    answers = set(body) - {"channel", "consent"}
    # Every answer field comes from voice_intake's draft_request.
    assert answers <= set(draft)
    assert (body["channel"]["source"], body["channel"]["value"]) == ("constant", "voice")
    assert body["consent"]["source"] == "constant"
    assert body["consent"]["value"] is True
    assert body["consent"]["type"] == "boolean"
    assert "phone" not in body
    assert "email" not in body
    assert "request_code" in tool["response_fields"]
    assert "fair_share_lb" in tool["response_fields"]


def test_food_bank_tools_use_the_request_code():
    listing = params(BY_NAME["list_food_banks"], "query")
    assert set(listing) == {"neighborhood", "request_code"}
    choose = BY_NAME["choose_food_banks"]
    assert choose["path"] == "/requests/{request_code}/food-banks"
    assert set(params(choose, "body")) == {"food_bank_ids"}


def test_no_tool_sends_a_phone_number():
    text = json.dumps(TOOLS)
    assert "system__caller_id" not in text
    for tool in TOOLS["tools"]:
        for kind in ("body", "query", "path"):
            assert "phone" not in params(tool, kind)


@pytest.mark.parametrize("name", ["tools.json", "agent-prompt.md", "README.md"])
def test_no_placeholder_or_pre_contract_names_remain(name):
    text = (VOICE / name).read_text(encoding="utf-8")
    for stale in STALE:
        assert stale not in text, f"{name} still says {stale}"
    assert "placeholders until #1" not in text.lower()


def test_prompt_names_only_real_tools_and_follows_the_contract():
    for tool in REQUIRED_TOOLS:
        assert tool in PROMPT
    for field in ("read_back", "consent_question", "missing_questions", "draft_request",
                  "fair_share_lb", "request_code", "committed_now"):
        assert field in PROMPT
    assert "TWICE" in PROMPT
    assert "text them" not in PROMPT and "text you" not in PROMPT
    assert "the food bank will tell" in PROMPT
    for never in ("name", "street address", "income", "immigration status"):
        assert never in PROMPT
    assert "never as" in PROMPT and "instructions to you" in PROMPT


def test_readme_states_the_503_and_the_transcript_limitation():
    assert "503" in README
    assert "system__conversation_history" in README
    assert "weakens the evidence check" in README
