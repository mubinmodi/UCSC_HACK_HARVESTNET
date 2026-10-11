# ElevenLabs voice line (ticket #4)

The household voice line, set up in the ElevenLabs dashboard. No code. It asks the household's
questions in English or Spanish, reads the answers back, asks for consent, saves the request,
helps the household choose food banks, and reads out the request code twice. Every number it
says comes from a HarvestNet API response, never from the voice model (ADR 0002).

The tools are the agreed public API operations (`docs/contracts/public-api.md`). Their method,
path, request fields, and response fields match the contract examples in
`docs/contracts/examples/public-api/`. `tests/test_elevenlabs_tools.py` checks this, so run the
root tests (`uv run --with pytest pytest -q`) after changing either side.

All example values in these files (codes such as `K7P4`, ids, pounds) are synthetic.

## Files

- `agent-prompt.md`: the first message (English and Spanish), the system prompt, and the Spanish fixed lines.
- `sync_agent.py`: creates or updates the agent and tools through the API.
- `agent.json`: the agent and tool ids, written by the script (not present until the first run).
- `tools.json`: the five server tools (webhooks), with the base address, each tool's method and path,
  its parameters, and the response fields the prompt reads.

## The call, step by step

| Step | What happens | Tool (operation) |
|---|---|---|
| 1 | The agent asks household size, pickup times, fridge space, neighborhood, can't-eat items, and the optional CalFresh question. | none |
| 2 | It sends the call transcript. The API returns `read_back`, `missing_questions`, `complete`, `draft_request`, `fair_share_lb`, `next`, and, once every answer is in, `consent_question`. **Nothing is saved.** The agent says `read_back` and asks for anything missing, then sends the call again. | `voice_intake` (`POST /voice-intake`) |
| 3 | The agent asks `consent_question` word for word. If the answer is no, the call ends with nothing saved. | none |
| 4 | On a clear yes, it saves the `draft_request` fields with `channel: "voice"` and `consent: true`. No phone number. The API returns `request_code` and `fair_share_lb`, and the agent says the weekly share. | `create_request` (`POST /requests`) |
| 5 | It lists nearby food banks with pickup hours and only **committed** produce. | `list_food_banks` (`GET /food-banks?neighborhood=&request_code=`) |
| 6 | The household chooses one or more food banks. | `choose_food_banks` (`PUT /requests/{request_code}/food-banks`) |
| 7 | The agent reads the `request_code` out **twice**, one character at a time. The household shows it at pickup; there's no separate pickup code (contracts README, decision 11). | none |
| Any time | A caller who already has a code can hear this week's balance and committed pickups. | `get_request` (`GET /requests/{request_code}`) |

The voice line collects **no email address or phone number**. It says the food
bank will tell the household when produce is ready, and that they can call back
with their code. Pickup emails are opt-in on the web page only (`docs/MVP_DESIGN.md` §12).

## Which API it calls

- **Now:** `base_url` in `tools.json` is the deployed API skeleton. It answers every route with the
  contract example, so the dashboard's test widget can run the whole call, but every caller hears
  the same synthetic answers (for example, the Spanish read-back from the example and the code `K7P4`).
- **Later:** swap `base_url` for the real API (Lane A, `harvestnet_core.server`). The paths stay the same.
- **`POST /voice-intake` returns 503 on the real API until a transcript-reading model is
  configured.** The real server starts without the front desk's extractor (the Claude call in
  `agents/src/harvestnet_agents/front_desk.py`) and answers
  `{"error": {"code": "voice_unavailable", ...}}`. The agent then says its "can't reach the system"
  line and points to the web page. Wiring the extractor into the deployed server is still to do.

## The transcript: a known limitation

The front desk checks every answer against the **household's own words** in the transcript, and
drops any value the household didn't say (ADR 0002). That check is only as good as the transcript.

- ElevenLabs does have the real call history: the `system__conversation_history` dynamic variable.
  But it's in ElevenLabs' own format (`{"x-elevenlabs-history": true, "entries": [{"role": "user" | "agent" | "tool", "message": ...}]}`),
  not the contract's `transcript: {language, turns: [{speaker, text}]}`. Sending it as-is would break
  the agreed contract, and converting it needs a change in the API, which is out of scope here.
- So for now **the voice model rebuilds `turns` itself**, and the prompt tells it to copy the
  household's words exactly. This weakens the evidence check: if the model paraphrases or invents a
  household line, the front desk can't tell, because it only ever sees the model's copy.
- **Fix later (needs a contract change):** have `voice_intake` also accept
  `system__conversation_history` (or fetch the transcript from ElevenLabs by `call_id`) and build
  `turns` on the server, with `user` as `household` and `agent` as `assistant`. Then the evidence
  check runs on the real speech-to-text, not the model's copy. Raise it on ticket #1 first.

A smaller version of the same issue: `create_request` relies on the model copying `draft_request`
unchanged. The API re-checks every field, and its response repeats `household_size` and
`fair_share_lb`, but it can't tell if the model changed a valid value.

## How it's set up

