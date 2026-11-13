"""Hidden acceptance fixtures for RelayDesk: fictional outside services in-process (`hub.py`),
the candidate as a subprocess launched from its `run.json`.

`DRIFT_CANDIDATE` is the candidate checkout; `DRIFT_STEP` is the step being evaluated. It applies
the requirement lifecycle: sign-in from request 4, asynchronous suggestions and Pollen streaming
from request 5, Comet retired from request 13, multi-currency orders (and the retired v1 order
API) from request 15. Earlier-step tests branch on these so requested changes are not counted as
regressions.

Upgrade tests (requests 13, 14, 15 and probes) start the code as it was just before a request:
the tree of the commit that added `docs/requests/<that request>.md`, run with the candidate's
`.venv`, on the same data directory as the current version afterwards.
"""

from __future__ import annotations

import atexit
import csv
import html
import io
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import hub as hubmod  # noqa: E402

CANDIDATE = Path(os.environ.get("DRIFT_CANDIDATE", ".")).resolve()
STEP = int(os.environ.get("DRIFT_STEP", "15"))
AUTH = STEP >= 4  # request 4: teams and sign-in
ASYNC = STEP >= 5  # request 5: suggestions answer at once; Pollen streams
RETIRED = STEP >= 13  # request 13: Comet retired
MONEY = STEP >= 15  # request 15: multi-currency orders, v1 order API retired

SCALE = 0.05  # RELAYDESK_TIME_SCALE used by every app
# Unfinished suggestion states: request 10 added `queued`, request 11 `cancelled` (terminal).
UNFINISHED = {"running", "queued"} if STEP >= 10 else {"running"}
TERMINAL = {"completed", "failed", "cancelled"}
HEADER = ["id", "customer_email", "subject", "body"]

TEAMS = {
    "teams": [
        {"id": "north", "name": "North Desk", "users": [
            {"username": "nora", "password": "north-pass-1"},
            {"username": "nils", "password": "north-pass-2"}]},
        {"id": "south", "name": "South Desk", "users": [
            {"username": "sara", "password": "south-pass-1"}]},
    ]
}
USERS = {
    u["username"]: (u["password"], t["id"]) for t in TEAMS["teams"] for u in t["users"]
}
DEMO = {"pollen": "pollen-demo-token", "comet": "comet-demo-key"}
TOKENS = {
    service: {team: token for token, team in tokens.items() if team != "demo"}
    for service, tokens in hubmod.TOKENS.items()
}
# Pollen's reply endpoint (hub plan key, path) before and after streaming arrived.
POLLEN = ("pollen_stream", "/pollen/draft/stream") if ASYNC else ("pollen", "/pollen/draft")
# The non-streaming reply service used by tests of earlier requests once Comet is retired.
SECOND = "harbor" if RETIRED else "comet"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def uid(prefix: str = "T-") -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def csv_bytes(rows, header=HEADER) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([row[k] for k in header] if isinstance(row, dict) else row)
    return out.getvalue().encode()


def error_code(response: httpx.Response) -> str | None:
    try:
        return response.json()["error"]["code"]
    except (ValueError, KeyError, TypeError):
        return None


def expect_error(response: httpx.Response, status: int, code: str) -> None:
    assert (response.status_code, error_code(response)) == (status, code), response.text[:500]


def shows(page: str, text: str) -> bool:
    """`text` appears in an HTML page, raw or HTML-escaped."""
    return any(v in page for v in (text, html.escape(text), html.escape(text, quote=False)))


