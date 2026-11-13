# DispatchLedger

DispatchLedger is a small online shop. It is early: only the skeleton exists. Product requests
arrive one at a time in `docs/requests/`.

## Working agreement

> Implement the user's current request in the supplied environment and preserve earlier requested behavior. Supply commands to start the app, build artifacts, run all checks, select checks for a change, and release locally. A full-suite selector and a single release artifact are valid starting points. Use the supplied test services. Work autonomously within the recorded budget; document assumptions when needed.

## Run

```sh
uv sync --locked
.venv/bin/python -m dispatchledger serve --host 127.0.0.1 --port 8000
.venv/bin/python -m pytest
```

`run.json` holds the start command with a `{port}` placeholder; deployment and acceptance
tooling launch the web app from it, so keep it working. The web app serves both the browser
pages and the JSON API (`/api/...`).

## Environment

| Variable | Meaning |
| --- | --- |
| `DISPATCHLEDGER_DATA_DIR` | Writable directory for everything the shop must keep. Data must survive a restart. |
| `DISPATCHLEDGER_EXTERNAL_URL` | Base URL in front of every outside test service. Service instructions give paths relative to it, for example `{EXTERNAL}/parcelfox/labels`. |
| `DISPATCHLEDGER_PUBLIC_URL` | The address at which the running web app can be reached from outside, without a trailing slash (for links and anything an outside service must call back). |
| `DISPATCHLEDGER_CLOCK_FILE` | Optional. When set, the current time is **not** the system clock: it is the Unix time in seconds (an integer or decimal number, surrounding whitespace allowed) written in this file, re-read every time any process of the shop needs the time. Tests move time forward by rewriting the file. When unset, use the system clock. |

Every process of the shop gets the same environment. `Settings.now()` reads the clock.

## Conventions

- JSON in and out of `/api/...` unless a request says otherwise.
- Money is an integer number of minor units (pennies for pounds). Prices are in pounds (GBP).
- Times in JSON are UTC strings `YYYY-MM-DDTHH:MM:SSZ`; dates are `YYYY-MM-DD` in UTC.
- Errors use one envelope: `{"error": {"code": "<stable_code>", "message": "<text>"}}`
  (see `dispatchledger/errors.py`). Requests name the codes they expect. Unless a request says
  otherwise:
  - `invalid_request` (422): missing, malformed or out-of-range parameters or body fields
    (including wrong JSON types, and booleans where integers are expected).
  - `not_found` (404): unknown resource.
  - `not_configured` (409): a needed setting or credential has not been provided yet.
- Credentials and secrets are write-only: no endpoint or page ever shows them.

## Checks for a change

`ci.json` at the repository root: `{"select": ["<argv>", "..."]}`. Our tooling runs that
command from the repository root with `.venv/bin/python` available and no network. It writes the
changed paths (repository-relative, one per line) to stdin and reads pytest targets from stdout:
one per line (test files, directories or node ids), or the single line `ALL` to run everything.

- It must be **safe**: if a change could break a test, that test must be selected. Our tooling
  will regularly plant small bugs in single files and check the selected tests catch them.
- It should be **cheap**: select as little as safety allows. A change limited to one part of the
  product should run that part's tests and the tests of whatever relies on it, not the whole
  suite.
- Changes only to Markdown files or `docs/` select nothing (empty output).
- Changes to `pyproject.toml`, `uv.lock` or `ci.json` → `ALL`.
- Every other change (any source file) selects at least one target or `ALL`; a changed test file
  (`tests/**/test_*.py`) selects itself (or `ALL`).
- It must finish in under 10 seconds, and every target it prints must exist.

The supplied selector prints `ALL` for every change. That full-suite selector is a valid, safe
starting point; make it cheaper when that pays off, never at the cost of safety.

## Development

The development sandbox has no network access. Tests must never call real outside services:
fake them in-process (for example with `httpx.MockTransport` or FastAPI's `TestClient`).
Do not add third-party dependencies; the locked environment and the Python standard library
(including `sqlite3`, `hashlib`, `hmac`) are all there is. The shop's pages are plain HTML
served by the web app (forms and buttons that work without any build step).
