---
type: note
status: draft
lifecycle: active
created: 2026-11-12
tags: [anaxigraph, evals, architecture, caseflow]
---

# Eval 3 — CaseFlow

**Question:** After repeated requests, can a new agent safely extend, diagnose, and remove document workflows without understanding or rewriting the whole application?

CaseFlow is a fictional case-document workspace. It stresses evolving source connectors, durable work, document versions, permissions, and cross-language dependencies. Use the arms, budgets, checkpointing, private evaluation, and cost accounting in [shared protocol](../../docs/protocol.md). This document specifies an evaluation; the fixtures, runner, and tests have not been implemented or executed.

## Environment and fixture contract

Fix the implementation environment across arms: Python service/background processing and a TypeScript browser interface, with the same available libraries and database. Do not supply application architecture or require separate services. All external services are fictional, local, deterministic fixtures; there are no paid APIs or real documents.

Reveal a fixture's documentation, sample responses, and failure semantics with the first request that uses it. Keep future requests, acceptance cases, and probe variants outside the coding agent's filesystem. Hidden tests vary documented inputs; they do not add requirements.

| Fixture | Public contract, revealed when needed |
| --- | --- |
| Manual files | UTF-8 text; CSV columns `external_id,title,text`; IDs unique within one source and workspace. A repeated identical row is a no-op; a conflicting duplicate is rejected. Invalid rows produce row-specific errors while valid rows import. |
| ParcelBox, step 02 | `GET /documents?cursor=…` returns `items:[{id,title,text,revision}]` and nullable `next_cursor`. Cursors are opaque. An unchanged `(id,revision)` is a no-op. HTTP 429 includes integer `Retry-After`; 401 is permanent until configuration changes. |
| PDF pack, step 04 | Small text PDFs with supplied expected text, plus scanned-image and malformed examples. No OCR requirement. Unsupported and corrupt documents must be reported explicitly. |
| NoticeSink, step 08 | `POST /messages` accepts `message_id,workspace_id,document_id,revision,recipient,text`. The fixture deduplicates identical message IDs and can return 503 before acceptance or lose the response after acceptance. Retries must reuse the same ID. Snapshot the responsible person at approval time; later reassignment does not retarget a queued message. |
| BoxLoop, step 10 | `POST /exports` creates an export job; `GET /exports/{id}` returns `pending`, `ready` with a download URL, or `failed`. Downloads are UTF-8 JSON arrays with `key,name,body,version`. Keys are scoped to a connection; unchanged key/version is a no-op. There is no streaming or incremental cursor. |
| Identity and clock | Fixed local user sessions and a controllable clock. The published role table and timestamps are authoritative; tests never depend on real waiting. |

The evaluator owns fixture logs and test outcomes. AnaxiGraph may inspect candidate code and public contracts, but its recommendations or self-reported impact graph are never grading truth.

## Consecutive requests

Deliver only the quoted text and currently relevant fixture documentation to the coding agent. Each private check below is an evaluator specification, not an additional agent instruction. Preserve all previously requested behavior.

### 00 — Initial build

> “Make me a little browser app called CaseFlow for keeping case documents together. I want to create a case, give it a name, paste in some documents, and open them again later. Ask me for a title if I leave it blank. Please keep everything when I close and restart it.”

**Private check:** Create two cases, add different documents, restart every application process, and verify persisted contents and stable document identities through the UI. Empty titles produce a useful validation error.

### 01 — Bulk intake

> “Pasting these one by one is slow. Let me upload a CSV of documents using the sample file. If a few rows are wrong, tell me which ones and still keep the good ones. Uploading the same thing twice shouldn't give me duplicates.”

**Private check:** Mixed valid/invalid rows, Unicode, quoted commas, identical replay, and conflicting IDs follow the published CSV contract. Partial failure does not silently drop good rows.

### 02 — First connected source

> “Our documents are also in ParcelBox. Let me connect it to a case and import everything, including documents beyond the first page. Sometimes it asks us to wait; show what's happening and continue when it lets us.”

**Private check:** Opaque three-page pagination, rate limiting, permanent authentication failure, and re-import. Inspect fixture calls as well as final document counts.

### 03 — Long-running work

