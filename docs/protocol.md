---
type: note
status: draft
lifecycle: active
created: 2026-11-12
tags: [anaxigraph, evaluation, architecture, ci-cd]
---

# AnaxiGraph Eval Suite — Protocol

**Deliverable:** three authored evaluation scenarios, each containing one initial build request and 15 consecutive follow-ups, with an experiment and measurement specification. **Status: specifications, not an implemented or executed benchmark.** Fixture servers, independent tests, runner bindings and large-repository snapshots must be qualified before paid campaigns. No results are claimed here.

Repository entry point: [README](../README.md). See [import provenance](provenance.md) for the original design sources and portable-link changes.

## The question this suite answers

Does access to AnaxiGraph help an agent deliver correct changes with less future effort, less unnecessary coupling, and cheaper **safe** verification and release than the same agent with a good architecture charter?

The decisive observations are subsequent changes to working software. Having a factory, a graph, many packages, or fewer lines is not itself a success. A modular monolith can perform well; a collection of services that must always release together can perform badly.

AnaxiGraph can lose a fair experiment: incorrect advice, stale maps, weak language support, over-abstraction, attention overhead, or an agent ignoring useful advice can outweigh its benefits. A benchmark that guarantees its victory cannot guide its development. Conversely, a test that never creates maintenance pressure cannot establish that architectural guidance is useless.

The workspace capability brief explicitly distinguishes shipped and intended features, notes weaker JavaScript/TypeScript evidence and runtime-wiring blind spots, and describes AnaxiGraph as read-only. This suite tests the resulting code and agent behavior independently; it does not require roadmap features or let AnaxiGraph grade itself.

## The three evals

| Eval | Product the user builds | Principal pressure | Decisive late evidence |
|---|---|---|---|
| [RelayDesk](../evals/relaydesk/spec.md) | AI-assisted customer-support desk | Providers with different protocols and capabilities; changing integration needs | Add, replace and remove providers without rewriting unrelated product behavior; isolate failures |
| [DispatchLedger](../evals/dispatchledger/spec.md) | Orders, fulfillment, shipping and reporting | Browser, server and worker releases; shared event/data contracts | Cosmetic browser release against old server; safe worker replacement with queued work; broaden checks for real contract changes |
| [CaseFlow](../evals/caseflow/spec.md) | Document intake and long-running case processing | Connector growth, durable jobs, permissions and inherited code | New developer can locate and change the right code; connector changes stay local; shared authorization changes propagate correctly |

All have 16 ordered product prompts, numbered 00–15. Names and services in scenarios are fictional fixtures. Scenario documents are **operator material**: never mount them wholesale in a coding-agent workspace.

## Experiment arms and isolation

| Arm | What the coding agent receives |
|---|---|
| A — Bare | Common environment and task instructions, ordinary repository documentation, normal search/editor/shell tools; no architecture charter or sidecar |
| B — Charter | Exactly A plus the charter below |
| C — AnaxiGraph | Exactly B plus the pinned AnaxiGraph release, its necessary usage instructions and consultation loop |

**C minus B is the primary comparison.** B minus A measures guidance. C minus A measures the combined package and must not be described as the incremental effect of the tool alone. Including the same charter in C prevents extra architectural instructions being mistaken for tool benefit.

Pin the agent/model version, reasoning setting, temperature if supported, context policy, tools, dependency image, CPU/RAM, concurrency, retry policy, request order and total resource budget. Record unavailable seeds rather than pretending API seeds make trajectories identical. Give each arm a separate checkout, database, cache and sidecar state; no shared generated advice or previous solutions. Randomize arm execution order within matched blocks. Stagger measured CI runs or reserve equal isolated resources.

In real repositories, preserve operational/build instructions for every arm. Remove only benchmark-controlled architecture guidance. If inherited architectural guidance cannot be separated, label A “existing repository guidance”; do not claim it is guidance-free.

### Concise charter, copied verbatim into B and C

