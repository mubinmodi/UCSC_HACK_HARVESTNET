# Sponsors serve organizations; they never decide

HarvestNet uses its sponsors only in roles a real organization already has around its negotiator. Cisco AGNTCY is the network between organizations. Beeceptor stands in for each organization's own systems of record: fleet telematics, inventory, cold-storage occupancy, and cached copies of real price and route data. ElevenLabs is the voice channel for people in the field, such as a farmer reporting a surplus lot or a harvest crew receiving a shift notice. n8n is each organization's back office, where humans approve commitments. We chose this over showcasing each sponsor as a feature of its own, because a sponsor placed in the middle of the negotiation would either be theater or become a central decision-maker (see ADR 0001). NVIDIA Brev is not used.

## Consequences

- Each organization has its own Beeceptor endpoints and its own n8n approval workflow, and only that organization's specialists or people use them.
- Disruptions are assessed from data, the food profile, and actual exposure history (ADR 0003). The same reading may have different implications for different foods. Injected readings remain labeled synthetic; they do not establish a real-world failure.
- Voice input becomes a draft surplus offer only after calculators check it and the farmer confirms a read-back (ADR 0002).
- n8n carries a human's decision and never makes one.
- The offline core must support repeatable evaluation without sponsor availability: mocked inputs, text intake, and local approval controls are planned fallbacks. A fallback does not establish use of a sponsor service.
- Integrations are proposed. Public documentation has been reviewed, but project accounts, credits, entitlements, and working calls remain unverified. Beeceptor mocks do not become authoritative operational records merely because they resemble a live system.