> “Some imports take ages. Let me leave the page while they run and come back to see progress. If the app restarts halfway through, it should carry on without importing the same documents again. I also want a cancel button. It can finish the request already in progress, then stop; keep the documents it already imported.”

**Private check:** Stop processing after an acknowledged page, restart, and verify eventual completion with no duplicate documents. Cancellation stops further intake after an in-flight request finishes; already imported documents remain. Progress never reports completion before persistence.

### 04 — A second document format

> “Can I upload ordinary text PDFs too? Put their text in the same place as pasted documents. If it's a scan you can't read, or a broken file, tell me instead of showing an empty document as if it worked.”

**Private check:** Exact normalized text from supplied PDFs; explicit per-file unsupported/corrupt outcomes. Other uploads continue. No hidden requirement to recognize images or recover arbitrary damaged PDFs.

### 05 — Find documents

> “Add search inside a case. Search titles and document text, ignoring capitals, and show a short matching snippet. I should be able to click a result and open the right document.”

**Private check:** Document/title hits, non-hits, Unicode examples defined in the sample pack, and case-scoped results. Preserve original text and stable result links.

### 06 — Teams and permissions

> “Two teams will use this. Give each team its own workspace. Owners can manage members and connections, editors can add and change documents, and viewers can only read. Nobody should be able to see another team's material, even with a copied link.”

**Private check:** Fixed role matrix through UI and direct HTTP operations, including search, job status, document contents, and source configuration. Reject cross-workspace object references; changing a URL is not authorization.

### 07 — Review history

> “Editors need to mark documents approved or needing changes and leave a comment. Keep who did it and when, and the version they reviewed. If they change their mind, keep the earlier decision in the history too. Viewers should just be able to read that history.”

**Private check:** Ordered immutable decision history, actor identity, controllable timestamps, and read-only viewer behavior. Decisions refer to a specific document revision.

### 08 — Notify somebody

> “Give each document a person responsible: start with whoever added it or set up its import, and let a workspace owner change that. When a document is approved, send that person a message through NoticeSink. It sometimes goes offline, so try again later. Please don't send the same approval message twice, including after a restart. A separate later approval should get its own message.”

**Private check:** Default and reassigned responsibility determine the recipient at approval time. Approval persists despite delivery failure. Retry before acceptance and after a lost response; NoticeSink records one logical message with the same ID. A later, separate approval decision produces its own message. Reassignment follows the published recipient-snapshot rule; step 15 will add permission rechecking before delivery.

### 09 — Historical reporting

> “Show me how many approvals happened each month, with a date filter and workspace totals. Count each approval decision, including a later re-approval, using UTC when it happened. Later edits mustn't change old totals. Include the start date and stop just before the end date, and explain that beside the filter.”

**Private check:** Count approval decisions, not distinct documents; exercise month-boundary timestamps, the requested inclusive start/exclusive end dates, and historical decisions after later edits. Filtered totals respect workspace permissions.

### 10 — A different connected source

> “Another team uses BoxLoop. Add that too. It makes us request an export and wait for a download, so please show progress while it's preparing. I'd like both connections to keep working in the same case.”

**Private check:** Pending-to-ready, failed export, restart during polling, mixed sources with overlapping external IDs, and unchanged re-import. A paginated-source assumption must not corrupt asynchronous exports.

### 11 — Updated source documents

> “When a source document changes, bring in the new version and make that the one people normally open. Keep the old versions and their reviews. The new version needs its own review, and I'd like search to use the latest version.”

**Private check:** Identical revision replay, new revision, previous approved version retained, new version unreviewed, and latest-only search. Existing approval notices continue to refer to their original revision.

### 12 — Export for another team

> “Let me download a case as JSON, including document IDs, latest text, old versions, and review history. Use the example format so the other team's importer can read it. Viewers can download too, but only what they are allowed to see.”

**Private check:** Supplied JSON schema, stable identities and timestamps, complete version/history relationships, escaping, and no cross-workspace data. Empty cases export valid empty collections.

### 13 — Retire an integration

> “We're stopping ParcelBox. Remove its connection option and stop its unfinished imports. Keep everything it already brought in, including the history and exports. BoxLoop and normal uploads should carry on as before.”