```markdown
# Engineering charter

Deliver the requested behavior and preserve working behavior. Before editing,
find the existing owner of the responsibility and the contracts it participates in.

Keep unrelated responsibilities separate. Prefer the smallest design that makes
the current change and plausible next changes easy. Reuse an existing extension
point; introduce an abstraction when real variation justifies it. Keep integration
protocols and vendor-specific behavior at the edge. Represent capability and error
differences honestly. Do not add services, factories or frameworks for their own sake.

Keep public interfaces explicit and compatible. Consider stored data, events,
configuration, authorization and runtime registration as well as imports.

Make meaningful parts independently buildable and testable where practical.
Select checks from the actual change impact; broaden them when impact is uncertain.
Never suppress a necessary check to make CI faster. Preserve independent release
options where contracts allow them, and verify compatibility with deployed versions.

Use tests to protect behavior and boundaries. Keep changes reviewable. Record the
checks performed, unresolved risks and any deliberate tradeoff. Remove obsolete
code when replacing a feature, without discarding supported behavior or data.
```

For C, discover actual tool capabilities before freezing a campaign. The implementation-specific command/MCP binding belongs in a versioned runner adapter, not in these product prompts. Minimum consultation: before each request, refresh to the current source revision and obtain task context/impact; after edits, refresh and inspect consequences or available findings. If a promised surface is absent, record it and use only supported operations. Log whether advice was accepted, rejected, deferred or unused. The agent may disagree. No evaluator answers enter sidecar memory.

Count indexing, annotation/model work, refreshes, calls, reading and repairs in C's budget. Report cold initialization and warm incremental cost separately. Discretionary use can be a later deployment-realism experiment; do not mix it with this defined treatment.

## Common public environment

Use the same pinned environment within each scenario: Python backend/worker and TypeScript browser where those surfaces are required; framework, package layout and process boundaries are the agent's choices. Do not compare different stacks across arms. A Python-only variant is a separate stratum, useful for distinguishing product limits from benchmark effects.

Provide ordinary build/run instructions, dependency locks, local fictional external services, credentials that work only against those fixtures, example data, and a browser. No live LLM, email, payment or shipping account is needed. Fixtures have deterministic error sequences, replayable clocks and seeds. Protocol documentation appears with the request introducing the service, including all behavior that hidden tests will require. Unknown requirements cannot be invented by the evaluator.

The common technical envelope says:

> Implement the user's current request in the supplied environment and preserve earlier requested behavior. Supply commands to start the app, build artifacts, run all checks, select checks for a change, and release locally. A full-suite selector and a single release artifact are valid starting points. Use the supplied test services. Work autonomously within the recorded budget; document assumptions when needed.

This asks every arm for observable operations without teaching the desired architecture. A thin harness adapter normalizes these commands; it must not partition the agent's application or implement selection on its behalf.

## Sequential run procedure

1. Qualify the runner: shell/edit/build/browser access, fixture reachability, local release permissions, deterministic baseline checks, checkpoint/restore and sidecar operation. Run a trivial request through every arm. An infrastructure failure is not a model result. A prior development campaign completed zero request steps because shell sandbox initialization failed; qualify shell access before spending on model runs.
2. Start each matched block from identical inputs. Give only prompt 00 and its public fixtures. Reveal 01–15 one at a time after the previous turn terminates; never preannounce future features or scoring probes.
3. Continue the same conversation to mimic ordinary iterative coding. Freeze a common context rollover rule; any summaries come from the arm's own history and count toward its cost. Do not give one arm a hand-written architecture summary. Retain repository history in every arm.
4. Each request ends at agent completion or its resource cap. Permit at most two repair turns using **public** CI feedback, within the same total request budget. Record the unrepaired patch, repairs and final snapshot. Evaluator-only audit results are not fed back during the trajectory.
5. Commit/checkpoint every resulting state and record a hash of the dirty tree if a commit cannot be created. Save tool transcripts, processes, tests, built artifacts and local release manifests. Nothing goes to a real production environment.
6. Continue all 16 scheduled requests even when a feature fails, preserving the resulting state; never silently restore a stronger arm's solution. Classify later failure dependencies. A crashed unrecoverable run remains an incomplete trajectory, with downstream success counted as absent. Report infra-invalid blocks separately and rerun all matched arms under the preregistered rule.
7. Independently audit all active cumulative requirements at every checkpoint. Maintain a frozen requirement lifecycle: a later explicit request can supersede earlier behavior. Retiring Comet or ParcelBox removes new-use requirements while retaining historical-data obligations; a probe removing JSON export supersedes export availability. Requested removals are not regressions. Distinguish “working at the end” from “remained working throughout.” Report completion and regression rates across **all** attempted trajectories before conditional efficiency statistics.
8. After step 15, run the sealed probe families in each scenario on separate copies of that snapshot. Use a fresh maintenance agent, the same charter and ordinary tools for all copies, with **no sidecar** in this primary inheritance test. This isolates the maintainability of the produced code. A second, separately reported test can give maintainers their original arm's assistance to measure assisted productivity.

