# HarvestNet MVP: independent work lanes

**The rule:** after ticket 01 (contract day), nobody waits on anybody. Each lane builds and tests against the four agreed contracts and the **real API skeleton**, never against a teammate's unfinished work. Integration happens only in the **join** tickets (20–24), and whoever finishes early keeps working down their own lane.

**Why it works:** the real API is live from day one, returning example data, and Lane A swaps in real logic behind the same address. Stand-in agents and stand-in calculators follow the same interfaces as the real ones. Beeceptor stands in only for the outside organizations' own systems, which we don't have.

| Lane | Owner | Tickets (each waits only on 01 or the same lane) |
|---|---|---|
| **Frontend** | Frontend person | 02 household page · 03 donor page and food bank dashboard · 04 ElevenLabs voice agent · 05 results strip · 06 wording, translations, demo slides |
| **A: Core** | Full-stack A | 07 harness and records → 08 calculators, matching, versions, stop rules → 09 real API logic, 10 baselines and evaluation |
| **B: Agents** | Full-stack B | 11 rules-based negotiators → 13 LLM negotiators · 12 produce profiles and fair-share table → 15 cooler-failure logic · 14 front-desk assistant |
| **C: Platform** | Full-stack C | 16 Beeceptor systems and cooler switch · 17 AGNTCY with stand-in agents · 18 n8n approvals and texts · 19 deployment hardening and fallbacks |

**Shared start:** 01, contract day plus the real API skeleton on AWS (everyone, with C deploying).

**Joins** (each has one owner and starts once its inputs are done):

| Join | Owner | Waits on |
|---|---|---|
| 20 real agents in the harness | B | 08, 11, 12 |
| 21 agents over AGNTCY | C | 17, 20 |
| 22 live households, approvals, and voice | A | 09, 14, 18 |
| 23 cooler failure end to end | B | 15, 16, 21, 22 |
| 24 evaluation on the live system | A | 10, 13, 20 |
| 25 demo rehearsal | Frontend person leads | 06, 23, 24 |

**Frontend lane note:** every frontend ticket is screens, wording, no-code voice setup, or slides, against a live API. No backend work is needed.

**If you finish your lane early:** help the join owner on the path to the demo (20 → 21 → 23), or rehearse the demo.
