---
type: note
status: draft
lifecycle: active
created: 2026-11-12
tags: [anaxigraph, evaluation, ci-cd, architecture]
---

# Eval 2 — DispatchLedger

An online shop grows into a fulfilment operation with a browser interface, shipping worker, carriers, reporting, and persistent orders. The central question is whether an agent can make genuinely local releases cheaply while recognising changes that require broader verification.

This is an evaluation specification, not an implemented or executed benchmark. Follow [shared protocol](../../docs/protocol.md) for arms, budgets, checkpoints, scoring, and scale experiments. Do not give this whole document to the coding agent. Reveal one numbered prompt and its public attachment at a time; keep acceptance checks and later requests private. Fixture organisations and services below are fictional.

## Public environment and fixture contracts

At step 00, disclose the chosen stack, installation/run commands, deterministic clock controls, and the same basic CI runner to every arm. Require a local browser demo, persistent storage, and documented unattended build/test commands. No paid services, actual payments, or cloud deployment are needed. Public example data contains three products, two buyers, and GBP prices in integer pennies. Each fixture includes runnable examples and its complete protocol at the step that introduces it.

| Reveal | Fixture attachment given to the agent | Behaviour the evaluator can vary |
|---|---|---|
| 02 | **ParcelFox:** `POST /labels`, bearer test token; `{order_ref, shipment_ref, address, weight_g, idempotency_key}` → `{label_id, tracking_code, label_text}`. Repeated key returns the original label. | Deterministic 503 before acceptance, or connection loss after label creation; `GET /labels/by-key/{key}` reconciles uncertain outcomes. |
| 04 | **MailPost:** `POST /messages` with recipient, subject, body, and deduplication key. Returns a message ID; repeated key delivers once. | Delivery failure before acceptance and lost acknowledgement after acceptance; message-log lookup by key. |
| 05 | **QuickCrate:** `POST /jobs` uses a different credential header and nested parcel payload; returns job ID. `GET /jobs/{id}` returns pending/ready/failed; ready contains label data. | Completion through polling or signed callback; callback ID, HMAC format, retry schedule, and signature examples are supplied. Duplicate and out-of-order callbacks are documented. |
| 07 | **Warehouse feed:** snapshot records contain warehouse, SKU, available quantity, and monotonically increasing revision. | Stale snapshots, zero stock at preferred warehouse, split availability. |
| 14 | **ParcelPine:** `POST /shipments` accepts token authentication, kilograms as a decimal string, and a recipient object. Response is `{reference, document:{format:"text",content}, tracking}`. | Unsupported destinations return a documented non-retryable code; 429 specifies a retry delay. Idempotency and lookup are documented. |

Fixture servers record requests and external side effects independently. Responses use generated order/customer identifiers, not fixed strings the application can memorise. Tests interact through the browser, application API, worker command, and observable fixture calls; they do not require particular internal class or table names. Service credentials are local test values.

The public data pack also releases these rules at the relevant step: 00, quantities are positive integers and product IDs must exist; 01, a repeated checkout submission key identifies the same order; 03, retry transient carrier failures at most three times with virtual delays of 1, 2 and 4 seconds, then show “needs attention”; 07, warehouse feeds describe physical stock before this app's unfulfilled reservations, so newer snapshots must not erase reservations; 09, returns use a unique reference and cannot exceed delivered quantities minus previous returns; 11, historical fixture records include purchase-time product names and prices; 15, legacy orders are GBP and amounts use the documented currency's minor unit. These are fixture specifications to implement and publish, not undisclosed grading rules.

## Sequential user prompts

Each **Acceptance** paragraph is evaluator-only. Every tested business rule must already appear in the quoted request or its public attachment; hidden cases vary data and timing, not requirements.

### 00 — First shop

> “Build me a little shop called DispatchLedger. Show the products and prices, let someone add things to a basket and place an order, and give me a page where I can see orders. Use the sample products. No real payments yet. Keep the orders if I restart it, and give me buttons I can actually try.”

**Acceptance:** Product display, basket totals, checkout, order list, and restart persistence work. Server rejects invalid quantities and unknown products according to the public input examples. Capture the first application API and data snapshot.

