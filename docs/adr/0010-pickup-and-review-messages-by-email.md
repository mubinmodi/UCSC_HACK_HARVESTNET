# Pickup and review messages by email, through n8n Cloud and Amazon SES

October 11, 2026, decided by the user: households and staff approvers get email instead of text messages. Real SMS to US phones needs a provider such as Twilio plus US carrier (A2P 10DLC) registration, which costs money and takes days to weeks to approve; a trial account only reaches verified numbers. Email through Amazon SES in the team's AWS account costs about $0.10 per 1,000 messages, and sending it through n8n keeps n8n as the sponsor that carries messages.

## Decision

- Households may give an optional email instead of a phone number. It is used only for pickup messages and deleted with the request after 7 days.
- Pickup, changed-pickup and thank-you emails, and staff approvers' review requests, go from the core or the approvals service to n8n Cloud webhooks, and n8n sends them through Amazon SES SMTP. n8n never approves anything; it only carries messages (ADR 0004).
- "Can't make it" is a link in the pickup email that opens the household page, where the household taps to release. There is no SMS reply.
- The public API changed from `phone` to `email` (contract-v0.2).

## Consequences

- SES starts in sandbox mode: only verified addresses receive mail until production access is requested. Demos use a short list of verified addresses.
- The voice line still collects no contact detail, so voice callers learn about pickups by calling back with their code.
- Switching back to SMS later means a provider account, carrier registration, and restoring the reply path.