def wait_for(predicate, timeout: float = 10.0, interval: float = 0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    return predicate()


def provider_text(call: dict) -> str:
    """Everything a reply service was sent, as one string."""
    body = call["body"] or {}
    if call["service"] == "pollen":
        return "\n".join(m["content"] for m in body.get("messages", []))
    if call["service"] == "comet":
        return "\n".join(e["text"] for e in body.get("conversation", []))
    if call["service"] == "harbor":
        return body.get("prompt", "")
    if call["service"] == "quartz":
        return "\n".join(i["text"] for i in body.get("input", []))
    if call["service"] == "nimbus":
        return "\n".join([body.get("instructions", ""), *body.get("context", [])])
    return json.dumps(body, ensure_ascii=False)


REPLY_CALLS = {
    "pollen": ("pollen", "/pollen/draft", "POST"),
    "comet": ("comet", "/comet/compose", "POST"),
    "harbor": ("harbor", "/harbor/jobs", "POST"),
    "quartz": ("quartz", "/quartz/responses", "POST"),
    "nimbus": ("nimbus", "/nimbus/v1/replies", "POST"),
}


def reply_calls(hub, provider: str) -> list[dict]:
    """Requests that asked `provider` for a reply (submissions, not polls or cancels)."""
    service, part, method = REPLY_CALLS[provider]
    calls = hub.calls_to(service, part, method)
    if provider == "nimbus":
        calls = [c for c in calls if c["path"].rstrip("/") == "/nimbus/v1/replies"]
    if provider == "harbor":
        calls = [c for c in calls if c["path"].rstrip("/") == "/harbor/jobs"]
    return calls


def reply_text(hub, call: dict) -> str:
    """The reply text a recorded reply-service call produced."""
    response = call["response"] or {}
    body = response.get("body")
    if "events" in response:
        names = {"delta", "text_delta", "content_delta", "chunk"}
        return "".join(
            d.get("text", d.get("delta", "")) for n, d in response["events"] if n in names
        )
    if call["service"] == "comet":
        return body["completion"]["body"]
    if call["service"] == "harbor":
        job = hub.jobs[body["job_id"]]
        return job["answer"]
    return body["text"]


# -- old versions ------------------------------------------------------------------------------
_SOURCES: dict[str, Path] = {}


def previous_source(pattern: str) -> Path:
    """The candidate's code just before the request saved as `docs/requests/<pattern>`."""
    if pattern in _SOURCES:
        return _SOURCES[pattern]
    log = subprocess.run(
        ["git", "log", "--diff-filter=A", "--format=%H", "--",
         f":(glob)docs/requests/{pattern}"],
        cwd=CANDIDATE, capture_output=True, text=True,
    )  # fmt: skip
    commits = log.stdout.split()
    if log.returncode or not commits:
        pytest.fail(f"no commit adds docs/requests/{pattern}: {log.stderr[-500:]}")
    dest = Path(tempfile.mkdtemp(prefix="rd-prev-"))
    atexit.register(shutil.rmtree, dest, True)
    tree = subprocess.run(
        ["git", "archive", "--format=tar", commits[0]], cwd=CANDIDATE, capture_output=True
    )
    if tree.returncode:
        pytest.fail(f"git archive failed: {tree.stderr[-500:]!r}")
    subprocess.run(["tar", "-x", "-C", str(dest)], input=tree.stdout, check=True)
    venv = dest / ".venv"
    if venv.is_symlink() or venv.is_file():
        venv.unlink()
    elif venv.exists():
        shutil.rmtree(venv)
    venv.symlink_to(CANDIDATE / ".venv")
    _SOURCES[pattern] = dest
    return dest


# -- the candidate -----------------------------------------------------------------------------
class Client:
    """One browser: an HTTP client with its own cookies, signed in as `username` from request 4."""

    def __init__(self, app: "App", username: str = "nora") -> None:
        self.app, self.username = app, username
        self.team = USERS[username][1]
        self.http: httpx.Client | None = None
        self.connect_http()

    def connect_http(self) -> None:
        if self.http:
            self.http.close()
        self.http = httpx.Client(base_url=self.app.base, timeout=30)
        if AUTH:
            password = USERS[self.username][0]
            r = self.http.post("/api/login", json={"username": self.username, "password": password})
            assert r.status_code == 200, f"sign-in failed: {r.status_code} {r.text[:300]}"

    def close(self) -> None:
        if self.http:
            self.http.close()

    def request(self, method: str, path: str, **kw) -> httpx.Response:
        return self.http.request(method, path, **kw)

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, **kw):
        return self.request("POST", path, **kw)

    def put(self, path, **kw):
        return self.request("PUT", path, **kw)

    def delete(self, path, **kw):
        return self.request("DELETE", path, **kw)

    def ok(self, method: str, path: str, status: int | tuple = 200, **kw):
        r = self.request(method, path, **kw)
        allowed = status if isinstance(status, tuple) else (status,)
        assert r.status_code in allowed, f"{method} {path}: {r.status_code} {r.text[:500]}"
        return r.json() if r.content else None

    # domain helpers ---------------------------------------------------------------------
    def token(self, service: str) -> str:
        if not AUTH and service in DEMO:
            return DEMO[service]
        return TOKENS[service][self.team]

    def connect(self, *services: str) -> None:
        for service in services:
            self.ok("PUT", f"/api/connections/{service}", json={"token": self.token(service)})

    def import_rows(self, rows) -> httpx.Response:
        return self.post("/api/imports", content=csv_bytes(rows),
                         headers={"Content-Type": "text/csv"})  # fmt: skip

    def tickets(self, n: int = 1, **fields) -> list[dict]:
        rows = []
        for _ in range(n):
            ident = uid()
            rows.append({
                "id": ident,
                "customer_email": fields.get("customer_email", f"{ident.lower()}@example.com"),
                "subject": fields.get("subject", f"Question {ident} about my order"),
                "body": fields.get("body", f"Body of {ident}: the parcel never arrived — hjelp!"),
            })  # fmt: skip
        r = self.import_rows(rows)
        assert r.status_code == 200, r.text[:500]
        return rows

    def ticket(self, ident: str) -> dict:
        return self.ok("GET", f"/api/tickets/{ident}")

    def ask(self, ident: str, **body) -> httpx.Response:
        return self.post(f"/api/tickets/{ident}/suggestions", json=body)

    def suggestion(self, ident: str) -> dict:
        return self.ok("GET", f"/api/suggestions/{ident}")

    def wait(self, ident: str, timeout: float = 10.0, until=TERMINAL) -> dict:
        found = wait_for(lambda: (s := self.suggestion(ident))["status"] in until and s, timeout)
        assert found, f"suggestion {ident} still {self.suggestion(ident)['status']}"
        return found

    def suggest(self, ident: str, timeout: float = 10.0, **body) -> dict:
        r = self.ask(ident, **body)
        assert r.status_code in ((201, 202) if ASYNC else (201,)), r.text[:500]
        created = r.json()
        if created["status"] in TERMINAL:
            return created
        return self.wait(created["id"], timeout)

    def page(self, path: str) -> str:
        r = self.get(path)
        assert r.status_code == 200, f"{path}: {r.status_code}"
        assert "html" in r.headers.get("content-type", ""), r.headers.get("content-type")
        return r.text


