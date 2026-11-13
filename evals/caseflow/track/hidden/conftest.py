"""Hidden acceptance fixtures for CaseFlow: fake outside services in-process (`hub.py`), the
candidate as a subprocess launched from its `run.json`.

`DRIFT_CANDIDATE` is the candidate checkout; `DRIFT_STEP` is the step being evaluated. It applies
the requirement lifecycle:

- before step 6 there are no identities or workspaces; from step 6 every call names a user and
  every case lives in a workspace;
- from step 13 ParcelBox is retired: ParcelBox-only checks turn into retirement checks and
  source-agnostic checks use BoxLoop instead;
- probe 4 (removing JSON downloads) retires request 12's export. It is detected from
  `DRIFT_PROBE=4` or from the probe request saved in the candidate's `docs/requests/`.
"""

from __future__ import annotations

import datetime as dt
import functools
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import httpx
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import hub as hubmod  # noqa: E402

CANDIDATE = Path(os.environ.get("DRIFT_CANDIDATE", ".")).resolve()
STEP = int(os.environ.get("DRIFT_STEP", "15"))


def _probe() -> int | None:
    if os.environ.get("DRIFT_PROBE"):
        return int(os.environ["DRIFT_PROBE"])
    requests = CANDIDATE / "docs" / "requests"
    for number in (1, 2, 3, 4):
        if any(requests.glob(f"probe-p{number}-*.md")):
            return number
    return None


PROBE = _probe()
TEAMS = STEP >= 6  # identities, workspaces and roles
VERSIONS = STEP >= 11  # edits and source revisions keep old versions
PARCEL_RETIRED = STEP >= 13
EXPORT_RETIRED = PROBE == 4
SOURCE = "boxloop" if PARCEL_RETIRED else "parcelbox"  # for source-agnostic checks

OWNER, EDITOR, VIEWER, RESTRICTED, OUTSIDER = "olivia", "ed", "vic", "rita", "zed"
START = "2026-03-01T09:00:00Z"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def uid(prefix: str = "x") -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def error_code(response: httpx.Response) -> str | None:
    try:
        return response.json()["error"]["code"]
    except (ValueError, KeyError, TypeError):
        return None


def expect_error(response: httpx.Response, status: int, code: str | None = None) -> None:
    got = (response.status_code, error_code(response)) if code else response.status_code
    want = (status, code) if code else status
    assert got == want, f"{response.request.method} {response.request.url}: {response.text[:500]}"


def ok(response: httpx.Response, status: int = 200):
    assert response.status_code == status, (
        f"{response.request.method} {response.request.url} -> {response.status_code}: "
        f"{response.text[:500]}"
    )
    return response.json() if response.content else None


def subset(record: dict, expected: dict) -> bool:
    return all(k in record and record[k] == v for k, v in expected.items())


def iso(moment: dt.datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(text: str) -> dt.datetime:
    return dt.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)


def wait_for(predicate, timeout: float = 10.0, interval: float = 0.1):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    return predicate()


