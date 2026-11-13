# Changelog

Record changes to tasks and measurement separately from tooling and documentation.
Every experimental report must pin an exact commit in addition to this version.

## 0.2.1 — 2026-11-13

- DispatchLedger oracle fix: the hidden harness waited for `200` from `/api/health`, but
  request 10 makes every unlisted `/api` endpoint staff-only and does not list health, so an
  agent following it literally answers `401` and every hidden test failed to start the app.
  Any non-5xx health reply now counts as started. No test asserts on health itself.
- Comparison effect: outcomes change for any DispatchLedger candidate that protects health
  (0/106 → 106/106 for one pilot candidate at request 11). Prompts are unchanged. Known
  prompt gap kept for comparability: request 10 should list `/api/health` as public, as
  RelayDesk request 4 and CaseFlow request 6 do.

## 0.2.0 — 2026-11-13

- Added executable G-track packages for RelayDesk, DispatchLedger and CaseFlow under
  `evals/<id>/track/`: a public seed repository, per-step request files, an
  in-process fixture hub, hidden cumulative black-box tests for all 16 steps
  (123, 137 and 102 tests), and four continuation probes each with their own tests.
- Fixtures are deterministic local Python stand-ins for the spec's services. This is
  the Python-only stratum the protocol permits; browser/UI checks are not included.
- Qualification: an independent reference implementation per scenario passes every
  hidden test at every step when replayed through the anaxigraph-v2 feature-drift
  runner (`--agent ref:<repo>`, 2026-11-13). Probe tests fail against unmodified
  step-15 code, as intended.
- Interpretation: measures behavior and maintainability under the runner's rules;
  it is not the large-repository (R) track. No treatment result is reported here.

## 0.1.0 — 2026-11-12

- Imported the authored RelayDesk, DispatchLedger, and CaseFlow specifications:
  16 sequential requests each, evaluator requirements, fixture contracts, and
  continuation probes.
- Added the shared experiment protocol and the charter used by both guided arms.
- Added a scenario catalog, generated prompt queues, and tools to list scenarios,
  retrieve individual prompts, export operator bundles, and validate consistency.
- Added navigation, agent maintenance instructions, contribution/versioning rules,
  experiment and improvement templates, and evidence-handling guidance.
- Added 12 tooling tests and a GitHub Actions validation template. The connected
  app lacks workflow-write permission, so automated CI is not activated; the
  same commands pass locally.

Status: specification and repository-tooling release. Fixture services, independent
evaluator tests, runner bindings, and qualified large-repository cases are not yet
implemented. No benchmark campaign or treatment result is reported.
