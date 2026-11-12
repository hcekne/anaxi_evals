---
type: note
status: draft
lifecycle: active
tags: [anaxigraph, evaluation, architecture, integrations]
---

# Eval 1 — RelayDesk

**Purpose:** test whether architecture advice makes successive integrations cheaper to add, change, diagnose and remove while preserving behaviour. Follow [shared protocol](../../docs/protocol.md) for arms, budgets, scoring and scale tracks. This is an evaluation specification; fixtures, hidden tests and runner have not been implemented or executed.

RelayDesk is a small browser helpdesk with AI reply drafts, knowledge search and order lookup. The architecture remains the coding agent's choice. No points are awarded for classes, factories, interfaces, service count or particular directories. A simple implementation wins if it remains correct and inexpensive to extend.

## Delivery and public fixtures

Deliver only the current numbered prompt and its current attachments. Future prompts, evaluator checks, mutations and probes remain outside the coding agent's filesystem and context. All tests enforce behaviour stated in prompts or public contracts. They must not require an undisclosed architecture, API name or UI layout. Public test bindings describe how the harness starts the app and operates its exposed UI/API; they do not prescribe implementation boundaries.

Use the protocol's pinned stack. External services below are fictional, deterministic local HTTP servers supplied by the harness. They record requests, support programmable errors and virtual time, and require no paid APIs. The fixture bundle documents every released request/response, error code and capability with executable examples. Release capabilities when needed, rather than letting a future provider leak into an earlier task.

| Release | Attachment contract supplied to agent |
| --- | --- |
| 00 | Ticket CSV: `id,customer_email,subject,body`; three synthetic tickets. |
| 02 | Pollen: `POST /draft`, bearer token, `{messages:[{role,content}]}` → `{text,request_id}`. |
| 03 | Comet: `POST /compose`, `X-Api-Key`, `{conversation:[{speaker,text}]}` → `{completion:{body},id}`. |
| 04 | Two synthetic teams and credentials; each provider records which team credential was used. |
| 05 | Pollen streaming: `POST /draft/stream`; SSE `delta` events with text and one `done` event. Comet remains non-streaming. |
| 06 | Knowledge: `GET /articles?q=...&team=...` → article IDs, title, text and URL. Tenant credentials determine access. |
| 07 | Orders: `GET /orders/{id}` → `{id,status,total_cents}`; all initial orders are USD. Caller credentials scope records to a team. |
| 08 | Both providers: 429 with integer `Retry-After`, 503 temporary failure, 401 invalid credentials. Prescribed retry limit: two retries after the initial call; never retry 401. |
| 09 | Harbor: `POST /jobs` → `{job_id}`; `GET /jobs/{id}` → pending or `{state:"complete",answer}`; `DELETE /jobs/{id}` cancels. Poll at most once per virtual second. No streaming. |
| 10–11 | Worker restart, virtual clock and provider request tracing. A durable job ID identifies one user submission; cancellation behaviour is specified below. |
| 12 | Quartz: `POST /responses`, bearer token, typed `{input:[{type:"text",text}]}`. SSE events are `text_delta`, `citation`, `completed`; citations are separate from text. No job polling or order-tool execution. |
| 14 | Two locally supplied font files and a public browser font-loading check. |
| 15 | Orders v2: `{id,status,money:{minor_units,currency}}`; supported currencies USD/EUR with two decimal places and JPY with zero. Existing v1 saved results remain USD. |

Fixture records deliberately use different content lengths, non-ASCII text, missing optional metadata and distinct credentials. Exact answer prose is deterministic fixture output, so tests check preservation and presentation without judging model writing quality.

## Sequential user prompts and evaluator checks

The quoted paragraph is the user prompt. The following check text is evaluator-only.

### 00 — Build the first helpdesk

> “Make me a little helpdesk website called RelayDesk. I want to upload this CSV of customer messages, see an inbox, open a message and write a reply draft. I don't need it to send emails. If a file cannot be read, tell me and keep the tickets already there. Please make it runnable on my laptop and include a way to check that it works.”