### 01 — Limited stock

> “We only have a few of each item. Show what is left and stop people buying more than we have, even if two people order the last item at almost the same time.”

**Acceptance:** Concurrent last-item checkouts cannot oversell; failed checkout leaves inventory unchanged. Repeating the documented checkout submission key returns the same order, rather than reserving twice; this key is described in the attachment.

### 02 — Shipping labels

> “We are using ParcelFox for deliveries. Let me put in an address and package weight, then get a label for an order. Show its tracking number. Their little test service and instructions are attached.”

**Acceptance:** Correct recipient/weight mapping, persisted label association, and understandable validation errors. Duplicate label clicks produce one physical shipment under the supplied idempotency contract.

### 03 — Work in the background

> “Getting labels is slowing the page down. Queue them and let me run the shipping work on the warehouse computer while the shop keeps taking orders. Show waiting, working, done, or needs attention. If ParcelFox is temporarily down, try again; never send the same parcel twice.”

**Acceptance:** Separate worker command, responsive checkout while carrier hangs, durable queue after restart, bounded retry with documented defaults, and reconciliation after acknowledgement loss. Measure independent worker build/start capability without requiring separate repositories.

### 04 — Customer updates

> “Email customers when their order is accepted and when it ships. Use MailPost. If sending fails, try again later without holding up shipping, and please do not send duplicate emails.”

**Acceptance:** Both events arrive once despite retries/restarts; shipping continues during email outage. Failure state is visible and retryable. Check interleavings where email fails after label creation.

### 05 — Another carrier

> “Add QuickCrate too and let me pick the delivery company. They say their label can take a while to be ready. Show that properly, and keep ParcelFox working.”

**Acceptance:** Async readiness and recovery using polling, verified callbacks, or both, plus both carriers' existing behaviour. If callbacks are exposed, the public attachment requires rejecting unsigned callbacks and handling duplicate/out-of-order delivery. Do not require an unused completion mechanism. Record changes to already-existing shipping and order logic.

### 06 — Daily report

> “Give me a daily report of accepted orders, items sold, and order value. Let me download it as CSV. Use UTC dates, and do not count something twice just because it was retried.”

**Acceptance:** Boundary-time fixtures, deterministic CSV values, correct integer arithmetic, and no double counts from duplicate submissions or delivery events. Report semantics exclude rejected checkouts and are independent of label readiness.

### 07 — Two warehouses

> “We now have two warehouses. Use the attached stock feed, and let me choose which warehouse to try first. If it cannot supply an order, use the other one. Old stock messages should not put stock back by mistake.”

**Acceptance:** Latest-revision handling, preferred/fallback choice, correct reservation release on failure, and no inventory corruption from repeated snapshots. Test whole-order fulfilment by one warehouse at this step; do not reject a correct implementation that already supports splitting.

### 08 — Split deliveries

> “Some orders need items from both warehouses. Allow that now, with a separate label for each parcel. Tell the customer which items are in each delivery. Do not say the whole order has shipped until all its parcels have.”

**Acceptance:** Per-shipment identity, allocation conservation, mixed-carrier completion, partial failure/retry, and correct aggregate status. Earlier single-parcel orders still load and ship after upgrading stored data.

### 09 — Returns

> “Let me record that someone returned some items, put the accepted returns back in stock, and show the remaining order value in the report. It is just a record for now, no bank connection. Clicking twice must not record two returns.”

**Acceptance:** Return quantity cannot exceed delivered quantity; duplicate return reference is idempotent. Public examples define report columns as original value, returned value, and remaining value. Verify partial returns across shipments and persistence.

### 10 — Second shop

> “I am opening a second shop in the same app. Give it its own products, orders, stock, carrier settings, and staff login. Staff from one shop must not see or change the other shop's information.”

**Acceptance:** Public fixture provides two staff accounts and shop IDs. Browser/API access, exports, callbacks, worker jobs, and credentials remain scoped correctly; the first shop's existing data migrates without loss. This is deliberately a broad change.

### 11 — Keep order history accurate

> “If I rename a product or change its price tomorrow, yesterday's orders, emails, returns, and reports should still show what the customer actually bought and paid. New orders should use the new details.”