class App:
    """One running candidate with its own (or a shared) data directory."""

    def __init__(self, hub, source: Path = CANDIDATE, data: Path | None = None) -> None:
        self.hub, self.source = hub, source
        self.root = Path(tempfile.mkdtemp(prefix="rd-app-"))
        self.data = data or self.root / "data"
        self.teams = self.root / "teams.json"
        self.teams.write_text(json.dumps(TEAMS))
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.proc: subprocess.Popen | None = None
        self.clients: list[Client] = []
        self.start()
        self.c = self.client("nora")

    @property
    def env(self) -> dict:
        return {
            **os.environ,
            "RELAYDESK_EXTERNAL_URL": self.hub.url,
            "RELAYDESK_DATA_DIR": str(self.data),
            "RELAYDESK_TEAMS_FILE": str(self.teams),
            "RELAYDESK_TIME_SCALE": str(SCALE),
            "PYTHONDONTWRITEBYTECODE": "1",
        }

    def start(self) -> None:
        command = json.loads((self.source / "run.json").read_text())["command"]
        argv = [part.replace("{port}", str(self.port)) for part in command]
        self.log = open(self.root / "service.log", "ab")
        self.proc = subprocess.Popen(
            argv, cwd=self.source, env=self.env, stdout=self.log, stderr=subprocess.STDOUT
        )
        deadline = time.monotonic() + 45
        with httpx.Client(base_url=self.base, timeout=5) as probe:
            while time.monotonic() < deadline:
                if self.proc.poll() is not None:
                    break
                try:
                    if probe.get("/api/health").status_code == 200:
                        for client in self.clients:
                            client.connect_http()
                        return
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
        tail = (self.root / "service.log").read_text(errors="replace")[-2000:]
        self.stop()
        pytest.fail(f"candidate service did not start from {self.source}:\n{tail}")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.log.close()

    def kill(self) -> None:
        """An abrupt stop: SIGKILL, no chance to clean up."""
        if self.proc and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGKILL)
            self.proc.wait()
        self.log.close()

    def restart(self, abrupt: bool = False) -> None:
        self.kill() if abrupt else self.stop()
        self.start()

    def client(self, username: str = "nora") -> Client:
        client = Client(self, username)
        self.clients.append(client)
        return client

    def close(self) -> None:
        for client in self.clients:
            client.close()
        self.kill()
        shutil.rmtree(self.root, ignore_errors=True)


@pytest.fixture(scope="session")
def hub():
    server, state = hubmod.start()
    yield state
    state.reset()
    server.shutdown()


@pytest.fixture(autouse=True)
def _fresh_hub(hub):
    hub.reset()
    hub.orders_v1 = not MONEY
    yield
    hub.reset()


@pytest.fixture(scope="module")
def app(hub):
    instance = App(hub)
    yield instance
    instance.close()


@pytest.fixture
def fresh_app(hub):
    instance = App(hub)
    yield instance
    instance.close()


@pytest.fixture
def c(app):
    """The default browser: nora of team north (no sign-in before request 4)."""
    return app.c


@pytest.fixture
def south(app):
    if not AUTH:
        pytest.fail("teams exist from request 4")
    found = [cl for cl in app.clients if cl.username == "sara"]
    return found[0] if found else app.client("sara")


def upgrade(hub, pattern: str, prepare, abrupt: bool = False):
    """Run `prepare(old_app)` on the code from before `pattern`, stop it (or kill it), start the
    current code on the same data and return `(new_app, prepare's result)`; caller closes."""
    data_root = Path(tempfile.mkdtemp(prefix="rd-shared-"))
    atexit.register(shutil.rmtree, data_root, True)
    old = App(hub, source=previous_source(pattern), data=data_root / "data")
    try:
        result = prepare(old)
    finally:
        old.kill() if abrupt else old.stop()
        old.close()
    return App(hub, data=data_root / "data"), result
