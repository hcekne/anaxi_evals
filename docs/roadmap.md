# Implementation and qualification backlog

This is the development backlog for suite 0.1.0. The [catalog](../catalog.json) records current readiness. The [protocol](protocol.md) defines the intended experiment; checking off a document does not establish that its instrument works.

## Available now

- Three scenario specifications, 48 sequential user prompts and 12 maintenance-probe families.
- A shared protocol, experimental charter, machine-readable catalog and prompt queues.
- Prompt retrieval/export, deterministic regeneration, consistency checks and tooling tests.
- Contributor guidance, version history and experiment/improvement templates.

## Build next, in order

1. **Qualify one scenario end to end.** Start with RelayDesk unless implementation evidence favors another. Implement deterministic local services, CSV/data packs, font assets and versioned public contracts. Release each attachment at its introducing step, including its documented failure behavior. Publish no future fixtures early.
2. **Implement independent behavioral oracles.** Exercise UI/API/worker behavior and fixture-side effects. Preserve a cumulative requirement lifecycle through additions and explicit removals. Tests must not depend on a preferred architecture or undocumented business rule.
3. **Bind the runner and sidecar.** Pin environment, actual supported AnaxiGraph operations, arm instructions, costs and budgets. Implement isolation, one-at-a-time reveal, public repair feedback, checkpoints and fresh-maintainer forks. Prove shell, browser, fixtures and checkpoint recovery work for every arm before model spending.
4. **Implement safe CI and release instrumentation.** Capture actual selected jobs, full candidate tests and independent audit separately. Measure cold/warm work, artifact changes, mixed-version behavior, queue persistence and release latency. Qualify mutations before judging selectors.
5. **Qualify the measuring instrument.** Distinguish full-suite, sound-selective, unsafe-skip-everything, always-red and over-abstracted reference implementations. Failures and exclusions must remain visible. A green package validation is insufficient.
6. **Expand to all three growth scenarios.** Complete DispatchLedger and CaseFlow fixtures/oracles; run development pilots within a separately agreed campaign budget. Log ambiguity and instrument failures using the [improvement template](../templates/improvement.md).
7. **Freeze S and R inputs.** Build executable stress seeds with controlled variation; separately select authorized/licensed real repositories and pin commits, authored LOC, environments, passing baselines, and scenario mappings. Keep scale claims within the evidence actually collected.
8. **Run confirmation on fresh private instances.** Freeze versions, thresholds, repetitions, randomization and analysis before evaluation. Public scenarios and previously inspected confirmation failures remain development evidence.

Each implemented part needs exact source/environment hashes, a reproducible qualification command, raw evidence references and documented failure limits before its readiness field changes. Keep fixture/runner code and their usage docs together when adding them; avoid placeholder commands that pretend unimplemented operations work.