**Private check:** Saved ParcelBox configuration and pending jobs cannot trigger further requests; retained documents remain readable/searchable/exportable. Remove active source support without deleting historical source identities. Measure removal cost and collateral changes.

### 14 — A small visual change

> “Use the supplied font files for the document screen and add a larger-text choice. Keep the text choice when I reopen the browser, and let me use the choice with a keyboard. It should work with our local server running and no internet access. I'd like to release this screen change while the server and imports keep running.”

**Private check:** Local font requests, computed font/size, persistence, keyboard operation, and loading without internet while the local server is reachable. No disconnected-browser synchronization is required. Check whether a frontend artifact can be built, verified, and released with unchanged server/worker artifacts.

### 15 — A genuinely shared change

> “Some editors should only see documents they are responsible for. Add a restricted-editor option, using the responsibility we already assign. For those editors, hide everything else everywhere: lists, search, copied links, history, totals, downloads, and messages. If someone loses access, don't send a message that's still waiting.”

**Private check:** Published role matrix across every named surface, both existing and new documents, owner reassignment, pending delivery after revocation, and direct HTTP calls. This request should trigger broad relevant checks; selecting only UI tests is unsafe.

## Sealed continuation probes

Branch each probe from the same completed step-15 snapshot; do not apply probes sequentially. Primary probes use a fresh coding-agent context, identical product documentation, the common charter and ordinary tools, with no AnaxiGraph or external sidecar memory for any builder arm. Original-arm assistance belongs in a separate secondary test. Reveal the complete requested behavior and new fixture contract only when the probe begins. Keep sampled cases private.

| Probe | Human request and published contract | What to measure |
| --- | --- | --- |
| C1: Familiar extension | “Add ArchiveTap as another document source.” Its cursor-paged response uses `record_key,heading,content,edition`; semantics match ParcelBox but credentials and field names differ. | Correct extension, time to first relevant code, source files read, existing responsibilities changed, and tests/builds invoked. Retired ParcelBox must stay retired. |
| C2: New capability | “Add ArchiveTap as another source. It also tells us when documents are withdrawn. Hide those from normal views but retain their history for owners.” Publish the complete source contract, ordered tombstone/reappearance events, and authorization rules. | Whether the existing abstraction can evolve without corrupting other sources; migration compatibility, broad-check recall, and justified contract changes. Do not demand zero shared edits. |
| C3: Debugging handoff | “BoxLoop imports nothing after a restart. Please fix it.” Start from a qualified fault variant in which saved source identifiers disagree with runtime registration. | Correct root cause, minimal durable repair, search/read effort, restart regression tests, and no provider-specific workaround in unrelated job logic. Fault must be reproducible before release. |
| C4: Reversible feature | “Remove JSON downloads. Keep the rest, including reporting and the documents already here.” | Successful removal, retained behavior, obsolete dependencies removed where safe, and whether shared data/history survive. Fewer lines alone do not establish a better result. |

## CI selection challenges and scale validity

On disposable checkpoint copies, inject one qualified regression at a time: wrong dynamic connector key; migration dropping a document's workspace identity; search bypassing the shared permission check; revocation omitted from pending delivery; parsing a UTC month boundary incorrectly. First establish that the full evaluator suite detects each mutation. Then run the candidate's normal change-selection mechanism and measure whether it selects checks that expose the regression. Invalid or surviving mutations are reported, not counted as selector misses.

Separate *code-created-by-the-agent* from *inherited-code* tracks. In the latter, start with a licensed, frozen, runnable application near the target scale, with real UI/API/worker/data behavior and measured language composition. Adapt prompt 00 to “Add a CaseFlow workspace to this existing application”; retain the product obligations and freeze the adaptation before arm assignment. Preserve existing application behavior with evaluator-owned checks. Use the common protocol's corpus qualification and large-repository limits; duplicated filler files provide no evidence of production-scale maintainability.

Report late-request cost (steps 10–15), continuation cost, safe test-selection coverage, independent release success, regressions, and total agent/sidecar overhead. Distinguish narrow extensions, unfamiliar capabilities, cosmetic changes, and shared authorization changes. A useful abstraction reduces repeated effort while allowing honest differences; factory counts, class counts, and AnaxiGraph's own architecture verdict receive no points.
