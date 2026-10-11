# Mission: HarvestNet MVP

## Why
Win the Cisco "When AI Agents Disagree" Level 3 track with HarvestNet, and lead the team that builds it. That means explaining the design to judges in three minutes, holding up under their hardest questions, and keeping teammates' work true to the design rules.

## Success looks like
- Give the 30-second pitch from memory: problem, who negotiates, fair share, why there's no central decider.
- Answer the hard judge questions without notes: "why not one central optimizer?", "isn't the fair-share table a central decider?", "what if they never agree?", "where's Level 2?".
- Walk through all five MVP workflows and name which agent decides at each step.
- Split the build into the order in `docs/MVP_DESIGN.md` section 18, and catch a teammate's change that breaks a rule (a central decider, an invented number, an auto-commit).

## Constraints
- Already comfortable with agent systems and LangGraph, so skip agent basics.
- Hackathon timing: short lessons, one win each.
- Plain, simple English.
- The design source of truth is `docs/MVP_DESIGN.md`, `CONTEXT.md`, and `docs/adr/`. If a lesson and those disagree, they win.

## Out of scope
- Agent fundamentals, prompt engineering basics.
- Deferred features (rescue fund, drivers, cooked meals, shelters, cross-docks), except to say why they were cut.
- Writing application code. That needs a separate go-ahead.