Checkpoint probes can also branch at 05 and 10 without changing the main trajectory. Use equivalent withheld probe variants at each checkpoint to estimate how maintenance cost grows; do not compare easy early features with harder late features and call the difference architectural decay.

### Budget and replication defaults

These are proposed operating defaults, not a power calculation or permission to start spending:

- Qualification: one short smoke run per arm, then one full development trajectory per scenario/arm to find ambiguous tasks and broken fixtures. These runs are excluded from confirmation.
- Pilot: 3 matched replicates × 3 scenarios × 3 arms = **27 trajectories, 432 ordinary request turns**, plus explicitly budgeted repairs and probes.
- Start with 30 elapsed minutes and 60,000 billable input-plus-output tokens per request, including sidecar model work. Token and time caps both apply; record cached input separately and actual monetary cost from the run's billing metadata. If the runner cannot enforce total usage across tools, use a measured cost ledger and hard time cap; do not claim equal token budgets.
- Probes use the same per-request cap. Freeze caps after qualification; do not increase them only for a losing arm. Preregister a total campaign monetary ceiling before execution.
- Use pilot variance and the smallest useful effect to size confirmation. A starting planning quantity is 10 matched trajectories per scenario/arm; **10 is not a claim of sufficient statistical power**. Large-repository confirmation is a separate budget.

## Correctness and safe selection are the gate

A completed request must satisfy its published behavior, preserve active previous requirements, pass candidate CI and the independent cumulative audit, and pass any release rehearsal explicitly required at that step. Missing features, disabled validation, skipped migrations, wrong-tenant data, duplicate side effects and lost jobs are failures even if CI is green. Always-red CI cannot deliver a change; unexplained red exits are not successful fault detection. Report clean-change false rejections, including release rejection, and credit efficiency only for successfully delivered audit-correct changes.

Every checkpoint has two runs on clean, identically provisioned copies:

- **Candidate CI:** the repository's actual change selector and its chosen checks, exactly as the proposed workflow would execute.
- **Audit:** the full candidate suite plus evaluator-owned functional, compatibility and adversarial checks, outside the measured candidate-CI critical path. Audit cost is still reported as benchmark expense.

Do not reward a small suite for being incomplete. Fixed evaluator cases anchor functional coverage, independent of how many tests an arm writes. Candidate tests may evolve, but prior assertions and deletions are logged; tests removed without equivalent protection are flagged. Evaluator files and expected values are inaccessible to the coding agent.

### Selection challenge procedure

At eligible checkpoints, inject one semantic fault at a time into isolated copies of a working snapshot. Freeze a library of mutation **intent**, such as “a serialized field loses its unit,” and use reviewed per-implementation patches; identical textual patches cannot be assumed to apply to different architectures. Reviewers are blind to arm labels. Preserve syntax/build validity unless build detection itself is the specified challenge.

For each mutation, record the baseline passing audit, changed files/configuration, selector output, selected-check result, full candidate-suite result, independent audit failure, and exact artifact hashes. Qualify a mutation as behavior-changing only if the corresponding evaluator case fails. Equivalent, inapplicable or flaky mutations are excluded with reasons; report counts by arm so exclusions cannot hide weak coverage.

Classify qualified cases:

| Result | Interpretation |
|---|---|
| Selected CI fails with the expected build/test assertion | Detected before release |
| Selected CI passes; full candidate suite fails | Selection miss |
| Selected CI and full candidate suite pass; independent audit fails | Candidate test-coverage gap |
| Selector/build crashes for an unrelated infrastructure reason | Invalid detection evidence; investigate/repeat |

