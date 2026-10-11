# Food behavior lives in food profiles, not in code

HarvestNet needs a general architecture for crops and food products, not logic tied to strawberries. Food-specific properties come from a versioned food profile: handling requirements, quality/storage targets, chilling sensitivity, usable-life assumptions, packaging units, compatibility, quality categories, candidate pathways, and required assessments. Specialists apply common procedures to the profile and actual lot evidence. Negotiator rules do not branch on crop names. We chose this over writing crop-specific checks because those checks would multiply with every food and weaken the whole-chain design. The earlier tomato mistake illustrates why maturity, temperature and exposure duration matter; a refrigerated vehicle is neither universally suitable nor universally unsuitable for tomatoes.

## Consequences

- Strawberries are the demonstration's lead example, not a special case. Lettuce, dairy, and prepared meals each need a reviewed profile; implementation is not established.
- General references, actual lot evidence, and synthetic assumptions remain distinct. Storage quality targets do not automatically establish safety limits or remaining usable life.
- Adding a profile supports a new food only when its required assessments are supported. Otherwise the result is explicitly unsupported, rather than assumed eligible.
- Truck selection, storage checks, deadlines, and pathway eligibility respond to profile properties and current evidence. Generality is evaluated across profiles, not asserted from a change of food name.
