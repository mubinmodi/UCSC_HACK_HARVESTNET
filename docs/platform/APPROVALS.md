# Human approvals and household texts (#18)

`python -m harvestnet_platform.approvals` starts the review/notification adapter on
localhost:8030. Set `API_EVENTS_TOKEN` (random secret), `APPROVAL_PUBLIC_URL`, and
`REPLY_BINDING_KEY` (random secret). SQLite stores drafts, opaque organization
decision capabilities, and, for SMS replies, which pickup the last text to a phone
was about. The phone is stored only as a keyed hash; no phone numbers, SNAP
answers, or text contents are retained.

An authenticated core posts to `/approval-requests` with `lot_id` (the core's
change requests still say `event_id`, which is read too), `version`, the complete
`terms`, and named approving `organizations` (`market`, `city`, `rural`,
`eastside`). Each organization gets a separate random review URL, the exact
`sha256:` terms hash, an `expires_at` in ISO 8601, and a message. Links last
`APPROVAL_LINK_TTL_SECONDS` (default 3600, at most 86400), or `ttl_seconds` in the
request. A repeat of the same request is refused, so a webhook retry adds no links.
To replace a lost or expired link for the same version, post the same request
with `"reissue": true` (and the organizations to reissue): the old link stops
working. A link that already carries a decision can't be reissued; changed terms
need a new version.
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

Set `CORE_API_URL` and `CORE_API_TOKENS` for the live core. `CORE_API_TOKENS` is a
JSON map of each organization to its own core staff token, the same shape as the
core's `HARVESTNET_STAFF_TOKENS` (which is also read if `CORE_API_TOKENS` is unset);
each decision is sent with its own organization's token. A single legacy
`CORE_API_TOKEN` still starts, with a warning, but only commits that one
organization's decisions. Human decisions POST to `/approvals` as the contract's `record_approval`:
`lot_id`, `version`, `organization_id`, `terms_hash` (`sha256:...`), `decision`,
and the idempotent `receipt_id`. With no core, the labeled local fallback records
a human decision but **does not commit**. A core rejection (401, 409, and so on)
comes back with the core's own status and error. Only an unreachable core returns
503; retry the same human decision safely. The core deduplicates receipt IDs and
enforces the current version, required approvals, holds and deadlines.

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
The text asks the household to reply YES or CAN'T MAKE IT, and the platform
remembers that this phone's last text was about this pickup.
Optional `snap: yes` and `market` metadata add a tip only if `verified: true`,
`nearby: true`, source URL exists, and timezone-aware verification is within
30 days. This is a freshness policy, not proof of current participation; feed
trusted verified market records. All example market data in tests is synthetic.
Names, pounds, time and code come from the core, never model arithmetic.

Reply workflow receives the inbound SMS (`From` and `Body`, as Twilio sends them,
or `from` and `text`) and posts it to `/household/replies`. The platform finds the
pickup in the last text sent to that phone, still open. **YES** confirms and
answers with the food bank, window and code; nothing changes. **CAN'T MAKE IT**
(also "cannot make it", "no puedo ir") calls the core's
`POST /pickups/{pickup_id}/release` with that pickup's `request_code`, and the
reply is sent back by SMS. Any other text gets the two options back. An unknown
number changes nothing. A trusted caller may instead name `pickup_id` and
`request_code` directly. A missing or offline core reports `release_pending` and
keeps the pickup for a retry; it never pretends food was released. The core owns
reassignment to the next household and expiry of requests.

The incoming webhook must be authenticated. Twilio can't add a custom header, so
in deployment either put Twilio's signature check in front of this webhook or use
credentials Twilio can send (Basic auth in the webhook URL). A raw, unverified
text is never treated as authorization.

The four workflows are now imported as unpublished drafts in the HarvestNet n8n
Cloud workspace. A separate manual connection check successfully calls the live
Beeceptor service. Credential binding, SMS delivery and the real core integration
remain unverified until the public platform/core URLs, credentials, SMS provider
and ticket #1 are available. Tests verify the real local HTTP
callbacks, stale-version rejection, eligibility filtering, and release adapter.

Sources: [n8n Webhook authentication](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/),
[workflow import/export](https://docs.n8n.io/workflows/export-import/).