Both selection misses and coverage gaps are **unsafe greens**. Cheap CI with unsafe greens cannot win on safety. A selector that always runs everything can be safe but inefficient. Add clean cosmetic changes and compatible connector additions as negative controls; blanket rejection or blanket full rebuilds must show their cost.

Include shared types, API schemas, SQL migrations, runtime registrations, environment defaults, queue payloads, generated clients, lockfiles and shared build configuration. An import graph alone is not the oracle. Zero observed misses means zero on the qualified challenge set, not a universal safety guarantee.

## Measures and exact interpretation

Use a vector of outcomes, not one architecture score. Report distributions and paired differences, not only means.

| Measure | Operational definition | Why it matters |
|---|---|---|
| Functional completion | Accepted requests / 16; additionally all-requirements pass at step 15 and cumulative regressions | Prevents cheap incomplete implementations winning |
| Unsafe-green rate | Qualified faulty changes with candidate CI green / all qualified faulty changes; split selection misses and coverage gaps | Tests whether reduced checking remains useful |
| False rejection | Audit-correct clean changes rejected by candidate CI/release / all qualified clean controls | Prevents an always-red selector winning |
| Independent release success | Passed eligible release rehearsals / all scheduled eligible rehearsals, with missing features recorded as failures | Distinguishes real independence from folder structure |
| Late maintenance effort | Wall time, agent/model cost, input bytes read, commands and repair turns for each fixed withheld probe | Measures the cost paid by the next developer |
| Verification work | Sum of measured CPU-seconds and job-seconds of executed build/test/setup work, plus counts | Avoids equating one tiny test with one integration job |
| Verification latency | Wall time from CI start through the last required check, at fixed concurrency; cold and warm | Measures developer waiting time |
| Release latency | From accepted patch through selected build/check/publish-to-local-registry/rollout/health verification | Covers CD, not only pytest runtime |
| Safe work reduction | 1 − candidate selected work / full candidate work on the same revision and cache profile; also show both absolute values and audit adequacy | Within-repository CI opportunity; ratios alone can be gamed by inflating full suites |
| Release blast radius | Artifacts rebuilt, artifact digests changed, services restarted, databases migrated, consumers retested per local request | Makes hidden coupling observable |
| Change breadth | Existing files touched **and** evaluator-mapped responsibilities touched; separate core behavior, adapter, composition/config, tests and docs | Prevents one giant file or arbitrary file splitting gaming locality |
| Core intrusion | Semantic edits to existing orchestration/domain/consumer behavior for each new connector; separately count registration/manifest edits | Measures whether an abstraction actually absorbs variation |
| Integration slope | Probe effort and core intrusion versus number of installed integrations; report within-family differences at 05/10/15 | Tests whether the next connector gets expensive |
| Parallel work | Two independently produced local patches from the same base: merge conflicts, post-merge failures, resolution time and ability to release separately | Measures concurrent development, not merely parallel CI |
| Navigation | Time/bytes to first correct owning location; validated consumers/contracts found; unsupported claims | Tests the code-map hypothesis separately |
| Structural diagnostics | Production/test/config LOC separately; gross added+deleted LOC across commits; duplication, complexity distribution, module fan-out, SCCs and transitive reach | Explains results without substituting for them |
| Total cost | Agent + sidecar + indexing + refactoring + all retries; CI compute and runtime dependencies separately | Prevents amortization hiding expensive setup |

“Responsibility” means an observable product concern such as drafting, shipment booking or authorization, mapped by an arm-blinded reviewer from endpoints, state ownership and behavior. Record mixed-responsibility files rather than forcing each file into one arbitrary bucket. Check reviewer agreement on a sample and keep disputed mappings visible. For cycles, specify file and package graphs, resolver/version, language coverage and unresolved edges. A renamed directory does not reset coupling.

Measure LOC with one pinned counter; exclude vendor, generated clients, fixtures, migrations generated by tooling and binaries from authored production LOC, but report their totals separately. Include hand-written migrations in authored counts. Report net surviving lines **and** gross churn: a costly rewrite can leave a very small final repository. Do not reward a particular factory count or class hierarchy.

