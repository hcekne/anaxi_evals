# Improving the evals

Changes should make the suite better at detecting correct, maintainable software
and safe independent delivery. Fewer lines, files, factories, or tests are useful
diagnostics only when supported by behavior and maintenance evidence.

Start with the affected scenario and the [protocol](docs/protocol.md). For a
substantive improvement, use the [improvement record](templates/improvement.md)
to describe the observed problem, its evidence, the proposed change, and which
previous results remain comparable. A small wording or link correction needs only
a clear commit or PR description.

## Editing and checking

1. Work on a branch when a baseline exists. Keep changes focused and retain stable
   scenario IDs and step numbers. Add a new variant when changing the task's meaning
   would otherwise silently replace a frozen case.
2. Edit canonical scenario text in `evals/<scenario>/spec.md`. Update the protocol
   and catalog when affected. Add complete public fixture contracts before requiring
   new behavior in evaluator cases. Keep future requests and private outcomes away
   from subject agents.
3. Run `python3 tools/evals.py sync`, then inspect the generated request diff. Check
   that all 16 prompts remain in the intended sequence and no acceptance text leaked
   into them. The root and per-scenario JSONL files are generated artifacts.
4. Run `python3 tools/evals.py validate` and
   `python3 -m unittest discover -s tests`. Add meaningful tooling tests when changing
   parsing, export, or validation behavior. Fixture/runner changes additionally need
   their own behavioral qualification once those components exist.
5. Update `CHANGELOG.md` and the version in `catalog.json` for a release. Record
   affected cases, expected effect on interpretation, and validation performed.
6. Submit the change through the owner's authorized Git workflow. A local edit does
   not authorize a paid run or a push to an otherwise restricted remote.

## Versions and comparisons

`catalog.json` carries the suite version. Each result must also pin the full Git
commit, scenario/variant, protocol and prompt hashes, fixture/oracle hashes, and run
configuration. A version string alone cannot identify an experiment.

| Change | Version policy |
| --- | --- |
| Clarify prose or repair navigation without changing delivered inputs or measurement | Patch release; state that measured behavior is unchanged. |
| Add a scenario, qualified variant, or optional metric | Minor release; preserve existing IDs and document scope. |
| Change prompts, required behavior, scoring, treatment, budgets, or an existing comparison contract | Breaking change: minor release while the suite is `0.x`; major release after `1.0`. Document the break explicitly. |

A bug fix that changes outcomes is a comparison change even if the code diff is
small. Never pool old and new measurements solely because their version numbers
look compatible. Use a matched rerun or a documented bridge study. Preserve old
versions through Git history and retain their reports unchanged; add a correction
or superseding report rather than editing away a failed result.

## Evidence and experiment integrity

- Preserve all attempted trajectories, failures, exclusions, and repair costs.
  Separate infrastructure-invalid runs from product failures using a frozen rule.
- Keep AnaxiGraph's graph and advice out of grading truth. Use independently
  qualified behavioral, selection, and release evidence.
- Work on exposed development cases. Validate a proposed instrument correction on
  fresh cases before confirmation. A disclosed holdout becomes development data;
  replace it before claiming unseen confirmation.
- Keep the same charter in B and C, measure C minus B as tool benefit, and charge
  sidecar setup, refresh, and interaction costs to C.
- Record null for missing measurements, not zero. Label modeled timing separately
  from measured timing. Do not claim 300k-line relevance from generated padding.

Use [docs/iteration.md](docs/iteration.md) for the work cycle and
[results/README.md](results/README.md) for evidence handling. The repo's checks do
not execute the benchmark or establish that any treatment improves code quality.
