# Human approvals and household emails

`python -m harvestnet_platform.approvals` (port 8030) is the one service for two jobs: issuing **review links** to Staff approvers, and turning the core's pickup notices into **household emails**. Neither it nor n8n ever decides or commits anything. Only each named organization's Staff approver does, for one exact version; transport acceptance is not approval, and no reply means no approval (ADR 0001, 0004).

It needs `API_EVENTS_TOKEN` (a random secret for trusted callers) and `APPROVAL_PUBLIC_URL` (the HTTPS origin in the links). `APPROVALS_DB` is a SQLite file holding the issued terms and links. Household email addresses are not stored here; they live only in the core's expiring request record.

## Who approves what, and where

- **Ordinary lots** are approved on the donor page or food bank dashboard. The Staff approver's own page calls the core's `POST /approvals` with that organization's staff token.
- **A changed version after a cooler failure** is approved through review links. The food bank's cooler watcher asks this service to issue them, one per named organization.

## Review links

`POST /approval-requests` (authenticated with `API_EVENTS_TOKEN`) takes `lot_id`, `version`, the complete `terms` and the named `organizations` (the roster's approvers: `market`, `city`, `rural`, `eastside`). Each organization gets its own random link, the exact `sha256:` terms hash, an ISO 8601 `expires_at` and a message.

- Links last `APPROVAL_LINK_TTL_SECONDS` (default 3600, at most 86400), or `ttl_seconds` in the request.
- A repeat of the same request is refused, so a webhook retry adds no links.
- To replace a lost or expired link for the same version, post the same request with `"reissue": true` (and the organizations to reissue). The old link stops working. A link that already carries a decision cannot be reissued, and changed terms need a new version, which invalidates every older link.
- A link is a bearer capability. Possession authenticates the invited Staff approver, not a named identity, so send each link only to that organization's person, over HTTPS, and never log it or show it to an agent.
- The review page shows all exact terms with Approve and Decline. `GET` never approves. `POST /human/decision` carries the displayed version, the hash and an explicit human confirmation. An old version, altered terms or an expired link fails.

## Decisions reach the core

The platform checks the capability and exact terms, then sends the receipt (`lot_id`, `version`, `organization_id`, `terms_hash`, `decision`, `receipt_id`) to the core's `POST /approvals`, which deduplicates by `receipt_id` and enforces the current version, required approvals, holds and deadline. Contract: [`public-api.md`](../contracts/public-api.md).

- **Credentials.** Set `CORE_API_URL` and `CORE_API_TOKENS`, a JSON map of organization to its own core staff token (the shape of the core's `HARVESTNET_STAFF_TOKENS`, which is read if `CORE_API_TOKENS` is unset). Each decision is sent with its own organization's token.
- **Errors.** A core rejection (401, 409, ...) comes back with the core's own status and error. Only an unreachable core returns 503; retry the same decision.
- **No core configured.** The labeled local fallback records the decision but does not commit.
- **Optional n8n relay.** With `N8N_DECISION_WEBHOOK_URL` and `N8N_WEBHOOK_TOKEN`, the receipt goes through the n8n workflow `human-decisions.json`, which forwards it unchanged to the core with a separate restricted credential. The AWS stack does not use it: it sends decisions directly.

## Emails

Everything is sent by n8n Cloud's Send Email node over Amazon SES. The service prepares the subject and text; n8n sends them.

- **Review emails.** `APPROVER_EMAILS_JSON` maps organization ID to its Staff approver's address, and `N8N_APPROVAL_WEBHOOK_URL` is the published workflow's webhook. The service emails only mapped addresses that are in `SES_TEST_RECIPIENTS`. Otherwise the response carries the link for manual delivery, labeled `manual` or `outside_test_allowlist`. A webhook timeout is `uncertain`: the link is already issued, so reissue only deliberately.
- **Pickup emails.** The core's outbox posts each notice to `N8N_PICKUP_WEBHOOK_URL` (or `N8N_RELEASE_WEBHOOK_URL` for the thank-you). The n8n workflow calls this service's `POST /notifications/prepare`, which returns the email in the household's language (English or Spanish). It names the committed produce, the window and the request code, and it carries a *Can't make it* link to the household page. Opening the link changes nothing; the household must tap the button, which calls `POST /pickups/{pickup_id}/release`. A cooler-failure release sends no thank-you. Names, pounds, times and codes come from the core, never from model arithmetic. Delivery, outbox and privacy rules: [`docs/core/README.md`](../core/README.md).
- **Market Match tip.** A tip is added only for a household that said it receives SNAP, and only when the market record is `verified`, `nearby`, has a source URL, and was verified (timezone-aware) within 30 days. That is a freshness policy, not proof of current participation. Feed only trusted verified market records; test data is synthetic.

## n8n

`python integrations/n8n/build_workflows.py` generates four inactive, credential-free workflow files in `integrations/n8n/` (CI checks they are current): `approval-requests`, `pickup-emails`, `cannot-make-it` and `human-decisions`. Importing them sends nothing.

The workflows running in n8n Cloud were built by the team (see [`HANDOFF.md`](HANDOFF.md) for which are active). To set one up, configure:

- A Header Auth credential for the incoming webhook (a dedicated secret; it is `N8N_WEBHOOK_TOKEN`).
- A Header Auth credential for calls to this service: `Authorization: Bearer <API_EVENTS_TOKEN>`.
- An Amazon SES SMTP credential, created in n8n Cloud. SES SMTP credentials are regional and separate from AWS access keys. The deployment never creates or copies them.
- The n8n variables `HARVESTNET_PLATFORM_URL` (HTTPS), `HARVESTNET_EMAIL_FROM` (the verified From address, the same as `SES_SENDER_EMAIL` in the deployment settings) and, for the relay only, `HARVESTNET_CORE_URL`.
- Saved execution data turned off, including errors, so email addresses, SNAP answers, pickup codes and review links are not retained.

Incoming webhooks must use HTTPS and Header Auth. In the SES sandbox, the From identity and every recipient must be verified; keep `SES_TEST_RECIPIENTS` to verified demo addresses. Verifying an address in `.env` alone does nothing.

References: [n8n Webhook authentication](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/), [workflow import/export](https://docs.n8n.io/workflows/export-import/).