For reproducible structural diagnostics, report cyclomatic complexity per function (median, p95 and maximum, with analyzer rules pinned), largest authored module, duplicate-token fraction, direct fan-in/fan-out, and strongly connected component count and largest component. For a resolved graph of N components, report propagation cost as the number of reachable ordered component pairs divided by N(N−1), excluding self-pairs; unresolved edges and language coverage accompany that number. Keep the component definition fixed and also report a file-level graph. These are explanatory metrics: a legitimately shared authorization component can have high reach.

Run a parallel-development probe by taking two independent changes from the same base: RelayDesk's new service plus header appearance; DispatchLedger's new carrier plus theme; CaseFlow's new source plus document-screen spacing. Generate each patch independently, merge in both orders on disposable copies, then run the audit and eligible separate-release rehearsals. Record conflicts and integration repair work without requiring zero conflicts for every valid implementation.

### Release rehearsal

Keep the prior known-good UI, API, worker, schemas and stored data as versioned artifacts. Deploy only the candidate component to an isolated local environment while other components remain at their previous versions. Run mixed-version behavioral checks, verify the expected artifact changes, perform a rolling update with queued/in-flight work where relevant, and exercise rollback if the migration is declared reversible. Record coordinated releases honestly when required. A dummy “deploy” script copying a success marker is invalid.

At each release request, publish the required compatibility window and retained data/queue examples with its fixture attachment. For cosmetic changes, this is the immediately preceding server/worker version. For a breaking shared-contract change, require existing stored data and queued work to survive; allow a declared coordinated rollout or staged compatibility migration rather than secretly requiring every old/new version combination. Score actual independence separately. Persisted-payload fixtures are created through the old running application, so tests need not assume an internal table or queue schema.

For a fonts-only change, no server/worker artifact should need rebuilding or restarting; UI packaging and a relevant compatibility/smoke check may still be required. For a genuinely shared authorization or event-contract change, broader checks are correct. Do not impose a universal “under 10% of tests” target.

Cached compatibility evidence is valid only for the exact relevant content/version/configuration inputs. The principle of checking a candidate against versions actually deployed is also used by Pact's compatibility matrix; this suite requires the behavior, not the Pact product. [Pact: Can I Deploy](https://docs.pact.io/pact_broker/can_i_deploy)

### Timing protocol

Measure at least five repetitions of CI/release rehearsals after correctness qualification, randomized between arms. Report median and range; only report p95 when enough observations support it. Pin runner resources and maximum parallel jobs. Include scheduling/setup/container startup in wall time and separately report compute. Use clean cold caches and a precisely defined warm cache restored from the preceding checkpoint; do not reuse the audit's warmed cache. Track compilation, dependency installation and test execution separately.

