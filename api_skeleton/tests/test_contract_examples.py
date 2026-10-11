"""Every example JSON parses and matches its contract doc (ticket #1).

These read only files in docs/contracts/ and Lane B's packaged data. No network.
"""

import json
import re

import pytest

from conftest import API_EXAMPLES, CONTRACTS, EXAMPLES, REPO, api_example_files, load

AGENT_DATA = REPO / "agents" / "src" / "harvestnet_agents" / "data"
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
OFFSET = re.compile(r"(Z|[+-]\d{2}:\d{2})$")


def walk(value, path=""):
    """Yield (path, key, value) for every dict entry, recursively."""
    if isinstance(value, dict):
        for k, v in value.items():
            yield path, k, v
            yield from walk(v, f"{path}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from walk(v, f"{path}[{i}]")


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from strings(v)


ALL_EXAMPLE_FILES = sorted(EXAMPLES.rglob("*.json"))
DOC_FILES = ["README.md", "scenario-fixtures.md", "agent-moves.md", "calculators.md", "public-api.md"]


def doc(name):
    return (CONTRACTS / name).read_text(encoding="utf-8")


# --- Every example file -------------------------------------------------------------------


def test_there_are_examples_for_all_four_contracts():
    names = {p.name for p in EXAMPLES.glob("*.json")}
    assert {"scenario-normal-afternoon.json", "agent-moves.json", "calculators.json"} <= names
    assert len(api_example_files()) >= 19


@pytest.mark.parametrize("path", ALL_EXAMPLE_FILES, ids=lambda p: str(p.relative_to(EXAMPLES)))
def test_example_parses_and_is_labeled_synthetic(path):
    data = load(path)
    assert data["synthetic"] is True


@pytest.mark.parametrize("path", ALL_EXAMPLE_FILES, ids=lambda p: str(p.relative_to(EXAMPLES)))
def test_every_timestamp_carries_an_offset(path):
    for s in strings(load(path)):
        if TIMESTAMP.match(s):
            assert OFFSET.search(s), f"{s!r} has no UTC offset"


@pytest.mark.parametrize("name", DOC_FILES)
def test_every_contract_doc_is_marked_agreed(name):
    assert "**Status: Agreed (team, October 11, 2026; recorded by Claude at the leader's direction).**" in doc(name)


@pytest.mark.parametrize("name", DOC_FILES)
def test_links_in_contract_docs_point_at_real_files(name):
    for target in re.findall(r"\]\(([^)#]+)\)", doc(name)):
        if target.startswith("http"):
            continue
        assert (CONTRACTS / target).resolve().exists(), target


def test_every_example_file_is_named_in_a_contract_doc():
    text = "".join(doc(n) for n in DOC_FILES)
    for path in EXAMPLES.glob("*.json"):
        assert f"examples/{path.name}" in text
    for path in api_example_files():
        assert f"examples/public-api/{path.name}" in doc("public-api.md")


# --- Scenario fixture ---------------------------------------------------------------------


@pytest.fixture(scope="module")
def scenario():
    return load(EXAMPLES / "scenario-normal-afternoon.json")


def test_scenario_has_the_ticket_1_parts(scenario):
    assert scenario["kind"] == "scenario"
    roles = [o["role"] for o in scenario["organizations"]]
    assert roles.count("food_bank") == 3 and roles.count("donor") >= 1 and "advocate" in roles
    assert scenario["requests"] and scenario["surplus_offers"]
    assert [f["kind"] for f in scenario["faults"]] == ["cooler_failure"]
    assert "expected" not in scenario  # ADR 0005: no prescribed winner


def test_scenario_top_level_fields_are_documented(scenario):
    text = doc("scenario-fixtures.md")
    for key in scenario:
        assert f"`{key}`" in text, key
    for check in scenario["rule_checks"]:
        assert f"`{check}`" in text, check


def test_scenario_references_only_its_own_organizations(scenario):
    ids = {o["organization_id"] for o in scenario["organizations"]}
    banks = {b["organization_id"] for b in scenario["food_banks"]}
    assert set(scenario["turn_order"]) == ids
    for r in scenario["requests"]:
        assert set(r["chosen_food_bank_ids"]) <= banks
    for offer in scenario["surplus_offers"]:
        assert offer["donor_id"] in ids
    for d in scenario["donors"]:
        assert set(d["travel_minutes"]) == banks
        assert set(d["drop_off"]["food_bank_ids"]) <= banks
    for f in scenario["faults"]:
        assert f["food_bank_id"] in banks and f["synthetic"] is True
    assert {h["organization_id"] for h in scenario["humans"]} <= ids


def test_scenario_uses_real_profiles_and_the_fair_share_table(scenario):
    profiles = load(AGENT_DATA / "produce_profiles.json")
    table = load(AGENT_DATA / "fair_share_table.json")
    known = {p["id"]: p for p in profiles["profiles"]}
    assert scenario["policies"]["produce_profile_set_version"] == profiles["version"]
    assert scenario["policies"]["fair_share_table_version"] == table["version"]
    for offer in scenario["surplus_offers"]:
        for item in offer["items"]:
            assert item["produce_id"] in known
            units = known[item["produce_id"]]["units"]["value"]
            assert item["unit"] in units
            if units[item["unit"]] is None:
                assert item["lb_per_unit"], f"{item['produce_id']} in {item['unit']} needs a stated pack weight"


def test_scenario_requests_hold_no_identity(scenario):
    for r in scenario["requests"]:
        assert not {"name", "address", "phone", "email", "income"} & set(r)
        assert r["consent"] is True
        assert r["snap"] in {"yes", "no", "not_said"}


# --- Agent moves --------------------------------------------------------------------------

MOVE_KINDS = {"accept", "counter", "reject", "request_hold", "ask_human", "pass"}
AMENDMENT_KINDS = {"set_pounds", "shift_pounds", "set_transport"}


@pytest.fixture(scope="module")
def move_pairs():
    return load(EXAMPLES / "agent-moves.json")["pairs"]


def test_at_least_three_move_pairs_are_documented(move_pairs):
    assert len(move_pairs) >= 3
    text = doc("agent-moves.md")
    for pair in move_pairs:
        assert f"`{pair['name']}`" in text


def test_every_move_kind_is_documented():
    text = doc("agent-moves.md")
    for kind in MOVE_KINDS | AMENDMENT_KINDS:
        assert f"`{kind}`" in text


@pytest.mark.parametrize("index", range(4))
def test_move_follows_the_rules(move_pairs, index):
    pair = move_pairs[index]
    inp, out = pair["input"], pair["output"]
    assert set(inp) == {"role", "draft", "facts", "turn"}
    assert out["organization_id"] == inp["turn"]["organization_id"]
    assert out["version"] == inp["draft"]["version"]
    assert out["action"] in MOVE_KINDS
    assert out["reason"].strip()
    assert (out["action"] == "counter") == ("amendment" in out)
    if "amendment" in out:
        assert out["amendment"]["kind"] in AMENDMENT_KINDS
    assert (out["action"] == "request_hold") == bool(out.get("holds"))
    if out.get("holds"):
        assert out["resource_owner"] == out["organization_id"]
    if inp["role"] == "advocate":
        assert out["action"] in {"counter", "pass"}


def test_move_pairs_cover_counter_and_ask_human(move_pairs):
    actions = {p["output"]["action"] for p in move_pairs}
    roles = {p["input"]["role"] for p in move_pairs}
    assert {"counter", "ask_human", "request_hold"} <= actions
    assert roles == {"donor", "food_bank", "advocate"}


# --- Calculators --------------------------------------------------------------------------

TICKET_CALCULATORS = {"fair_share", "household_portions", "storage_at", "pickup_feasibility", "to_pounds", "fair_share_gap"}


@pytest.fixture(scope="module")
def calc_examples():
    return load(EXAMPLES / "calculators.json")["examples"]


@pytest.fixture(scope="module")
def table():
    t = load(AGENT_DATA / "fair_share_table.json")
    sizes = {int(k): v for k, v in t["pounds_by_household_size"].items()}

    def share(size):
        top = max(sizes)
        return sizes[size] if size <= top else sizes[top] + (size - top) * t["each_additional_person_lb"]

    share.version = t["version"]
    return share


def test_every_ticket_calculator_has_an_example(calc_examples):
    assert TICKET_CALCULATORS <= {e["calculator"] for e in calc_examples}


def test_every_calculator_in_the_examples_is_documented(calc_examples):
    text = doc("calculators.md")
    for e in calc_examples:
        assert f"`{e['calculator']}`" in text


def test_each_example_has_an_output_or_an_error(calc_examples):
    for e in calc_examples:
        assert ("output" in e) != ("error" in e), e["name"]


def test_fair_share_examples_match_the_table(calc_examples, table):
    for e in (e for e in calc_examples if e["calculator"] == "fair_share"):
        assert e["output"]["pounds"] == table(e["input"]["household_size"])
        assert e["output"]["table_version"] == table.version


def test_fair_share_gap_examples_add_up(calc_examples, table):
    for e in (e for e in calc_examples if e["calculator"] == "fair_share_gap"):
        shorts = [table(h["household_size"]) - h["received_lb"] for h in e["input"]["households"]]
        assert e["output"]["gap_lb"] == sum(s for s in shorts if s > 0)
        assert e["output"]["households_below"] == sum(1 for s in shorts if s > 0)


def test_household_portions_never_exceed_fair_share_and_conserve_pounds(calc_examples, table):
    portions_examples = [e for e in calc_examples if e["calculator"] == "household_portions"]
    assert portions_examples
    for e in portions_examples:
        households = {h["request_code"]: h for h in e["input"]["households"]}
        out = e["output"]
        assert sum(p["pounds"] for p in out["portions"]) + out["left_over_lb"] == e["input"]["pounds_available"]
        for p in out["portions"]:
            h = households[p["request_code"]]
            gap = max(0, table(h["household_size"]) - h["received_lb"])
            assert p["fair_share_lb"] == table(h["household_size"])
            assert 0 <= p["pounds"] <= gap
            assert p["still_below_lb"] == gap - p["pounds"]
        if out["left_over_lb"] > 0:
            assert all(p["still_below_lb"] == 0 for p in out["portions"])


# --- Public API ---------------------------------------------------------------------------

METHODS = {"GET", "POST", "PUT"}
GROUPS = {"system", "household", "donor", "food_bank", "voice", "approvals", "results"}


def documented_operations():
    rows = re.findall(r"^\| `(\w+)` \| (GET|POST|PUT) \| `([^`]+)` \|", doc("public-api.md"), re.MULTILINE)
    return {(op, method, path) for op, method, path in rows}


def test_operation_table_matches_example_files(api_examples):
    from_files = {(e["operation"], e["method"], e["path"]) for e in api_examples}
    assert documented_operations() == from_files


def test_every_ticket_group_has_operations(api_examples):
    assert {e["group"] for e in api_examples} == GROUPS


@pytest.mark.parametrize("path", api_example_files(), ids=lambda p: p.stem)
def test_api_example_shape(path):
    e = load(path)
    assert e["operation"] == path.stem
    assert e["method"] in METHODS and e["group"] in GROUPS and e["summary"]
    request, response = e["example"]["request"], e["example"]["response"]
    template = "^" + re.sub(r"\{\w+\}", r"[^/]+", e["path"]) + "$"
    assert re.match(template, request["path"]), (request["path"], e["path"])
    if e["method"] in {"POST", "PUT"}:
        assert isinstance(request["body"], dict)
    else:
        assert "body" not in request
    assert isinstance(response["status"], int)
    assert response["body"]["mode"] == "example" and response["body"]["synthetic"] is True


@pytest.mark.parametrize("path", api_example_files(), ids=lambda p: p.stem)
def test_api_responses_never_return_contact_details_or_a_name(path):
    body = load(path)["example"]["response"]["body"]
    keys = {k for _, k, _ in walk(body)}
    assert not {"phone", "email", "name_of_person", "address", "income"} & keys
    assert not any("@" in s for s in strings(body))


def test_contract_v0_2_households_give_an_optional_email_not_a_phone():
    """User decision, October 11, 2026: pickup messages go by email through Amazon SES."""
    create = load(API_EXAMPLES / "create_request.json")["example"]
    assert "phone" not in create["request"]["body"]
    assert create["request"]["body"]["email"].endswith("@example.invalid")
    assert create["response"]["body"]["emails"] is True and "texts" not in create["response"]["body"]
    health = load(API_EXAMPLES / "get_health.json")["example"]["response"]["body"]
    assert health["contract_version"] == "contract-v0.2"
    text = doc("public-api.md")
    assert "contract-v0.2" in text and "Optional `email`" in text and "Optional `phone`" not in text
    assert "contract-v0.2" in doc("README.md")


def test_food_bank_views_show_snap_only_as_counts(api_examples):
    for e in api_examples:
        if e["group"] == "food_bank":
            keys = {k for _, k, _ in walk(e["example"]["response"]["body"])}
            assert "snap" not in keys
            if e["operation"] != "confirm_pickup":
                assert "request_code" not in keys


def test_nothing_in_the_examples_is_committed_by_an_approval_alone(api_examples):
    record = next(e for e in api_examples if e["operation"] == "record_approval")
    body = record["example"]["response"]["body"]
    assert body["committed"] is False and body["awaiting_approval_from"]


def test_json_round_trips_without_nan():
    for path in ALL_EXAMPLE_FILES:
        json.dumps(load(path), allow_nan=False)