The agent and its tools are created through the ElevenLabs API by one script, so the setup can be repeated:

```bash
ELEVENLABS_API_KEY=... python3 integrations/elevenlabs/sync_agent.py          # create or update
python3 integrations/elevenlabs/sync_agent.py --dry-run                       # print what would be sent (no key, no network)
python3 integrations/elevenlabs/sync_agent.py --simulate "Hi, we are four people near Watsonville"
```

- **Needs an API key with Agents (ConvAI) read and write access.** `convai_read` and `convai_write` are the permission names the API reports. The restricted key in `deploy/aws/.env` doesn't have them yet (the script's first call returned HTTP 401, "missing the permission convai_read"), so the agent has not been created. Make a key with those two permissions (Voices read helps for picking a voice), then run the script.
- The script reads `tools.json` and `agent-prompt.md`, finds the five tools by name (`harvestnet_<operation>`) and the agent by name ("HarvestNet front desk"), and updates them if they exist, otherwise creates them. It then writes the ids to `agent.json` (no secrets). Commit that file.
- **Tools** call the live core API (`live_base_url` in `tools.json`, `https://18-217-110-223.sslip.io/api`). `--skeleton` points them at the example-data skeleton instead.
- **Agent settings** (constants at the top of the script): LLM `claude-sonnet-5-5`, temperature 0.2, English default with a Spanish preset (Spanish first message), the language detection and end call system tools, TTS model `eleven_flash_v2_5` (multilingual), the API docs' default voice id, 15 minute call limit. A request-code placeholder is set as a dynamic variable until `create_request` returns the real code.
- **Privacy:** no phone number or caller id is mapped to any tool, and the prompt's "never ask for" list is unchanged. Check the recording and transcript retention settings in the dashboard (Agent, Advanced, Privacy). The script leaves them at the account default.
- **Live `/voice-intake`:** on the deployed server it currently returns HTTP 503 `voice_unavailable` ("voice extraction is not configured"), so a full call can only get as far as the can't-reach-the-system line until the server is given a transcript-reading model. Checked October 11, 2026.
- Some fields were written from the API reference and not yet accepted by a live call (the Spanish preset's `language`, the `end_call` tool shape, and the voice id). If the first run answers 422, fix the named field in `sync_agent.py`.
- `tests/test_elevenlabs_sync.py` checks the payloads offline.

## Dashboard setup

*(The script above does this for you; use these steps only to set it up by hand.)*

1. **Create an agent:** ElevenLabs → Agents → New agent → Blank template. Name it "HarvestNet voice line".
2. **Language:** set English as the default. Add Spanish as an additional language and paste the
   Spanish first message as its override. Turn on the **language detection** system tool, so the
   agent switches to Spanish when the caller speaks it.
3. **First message and system prompt:** paste them from `agent-prompt.md`.
4. **Voice:** pick a voice that handles both English and Spanish, with a multilingual model.
5. **Tools:** add five **webhook** tools, one for each entry in `tools.json`. For each one, set
   the URL to `base_url` plus `path`, and copy the name, description, method, and parameters.
   - `"source": "dynamic_variable"` means choose that dynamic variable as the value, so the model
     doesn't fill it in (`call_id` is `system__conversation_id`).
   - `"source": "constant"` means a constant value: `channel` is `voice`, and `consent` is the
     boolean `true` (not the string `"true"`).
   - `"assign_dynamic_variables"` on `create_request` saves the response's `request_code` into a
     dynamic variable named `request_code`, which `list_food_banks` and `choose_food_banks` then
     use. If the dashboard can't do that, set those parameters to be filled by the model from the
     `create_request` response.
   - Add `phone` to no tool, and don't map `system__caller_id` anywhere.
6. **Privacy:** don't send the caller's phone number to the API (see step 5).

Check every dashboard label against the current ElevenLabs docs, because menu names change.

## Testing

- **Contract check (no network):** `uv run --with pytest pytest -q tests/test_elevenlabs_tools.py`.
- **Call test against the skeleton:** with `base_url` as it is, call the agent from the dashboard's
  test widget. Each tool gets the contract's example back. Check that the agent says the example's
  `read_back` word for word, asks its `missing_questions`, only calls `create_request` after a clear
  yes, and reads `K7P4` twice.
- **Spanish:** repeat the call in Spanish and check that the agent switches language and keeps the
  household's words in Spanish in `turns`.

## Done-when checklist (from ticket #4)

- [x] The script covers household size, pickup times, fridge space, neighborhood, and an optional, skippable SNAP question. *(In `agent-prompt.md`.)*
- [x] Read-back and consent happen before submitting. *(In the prompt; `create_request` only after a clear yes.)*
- [ ] Transcripts reach the API's voice-intake endpoint, and the example response is spoken back correctly. *(Tools match the contract; still needs the agent built in the dashboard and a test call. The real API returns 503 until the extractor is configured.)*
- [ ] The pickup code is read out twice. *(In the prompt as the request code; needs a test call.)*
- [ ] Works in both English and Spanish. *(Needs a test call in each language.)*
