# From a finding to a better eval

The suite should improve as instruments are tested, while keeping published
comparisons interpretable. Treat changes to the benchmark and changes to AnaxiGraph
as separate interventions.

1. **Capture the finding.** Record the exact suite commit, scenario, step/probe,
   environment, expected behavior, observed behavior, and evidence reference. Decide
   whether this is an infrastructure failure, ambiguous task, faulty instrument,
   insufficient architectural pressure, or product failure. Keep uncertainty visible.
2. **Propose a falsifiable correction.** State what the changed instrument should
   distinguish and why. For example, a selector that skips a required consumer must
   fail an independent audit; a valid font-only release should demonstrate unchanged
   backend artifacts. Use [the improvement template](../templates/improvement.md).
3. **Change the development suite.** Edit canonical specifications or implementation,
   regenerate prompts, and record version/comparison impact. Do not reveal private
   audit feedback to an agent during its ongoing measured trajectory.
4. **Qualify the instrument.** Show a sound selective solution, a safe full-suite
   solution, an unsafe skip-everything solution, and an unnecessarily complicated
   solution. Verify the expected distinctions through observed behavior, without
   rewarding architectural ceremony. Check clean changes as well as injected faults.
5. **Freeze and rerun matched blocks.** Freeze the suite, tool release, environment,
   fixtures, evaluator cases, budgets, and reporting policy before comparing arms.
   Change one intervention at a time where feasible. If an instrument defect forces
   a mid-campaign correction, mark the affected blocks and follow the preregistered
   rerun rule for every arm.
6. **Report and retain.** Publish sanitized evidence, failures, uncertainty, and
   comparison limits. Keep prior reports immutable. Promote changes only after
   development validation; use fresh held-out instances for confirmation.

## Implementation order

The specifications are written; the following items remain to be built and qualified.

| Stage | Concrete completion evidence |
| --- | --- |
| One scenario's public fixtures | Local deterministic services, sample inputs, failure modes, replayable clocks, and versioned contracts. |
| Independent behavior checks | Cumulative requirement lifecycle, known-good/known-bad controls, failure logs, and snapshot hashes. |
| Runner and treatment adapters | One-step reveal, arm isolation, budgets, checkpoints, tool-cost ledger, and a smoke run in each arm. |
| Selective CI and release instruments | Selected/full/audit distinction; qualified faults; clean controls; actual artifacts, mixed versions, queues, and rollback evidence. |
| Three-scenario development pilot | Complete attempted-run accounting, diagnostic reports, and frozen corrections before confirmation. |
| Controlled stress and inherited repositories | Executable stress seeds; authorized and pinned real repositories; passing baselines, measured authored LOC, and realistic task mappings. |
| Locked confirmation | Fresh retained cases, preregistered decisions, matched complete trajectories, and uncertainty estimates. |

Do not mark a stage complete merely because its documentation or adapter interface
exists. The [experiment template](../templates/experiment.md) is a planning record,
not an executable runner configuration or a qualification certificate.

## Questions worth investigating

- Can a new provider be added or removed with low core intrusion while preserving
  capability differences and historical data?
- Does a cosmetic change build and release independently, with correct compatibility
  checks, while a shared semantic or permission change triggers broader checks?
- Can a fresh maintainer navigate and fix the resulting program cheaply without
  inheriting the builder's sidecar memory?
- Does benefit persist on authorized real repositories near 300k authored lines,
  after sidecar overhead and all failures are included?

Treat an AnaxiGraph loss as information. Diagnose stale maps, unsupported edges,
advice quality, uptake, and overhead through separately labeled ablations; do not
remove difficult cases because they favor another arm.
