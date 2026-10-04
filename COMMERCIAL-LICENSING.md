# ANPOS Commercial Distribution & Licensing — Requirements 75–82

ANPOS may be sold as a private/paid product without turning project execution into destructive DRM. The canonical source remains an inert protocol repository. Commercial billing, entitlement issuance, customer provisioning, and premium-service access are external distribution capabilities.

## Core commercial invariant

**A license controls commercial entitlements such as template access, new provisioning, update channels, premium blueprints/services, hosted orchestration, support, or seats. It must never remotely delete, corrupt, encrypt, disable, or sabotage an already-generated customer project.**

Repository-local entitlement files are caches/references only. They are never billing authority and cannot grant themselves commercial rights by being edited.

## 75 — Distribution modes

Supported commercial distribution modes are provider-adapter based:

1. **GitHub Marketplace App — recommended** for GitHub-native billing, account identity, plan lifecycle, and webhook events.
2. **GitHub Sponsors + private-repository access** for a simpler subscription model when its account/access limitations are acceptable.
3. **External checkout + GitHub App/private-repository provisioning** for operator-controlled billing, taxes, lifetime/annual licenses, or custom enterprise contracts.

The underlying premium ANPOS template/distribution repository may be private. A customer with access can create an independent repository from a GitHub template; the generated repository has its own history and must not be treated as revocable remote code.

Commercial mode is optional. Core ANPOS child-project behavior must not depend on a billing provider being online.

## 76 — Billing and commerce authority

For GitHub Marketplace mode:

- GitHub Marketplace purchase state is the external billing event source.
- The commercial service handles `marketplace_purchase` actions including `purchased`, `changed`, and `cancelled`.
- Paid Marketplace publication requires the operator to satisfy GitHub's current publisher/financial/listing requirements.
- Pricing values and Marketplace plan IDs are configured in the Marketplace/operator system, not hard-coded as authoritative repository values.
- On ambiguity, missed delivery, recovery, or support action, reconcile against the authenticated Marketplace API before changing entitlement state.

The commercial service database is the operational entitlement ledger. GitHub billing reality outranks a repository cache.

## 77 — Signed entitlement envelope

A successful purchase/trial/plan change may mint a signed entitlement envelope containing at minimum:

- license/entitlement ID;
- issuer;
- canonical GitHub account ID and account type;
- display login/name as non-canonical metadata;
- plan ID;
- seat/unit limit when applicable;
- feature entitlements;
- issued/not-before/expiry timestamps;
- unique token/event ID (`jti` or equivalent);
- signing key ID;
- asymmetric signature algorithm and signature.

Private signing keys never enter ANPOS repositories, Actions logs, PM systems, AI memory, or customer configuration. Verification public keys or key-discovery metadata may be public.

A customer repository may cache an opaque entitlement reference or signed public claims, but **server-side verification remains authoritative for premium downloads/services/provisioning**.

## 78 — Webhook security, replay protection, and idempotency

Marketplace/webhook processing must:

1. preserve the raw request body until verification;
2. verify GitHub `X-Hub-Signature-256` using the configured webhook secret and constant-time comparison;
3. require the expected event type;
4. deduplicate `X-GitHub-Delivery` before side effects;
5. validate action/payload shape;
6. process entitlement changes transactionally per canonical GitHub account ID;
7. make repeated deliveries idempotent;
8. record an immutable audit event without storing unnecessary payment/private data;
9. reconcile out-of-order or ambiguous events against the authenticated Marketplace API;
10. rotate compromised webhook/signing secrets/keys without invalidating already-generated project code.

Webhook secrets and entitlement-signing private keys must live only in an approved secrets manager/runtime.

## 79 — Non-destructive expiration/cancellation

Cancellation, downgrade, expiry, suspension, or payment failure may affect only commercial entitlements defined by the active plan.

Permitted examples:

- block creation of new premium customer projects;
- stop access to future premium ANPOS protocol releases;
- stop premium blueprint downloads;
- disable hosted Supervisor/orchestrator services;
- reduce future seat/provisioning limits;
- end commercial support/SLA access.

Forbidden examples:

- delete or alter customer repositories;
- intentionally break builds/tests;
- encrypt customer code/data;
- inject kill switches into generated applications;
- revoke unrelated Git/GitHub functionality;
- silently remove project files;
- prevent the customer from using code already lawfully generated under the license, except where an operator-supplied legal agreement explicitly and lawfully governs use.

Grace periods, offline behavior, and downgrade effects must be explicit and deterministic.

## 80 — Plans, seats, and entitlements

`config/licensing/product-catalog.json` is a non-authoritative product blueprint. The operator maps Marketplace/external plan IDs to feature entitlements in the commercial service.

Recommended entitlement categories include:

- private template/provisioning access;
- protocol update channel;
- premium blueprints/adapters;
- hosted orchestration;
- seat/project limits;
- team/organization features;
- enterprise/self-hosted services;
- support/SLA level.

Prices remain external because billing providers are the source of billing truth and commercial pricing changes independently of protocol code.

## 81 — Customer data and privacy

Commercial infrastructure must minimize retained customer information. Store canonical GitHub account IDs and only the metadata needed for entitlement, support, tax/accounting, fraud prevention, security, and legal obligations.

Requirements:

- no raw payment card data in ANPOS infrastructure when GitHub/another processor handles payment;
- no webhook secrets/signing keys in repositories;
- no billing/private customer data in AI memory or PM mirrors unless explicitly required and permitted;
- access logs and entitlement audit logs use retention limits;
- customer deletion/cancellation procedures account for legal/accounting retention obligations;
- for GitHub Marketplace cancelled trials, private customer data cleanup must meet GitHub's current Marketplace requirement (the policy blueprint sets a maximum of 30 days unless a stricter applicable rule governs).

AI/provider privacy rules from ANPOS 1.2 continue to apply.

## 82 — Commercial launch, legal, and operational gates

Commercial sale is not considered launch-ready merely because these blueprints exist. Before paid distribution the operator must verify, as applicable:

- private/template repository strategy;
- GitHub App ownership and minimum permissions;
- Marketplace verified-publisher/listing/financial onboarding requirements;
- webhook endpoint security and replay/idempotency tests;
- entitlement service/database availability and backups;
- signing-key storage, rotation, revocation, and public-key discovery;
- plan/seat mapping and downgrade behavior;
- customer provisioning/removal workflow;
- privacy policy and data-retention/deletion process;
- support/contact/refund/cancellation process;
- taxes/accounting obligations;
- operator-supplied commercial license/EULA/terms reviewed for the relevant jurisdictions;
- incident response for billing, entitlement, webhook, and key compromise.

ANPOS does **not** invent legally binding license terms. Commercial legal text is an operator-owned legal artifact and should be reviewed by qualified counsel before sale.

## Recommended GitHub-native flow

```text
GitHub Marketplace purchase/change/cancel
        ↓
Verify webhook signature + delivery ID
        ↓
Reconcile canonical GitHub account + plan
        ↓
Commercial entitlement ledger
        ↓
Mint/refresh signed entitlement
        ↓
Provision private-template/update/service access
        ↓
Customer creates independent child repositories
```

## Source vs commercial runtime boundary

The canonical ANPOS source stores this protocol, schemas, policy catalogs, and inactive commercial blueprints only. It stores no live webhook secret, signing private key, Marketplace customer record, paid plan ID, customer entitlement, payment data, or active license-service session.

Commercial runtime is a separately deployed GitHub App/service. Customer projects may contain only non-secret entitlement references or signed public claims. Editing those files never creates billing authority.