def previous_release(step: int) -> Path:
    """The candidate's code as it stood when request `step` arrived (the runner commits each
    request as `Request <step>` on top of the previous step's final state)."""
    found = subprocess.run(
        ["git", "-C", str(CANDIDATE), "log", "--format=%H", "-n", "1", f"--grep=^Request {step}$"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert found, f"no 'Request {step}' commit in the candidate history"
    root = Path(tempfile.mkdtemp(prefix=f"cf-release-{step}-"))
    archive = subprocess.run(
        ["git", "-C", str(CANDIDATE), "archive", found], capture_output=True, check=True
    ).stdout
    subprocess.run(["tar", "-x", "-C", str(root)], input=archive, check=True)
    (root / ".venv").symlink_to(CANDIDATE / ".venv")
    return root


class App:
    """One running candidate service with its own data directory."""

    def __init__(self, hub_url: str, data: Path | None = None, code: Path = CANDIDATE) -> None:
        self.hub_url = hub_url
        self.code = code
        self.root = Path(tempfile.mkdtemp(prefix="cf-app-"))
        self.data = data or self.root / "data"
        self.proc: subprocess.Popen | None = None
        self.user = OWNER if TEAMS else None
        self._ws: str | None = None
        self.clock: dt.datetime | None = None
        self.start()

    @property
    def env(self) -> dict:
        return {
            **os.environ,
            "CASEFLOW_EXTERNAL_URL": self.hub_url,
            "CASEFLOW_DATA_DIR": str(self.data),
            "PYTHONDONTWRITEBYTECODE": "1",
        }

    def start(self) -> None:
        port = free_port()
        command = json.loads((self.code / "run.json").read_text())["command"]
        argv = [part.replace("{port}", str(port)) for part in command]
        self.log = open(self.root / "service.log", "ab")
        self.proc = subprocess.Popen(
            argv, cwd=self.code, env=self.env, stdout=self.log, stderr=subprocess.STDOUT
        )
        self.http = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                break
            try:
                if self.http.get("/api/health").status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        tail = (self.root / "service.log").read_text(errors="replace")[-2000:]
        self.stop()
        pytest.fail(f"candidate service did not start:\n{tail}")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.http.close()
        self.log.close()

    def restart(self) -> None:
        self.stop()
        self.start()

    def close(self) -> None:
        self.stop()
        shutil.rmtree(self.root, ignore_errors=True)

    # HTTP --------------------------------------------------------------------------------
    def call(self, method, path, user="default", **kwargs) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}) or {})
        user = self.user if user == "default" else user
        if user:
            headers["X-User"] = user
        return self.http.request(method, path, headers=headers, **kwargs)

    def get(self, path, **kw):
        return self.call("GET", path, **kw)

    def post(self, path, **kw):
        return self.call("POST", path, **kw)

    def put(self, path, **kw):
        return self.call("PUT", path, **kw)

    def patch(self, path, **kw):
        return self.call("PATCH", path, **kw)

    def delete(self, path, **kw):
        return self.call("DELETE", path, **kw)

    # Clock --------------------------------------------------------------------------------
    def set_clock(self, when: str = START) -> str:
        self.clock = parse_iso(when)
        ok(self.http.put("/api/clock", json={"now": when}))
        return when

    def advance(self, seconds: int) -> str:
        assert self.clock is not None, "freeze the clock first"
        return self.set_clock(iso(self.clock + dt.timedelta(seconds=seconds)))

    def now(self) -> str:
        return iso(self.clock)

    # Workspaces and cases -------------------------------------------------------------------
    def workspace(self, name=None, owner=OWNER, members=None) -> str | None:
        """A new workspace owned by `owner` with `members` ({user: role}); None before step 6."""
        if not TEAMS:
            return None
        ws = ok(self.post("/api/workspaces", user=owner, json={"name": name or uid("ws-")}), 201)
        for member, role in (members or {}).items():
            ok(self.put(f"/api/workspaces/{ws['id']}/members/{member}", user=owner,
                        json={"role": role}))  # fmt: skip
        return ws["id"]

    @property
    def ws(self) -> str | None:
        if TEAMS and self._ws is None:
            self._ws = self.workspace(
                "Main", members={EDITOR: "editor", VIEWER: "viewer"}
            )
        return self._ws

    def case(self, name=None, ws="default", user="default") -> dict:
        body = {"name": name or uid("Case ")}
        ws = self.ws if ws == "default" else ws
        if ws:
            body["workspace_id"] = ws
        return ok(self.post("/api/cases", user=user, json=body), 201)

    def doc(self, case_id, title=None, text="Some text", user="default") -> dict:
        body = {"title": title or uid("Doc "), "text": text}
        return ok(self.post(f"/api/cases/{case_id}/documents", user=user, json=body), 201)

    def document(self, doc_id, user="default") -> dict:
        return ok(self.get(f"/api/documents/{doc_id}", user=user))

    def case_docs(self, case_id, user="default") -> list[dict]:
        return ok(self.get(f"/api/cases/{case_id}", user=user))["documents"]

    # Jobs -----------------------------------------------------------------------------------
    def job(self, job_id, user="default") -> dict:
        return ok(self.get(f"/api/jobs/{job_id}", user=user))

    def wait_job(self, job_id, statuses=("completed",), timeout=15.0, user="default") -> dict:
        def reached():
            job = self.job(job_id, user)
            return job if job["status"] in statuses else None

        found = wait_for(reached, timeout)
        assert found, f"job never reached {statuses}: {self.job(job_id, user)}"
        return found

    def connect(self, case_id, source, credentials, user="default") -> dict:
        body = {"source": source, "credentials": credentials}
        return ok(self.post(f"/api/cases/{case_id}/connections", user=user, json=body), 201)

    def start_import(self, connection_id, user="default") -> dict:
        return ok(self.post(f"/api/connections/{connection_id}/imports", user=user), 202)

    def review(self, doc_id, decision="approved", comment="", version=None, user="default"):
        version = version if version is not None else self.document(doc_id, user)["version"]
        body = {"decision": decision, "comment": comment, "version": version}
        return ok(self.post(f"/api/documents/{doc_id}/reviews", user=user, json=body), 201)


