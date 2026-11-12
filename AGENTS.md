# Working on the eval suite

These instructions are for agents **maintaining this repository**. Never copy this
file, the full repository, future requests, or evaluator material into a benchmark
subject's working directory. The treatment charter is [shared/charter.md](shared/charter.md).

1. Start with [README.md](README.md), [catalog.json](catalog.json), and
   [docs/protocol.md](docs/protocol.md). Read the affected scenario before editing it.
2. Preserve the central question: does AnaxiGraph improve correct maintenance and
   safe verification/release compared with the same agent and charter? A fair eval
   may show a loss or no benefit. Never tune scoring to guarantee a treatment wins.
3. Make routine, reversible changes within the owner's request without asking for
   confirmation. Preserve unrelated changes. Do not start paid campaigns, publish
   private evidence, or push to a remote without authorization under the owner's
   current policy. Never push a remote named `upstream`.
4. Edit prompts in `evals/<scenario>/spec.md`; these specifications are canonical.
   Run `python3 tools/evals.py sync` to regenerate request queues. Do not hand-edit
   generated JSONL. Keep existing scenario IDs and step numbers stable.
5. Keep user requests natural and free of architectural hints. Publish every
   required behavior through the current request or its fixture contract. Hidden
   tests vary documented inputs; they must not invent requirements.
6. For changes to tasks, fixtures, scoring, budgets, or treatment behavior, record
   evidence and compatibility impact using [CONTRIBUTING.md](CONTRIBUTING.md).
   Update the suite version in `catalog.json` and `CHANGELOG.md` as appropriate.
   Do not rewrite old results or call exposed development cases an unseen holdout.
7. Run `python3 tools/evals.py validate` and
   `python3 -m unittest discover -s tests`. These check repository tooling and
   consistency; they do not qualify fixtures or prove benchmark correctness.
8. Report what changed, the checks performed, and limitations. Distinguish authored
   specifications, implemented tooling, qualified instruments, and actual results.

As of 0.1.0, this repository contains specifications and prompt tooling. Fixture
services, independent evaluator tests, campaign execution, and real large-repository
cases still need implementation and qualification. Use [docs/iteration.md](docs/iteration.md)
to plan that work; do not fabricate results or mark missing components complete.