Build-system dependency queries can expose reverse dependencies and paths, but are evidence about the declared graph rather than proof that every runtime dependency is modeled. [Bazel query quickstart](https://bazel.build/query/quickstart)

## Demonstrating relevance at 300,000 lines without generating them

Use three explicitly separated tracks. Only the last can substantiate a claim about maintenance on real repositories of that size.

### G — Architecture growth, all 16 prompts

Start from a minimal environment with no product implementation. The agent builds the product through 00–15. This measures choices that accumulate during growth. Report actual size; make no 300k extrapolation from a 4k result. If all arms find simple clean designs, increase the diversity of evolution requirements in the **development split**, not hidden difficulty after viewing confirmation outcomes.

### S — Controlled topology and workload stress

Build and freeze a reusable seed once, independently of the experiment arms. Use functioning API, worker, UI, data, identity, reporting and integration areas, with public behavior and tests. Vary (independently) irrelevant repository breadth, number of consumers sharing a contract, number of integration variants, dynamic wiring and test-work distribution. Suggested levels: 8/32/96 responsibility areas, 2/8/24 consumers and 2/8/24 integration instances. Run a fractional design, not the entire Cartesian product.

The background must contain actual executable work and meaningful variation. Cloned files, arbitrary sleeps, duplicate tests and generated padding cannot count as realistic scale. Freeze both an initially well-separated seed and a moderately tangled but functional seed; every arm gets the same seed within a block. This distinguishes prevention from repair and avoids secretly giving the treatment the answer.

Use these fixtures to estimate how selection breadth, navigation, index refresh and maintenance work respond to controlled pressure. A weighted CI schedule can simulate expensive jobs using independently measured job durations, but label the output **modeled latency**, publish its scheduling assumptions, and never present it as measured production CI time.

### R — Real inherited repositories around 300k authored lines

Use existing repositories and history. The evaluated agent writes only the requested deltas. This is the direct solution to the generation-cost problem.

Before confirmation, freeze at least three eligible repositories, one supporting each scenario's product surfaces, with recorded commits, license/authorization, language mix, build image, passing baseline and non-generated authored LOC. Target roughly 200k–500k lines, including at least one above 300k; report the exact counts. Do not call a 300k checkout “300k production lines” when most are dependencies/tests. The user's floThink codebase is a relevant candidate **when its code is separately mounted and authorized**. No large application snapshot ships with this suite, and no source access or measured size is claimed.

For each repository, map the scenario's feature sequence onto a new product area or an existing incomplete area. Preserve the request intent and record every adaptation before seeing arm results. Include existing consumers outside the modified area. Have a maintainer verify that tasks are realistic, do not already exist, and can be completed without rewriting the repository. Freeze a scenario-to-repository capability map and public fixtures. This mapping is an explicit benchmark-construction requirement, not a claim that these new-app prompts run unchanged in any repository.

A cheaper first large-repository test uses four sealed maintenance probes per repository from one identical snapshot, rather than asking agents to rebuild existing features. Call that **inherited maintenance**, not a 16-turn growth result. Subsequently run the adapted longitudinal sequence where feasible. Archive original build/test workloads and old artifacts; measure real candidate CI and release behavior with unchanged neighboring consumers.

Isolate code quality from tool assistance: run both (a) common fresh maintainers on products built by A/B/C, and (b) different assistance arms on the **same** large inherited snapshot. The former tests architecture produced; the latter tests navigation/change assistance. Do not mix their conclusions.

Preexisting issue-repair benchmarks demonstrate the practicality of pinned repository snapshots, problem statements and before/after regression cases; SWE-bench documents these fields explicitly. They do not by themselves establish long-horizon architectural quality. [SWE-bench dataset structure](https://www.swebench.com/SWE-bench/guides/datasets/)

**Evidence ladder:** G supports growth claims; S supports controlled scaling mechanisms; R supports measured large-repository maintenance claims. All three together are stronger than any alone. Neither synthetic LOC nor extrapolated hours substitutes for R.

## Statistical comparison and iteration discipline

Freeze a development set, a validation set and a locked confirmation set by scenario variants and repository snapshots. Future request text, test data, mutation locations and probe instances are hidden from the coding agent. The templates in this package are visible to the tool developer, so they are **development material**, not an untouched final holdout. An independent evaluator must instantiate and retain fresh confirmation cases. Do not tune AnaxiGraph on a confirmation failure and reuse that case as unseen evidence.

The unit of independence is the complete trajectory/repository block, not each test or each of 16 correlated steps. Pair results by scenario, starting commit and replicate. Report per-scenario effects first; use a cluster bootstrap or hierarchical analysis over complete trajectories for intervals. With only three scenarios, uncertainty about other domains remains even with many runs. Never treat thousands of tests as thousands of independent experiments.

Preregister useful differences before confirmation. The two benefit endpoints are (1) total billed agent-plus-sidecar cost of the fixed late maintenance probes and (2) end-to-end safe release latency, including CI. CI-only latency and maintenance wall time remain secondary, preventing selection of whichever measure looks best afterward. Suggested decision policy: no new observed critical safety failures; completion noninferiority within a 5-percentage-point margin supported by its interval; and at least a 20% reduction in one benefit endpoint against B, with the improvement interval excluding zero and the interval excluding a regression greater than 10% on the other endpoint. These are proposed business thresholds, not established constants. Low sample size or wide intervals produce “inconclusive,” not “equivalent.” Correct for testing two primary benefit outcomes, for example Holm correction, and retain scenario-specific failures.

Report cost and safety for all trajectories. Conditional comparisons among fully correct paired snapshots are useful but must accompany completion/failure results to avoid survivor bias. Failures do not become zero-second successful changes. Also report success within the fixed cap and capped time-to-success so unsuccessful runs remain visible.

For diagnosis after the primary comparison, run separately labeled ablations: charter + graph/navigation only; charter + recommendations only; full AnaxiGraph. Record factual map quality, freshness, advice uptake, time spent and outcomes. A useful map with ignored advice suggests an interaction problem; adopted incorrect advice suggests product reasoning problems; sound advice with no incremental benefit suggests the charter/model already handles that workload. These are testable explanations, not excuses to discard losses.

Use a simple lifetime cost calculation alongside raw measurements: setup + feature-development + refactoring + maintenance probes + CI/release compute. If a larger initial investment pays off, estimate the break-even number of comparable later changes and state the workload assumption. Do not amortize against imaginary thousands of future requests.

## Runner contract and implementation handoff

The benchmark runner must implement these logical operations; names below are a proposed harness interface, **not existing AnaxiGraph commands**:

```text
prepare(frozen_run_manifest) -> isolated checkout, fixtures, environment
reveal(step_id) -> current user prompt and current public fixture docs only
run_agent(arm, budget) -> final tree, transcript, resource ledger
checkpoint() -> source hash, artifacts, database snapshot, command manifest
run_candidate_ci(base, head, cache_profile) -> actual jobs/results/timing
audit(snapshot, cumulative_requirements) -> evaluator-owned verdicts
rehearse_release(old_snapshot, new_snapshot, probe) -> compatibility evidence
probe(snapshot_copy, withheld_request, common_maintainer) -> measured change
challenge(snapshot_copy, qualified_mutation) -> selected/full/audit comparison
report(matched_blocks) -> raw records, paired estimates, limitations
```

[`requests.jsonl`](../requests.jsonl) at the repository root contains the 48 authored user prompts for an operator's delivery queue. Each record has scenario, step, title and user text; it excludes evaluator checks. It is not safe to expose the whole queue to the coding agent. The runner must reveal one record and the corresponding public fixture attachments at a time. Attachments and private cases still need implementation from the scenario specifications.

The command manifest records argv arrays and working directories for start/build/full-checks/select-checks/local-release/rollback, environment references, output artifacts and job prerequisites. The selector emits a job plan with reasons, not just “safe.” Capture the actual executed jobs to detect discrepancies. Keep a full-suite fallback; absence of a usable selector means full-suite behavior, not zero CI cost.

An implementation-ready run manifest must freeze: suite version; scenario/track/variant; starting source hash; fixture and oracle hashes; model/agent/AnaxiGraph versions; charter hash; tool permissions; context/repair policy; all budgets; hardware and parallelism; cache profile; timing repetitions; randomized order; required public behaviors; eligible probes and mutation families; significance and decision policy. Missing entries block campaign qualification, not completion of this design document.

Per-step machine records should include:

```json
{
  "suite_version": "0.1.0",
  "run_id": "assigned-by-runner",
  "scenario": "relaydesk",
  "track": "G",
  "arm": "C",
  "replicate": 1,
  "step": 0,
  "source_before": null,
  "source_after": null,
  "outcome": "not_run",
  "requirements_passed": null,
  "requirements_total": null,
  "agent_seconds": null,
  "agent_tokens": null,
  "sidecar_seconds": null,
  "sidecar_tokens": null,
  "total_cost": null,
  "selected_jobs": [],
  "full_jobs": [],
  "ci_seconds": null,
  "ci_cpu_seconds": null,
  "cache_profile": null,
  "release_evidence": [],
  "changed_files_by_role": {},
  "responsibilities_changed": [],
  "mutations": [],
  "raw_evidence_refs": []
}
```

Null means unmeasured, never zero. Each test verdict must resolve to logs, inputs and immutable snapshot hashes. Currency and provider billing basis accompany `total_cost` in real records. Raw transcripts may contain private source and must remain in the authorized experiment store.

## What to build first

Implement the local fixture services and independent acceptance cases for one scenario, then qualify the runner and the selected/full/audit distinction. Exercise a deliberately full-suite solution, a sound selective solution, and an unsafe “skip everything” solution: the instrument must separate all three before any tool comparison. Include one deliberately over-abstracted solution so architectural ceremony alone cannot win.

Then run the three-scenario development pilot, freeze the protocol corrections, construct the large inherited-repository cases, and run confirmation on unseen instances. This package supplies the tasks and decision rules; it does not claim that the still-unbuilt instruments or any treatment have passed them.
