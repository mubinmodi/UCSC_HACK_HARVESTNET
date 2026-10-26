# Committed produce is not counted as waste

October 11, 2026, decided by the user. "Produce wasted" first counted every pound the scenario's households didn't collect. Food banks serve other clients too, so even a good run showed most of a lot as wasted (869 of 900 lb, synthetic) and every method looked the same. That measured the scenario's size, not waste, and it contradicted design §8: surplus that a food bank can use still goes out rather than to waste.

## Decision

Each pound of a surplus lot is counted once, on one pathway: collected by a household, committed to a food bank that can store it and hand it out before it stops being usable, or wasted (no pathway). The produce profile's usable life and the food bank's held storage decide whether a commitment is viable (ADR 0003). A commitment that spoils before it could be handed out, such as cold produce left in a failed cooler, is still waste.

## Consequences

- Results report the three-way split, and keep the old measure visible beside it as "not collected by the scenario's households", so the change is transparent.
- Food banks may take produce beyond their households' fair share once that share is met, bounded only by their own storage, hours, truck and the produce's usable life. Fair-share figures never count those extra pounds.
- Waste is a scenario-end accounting measure on synthetic data. It is not observed spoilage, and produce at a food bank still has to be handed out.
