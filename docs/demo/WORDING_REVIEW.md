# Wording review (ticket #6)

What ticket #6 changed in the household-facing wording, the choices it made, and what a native
Spanish speaker still needs to check. Claude wrote the Spanish. Nobody has checked it with native
speakers or with households yet.

## Choices made for consistency

| Choice | Where it applies | Why |
|---|---|---|
| Spanish uses **usted**, not tú | Household page, voice line, API sentences, texts | The voice line and the API's read-back already used usted. The page showed both on one screen. |
| Fair share in Spanish is **porción** ("su porción", "la porción de frutas y verduras frescas de su hogar") | Household page, voice line, API, results strip | The page said "parte justa" while the API said "porción". |
| Produce in Spanish household text is **frutas y verduras** where the page talks in general; "productos" stays in "lave los productos" | Household page, voice line | Plainer than "productos" on its own. |
| English household screens say **confirmed**, not "committed" | Household page | "Committed" is our internal word. The household only needs to know the produce is confirmed. |
| "Can't make it" passes the portion to **another family** (Spanish: **otra familia**) | Household page, API release message, n8n texts, cooler-change texts | The contract example and the user story say "another family". The cooler texts said "another household". |
| The household's code is **"your code"**, never "pickup code" | n8n texts | There is no separate pickup code (contracts README decision 11). |
| Spanish item lists say **"4 lb de manzanas"** | API pickup sentence, n8n texts, cooler texts | "4 lb manzanas" is not natural Spanish. |
| Spanish pickup sentence starts **"Puede recoger en …"** | API pickup sentence, cooler texts | Replaces "Listo para recoger en …", which doesn't agree with anything. |

## One source for Spanish produce names

`agents/src/harvestnet_agents/data/produce_profiles.json` now has `name_es` for each profile:
Manzanas, Lechuga romana, Papas, Tomates. `ProduceProfile.display_name(language)` returns it.
It is never machine-translated: an item without `name_es` keeps its English name on the API, and
the cooler-change texts refuse to guess one.

These use it:
- `GET /requests/{code}`: item names and the pickup sentence follow `?language=`, or the request's
  own language when the page sends none.
- `GET /food-banks`: produce confirmed at each food bank, in the household's language.
- Cooler-change texts (`household_change_notices`), when no name is passed in.

## What a native speaker should check

1. **Household page** (`frontend/household/src/i18n.ts`, the `es` block). Check the whole page
   for tone after the switch to usted. In particular: "Sobre su hogar", "Díganos qué le funciona",
   "Ya puede recoger", "Cedida a otra familia", "Conservar mi recogida", "Buscar novedades",
   "Esta cantidad es un ejemplo por ahora".
2. **API sentences** (`agents/src/harvestnet_agents/front_desk.py`, `_T[Language.ES]`). The
   read-back ("Esto es lo que tengo.", "No pueden comer: …"), the consent question, "Puede recoger
   en …", and times such as "de 6 a 8 p. m." and "después de las 6 p. m.".
3. **"prefiere no decir"** in the Spanish read-back. "prefiere no decirlo" may read better. It was
   left unchanged because the agreed contract example (`docs/contracts/examples/public-api/voice_intake.json`)
   shows it.
4. **Produce names** (`produce_profiles.json`, `name_es`). "Papas" (not "patatas") is the usual
   word in California. Check "Lechuga romana".
5. **Voice line** (`integrations/elevenlabs/agent-prompt.md`). The Spanish first message and the
   table of fixed lines. Spoken "libras" versus written "lb".
6. **Cooler-change texts** (`agents/src/harvestnet_agents/cooler_failure_flow.py`, `_NOTICE`).
   "Su recogida cambió", and the reply words "SÍ" and "NO PUEDO IR".
7. **n8n pickup text** (`harvestnet_platform/approvals.py`, `PICKUP_TEXT['es']`). Especially the
   Market Match tip. Also check that it describes Market Match correctly, and verify the
   participating markets before the tip is shown to anyone (design section 9, Workflow 3).
8. **Results strip** (`frontend/results-strip/src/App.tsx`). "Por orden de llegada",
   "Cobertura del banco peor atendido", "Negociadores con IA".
9. **Released message** (`harvestnet_core/api.py`, `RELEASED_MESSAGE` and `SAVED_MESSAGE`).

## Known gaps (not changed here)

- **Food bank names** come from the scenario fixtures in English ("Rural food bank") and appear
  inside Spanish sentences. Real food banks have proper names, so this only affects the demo.
- **n8n reply confirmations** (`household_reply` in `harvestnet_platform/approvals.py`: "thanks,
  see you …", "we couldn't find an open pickup …") are English only. The reply doesn't carry the
  household's language.
- **Times in n8n texts** are shown as the notice gives them. The sender should pass readable times.
- **Staff screens** (donor page, food bank dashboards, approval review pages) are English only.
  They are for staff, not households. Their wording was reviewed for plain English and left as is.
- **API error messages** are English only. The household page shows its own translated errors
  instead.
