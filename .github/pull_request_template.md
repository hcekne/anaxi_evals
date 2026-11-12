## Change and reason

Describe the concrete problem and resulting behavior. Link the affected scenario,
improvement record, and sanitized evidence when relevant.

## Experiment impact

- Affected prompts, fixtures, metrics, treatments, or tool interfaces:
- Suite version and compatibility impact:
- Prior results needing correction or matched rerun:
- Development/holdout exposure:

## Validation

- [ ] `python3 tools/evals.py sync` run when canonical content changed; generated diff reviewed.
- [ ] `python3 tools/evals.py validate` passed.
- [ ] `python3 -m unittest discover -s tests` passed.
- [ ] Changelog/version updated when needed.
- [ ] No raw private evidence, credentials, future-case leakage, or unsupported result claims.

Describe any additional instrument qualification, remaining limitations, or checks
that could not run. Repository checks alone do not qualify the benchmark.
