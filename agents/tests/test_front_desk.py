"""Front-desk assistant (#14). No test calls the Claude API: the extractor is injected,
and recorded (synthetic) extractor outputs stand in for it. See tests/fixtures/front_desk/."""

import json
import re
from datetime import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from harvestnet_agents.llm_negotiators import SpendingCap
from harvestnet_agents.front_desk import (
    EXTRACTION_SCHEMA,
    AgreementStatus,
    ClaudeExtractor,
    DraftRequest,
    ExtractionError,
    Language,
    PickupFacts,
    PickupWindow,
    ProducePortion,
    SnapAnswer,
    Transcript,
    Weekday,
    committed_portions,
    consent_wording,
    draft_from_form,
    fair_share_wording,
    intake_transcript,
    missing_questions,
    pickup_wording,
    read_back,
)

FIXTURES = Path(__file__).parent / "fixtures" / "front_desk"
FIXTURE_NAMES = sorted(p.stem for p in FIXTURES.glob("*.json"))


def load(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def recorded(output):
    """An extractor that replays a recorded output and remembers what it was shown."""

    def extractor(transcript):
        extractor.seen = transcript
        return output

    return extractor


def intake(name):
    fx = load(name)
    return intake_transcript(Transcript.from_dict(fx["transcript"]), recorded(fx["extractor_output"]))


def numbers_in(text):
    return set(re.findall(r"\d+", text))


def complete_draft(**changes):
    base = dict(
        language=Language.EN,
        household_size=4,
        pickup_windows=(PickupWindow(days=(Weekday.MON, Weekday.TUE, Weekday.WED, Weekday.THU, Weekday.FRI), start=time(18, 0)),),
        limited_fridge=True,
        neighborhood="Watsonville",
        cant_eat=("eggplant",),
        snap=SnapAnswer.YES,
    )
    base.update(changes)
    return DraftRequest(**base)


# --- 1. Recorded transcripts become correct draft requests -------------------------------


def test_fixtures_cover_both_languages_and_missing_fields():
    langs = {load(n)["transcript"]["language"] for n in FIXTURE_NAMES}
    assert langs == {"en", "es"}
    assert any(load(n)["expected_draft"]["missing"] for n in FIXTURE_NAMES)


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_recorded_transcript_becomes_expected_draft(name):
    assert intake(name).to_dict() == load(name)["expected_draft"]


def test_missing_fields_stay_missing_not_defaulted():
    draft = intake("en_missing")
    assert draft.limited_fridge is None
    assert draft.neighborhood is None
    assert draft.cant_eat is None  # unanswered, which is not the same as "nothing"
    assert not draft.is_complete
    assert draft.missing == ("limited_fridge", "neighborhood", "cant_eat")


def test_empty_cant_eat_is_an_answer_not_missing():
    draft = intake("es_complete")
    assert draft.cant_eat == ()
    assert "cant_eat" not in draft.missing


def test_unanswered_snap_is_not_said_and_never_missing():
    draft = intake("en_missing")
    assert draft.snap is SnapAnswer.NOT_SAID
    assert "snap" not in draft.missing


def test_number_the_household_did_not_say_is_dropped():
    # "me and my two kids": the extractor counted 3, but no one said 3.
    draft = intake("en_ungrounded")
    assert draft.household_size is None
    assert ("household_size", "number_not_in_evidence") in draft.dropped


def test_value_not_in_transcript_is_dropped():
    draft = intake("en_ungrounded")
    assert draft.neighborhood is None  # "Salinas" was never said
    assert "onions" not in draft.cant_eat  # invented item dropped, said items kept
    assert draft.cant_eat == ("tomatoes", "peppers")


def test_evidence_must_come_from_the_household_not_the_assistant():
    # The assistant mentioned CalFresh; the household never said it receives it.
    draft = intake("en_ungrounded")
    assert draft.snap is SnapAnswer.NOT_SAID
    assert ("snap", "evidence_not_in_transcript") in draft.dropped


def test_pickup_time_the_household_did_not_say_is_dropped():
    # "por la tarde" names no hour, so the extractor's 15:00 is dropped.
    draft = intake("es_ungrounded")
    assert draft.pickup_windows is None
    assert "pickup_windows" in draft.missing


@pytest.mark.parametrize(
    "bad",
    [
        {"household_size": {"value": "four", "evidence": "a family of 4"}},
        {"household_size": {"value": 0, "evidence": "a family of 4"}},
        {"household_size": {"value": True, "evidence": "a family of 4"}},
        {"pickup_windows": {"value": [{"days": ["mon"], "start": "25:00", "end": None}], "evidence": "Weekdays after 6 pm"}},
        {"pickup_windows": {"value": [{"days": ["mon"], "start": "20:00", "end": "18:00"}], "evidence": "Weekdays after 6 pm"}},
        {"snap": {"value": "maybe", "evidence": "we get CalFresh"}},
        {"limited_fridge": {"value": "yes", "evidence": "it's a small fridge"}},
    ],
)
def test_malformed_extractor_values_are_dropped_not_repaired(bad):
    fx = load("en_complete")
    output = {**fx["extractor_output"], **bad}
    draft = intake_transcript(Transcript.from_dict(fx["transcript"]), recorded(output))
    (field,) = bad
    assert (field, "invalid_value") in draft.dropped
    if field == "snap":
        assert draft.snap is SnapAnswer.NOT_SAID
    else:
        assert field in draft.missing


def test_extractor_output_missing_a_field_entirely_marks_it_missing():
    fx = load("en_complete")
    output = {k: v for k, v in fx["extractor_output"].items() if k != "neighborhood"}
    draft = intake_transcript(Transcript.from_dict(fx["transcript"]), recorded(output))
    assert draft.missing == ("neighborhood",)


def test_web_form_becomes_draft_without_an_llm():
    draft = draft_from_form(
        {
            "household_size": "4",
            "pickup_windows": [{"days": ["mon", "tue", "wed", "thu", "fri"], "start": "18:00", "end": None}],
            "limited_fridge": "yes",
            "neighborhood": " Watsonville ",
            "cant_eat": ["eggplant"],
            "snap": "yes",
        },
        Language.EN,
    )
    assert draft == complete_draft()


def test_web_form_leaves_absent_and_blank_fields_missing():
    draft = draft_from_form({"household_size": 2, "neighborhood": "  ", "snap": "prefer_not_to_say"}, Language.ES)
    assert draft.missing == ("pickup_windows", "limited_fridge", "neighborhood", "cant_eat")
    assert draft.snap is SnapAnswer.NOT_SAID


def test_draft_holds_no_transcript_text():
    # Privacy (section 12): only the request fields are kept, never the call itself.
    dumped = json.dumps(intake("en_complete").to_dict())
    assert "allergic" not in dumped and "I work until" not in dumped


# --- 2. The read-back wording matches the draft exactly ----------------------------------


def test_english_read_back_is_built_from_the_draft():
    assert read_back(intake("en_complete")) == (
        "Here is what I have. "
        "Household: 4 people. "
        "Pickup: weekdays after 6 pm. "
        "Fridge space: limited. "
        "Neighborhood: Watsonville. "
        "Can't eat: eggplant. "
        "SNAP/CalFresh: yes. "
        "Is that right?"
    )


def test_spanish_read_back_is_built_from_the_draft():
    assert read_back(intake("es_complete")) == (
        "Esto es lo que tengo. "
        "Hogar: 4 personas. "
        "Recogida: entre semana después de las 6 p. m. "
        "Espacio en el refrigerador: limitado. "
        "Vecindario: Watsonville. "
        "No pueden comer: nada. "
        "SNAP/CalFresh: sí. "
        "¿Es correcto?"
    )


def test_read_back_asks_for_missing_fields_instead_of_filling_them():
    text = read_back(intake("en_missing"))
    assert text == (
        "Here is what I have. "
        "Household: 2 people. "
        "Pickup: Saturday before 11 am. "
        "SNAP/CalFresh: prefer not to say. "
        "I still need a few answers. "
        "Is your fridge space limited? "
        "What neighborhood are you near? "
        "Is there anything your household can't eat?"
    )


def test_spanish_read_back_asks_for_missing_fields():
    assert read_back(intake("es_ungrounded")) == (
        "Esto es lo que tengo. "
        "Espacio en el refrigerador: limitado. "
        "Vecindario: Castroville. "
        "No pueden comer: chiles. "
        "SNAP/CalFresh: no. "
        "Todavía necesito algunas respuestas. "
        "¿Cuántas personas hay en su hogar? "
        "¿Cuándo puede recoger?"
    )


@pytest.mark.parametrize(
    "change, before, after",
    [
        ({"household_size": 5}, "4 people", "5 people"),
        ({"household_size": 1}, "4 people", "1 person"),
        ({"limited_fridge": False}, "Fridge space: limited", "Fridge space: not limited"),
        ({"neighborhood": "Freedom"}, "Watsonville", "Freedom"),
        ({"cant_eat": ("eggplant", "okra")}, "eggplant.", "eggplant and okra."),
        ({"snap": SnapAnswer.NO}, "SNAP/CalFresh: yes", "SNAP/CalFresh: no"),
        (
            {"pickup_windows": (PickupWindow(days=(Weekday.SAT, Weekday.SUN), start=time(9, 30), end=time(12, 0)),)},
            "weekdays after 6 pm",
            "weekends 9:30 am to 12 pm",
        ),
    ],
)
def test_every_draft_change_shows_in_the_read_back(change, before, after):
    old, new = read_back(complete_draft()), read_back(complete_draft(**change))
    assert before in old and before not in new.replace(after, "")
    assert after in new


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_read_back_has_no_number_the_draft_lacks(name):
    draft = intake(name)
    allowed = set()
    if draft.household_size is not None:
        allowed.add(str(draft.household_size))
    for w in draft.pickup_windows or ():
        for t in (w.start, w.end):
            if t is not None:
                allowed |= {str((t.hour % 12) or 12), f"{t.minute:02d}"}
    assert numbers_in(read_back(draft)) <= allowed


def test_consent_needs_a_complete_draft():
    with pytest.raises(ValueError):
        consent_wording(intake("en_missing"))


@pytest.mark.parametrize("lang, expected_start", [(Language.EN, "Can I save these answers?"), (Language.ES, "¿Puedo guardar estas respuestas?")])
def test_consent_wording_in_the_households_language(lang, expected_start):
    text = consent_wording(complete_draft(language=lang))
    assert text.startswith(expected_start)
    assert "7" in text  # requests expire after 7 days (section 12)
    assert numbers_in(text) == {"7"}


def test_missing_questions_follow_the_households_language():
    assert missing_questions(intake("es_missing")) == (
        "¿Cuándo puede recoger?",
        "¿Hay algo que no puedan comer en su hogar?",
    )


@pytest.mark.parametrize(
    "lang, expected",
    [
        (Language.EN, "Your household's fresh produce share: 12 lb a week."),
        (Language.ES, "La porción de frutas y verduras frescas de su hogar: 12 lb por semana."),
    ],
)
def test_fair_share_wording_uses_only_the_given_number(lang, expected):
    assert fair_share_wording(12, lang) == expected


# --- 3. Only committed produce is reported -----------------------------------------------


def facts(*portions, **changes):
    base = dict(
        food_bank="Rural Food Bank",
        window_start=time(18, 0),
        window_end=time(20, 0),
        code="K7Q2",
        portions=portions,
    )
    base.update(changes)
    return PickupFacts(**base)


COMMITTED = (AgreementStatus.COMMITTED, AgreementStatus.MOVING, AgreementStatus.AT_FOOD_BANK)
NOT_COMMITTED = tuple(s for s in AgreementStatus if s not in COMMITTED)


def test_statuses_cover_the_draft_agreement_lifecycle():
    assert {s.value for s in NOT_COMMITTED} >= {"offered", "negotiating", "held", "disagreement", "unclaimed"}


@pytest.mark.parametrize("status", NOT_COMMITTED)
def test_produce_still_being_negotiated_is_never_reported(status):
    f = facts(ProducePortion("romaine", 2, status), ProducePortion("apples", 5, AgreementStatus.COMMITTED))
    assert [p.item for p in committed_portions(f.portions)] == ["apples"]
    text = pickup_wording(f, Language.EN)
    assert "romaine" not in text and "apples" in text


def test_nothing_committed_means_the_waiting_list_wording():
    f = facts(ProducePortion("romaine", 2, AgreementStatus.HELD), ProducePortion("apples", 5, AgreementStatus.NEGOTIATING))
    text = pickup_wording(f, Language.EN)
    assert text == "You are on the list. We will let you know when produce is ready at a food bank you chose."
    assert "Rural Food Bank" not in text and "K7Q2" not in text
    assert pickup_wording(f, Language.ES) == (
        "Ya está en la lista. Le avisaremos cuando haya productos listos en un banco de alimentos que eligió."
    )


def test_unknown_status_is_rejected():
    with pytest.raises(ValueError):
        ProducePortion("apples", 5, "maybe")


def test_english_pickup_wording_uses_only_given_facts():
    f = facts(ProducePortion("apples", 5, AgreementStatus.AT_FOOD_BANK), ProducePortion("potatoes", 3, AgreementStatus.COMMITTED))
    assert pickup_wording(f, Language.EN) == (
        "Ready for pickup at Rural Food Bank, 6 to 8 pm: 5 lb apples and 3 lb potatoes. "
        "Your code is K7Q2. Please wash produce before eating."
    )


def test_spanish_pickup_wording_uses_only_given_facts():
    f = facts(ProducePortion("manzanas", 5, AgreementStatus.COMMITTED), ProducePortion("papas", 3, AgreementStatus.COMMITTED))
    assert pickup_wording(f, Language.ES) == (
        "Puede recoger en Rural Food Bank, de 6 a 8 p. m.: 5 lb de manzanas y 3 lb de papas. "
        "Su código es K7Q2. Por favor lave los productos antes de comerlos."
    )


def test_voice_line_reads_the_code_twice():
    f = facts(ProducePortion("apples", 5, AgreementStatus.COMMITTED))
    text = pickup_wording(f, Language.EN, voice=True)
    assert text.count("K 7 Q 2") == 2


def test_balance_appears_only_when_both_numbers_are_given():
    f = facts(ProducePortion("apples", 8, AgreementStatus.COMMITTED), received_lb=8, fair_share_lb=12)
    assert "This week: 8 of 12 lb received." in pickup_wording(f, Language.EN)
    assert "Esta semana: 8 de 12 lb recibidas." in pickup_wording(f, Language.ES)
    assert "This week" not in pickup_wording(facts(ProducePortion("apples", 8, AgreementStatus.COMMITTED), received_lb=8), Language.EN)


def test_pickup_wording_has_no_number_the_facts_lack():
    f = facts(ProducePortion("apples", 2.5, AgreementStatus.COMMITTED), window_start=time(17, 30), window_end=time(19, 0))
    text = pickup_wording(f, Language.EN)
    assert "2.5 lb apples" in text and "5:30 to 7 pm" in text
    assert numbers_in(text) <= {"2", "5", "30", "7"}


# --- 4. Claude adapter (no network; a fake client stands in) -----------------------------


def test_extraction_schema_is_strict_compatible():
    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(EXTRACTION_SCHEMA)
    assert set(EXTRACTION_SCHEMA["properties"]) == {
        "household_size", "pickup_windows", "limited_fridge", "neighborhood", "cant_eat", "snap"
    }


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def fake_response(text, stop_reason="end_turn"):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
    )