**Acceptance:** Edit product after purchase, then read/replay every named consumer. Old totals/descriptions remain stable, new orders change, and migration preserves the historical fixture's known values rather than using current catalogue values.

### 12 — Update a busy worker

> “Add a pause button for each warehouse so it can finish the parcel it is working on and leave the rest waiting. I need to update the warehouse program while orders are queued. When I start it again, carry on safely with those orders.”

**Acceptance:** Implementing the new pause control may legitimately change UI, API and worker. Check that feature normally first. Then freeze its working API/UI and queued/in-flight fixtures; rebuild and replace the worker alone using the same source with a new release identity, and resume against those existing artifacts. Completed parcels remain completed; waiting jobs retain their meaning; pause/resume is shop-scoped. Exercise documented shutdown acknowledgement loss. The sealed worker probe tests a substantive worker change later.

### 13 — Website appearance only

> “The shop page looks a bit plain. Add the two attached fonts and a choice between them. I want to put just this website change live while the shop server and warehouse program keep running exactly as they are.”

**Acceptance:** Font assets and choice work in a real browser. Build/release the frontend against the step-12 server and worker binaries; exercise checkout and tracking. Count backend checks, artifacts rebuilt, and process restarts. A passing cosmetic change must not quietly redeploy the whole system.

### 14 — Third carrier

> “Add ParcelPine using the attached instructions. I want the same choice of carriers, labels, tracking, and helpful error messages. Everything we already do with the other companies should keep working.”

**Acceptance:** Exact weight conversion, unsupported-destination handling, rate-limit retry, deduplication, tenant settings, and existing carrier compatibility. Measure core logic edits separately from new carrier code, registration/configuration, and tests.

### 15 — More currencies

> “Let each shop sell in pounds, euros, or yen. Orders must remember their currency, and reports must keep currencies separate. No conversions. Yen has no pennies. Existing orders must still look right, including old links customers have.”

**Acceptance:** Public examples define GBP/EUR with two fractional digits and JPY with zero, one currency per order, and legacy orders as GBP. Check catalogue, checkout, historical links, emails, returns, CSV, storage migration, and queued work. This shared semantic change should trigger broader verification than step 13.

## Sealed follow-up probes

Run each on its own copy of the same step-15 snapshot, using the protocol's identical maintainer setup. Probe wording and fixture names remain withheld until reveal; do not train AnaxiGraph on their solutions.

| Probe request revealed to maintainer | Evidence collected |
|---|---|
| “Add the attached large-print theme and release only the website.” | New frontend with unchanged deployed API/worker; old client compatibility; rollback; selected versus full validation cost. |
| “Add this fourth carrier; its tracking reference arrives separately from the label.” | Fresh protocol with documented capability difference; marginal implementation cost, unrelated responsibility edits, regression suite, removal of the carrier again on a separate branch. |
| “We also need the attached three-decimal currency. Keep old orders, exports, and waiting shipments working.” | Precision through every real consumer; historical/queued compatibility. Reject test selection that treats this as formatting only. |
| “Handle this newly supplied warehouse pause reason and update the warehouse program without interrupting shop orders.” | Old queued payloads, old API/new worker and rollback-compatible storage; number of independently built/deployed artifacts and resulting outages. |

## Selection traps and scale

Inject one defect at a time into disposable copies after a passing checkpoint: remove shop filtering from reporting SQL; change a queue status string without updating its reader; map ParcelPine to the wrong credential in runtime configuration; discard idempotency keys only after a timeout; change currency formatting shared by emails and CSV; break a frontend-only font asset. Each mutation must be caught by the independent full oracle before it qualifies for selection scoring. Compare the agent's declared selective CI against that oracle. Tests that merely pass after skipping the affected consumer earn no speed credit.

Use the suite's real-repository and dependency-pressure tracks for large-codebase claims. Extra warehouses, shops, and carriers must be executable consumers with distinct contracts and tests; copied inert files do not count. Report selective build/test CPU and wall time, deployment blast radius, mixed-version correctness, late extension cost, total implementation/maintenance cost, and structural diagnostics separately. Do not award points for factories, microservices, folder counts, or a low number of edited files by itself.