Check: all three tickets load; opening one shows its own body; draft editing does not alter another ticket; no outbound email occurs. Invalid CSV produces a useful error without erasing existing tickets.

### 01 — Keep work and find tickets

> “Please keep the tickets and my drafts when I close and reopen it. Add a search box for the subject or customer's email, and let me mark a ticket closed and show it again later.”

Check: process restart preserves edits and status; search matches both named fields; closed tickets can be reopened; empty search restores the list.

### 02 — First AI provider

> “Can it suggest a reply using Pollen? I've attached their connection details. Put a button next to the draft. I want to review the suggestion before using it, and keep anything I already typed unless I choose to replace it.”

Check: correct Pollen request, ticket-specific content, visible suggestion, explicit replacement and unchanged manual draft before acceptance. Errors retain the draft.

### 03 — A second choice

> “Add Comet as another option, using these instructions. Let me choose either one when asking for a suggestion, and remember my usual choice. Everything else should work the same.”

Check: each provider receives its own documented protocol; preference persists; switching providers preserves ticket and draft state. Measure extension cost without penalising justified abstraction introduced here.

### 04 — Two separate teams

> “Two support teams will use this. Give each team its own tickets, drafts, saved provider choice and connection details. A person from one team mustn't be able to see the other team's stuff, even by copying a ticket link.”

Check: UI and direct requests enforce isolation; provider calls use the active team's key; changing preference or credentials in one team leaves the other untouched. Fixtures define a simple test sign-in; production identity integration is outside scope.

### 05 — Show replies arriving

> “Pollen can now show the reply as it arrives. Please do that so people aren't staring at a blank box. If I pick Comet, just show a working message until its reply is ready. Don't lose my original draft if something fails.”

Check: Pollen chunks become visible before completion and assemble exactly once; Comet is never sent an unsupported streaming call; interrupted streams show failure and cannot masquerade as completed suggestions.

### 06 — Answers from our help articles

> “Let people search our help articles and include the ones they select when asking for a reply. Show links to those articles beside the suggestion so the person can check them, and keep the links when they accept it. Use this article service.”

Check: selected article text enters the provider request; unselected articles do not; source links persist with accepted drafts; team isolation applies to search and direct article access.

### 07 — Look up an order

> “Most messages are about orders. Let the person enter an order number, fetch its status and total from this service, and choose to include that in the reply request. Show the total in dollars. Never fetch an order unless they ask.”

Check: documented order lookup, explicit consent, correct USD formatting, optional inclusion in AI context, correct team credentials, and clear missing-order handling.

### 08 — Handle outages

> “Sometimes these AI services are busy. Please retry temporary failures twice, respect their ‘try again in this many seconds’ message, and tell me clearly when it still hasn't worked. A bad connection key shouldn't keep retrying. Stick with the service I chose and keep my work safe.”

Check: exact maximum attempt count and virtual-time delays for supplied statuses; no retries on 401; no automatic provider switch; neither manual drafts nor completed suggestions are lost.

### 09 — A slow third provider

> “We want Harbor too. It gives you a job number and you have to come back for the answer; their notes are attached. Show that it's working while we wait. It doesn't do the word-by-word display, and that's fine.”

Check: submit once, poll as documented, display final answer and preserve existing capabilities; no fabricated streaming. Record changes to existing providers and shared consumers separately.

### 10 — Work through a batch

> “Let me select up to ten tickets and ask for suggestions in the background. I should be able to leave the page and come back. If the app restarts halfway through, the finished suggestions should still be there and unfinished tickets should carry on.”

Check: persistent job status and results, bounded batch size, restart recovery, isolation and no duplicate accepted draft. A retried external request is permitted where a provider lacks deduplication; count it and forbid duplicate visible outcomes rather than demanding impossible exactly-once transport.

### 11 — Stop unwanted work

> “Add a stop button for an unfinished suggestion, including ones in a batch. Once I stop it, a late answer mustn't appear in my draft. For Harbor, tell their service to cancel too. Stopping one ticket mustn't stop the others.”