def test_claude_extractor_sends_a_small_structured_request_and_parses_it():
    fx = load("en_complete")
    client = FakeClient(fake_response(json.dumps(fx["extractor_output"])))
    transcript = Transcript.from_dict(fx["transcript"])
    draft = intake_transcript(transcript, ClaudeExtractor(client=client, cap=SpendingCap(1.0)))
    assert draft.to_dict() == fx["expected_draft"]

    (call,) = client.calls
    assert call["model"] == "claude-sonnet-5-5"
    assert call["max_tokens"] <= 1024
    assert call["output_config"]["effort"] == "low"
    assert call["output_config"]["format"] == {"type": "json_schema", "schema": EXTRACTION_SCHEMA}
    user_text = call["messages"][0]["content"]
    assert "<transcript>" in user_text and "Household: We're a family of 4." in user_text


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_claude_extractor_raises_instead_of_guessing(stop_reason):
    client = FakeClient(fake_response("{", stop_reason=stop_reason))
    with pytest.raises(ExtractionError):
        ClaudeExtractor(client=client, cap=SpendingCap(1.0))(Transcript.from_dict(load("en_complete")["transcript"]))


def test_claude_extractor_spending_cap_comes_from_one_setting_and_defaults_to_zero(monkeypatch):
    fx = load("en_complete")
    transcript = Transcript.from_dict(fx["transcript"])
    monkeypatch.delenv("CLAUDE_RUN_CAP_USD", raising=False)
    client = FakeClient(fake_response(json.dumps(fx["extractor_output"])))
    with pytest.raises(ExtractionError, match="spending cap"):
        ClaudeExtractor(client=client)(transcript)
    assert client.calls == []  # no call was made

    monkeypatch.setenv("CLAUDE_RUN_CAP_USD", "0.50")
    extractor = ClaudeExtractor(client=client)
    assert extractor.cap.limit_usd == 0.5
    extractor(transcript)
    assert len(client.calls) == 1
    assert len(extractor.cap.entries) == 1 and extractor.cap.reserved_usd == 0


def test_claude_extractor_cap_is_shared_and_blocks_when_spent():
    fx = load("en_complete")
    transcript = Transcript.from_dict(fx["transcript"])
    client = FakeClient(fake_response(json.dumps(fx["extractor_output"])))
    cap = SpendingCap(0.0001)  # below one call's worst case
    with pytest.raises(ExtractionError):
        ClaudeExtractor(client=client, cap=cap)(transcript)
    assert client.calls == []


def test_the_extractors_model_comes_from_the_llm_config():
    from harvestnet_agents.llm_negotiators import load_llm_config

    config = load_llm_config()
    extractor = ClaudeExtractor(client=object(), cap=SpendingCap(0))
    assert (extractor.model, extractor.effort, extractor.max_tokens) == (
        config.front_desk_model, config.front_desk_effort, config.front_desk_max_tokens)
    assert ClaudeExtractor(client=object(), cap=SpendingCap(0), model="claude-opus-5-5").model == "claude-opus-5-5"