def source_items(items: list[tuple]) -> tuple[list[dict], list[dict]]:
    """(id, title, text, revision) tuples as ParcelBox items and as BoxLoop entries."""
    parcel = [{"id": i, "title": t, "text": x, "revision": r} for i, t, x, r in items]
    box = [{"key": i, "name": t, "body": x, "version": r} for i, t, x, r in items]
    return parcel, box


def credentials(key: str) -> dict:
    return {"token": key} if SOURCE == "parcelbox" else {"api_key": key}


def import_from_source(app, hub, case_id, items, key=None, user="default", connection=None):
    """Import `items` [(id, title, text, revision)] through the current source (ParcelBox before
    step 13, BoxLoop after) and wait for completion. Returns (connection, job, key)."""
    key = key or uid("k-")
    parcel, box = source_items(items)
    if SOURCE == "parcelbox":
        hub.parcelbox(key, parcel, page_size=2)
        connection = connection or app.connect(case_id, "parcelbox", {"token": key}, user=user)
    else:
        hub.boxloop(key, box, ready_after=0)
        connection = connection or app.connect(case_id, "boxloop", {"api_key": key}, user=user)
    job = app.start_import(connection["id"], user=user)
    job = app.wait_job(job["id"], user=user)
    return connection, job, key


def by_external(app, case_id, user="default") -> dict:
    return {
        d["external_id"]: d
        for d in (app.document(x["id"], user) for x in app.case_docs(case_id, user))
        if d.get("external_id") is not None
    }


def parcelbox_era(test):
    """A ParcelBox-only check. From step 13 ParcelBox is retired, so the check becomes: a new
    ParcelBox connection is refused with 422 unsupported_source."""
    if not PARCEL_RETIRED:
        return test

    @functools.wraps(test)
    def retired(**fixtures):
        app = fixtures.get("app") or fixtures.get("fresh_app")
        case = app.case()
        response = app.post(
            f"/api/cases/{case['id']}/connections",
            json={"source": "parcelbox", "credentials": {"token": "pb"}},
        )
        expect_error(response, 422, "unsupported_source")

    return retired


def export_era(test):
    """A JSON-download check. Probe 4 removes JSON downloads, so the check becomes: the download
    endpoint is gone (404)."""
    if not EXPORT_RETIRED:
        return test

    @functools.wraps(test)
    def retired(**fixtures):
        app = fixtures.get("app") or fixtures.get("fresh_app")
        case = app.case()
        assert app.get(f"/api/cases/{case['id']}/export").status_code == 404

    return retired


def expected_export(app, case_id, user="default") -> dict:
    """The request 12 export document, assembled from the regular API."""
    case = ok(app.get(f"/api/cases/{case_id}", user=user))
    documents = []
    for item in case["documents"]:
        doc = app.document(item["id"], user)
        documents.append({
            "id": doc["id"], "title": doc["title"], "text": doc["text"],
            "version": doc["version"], "source": doc["source"],
            "external_id": doc["external_id"], "responsible": doc["responsible"],
            "versions": ok(app.get(f"/api/documents/{doc['id']}/versions", user=user))["versions"],
            "reviews": [
                {k: r[k] for k in ("id", "version", "decision", "comment", "user", "decided_at")}
                for r in ok(app.get(f"/api/documents/{doc['id']}/reviews", user=user))["reviews"]
            ],
        })  # fmt: skip
    return {
        "format": "caseflow-case/1",
        "case": {"id": case["id"], "name": case["name"], "workspace_id": case["workspace_id"]},
        "documents": documents,
    }


@pytest.fixture(scope="session")
def hub():
    server, state = hubmod.start()
    yield state
    state.release()
    server.shutdown()


@pytest.fixture(autouse=True)
def _fresh_hub(hub):
    hub.reset()
    yield
    hub.release()


@pytest.fixture(scope="module")
def app(hub):
    instance = App(hub.url)
    yield instance
    instance.close()


@pytest.fixture
def fresh_app(hub):
    instance = App(hub.url)
    yield instance
    instance.close()