Check: cancel before dispatch, during streaming and during polling; Harbor cancellation request; late-result rejection; other tickets continue. Completed suggestions remain unchanged.

### 12 — Fourth provider with different output

> “Please add Quartz using the attached notes. It sends the words and article references separately. Show both properly. It can't look up orders itself, so include only the order information the person has already fetched and chosen to use.”

Check: typed input, separate citation rendering, text assembly, correct existing-context inclusion, no unsupported tool or poll calls; all earlier provider tests still pass. This is the principal late integration-cost measurement.

### 13 — Retire Comet

> “We're dropping Comet. Remove it from new work, but keep old suggestions readable with the name of the service that made them. If someone had Comet selected, ask them to choose another option. Don't silently send their message somewhere else.”

Check: no new Comet calls; old records readable; obsolete preference handled explicitly; remaining providers work without Comet credentials or runtime dependency. Assess deletion cost and residual coupling.

### 14 — A small visual release

> “Give the inbox a font menu with these two supplied fonts. Remember my choice in this browser. Nothing about tickets or replies should change. I'd like to put this visual update live while the reply jobs already running carry on.”

Check: actual loaded font and browser preference; no changed API, worker or stored-data behaviour; running jobs survive the release. Verify the built frontend against the previous backend/worker versions and record what actually required rebuilding, testing and deployment.

### 15 — A change that really crosses boundaries

> “Our shops now sell in dollars, euros and yen. The order service has changed as described here. Show the right currency and amount wherever an order appears, including the information sent for a reply. Old saved orders were all dollars and must still display correctly. Keep jobs already waiting in the queue working during the update.”

Check: USD/EUR cents and JPY integer amounts, no assumed currency conversion, provider input and UI agree, old persisted records and queued jobs remain interpretable. Test mixed old/new deployment versions according to the public release contract. Broad necessary verification is correct here; minimal test count alone must not win.

## Sealed probes after prompt 15

Fork the same final snapshot for each probe; do not accumulate their effects. Primary probes use the protocol's common fresh maintainer: identical charter and ordinary tools, without AnaxiGraph or its external memory, regardless of the builder arm. Original-arm assistance is a separate secondary experiment. Fix private variants before experiment runs.

| Probe prompt template | Evaluator objective |
| --- | --- |
| “Add this fifth reply service; its instructions are attached.” | Supply a new documented protocol with one familiar and one changed capability. Measure accepted change cost and edits outside integration/wiring boundaries; run every existing provider contract. |
| “Only change the accent colour and spacing of the inbox header.” | Verify a frontend release with old backend and worker artifacts, compare artifact hashes and detect unnecessary backend verification versus unsafe omissions. |
| “Quartz now names one of its events differently; here's the updated specification.” | Provider-local repair must preserve every other provider and existing saved suggestions. Measure localisation and diagnosis time. |
| “The order service now returns currency amounts this way; keep existing drafts and queued work usable.” | Use a predeclared compatible variant requiring consumer updates. Reward correct impact discovery and compatibility, not unjustified isolation. |

## Adversarial qualification and interpretation

Freeze the candidate selector, then inject faults into disposable copies and recompute its plan for each faulty diff: map a provider name to the wrong implementation in runtime configuration; swap a team's credential lookup; corrupt a terminal streaming event; drop the cancellation-state check; misread JPY as cents; remove an old-record compatibility branch. Full hidden verification must demonstrably detect each applicable fault before using it to evaluate selected-test detection. A selector that skips all tests is fast and unsafe, not successful.

The expected signature is a modest investment in shared behaviour followed by low marginal extension cost, preserved capability differences, reliable cancellations and safe local releases. Record early investment as well as late savings. AnaxiGraph loses this comparison if its advice adds machinery without lowering accepted-change cost, misses dynamic wiring, or makes test selection unsafe. Aggregate results belong in the shared protocol; this scenario alone cannot establish performance at 300,000 lines.
