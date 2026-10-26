# Human approvals and household emails (#18)

`python -m harvestnet_platform.approvals` starts the review/notification adapter on
localhost:8030. Set `API_EVENTS_TOKEN` (random secret) and `APPROVAL_PUBLIC_URL`.
SQLite stores drafts and opaque organization decision capabilities. Household
addresses live only in the core's expiring request contact record; they are not
stored by this adapter.

An authenticated core posts to `/approval-requests` with `lot_id`, `version`, the complete
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
- Amazon SES SMTP credential in n8n Cloud. SES SMTP credentials are regional and
  separate from AWS access keys. The verified From address is the n8n variable
  `HARVESTNET_EMAIL_FROM`; set it to `SES_SENDER_EMAIL` from the deployment env.
- n8n variables `HARVESTNET_PLATFORM_URL` (HTTPS) and `HARVESTNET_CORE_URL`.
- Disable saved execution payloads, including errors, to avoid retaining email
  addresses, SNAP status, pickup codes or organization decision links.

Approval workflow receives one issued request `{to, message, decision_url,
version}`. It carries the review request only. The human opens the page and
submits the decision there; n8n never approves or changes the terms.
Set `APPROVER_EMAILS_JSON` to a JSON map from organization ID to its authorized
human's address, and `N8N_APPROVAL_WEBHOOK_URL` to the published workflow webhook.
The adapter sends only mapped, allowlisted recipients. Otherwise it returns the
review link for manual delivery, labeled `manual` or `outside_test_allowlist`.
An uncertain webhook response is labeled `uncertain`; reissuing a link requires
an explicit `reissue: true` request and invalidates the old link.

For a separately configured n8n decision relay, set `N8N_DECISION_WEBHOOK_URL` to the published
`human-decisions.json` webhook and `N8N_WEBHOOK_TOKEN` to its Header Auth bearer
secret. The platform verifies the human capability and exact terms before sending
the decision receipt. This workflow forwards the receipt unchanged to the core's
`/approvals`, using `HARVESTNET_CORE_URL` and a separate restricted core approval
credential. It never creates a receipt or defaults the decision. Without this
webhook the direct core path serves as the labeled fallback. Missing core is
still local-only. The core must authenticate this trusted receipt bridge and
recheck the current version/holds; it must not accept arbitrary public receipts.
The AWS Compose stack uses the direct core path with per-organization tokens;
its n8n workflows carry review emails but do not relay decisions.

Pickup workflow forwards trusted core notice data to `/notifications/prepare`:
`committed: true`, `food_bank`, calculator `items: [{name, pounds}]`, `window:
{start,end}`, `request_code`, `pickup_id`, `version`, `release_url`, and `to`.
The prepared email names the committed produce and contains a *Can't make it*
link. The link opens the household page; opening it alone changes nothing.
The household must tap the release button, which calls the core's
`POST /pickups/{pickup_id}/release`. A separate workflow sends the thank-you
only after that household release. A cooler failure release does not send the
thank-you. The core queues email outbox entries with pickup events in the same
transaction, without storing an address or request code in the outbox. Once a
send starts, an ambiguous failure is labeled `uncertain` and never retried
automatically.
Optional `snap: yes` and `market` metadata add a tip only if `verified: true`,
`nearby: true`, source URL exists, and timezone-aware verification is within
30 days. This is a freshness policy, not proof of current participation; feed
trusted verified market records. All example market data in tests is synthetic.
Names, pounds, time and code come from the core, never model arithmetic.

The incoming webhooks must use HTTPS and Header Auth. In the SES sandbox, both
the From identity and every recipient need SES verification. Keep
`SES_TEST_RECIPIENTS` to verified demo addresses only. These workflow JSON files
are local inactive drafts. SES identity verification, SMTP credentials, n8n
publication, and live end-to-end delivery remain unverified.

Sources: [n8n Webhook authentication](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/),
[workflow import/export](https://docs.n8n.io/workflows/export-import/).
