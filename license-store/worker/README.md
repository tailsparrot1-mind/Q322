# Vkus License Store — Cloudflare Worker foundation

This directory is an isolated server-side foundation for the Vkus license store. It is intentionally not deployed and contains no merchant credentials.

## Current state

- D1 schema for plans, orders, payment events, licenses, activations.
- Worker endpoints: health, plans, order creation, Robokassa ResultURL, activation.
- SHA-256 signature implementation only. The Robokassa merchant account must be configured for SHA-256 before using this handler.
- License key is generated only after a verified ResultURL callback.
- Callback processing uses a unique event key and order state to prevent duplicate issuance.
- Email delivery is not implemented; no provider has been selected.
- Frontend storefront migration is a separate next step. Do not expose this Worker as a functioning shop until the existing storefront is ported and reviewed.

## Local setup

1. Install Node.js LTS and Wrangler 4.
2. From this directory run `npm install` (Wrangler is a dev dependency in the root package, to be added in the project integration stage).
3. Create local D1 database and apply migration:
   `wrangler d1 execute vkus-license-store --local --file=migrations/0001_initial.sql`
4. Configure local vars/secrets in a private `.dev.vars` file (never commit it).
5. Add active plans only after copying and verifying the existing store's actual tariff catalogue.

## Required production secrets

- `ROBOKASSA_MERCHANT_LOGIN`
- `ROBOKASSA_PASSWORD_1`
- `ROBOKASSA_PASSWORD_2`

Set with `wrangler secret put NAME`. Never paste secrets into chat or commit them.

## Important pre-production work

- Verify exact Robokassa signature formula and SHA-256 selection in merchant cabinet.
- Add rate limiting and abuse controls to public endpoints.
- Implement secure order-status retrieval and one-time license disclosure/retrieval (the ResultURL response must not disclose the license).
- Select and implement transactional email delivery.
- Add a cryptographic test suite and end-to-end sandbox tests, including duplicate callback, wrong signature, wrong amount, D1 failure, and callback retry.
- Test Robokassa payment page in the actual tkwry/WebKitGTK window on Kali/VMware.
- Add license revocation, activation limits, and a device binding policy after product requirements are confirmed.
- Do not switch to real payments until all tests and provider requirements pass.
