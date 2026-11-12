# AnaxiGraph evals

Three evolving-product evaluations for testing whether AnaxiGraph helps coding agents produce software that is easier to extend, maintain, verify and release. Each scenario has **one initial request and 15 consecutive follow-ups**, plus four maintenance-probe families.

**Current version: 0.1.0 — specifications and retrieval tools.** All 48 prompts, evaluator criteria and the shared experiment protocol are included. The helper commands work; fixture services, independent acceptance tests and the agent/sidecar runner still need implementation. No benchmark has been executed by this package. A passing repository check is not an AnaxiGraph result.

## Choose an eval

| ID | Specification | What it stresses | Prompt queue |
| --- | --- | --- | --- |
| `relaydesk` | [RelayDesk](evals/relaydesk/spec.md) | Adding, changing and retiring providers; honest capability differences; local UI releases | [16 prompts](evals/relaydesk/requests.jsonl) |
| `dispatchledger` | [DispatchLedger](evals/dispatchledger/spec.md) | Independent UI/server/worker releases; safe selective CI; stored-data and event compatibility | [16 prompts](evals/dispatchledger/requests.jsonl) |
| `caseflow` | [CaseFlow](evals/caseflow/spec.md) | Document connectors, durable jobs, permissions and maintenance by a fresh agent | [16 prompts](evals/caseflow/requests.jsonl) |

Stable IDs and paths are listed in [catalog.json](catalog.json). [requests.jsonl](requests.jsonl) is the combined operator queue. Each record has `scenario`, integer `step` (0–15), `title` and `user_prompt`.

## Get the files and retrieve a prompt

Use Python 3.10 or newer; the helper uses only the standard library. No installation or model credentials are needed for these commands.

```bash
git clone https://github.com/hcekne/anaxi_evals.git
cd anaxi_evals
python3 tools/evals.py list
python3 tools/evals.py list --json
python3 tools/evals.py prompt relaydesk 0
python3 tools/evals.py prompt dispatchledger 13 --json
python3 tools/evals.py validate
python3 -m unittest discover -s tests -v
```

Run commands from the checkout root. For reproducible experiments, check out a recorded full commit SHA before retrieving material and record the suite version too. Branch `main` evolves; it is not an experiment identifier. The tool can also use an alternate corpus with `--root PATH` before the subcommand.

`prompt` writes **only the selected user prompt** to stdout, or its four-field record with `--json`. Its stderr reminder is operator information. The operator must also supply the current public environment/fixture attachments described in the spec; those runnable attachments do not yet ship here. This command retrieves text, not a runnable evaluation or a stateful delivery scheduler.

To take one scenario to another evaluator environment:

```bash
python3 tools/evals.py export caseflow --output exports/caseflow-0.1.0
```

This creates a new directory containing `README.md`, `spec.md`, `requests.jsonl`, `protocol.md`, `charter.md`, `scenario.json` and `manifest.json`. The manifest records payload SHA-256 hashes, suite version, source commit and dirty status. Export refuses an existing destination. Internal links are adapted for the bundle; other scenarios are omitted. `exports/` is ignored by Git. A dirty or uncommitted export is development material, not a frozen release.

## Keep operator and coding-agent material separate

This repository is for **benchmark maintainers and operators**. It contains future requests, acceptance criteria, mutation ideas and maintenance probes. Do not clone or mount it inside a measured coding agent's workspace. A prompt-filtering helper does not enforce filesystem or network isolation; the future runner must do that.

The operator reveals one prompt and its current public attachments at a time, continuing the same conversation through steps 00–15. Each continuation probe branches independently from the completed snapshot using the protocol's common fresh maintainer. See the [shared protocol](docs/protocol.md) before running experiments.

| Arm | What the measured coding agent gets |
| --- | --- |
| A — Bare | Common environment, current product prompt, current public attachments and ordinary tools |
| B — Charter | A plus [shared/charter.md](shared/charter.md) |
| C — AnaxiGraph | B plus a pinned AnaxiGraph build and its supported consultation loop |

The primary comparison is **C versus B**. This repository's [AGENTS.md](AGENTS.md) is contributor guidance; never use it as the experimental charter or inject it into any arm. Future requests, private checks and evaluator results must remain outside the agent's access. Publicly visible scenarios are development cases; fresh confirmation cases belong in a separate authorized evaluator store.

## What to measure

The [protocol](docs/protocol.md) defines correctness and unsafe-green gates, late maintenance cost, safe CI and release latency, independently released artifacts, core edits for new integrations, fresh-agent navigation, parallel-development conflicts, total agent/sidecar cost, and structural diagnostics. LOC, import cycles and file counts help explain results; none alone establishes architectural quality. Preserve losses and inconclusive results as well as wins.

Large-codebase evidence uses three separate tracks: **G**, the 16-request growth sequence; **S**, controlled executable dependency/workload stress; and **R**, maintenance on pinned real inherited repositories around 300,000 authored lines. R reuses an existing codebase and measures requested deltas. No 300k repository, measured scale result or qualified S/R case is included yet; padding a small repository does not establish large-system behavior.

## Navigate and improve the suite

| Location | Purpose |
| --- | --- |
| [docs/protocol.md](docs/protocol.md) | Experiment design, measurement rules and proposed runner contract |
| `evals/<id>/spec.md` | Canonical numbered prompts, fixture contracts, evaluator criteria and probes |
| `evals/<id>/requests.jsonl`, [requests.jsonl](requests.jsonl) | Generated prompt queues; never edit directly |
| [shared/charter.md](shared/charter.md) | Generated verbatim from the protocol for arms B/C |
| [tools/evals.py](tools/evals.py), [tests/test_evals.py](tests/test_evals.py) | Discovery, retrieval, export and consistency checks |
| [CONTRIBUTING.md](CONTRIBUTING.md), [docs/iteration.md](docs/iteration.md) | Agent workflow, evidence, versioning and comparison rules |
| [templates/experiment.md](templates/experiment.md), [templates/improvement.md](templates/improvement.md) | Record an experiment plan or evidence-backed eval improvement |
| [results/README.md](results/README.md) | Sanitized result summaries and external raw-evidence references |
| [docs/roadmap.md](docs/roadmap.md) | Remaining implementation and qualification work |
| [CHANGELOG.md](CHANGELOG.md), [docs/provenance.md](docs/provenance.md) | Version history and original design provenance |

To improve an eval, record the observed problem and evidence, edit its canonical Markdown, regenerate dependent files, and validate:

```bash
python3 tools/evals.py sync
python3 tools/evals.py validate
python3 -m unittest discover -s tests -v
git diff --check
git diff
```

Update the catalog version and changelog as [CONTRIBUTING.md](CONTRIBUTING.md) requires. Keep stable scenario IDs and request order unless you deliberately introduce a new incompatible version. Repository CI runs the same consistency checks and tooling tests. It does not run paid agents or qualify application behavior.
