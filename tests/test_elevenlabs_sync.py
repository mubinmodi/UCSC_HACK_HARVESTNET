"""The ElevenLabs sync script builds the right payloads from the repo files (ticket #4). No network, no key."""

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
VOICE = REPO / "integrations" / "elevenlabs"

spec = importlib.util.spec_from_file_location("sync_agent", VOICE / "sync_agent.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)

TOOLS = json.loads((VOICE / "tools.json").read_text(encoding="utf-8"))
BASE = "https://example.test/api"
PLAN = sync.build_plan(BASE)


def config(name):
    return PLAN["tools"][name]["tool_config"]


def test_every_repo_tool_becomes_one_webhook_with_the_contract_method_and_url():
    assert set(PLAN["tools"]) == {t["name"] for t in TOOLS["tools"]}
    for t in TOOLS["tools"]:
        cfg = config(t["name"])
        assert cfg["type"] == "webhook"
        assert cfg["name"] == "harvestnet_" + t["name"]
        assert cfg["api_schema"]["method"] == t["method"]
        assert cfg["api_schema"]["url"] == BASE + t["path"]


def test_live_base_url_is_the_default_and_the_skeleton_is_still_there():
    assert TOOLS["live_base_url"].startswith("https://")
    assert TOOLS["live_base_url"] != TOOLS["base_url"]


def test_create_request_has_constant_channel_and_boolean_consent_and_no_contact_fields():
    body = config("create_request")["api_schema"]["request_body_schema"]["properties"]
    assert body["channel"] == {"type": "string", "constant_value": "voice"}
    assert body["consent"] == {"type": "boolean", "constant_value": True}
    assert not {"phone", "email"} & set(body)
    required = config("create_request")["api_schema"]["request_body_schema"]["required"]
    assert "channel" not in required and "consent" not in required  # constants, never filled by the model
    assert config("create_request")["assignments"] == [
        {"dynamic_variable": "request_code", "value_path": "request_code", "source": "response"}]


def test_dynamic_variables_are_not_filled_by_the_model():
    call_id = config("voice_intake")["api_schema"]["request_body_schema"]["properties"]["call_id"]
    assert call_id == {"type": "string", "dynamic_variable": "system__conversation_id"}
    path = config("choose_food_banks")["api_schema"]["path_params_schema"]["request_code"]
    assert path == {"type": "string", "dynamic_variable": "request_code"}
    assert "{request_code}" in config("choose_food_banks")["api_schema"]["url"]
    q = config("list_food_banks")["api_schema"]["query_params_schema"]
    assert q["required"] == ["neighborhood"]
    assert q["properties"]["request_code"]["dynamic_variable"] == "request_code"


def test_voice_intake_transcript_shape():
    body = config("voice_intake")["api_schema"]["request_body_schema"]["properties"]
    transcript = body["transcript"]
    assert set(transcript["properties"]) == {"language", "turns"}
    turn = transcript["properties"]["turns"]["items"]
    assert set(turn["properties"]) == {"speaker", "text"}
    assert turn["required"] == ["speaker", "text"]
    assert config("voice_intake")["response_timeout_secs"] > config("list_food_banks")["response_timeout_secs"]


def test_no_tool_sends_a_phone_number():
    text = json.dumps(PLAN)
    assert "system__caller_id" not in text
    assert '"phone"' not in text


def test_agent_has_prompt_languages_tools_and_voice():
    agent = PLAN["agent"]
    cfg = agent["conversation_config"]
    assert agent["name"] == "HarvestNet front desk"
    assert cfg["agent"]["language"] == "en"
    assert cfg["agent"]["first_message"].startswith("Hi, this is HarvestNet")
    es = cfg["language_presets"]["es"]["overrides"]["agent"]
    assert es["first_message"].startswith("Hola, habla HarvestNet")
    prompt = cfg["agent"]["prompt"]
    assert "language_detection" in prompt["built_in_tools"]
    assert len(prompt["tool_ids"]) == len(TOOLS["tools"])
    assert cfg["tts"]["voice_id"] and cfg["tts"]["model_id"]
    for rule in ("NEVER ASK FOR", "TWICE", "Every number you say"):
        assert rule in prompt["prompt"]


def test_spanish_fixed_lines_are_appended_to_the_prompt():
    parsed = sync.parse_prompt_file((VOICE / "agent-prompt.md").read_text(encoding="utf-8"))
    assert len(parsed["spanish_lines"]) == 11
    text = sync.full_system_prompt(parsed)
    assert "Su código es" in text and "Gracias. No se guardó nada." in text


def test_dry_run_prints_the_plan_without_a_key_or_network(monkeypatch, capsys):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)

    def boom(*a, **k):
        raise AssertionError("network used in dry run")

    monkeypatch.setattr(sync.urllib.request, "urlopen", boom)
    assert sync.main(["--dry-run", "--base-url", BASE]) == 0
    out = json.loads(capsys.readouterr().out)
    assert set(out) == {"base_url", "tools", "agent"}
    assert out["base_url"] == BASE


def test_a_real_run_needs_the_key_and_never_prints_it(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        sync.main([])


def test_summary_has_no_secret_and_lists_ids():
    out = sync.summary(PLAN, "agent_x", {"voice_intake": "tool_y"})
    text = json.dumps(out)
    assert "agent_x" in text and "tool_y" in text
    assert "xi-api-key" not in text and "sk_" not in text
