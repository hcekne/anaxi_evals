# CaseFlow

CaseFlow is a small browser app for keeping case documents together. It is early: only the
skeleton exists. Product requests arrive one at a time in `docs/requests/`.

## Working agreement

> Implement the user's current request in the supplied environment and preserve earlier requested behavior. Supply commands to start the app, build artifacts, run all checks, select checks for a change, and release locally. A full-suite selector and a single release artifact are valid starting points. Use the supplied test services. Work autonomously within the recorded budget; document assumptions when needed.

## Run

```sh
uv sync --locked
.venv/bin/python -m caseflow serve --host 127.0.0.1 --port 8000
.venv/bin/python -m pytest
```

`run.json` holds the start command with a `{port}` placeholder; deployment and acceptance
tooling launch the app from it, so keep it working. The app is one Python process: its HTTP
API lives under `/api/`, and its browser pages are HTML served by the same process (there is no
Node or TypeScript toolchain in this environment).

## Environment

| Variable | Meaning |
| --- | --- |
| `CASEFLOW_DATA_DIR` | Writable directory for everything the app must keep. |
| `CASEFLOW_EXTERNAL_URL` | Base URL in front of every outside service CaseFlow calls. Requests give paths relative to it, for example `{EXTERNAL}/parcelbox/documents`. |

There is no other configuration channel: credentials and settings arrive through the API.

## API conventions

- JSON in and out unless a request says otherwise. Ids are opaque strings chosen by CaseFlow.
- Timestamps are UTC strings in exactly the form `2026-01-31T23:59:59Z`.
- Errors use one envelope: `{"error": {"code": "<stable_code>", "message": "<text>"}}`
  (see `caseflow/errors.py`). Requests name the codes they expect. Unless a request says
  otherwise:
  - `invalid_request` (422): missing, malformed or out-of-range parameters or body fields
    (including wrong JSON types).
  - `not_found` (404): unknown resource.
  - `conflict` (409): the resource is in the wrong state for the operation.
  - `upstream_error` (502): an outside service failed or returned something unusable.
- Credentials are write-only: no endpoint or page ever returns them.

## Checks and CI selection

`ci.json` at the repository root is `{"select": ["<argv>", "..."]}`. Our tooling runs that
command from the repository root with `.venv/bin/python` available and no network. It writes the
changed paths (repository-relative, one per line) to stdin and reads pytest targets from stdout:
one per line (test files, directories or node ids), or the single line `ALL` to run everything.

- It must be **safe**: if a change could break a test, that test must be selected. Our tooling
  will regularly plant small bugs in single files and check the selected tests catch them.
- It should be **cheap**: select as little as safety allows. A change limited to one part of the
  product should run that part's tests and the tests of everything that depends on it, not the
  whole suite.
- Changes only to Markdown files or `docs/` select nothing (empty output).
- Changes to `pyproject.toml`, `uv.lock` or `ci.json` → `ALL`.
- Every other change (any source file) selects at least one target or `ALL`; a changed test file
  (`tests/**/test_*.py`) selects itself (or `ALL`).
- It must finish in under 10 seconds, and every target it prints must exist.

The selector shipped with the skeleton prints `ALL` for every change that is not
documentation-only. That full-suite selector is a valid starting point; make it cheaper when
you can do so safely.

## Development

The development sandbox has no network access. Tests must never call real outside services:
fake them in-process (for example with `httpx.MockTransport` or FastAPI's `TestClient`).
Do not add third-party dependencies; the locked environment and the Python standard library
(including `sqlite3`, `zlib`, `csv`, `base64`) are all there is.
