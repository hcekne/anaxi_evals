# RelayDesk

RelayDesk is a small helpdesk web app. It is early: only the skeleton exists. Product requests
arrive one at a time in `docs/requests/`.

> Implement the user's current request in the supplied environment and preserve earlier requested behavior. Supply commands to start the app, build artifacts, run all checks, select checks for a change, and release locally. A full-suite selector and a single release artifact are valid starting points. Use the supplied test services. Work autonomously within the recorded budget; document assumptions when needed.

## Run

```sh
uv sync --locked
.venv/bin/python -m relaydesk serve --host 127.0.0.1 --port 8000
.venv/bin/python -m pytest
```

`run.json` holds the start command with a `{port}` placeholder; deployment and acceptance
tooling launch the app from it, so keep it working. Everything the app does, including any
background work, must run inside the process started from `run.json`.

## Environment

| Variable | Meaning |
| --- | --- |
| `RELAYDESK_DATA_DIR` | Writable directory for anything the app must keep. |
| `RELAYDESK_EXTERNAL_URL` | Base URL in front of every outside service RelayDesk calls. Requests give each service's address relative to it, for example `{EXTERNAL}/pollen/draft`. |

Requests may add variables; nothing else configures the app.

## API conventions

- JSON in and out under `/api/` unless a request says otherwise. Pages for people live outside
  `/api/`.
- Errors use one envelope: `{"error": {"code": "<stable_code>", "message": "<text>"}}`
  (see `relaydesk/errors.py`). Requests name the codes they expect. Unless a request says
  otherwise:
  - `invalid_request` (422): missing, malformed or out-of-range parameters or body fields
    (including wrong JSON types).
  - `not_found` (404): unknown resource.
  - `conflict` (409): the resource is in the wrong state for the operation.
  - `not_configured` (409): a needed setting or credential has not been provided yet.
- Secrets are write-only: no endpoint or page ever returns them.

## Checks and the change selector

`ci.json` at the repository root: `{"select": ["<argv>", "..."]}`. Our tooling runs that command
from the repository root with `.venv/bin/python` available and no network. It writes the
changed paths (repository-relative, one per line) to stdin and reads pytest targets from
stdout: one per line (test files, directories or node ids), or the single line `ALL` to run
everything. The selector in this skeleton always prints `ALL`, which is a valid starting point.

- It must be **safe**: if a change could break a test, that test must be selected. Our tooling
  will regularly plant small bugs in single files and check the selected tests catch them.
- It should be **cheap**: select as little as safety allows.
- Changes only to Markdown files or `docs/` select nothing (empty output).
- Changes to `pyproject.toml`, `uv.lock` or `ci.json` → `ALL`.
- Every other change (any source file) selects at least one target or `ALL`; a changed test
  file (`tests/**/test_*.py`) selects itself (or `ALL`).
- It must finish in under 10 seconds, and every target it prints must exist.

## Development

The development sandbox has no network access. Tests must never call real outside services:
fake them in-process (for example with `httpx.MockTransport` or FastAPI's `TestClient`).
Do not add third-party dependencies; the locked environment and the Python standard library
(including `sqlite3`, `csv`, `html`, `threading`) are all there is.
