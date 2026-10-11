# ElevenLabs voice line (ticket #4)

The household voice line, set up in the ElevenLabs dashboard. No code. It asks the household's
questions in English or Spanish, reads the answers back, asks for consent, and then speaks what
the HarvestNet API returns: the fair share, nearby food banks, and the pickup code.

**The API endpoints are placeholders.** Ticket #1 (contract day) hasn't agreed the voice-intake
endpoint yet. Every URL in `tools.json` starts with `https://API_BASE_URL/`. When #1 lands, replace
the address and paths, and check the field names against the agreed contract.

All example numbers, names, and codes in these files are synthetic.

## Files

- `agent-prompt.md`: the first message (English and Spanish), the system prompt, and Spanish fixed lines.
- `tools.json`: the three server tools (webhooks), with placeholder URLs and example responses.

## The call, step by step

| Step | What happens | Tool |
|---|---|---|
| 1 | The agent asks household size, pickup times, fridge space, neighborhood, can't-eat items, and the optional CalFresh question | none |
| 2 | It sends the answers. The API returns a read-back and the consent question. **Nothing is saved.** | `prepare_request` |
| 3 | The agent reads it back and asks for consent. If the answer is no, the call ends with nothing saved. | none |
| 4 | On a clear yes, the request is saved. The API returns the fair share and nearby food banks. | `submit_request` |
| 5 | The household chooses food banks. The API returns a pickup code, which the agent reads out **twice**. | `choose_food_banks` |

The agent speaks the API's `speak` text as given, so every number comes from the API, never from
the voice model (ADR 0002).

## Dashboard setup

1. **Create an agent:** ElevenLabs → Agents → New agent → Blank template. Name it "HarvestNet voice line".
2. **Language:** set English as the default. Add Spanish as an additional language and paste the
   Spanish first message as its override. Turn on the **language detection** system tool, so the
   agent switches to Spanish when the caller speaks it.
3. **First message and system prompt:** paste them from `agent-prompt.md`.
4. **Voice:** pick a voice that handles both English and Spanish, with a multilingual model.
5. **Tools:** add three **webhook** tools, one for each entry in `tools.json`. Copy the name,
   description, method, URL, and parameters. For `conversation_id`, choose the dynamic variable
   `system__conversation_id`, so the model doesn't fill it in. Leave the URLs as placeholders
   for now.
6. **Privacy:** don't send the caller's phone number to the API. Texts are opt-in through the
   web page and n8n (ticket #18).

Check every dashboard label against the current ElevenLabs docs, because menu names change.

## Testing before the API exists

Until #1 is done, the tools have nowhere real to call. Two options:
- **Quick check:** point the three URLs at a mock that returns the `example_response` from
  `tools.json` (a Beeceptor endpoint works), then call the agent from the dashboard's test widget.
- **Prompt-only check:** remove the tools for now, and check that the questions, the skippable
  CalFresh question, and the language switch all work.

## Done-when checklist (from ticket #4)

- [ ] The script covers household size, pickup times, fridge space, neighborhood, and an optional, skippable SNAP question.
- [ ] Read-back and consent happen before submitting.
- [ ] Transcripts reach the API's voice-intake endpoint, and the example response is spoken back correctly. *(Blocked by the placeholder endpoint until #1.)*
- [ ] The pickup code is read out twice.
- [ ] Works in both English and Spanish.
