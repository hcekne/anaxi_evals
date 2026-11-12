# Changelog

Record changes to tasks and measurement separately from tooling and documentation.
Every experimental report must pin an exact commit in addition to this version.

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
