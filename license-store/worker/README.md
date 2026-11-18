# Vkus License Store — Cloudflare Worker foundation

This directory is an isolated server-side foundation for the Vkus license store. It is intentionally not deployed and contains no merchant credentials.

## Current state

- D1 schema for plans, orders, payment events, licenses, activations.
- Worker endpoints: health, plans, order creation, Robokassa ResultURL, activation.
- SHA-256 signature implementation only. The Robokassa merchant account must be configured for SHA-256 before using this handler.
- License key is generated only after a verified ResultURL callback.
- Callback processing uses a unique event key and order state to prevent duplicate issuance.
- Transactional email outbox and scheduled delivery are implemented against the Resend HTTP API. Free plan currently advertises 3,000 emails/month and 100/day; a verified sending domain and API key are still required before customer delivery.
- Frontend storefront migration is a separate next step. Do not expose this Worker as a functioning shop until the existing storefront is ported and reviewed.

## Local setup

1. Install Node.js LTS and Wrangler 4.
2. From this directory run `npm install`, then `npm test` and `npm run typecheck`.
3. Create local D1 database and apply migration:
   `wrangler d1 execute vkus-license-store --local --file=migrations/0001_initial.sql`
4. Configure local vars/secrets in a private `.dev.vars` file (never commit it).
5. Add active plans only after copying and verifying the existing store's actual tariff catalogue.

## Required Worker secrets and vars

- `RESEND_API_KEY` — Resend API key.
- `LICENSE_MAIL_FROM` — verified sender address on a domain onboarded in Resend.
- `LICENSE_ENCRYPTION_KEY` — base64-encoded 32-byte AES-GCM key.

Email delivery uses a D1 outbox and a one-minute scheduled trigger. Failed sends are retried with backoff; after eight failed attempts the outbox entry is marked failed. Resend Free currently advertises 3,000 emails/month and a 100/day limit; verify current pricing before launch.

## Required payment secrets

- `ROBOKASSA_MERCHANT_LOGIN`
- `ROBOKASSA_PASSWORD_1`
- `ROBOKASSA_PASSWORD_2`

Set with `wrangler secret put NAME`. Never paste secrets into chat or commit them.

## Important pre-production work

- Verify exact Robokassa signature formula and SHA-256 selection in merchant cabinet.
- Add rate limiting and abuse controls to public endpoints.
- Implement secure order-status retrieval and one-time license disclosure/retrieval (the ResultURL response must not disclose the license).
- Verify Resend domain, sender, and deliverability; test successful email, provider rejection, retry, and terminal failure.
- Add a cryptographic test suite and end-to-end sandbox tests, including duplicate callback, wrong signature, wrong amount, D1 failure, and callback retry.
- Test Robokassa payment page in the actual tkwry/WebKitGTK window on Kali/VMware.
- Add license revocation, activation limits, and a device binding policy after product requirements are confirmed.
- Do not switch to real payments until all tests and provider requirements pass.
