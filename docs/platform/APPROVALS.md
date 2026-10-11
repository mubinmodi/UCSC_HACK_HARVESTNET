# Human approvals and household texts (#18)

`python -m harvestnet_platform.approvals` starts the review/notification adapter on
localhost:8030. Set `API_EVENTS_TOKEN` (random secret) and `APPROVAL_PUBLIC_URL`.
SQLite stores only drafts and opaque organization decision capabilities; no
household phone numbers, SNAP answers, or text contents are retained.

An authenticated core posts to `/approval-requests` with `event_id`, `version`,
the complete `terms`, and named approving `organizations`. Each organization
gets a separate random, expiring review URL, exact terms hash, and message.
Distribute a URL only to that organization's authorized human. These are bearer
capabilities: possession authenticates the invited human, not their named identity.
Use HTTPS, don't log links, and never share links with agents. For stronger staff
identity the core can put this page behind its own staff login.

The review page displays all exact terms and Approve/Decline buttons. GET never
approves. POST includes the displayed version and hash plus an explicit human
confirmation. Old versions, altered terms and expired links fail. n8n has no
auto-approve node and unanswered requests have no effect. Transport acceptance
does not equal human approval. Issuing a higher version invalidates all old links.
Keep this mirror up to date with EVERY core amendment. Even with that mirror,
the core must independently recheck the current version and resource holds.

Set `CORE_API_URL` and `CORE_API_TOKEN` for the live core. Human decisions POST
to `/approvals` with event, organization, version, terms hash, decision, and an
idempotent receipt ID. With no core, the labeled local fallback records a human
decision but **does not commit**. A service outage returns 503; retry the same
human decision safely. The core must deduplicate receipt IDs and enforce current
version, required approvals, holds and deadlines before commitment. These core
operations are proposed pending ticket #1/#9, not deployed endpoints.

## Import n8n workflows

Run `python integrations/n8n/build_workflows.py`, then import the four JSON files
into n8n. They start inactive; import does not send anything. Configure:

- Incoming webhook Header Auth credential (a dedicated incoming secret).
- Platform HTTP Header Auth: `Authorization: Bearer API_EVENTS_TOKEN`.
- Twilio credential (or replace the Send text node with your SMS provider).
- n8n variables `HARVESTNET_PLATFORM_URL` (HTTPS) and `HARVESTNET_SMS_FROM`.
- Disable saved execution payloads, including errors, to avoid retaining phones,
  SNAP status, pickup tokens or organization decision links.

Approval workflow receives one issued request `{to, message, decision_url,
version}`. It carries the review request only. The human opens the page and
submits the decision there; n8n never approves or changes the terms.

For live n8n decision relay, set `N8N_DECISION_WEBHOOK_URL` to the published
`human-decisions.json` webhook and `N8N_WEBHOOK_TOKEN` to its Header Auth bearer
secret. The platform verifies the human capability and exact terms before sending
the decision receipt. This workflow forwards the receipt unchanged to the core's
`/approvals`, using `HARVESTNET_CORE_URL` and a separate restricted core approval
credential. It never creates a receipt or defaults the decision. Without this
webhook the direct core path serves as the labeled fallback. Missing core is
still local-only. The core must authenticate this trusted receipt bridge and
recheck the current version/holds; it must not accept arbitrary public receipts.

Pickup workflow forwards trusted core notice data to `/notifications/prepare`:
`committed: true`, `food_bank`, calculator `items: [{name, pounds}]`, `window:
{start,end}`, `request_code`, `pickup_id`, `version`, `release_url`, and `to`.
Optional `snap: yes` and `market` metadata add a tip only if `verified: true`,
`nearby: true`, source URL exists, and timezone-aware verification is within
30 days. This is a freshness policy, not proof of current participation; feed
trusted verified market records. All example market data in tests is synthetic.
Names, pounds, time and code come from the core, never model arithmetic.

Reply workflow receives `{text, request_code, pickup_id, release_token}` from a
trusted authenticated SMS bridge. The bridge must verify the SMS provider's
signature and associate sender/code with an issued pickup; never trust a raw
phone number or unsolicited text as authorization. Recognized cannot-make-it
messages call `/pickups/{pickup_id}/release` using the pickup-scoped token. A
missing/offline core reports `release_pending`, never pretends food was released.
The core owns reassignment to the next household and expiry of requests.

Live n8n, SMS delivery and the real core integration remain unverified until
their accounts/URLs and ticket #1 are supplied. Tests verify the real local HTTP
callbacks, stale-version rejection, eligibility filtering, and release adapter.

Sources: [n8n Webhook authentication](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/),
[workflow import/export](https://docs.n8n.io/workflows/export-import/).
