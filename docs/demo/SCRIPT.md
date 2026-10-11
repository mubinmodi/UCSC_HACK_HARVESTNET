# HarvestNet demo script (about 3 minutes)

Speaker notes for the demo in `docs/MVP_DESIGN.md` section 17 (Proposed), ticket #6. The slides are
`docs/demo/slides.html`. Open the file in a browser and use the arrow keys. Press T for a dark
theme if the room is dark.

**Total: 2:50.** Seven moments, plus a short opening and close. Each moment says what it proves.
The level tags match the slides.

**Honesty rules (ADR 0002).** All demo data is synthetic. Say "synthetic" or "recorded" when you show
a number. Never say a number that isn't on a screen or a slide. The LLM negotiators were not run
for the results on the slides, so say so if asked.

## Before you start

- Slides open on slide 1. The household page, the donor page, the food bank dashboards, and the
  results strip open in tabs, in that order.
- The phone for the voice line is ready, with the call in Spanish.
- If anything is down, use the fallbacks in `docs/demo/REHEARSAL.md` (added with ticket #25), and
  say "this is a recorded replay" when you use one.

## Opening (0:00 to 0:15) · slides 1 to 3

> Good produce goes to waste every day, while families nearby could use it. HarvestNet gives every
> donor and every food bank its own AI agent. They negotiate how each batch is shared. Nobody sits in
> the middle and decides. Every organization keeps its own keys, and the food still moves.

## 1. The household call (0:15 to 0:40) · slide 6 · Level 1

Show: the voice line, in Spanish.

> A parent calls in Spanish. Family of four, near Watsonville, can pick up after 6 pm, small fridge,
> gets CalFresh. The assistant reads it all back and asks before it saves anything. Their weekly fair
> share is 12 pounds. They choose the rural and the city food banks.

Proves: people can use it with no app and no account. The number comes from the fair-share
calculator, not from the AI.

## 2. The farmers market reports surplus (0:40 to 0:55) · slide 6 · Level 1

Show: the donor page.

> At closing time, a farmers market has 300 pounds of apples, 200 of romaine, and 400 of potatoes. It
> must be gone by 3 pm, and the market can drop some off.

Proves: any donor can join, including the farmers markets that SNAP shoppers use.

## 3. The agents negotiate (0:55 to 1:25) · slides 7 and 8 · Level 3

Show: the lot's version history on the donor page or a food bank dashboard.

> The food banks bid item by item. The city wants the romaine and has a refrigerated truck. The rural
> food bank has no truck today, so it asks the market to drop off. Every change is a new version, with
> a reason. The advocate speaks for the households furthest below their fair share. It can propose,
> but it can't vote.

If it runs long, skip to the finished version history. Don't wait.

Proves: real disagreement and real negotiation, with no central decider.

## 4. A live approval (1:25 to 1:40) · slide 7 · Level 3

Show: an n8n approval message or the dashboard's Accept button.

> Each manager approves the exact version. If anyone changes the terms, old approvals stop counting.
> Nothing is ever committed automatically.

Proves: humans approve their own commitments.

## 5. The cooler fails (1:40 to 2:10) · slide 9 · Level 2

Show: flip the Beeceptor cooler switch, then the city dashboard.

> Now the city's walk-in cooler fails. Its agent checks the produce profiles: romaine must stay cold,
> apples are fine. It searches the Directory for food banks with cold space and writes a reason card
> for each one. Rural has too little cold space, and its hours don't fit. Eastside is chosen. It's a new version, so
> both managers approve again.

Proves: discovery by capability, a response to a failure, and a reason for every choice.

## 6. The household gets a text (2:10 to 2:25) · slide 10 · Evidence

Show: the household page or the text message.

> The parent gets a text in Spanish: which food bank, what time, what's in it, and their code. If
> they can't make it, one reply passes it to the next family.

Proves: the fair share in action. A household counts as reached only when it confirms pickup.

## 7. The results strip (2:25 to 2:45) · slides 11 and 12 · Evidence

Show: the results strip.

> We compare against first-come-first-served on the same inputs. These are synthetic scenarios.
> On the normal afternoon, negotiation reached 4 households instead of 3. In one scenario it does
> worse on our fairness measure, and we show that too. We report whatever the numbers show.
> Produce committed to a food bank that can store it and hand it out in time isn't counted as
> wasted. On the normal afternoon no method wastes any. Waste shows up when storage runs out or
> the cooler fails.

Read the numbers from the screen. Don't round them up. The strip splits every pound once:
collected by households, committed to food banks, or wasted (no pathway at the scenario end).

## What changed in the waste measure (if asked)

Before October 11, 2026, "produce wasted" counted every pound the scripted households didn't
collect, so even a good run showed most of the lot as wasted. The team lead decided that produce
committed to a food bank that can store it and hand it out before it stops being usable is not
wasted. The old number is still in the results as "not collected by the scripted households".

## Close (2:45 to 2:50) · slide 16

> Every organization keeps its own keys. The food still moves. Thank you.

## Backup slides for questions

- Slide 4: the fair share and SNAP.
- Slide 13: when the system stops, keeps a disagreement, or asks a human.
- Slide 14: architecture and sponsors, and the fallback for each.
- Slide 15: how each level is met.

## What not to say

- "The AI decides who gets food." It doesn't. Agents negotiate, and humans approve.
- "We fed X people." We count households that confirmed a pickup.
- Any number that isn't on a screen. Cost figures in the design are estimates.
- "The LLM agents beat the baseline." They were not run for these results.
- "Nothing gets wasted." Wasted means produce with no pathway at the end of a synthetic
  scenario. It is not observed spoilage, and produce at a food bank still has to be handed out.
