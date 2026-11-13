"""Hidden acceptance fixtures for DispatchLedger: fake outside services in-process (`hub.py`),
the candidate web app as a subprocess launched from its `run.json`, and its worker command.

`DRIFT_CANDIDATE` is the candidate checkout; `DRIFT_STEP` is the step being evaluated. It
applies the requirement lifecycle: later requests deliberately change earlier behaviour
(queued labels at 3, warehouse stock at 7, staff login at 10, currencies at 15), so helpers
and era-dependent assertions follow the step being audited instead of treating requested
changes as regressions.
"""

from __future__ import annotations

import csv
import io
import itertools
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import hub as hubmod  # noqa: E402

CANDIDATE = Path(os.environ.get("DRIFT_CANDIDATE", ".")).resolve()
STEP = int(os.environ.get("DRIFT_STEP", "15"))
STOCK = STEP >= 1
QUEUED = STEP >= 3
EMAILS = STEP >= 4
QUICKCRATE = STEP >= 5
WAREHOUSES = STEP >= 7
SPLIT = STEP >= 8
RETURNS = STEP >= 9
SHOPS = STEP >= 10
PINE = STEP >= 14
CURRENCIES = STEP >= 15

T0 = 1772442000  # 2026-03-02T09:00:00Z
DAY = 86400
STAFF = {"main": ("morgan", "morgan-test-pass"), "harbour": ("rowan", "rowan-test-pass")}
CREDENTIALS = {
    "main": {
        "parcelfox": {"token": "pf-test-token"},
        "quickcrate": {"api_key": "qc-test-key", "callback_secret": "qc-callback-secret"},
        "parcelpine": {"token": "pp-test-token"},
    },
    "harbour": {
        "parcelfox": {"token": "pf-harbour-token"},
        "quickcrate": {"api_key": "qc-harbour-key", "callback_secret": "qc-harbour-secret"},
        "parcelpine": {"token": "pp-harbour-token"},
    },
}
ADA = {"name": "Ada Lovelace", "email": "ada@example.test"}
GRACE = {"name": "Grace Hopper", "email": "grace@example.test"}
ADDRESS = {"name": "Ada Lovelace", "line1": "12 Analytical Row", "city": "London",
           "postcode": "N1 9GU", "country": "GB"}  # fmt: skip


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def uid(prefix: str = "p") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def error_code(response: httpx.Response) -> str | None:
    try:
        return response.json()["error"]["code"]
    except (ValueError, KeyError, TypeError):
        return None


def expect_error(response: httpx.Response, status: int, code: str) -> None:
    assert (response.status_code, error_code(response)) == (status, code), response.text[:500]


def iso(t: float) -> str:
    return datetime.fromtimestamp(int(t), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def day_of(t: float) -> str:
    return iso(t)[:10]


def parse_time(value: str | None) -> float | None:
    if value is None:
        return None
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


def money(amount: int, currency: str = "GBP") -> str:
    if currency == "JPY":
        return f"¥{amount}"
    symbol = {"GBP": "£", "EUR": "€"}[currency]
    return f"{symbol}{amount // 100}.{amount % 100:02d}"


def plain(amount: int, currency: str = "GBP") -> str:
    return str(amount) if currency == "JPY" else f"{amount // 100}.{amount % 100:02d}"


def read_csv(text: str) -> list[list[str]]:
    return [row for row in csv.reader(io.StringIO(text)) if row]


def subset(record: dict, expected: dict) -> bool:
    return all(k in record and record[k] == v for k, v in expected.items())


_REVISION = itertools.count(1000)


class App:
    """One running candidate web app with its own data directory and clock file."""

    def __init__(self, hub, configure: bool = True) -> None:
        self.hub = hub
        self.root = Path(tempfile.mkdtemp(prefix="dl-app-"))
        self.data = self.root / "data"
        self.clock = self.root / "clock"
        self.now = T0
        self.clock.write_text(f"{self.now}\n")
        self.port = free_port()
        self.proc: subprocess.Popen | None = None
        self.tokens: dict[str, str] = {}
        self.workers: list[subprocess.Popen] = []
        self.start()
        if configure:
            self.configure_all()

    @property
    def public_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def env(self) -> dict:
        return {
            **os.environ,
            "DISPATCHLEDGER_EXTERNAL_URL": self.hub.url,
            "DISPATCHLEDGER_DATA_DIR": str(self.data),
            "DISPATCHLEDGER_PUBLIC_URL": self.public_url,
            "DISPATCHLEDGER_CLOCK_FILE": str(self.clock),
            "DISPATCHLEDGER_MAILPOST_KEY": "mp-test-key",
            "PYTHONDONTWRITEBYTECODE": "1",
        }

    def run_json(self) -> dict:
        return json.loads((CANDIDATE / "run.json").read_text())

    def start(self) -> None:
        argv = [part.replace("{port}", str(self.port)) for part in self.run_json()["command"]]
        self.log = open(self.root / "service.log", "ab")
        self.proc = subprocess.Popen(
            argv, cwd=CANDIDATE, env=self.env, stdout=self.log, stderr=subprocess.STDOUT
        )
        self.http = httpx.Client(base_url=self.public_url, timeout=30)
        self.tokens = {}
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                break
            try:
                # Request 10 makes every unlisted /api endpoint staff-only and does not
                # list /api/health, so a literal reading answers 401. Any non-5xx reply
                # means the web app is up; no DispatchLedger test asserts on health.
                if self.http.get("/api/health").status_code < 500:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        tail = (self.root / "service.log").read_text(errors="replace")[-2000:]
        self.stop()
        pytest.fail(f"candidate web app did not start:\n{tail}")

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
        for proc in self.workers:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        self.stop()
        shutil.rmtree(self.root, ignore_errors=True)

    # Clock ---------------------------------------------------------------------------------
    def set_clock(self, t: float) -> None:
        self.now = t
        self.clock.write_text(f"{t}\n")

    def advance(self, seconds: float) -> None:
        self.set_clock(self.now + seconds)

    def next_day(self, hour: int = 9) -> str:
        """Jump to a fresh UTC day (so report tests own their dates); returns that date."""
        start = (int(self.now) // DAY + 1) * DAY
        self.set_clock(start + hour * 3600)
        return day_of(start)

    # HTTP ----------------------------------------------------------------------------------
    def token(self, shop: str) -> str:
        if shop not in self.tokens:
            username, password = STAFF[shop]
            response = self.http.post("/api/login", json={"username": username, "password": password})
            assert response.status_code == 200, response.text[:500]
            self.tokens[shop] = response.json()["token"]
        return self.tokens[shop]

    def headers(self, staff: str | None) -> dict:
        if SHOPS and staff:
            return {"Authorization": f"Bearer {self.token(staff)}"}
        return {}

    def call(self, method, path, staff="main", shop=None, **kwargs) -> httpx.Response:
        headers = {**self.headers(staff), **(kwargs.pop("headers", {}) or {})}
        if shop is not None and SHOPS:
            params = dict(kwargs.pop("params", {}) or {})
            params["shop"] = shop
            kwargs["params"] = params
        return self.http.request(method, path, headers=headers, **kwargs)

    def get(self, path, **kw):
        return self.call("GET", path, **kw)

    def post(self, path, **kw):
        return self.call("POST", path, **kw)

    def put(self, path, **kw):
        return self.call("PUT", path, **kw)

    def patch(self, path, **kw):
        return self.call("PATCH", path, **kw)

    def ok(self, response: httpx.Response, *statuses: int) -> dict:
        assert response.status_code in (statuses or (200,)), response.text[:800]
        return response.json()

    # Shop helpers ----------------------------------------------------------------------------
    def configure(self, carrier: str, staff: str = "main") -> None:
        response = self.put(f"/api/carriers/{carrier}/credentials", staff=staff,
                            json=CREDENTIALS[staff][carrier])  # fmt: skip
        assert response.status_code in (200, 204), response.text[:500]

    def configure_all(self, staff: str = "main") -> None:
        if STEP >= 2:
            self.configure("parcelfox", staff)
        if QUICKCRATE:
            self.configure("quickcrate", staff)
        if PINE:
            self.configure("parcelpine", staff)

    def shop_of(self, staff: str | None) -> str | None:
        return staff if staff and staff != "main" else None

    def product(self, price=500, stock=20, name=None, staff="main", south=0, feed=True) -> str:
        pid = uid("p")
        body = {"id": pid, "name": name or f"Item {pid}", "price": price}
        if STOCK and not WAREHOUSES:
            body["stock"] = stock
        self.ok(self.post("/api/products", staff=staff, json=body), 201)
        if WAREHOUSES and feed:
            self.feed([("north", pid, stock), ("south", pid, south)], staff=staff)
        return pid

    def feed(self, rows, staff="main") -> dict:
        snapshots = [{"warehouse": w, "sku": s, "available": n, "revision": next(_REVISION)}
                     for w, s, n in rows]  # fmt: skip
        return self.ok(self.post("/api/warehouse-feed", staff=staff, json={"snapshots": snapshots}))

    def set_stock(self, pid, n, staff="main", warehouse="north") -> None:
        if WAREHOUSES:
            self.feed([(warehouse, pid, n)], staff=staff)
        else:
            self.ok(self.put(f"/api/products/{pid}/stock", staff=staff, json={"stock": n}))

    def get_product(self, pid, staff="main") -> dict:
        return self.ok(self.get(f"/api/products/{pid}", staff=None, shop=self.shop_of(staff)))

    def checkout(self, items, customer=ADA, key=None, staff="main") -> httpx.Response:
        body = {"customer": customer, "items": [{"product_id": p, "quantity": q} for p, q in items]}
        if key is not None:
            body["submission_key"] = key
        return self.post("/api/orders", staff=None, shop=self.shop_of(staff), json=body)

    def order(self, items=None, customer=ADA, staff="main", price=500) -> dict:
        if items is None:
            items = [(self.product(price=price, staff=staff), 1)]
        return self.ok(self.checkout(items, customer, staff=staff), 201)

    def get_order(self, order_id, staff="main") -> dict:
        return self.ok(self.get(f"/api/orders/{order_id}", staff=staff))

    def request_label(self, order_id, carrier=None, address=None, weight=1200, shipment=None,
                      staff="main") -> httpx.Response:  # fmt: skip
        body = {"address": address or ADDRESS, "weight_g": weight}
        if carrier is not None:
            body["carrier"] = carrier
        path = f"/api/orders/{order_id}/label"
        if shipment is not None:
            path = f"/api/orders/{order_id}/shipments/{shipment}/label"
        return self.post(path, staff=staff, json=body)

    def ship(self, order_id, carrier=None, shipment=None, staff="main", **kw) -> dict:
        """Request a label and (from request 3) run the worker; returns the order."""
        response = self.request_label(order_id, carrier, shipment=shipment, staff=staff, **kw)
        assert response.status_code in (200, 201, 202), response.text[:500]
        if QUEUED:
            self.work()
        return self.get_order(order_id, staff)

    # Worker --------------------------------------------------------------------------------
    def worker_argv(self) -> list[str]:
        spec = self.run_json().get("worker")
        assert isinstance(spec, list) and spec, "run.json has no worker command"
        return list(spec)

    def work(self, timeout: float = 60, check: bool = True) -> subprocess.CompletedProcess:
        result = subprocess.run(
            [*self.worker_argv(), "--until-idle"], cwd=CANDIDATE, env=self.env,
            capture_output=True, text=True, timeout=timeout,
        )  # fmt: skip
        if check:
            assert result.returncode == 0, (result.stdout + result.stderr)[-2000:]
        return result

    def worker_bg(self) -> subprocess.Popen:
        log = open(self.root / f"worker-{len(self.workers)}.log", "ab")
        proc = subprocess.Popen(self.worker_argv(), cwd=CANDIDATE, env=self.env, stdout=log,
                                stderr=subprocess.STDOUT)  # fmt: skip
        self.workers.append(proc)
        return proc


def shipment_of(order: dict, index: int = 0) -> dict:
    return order["shipments"][index]


def emails_of(order: dict, kind: str | None = None) -> list[dict]:
    return [e for e in order.get("emails", []) if kind is None or e["kind"] == kind]


def wait_for(predicate, timeout: float = 10.0, interval: float = 0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    return predicate()


def parallel(fn, count: int):
    barrier = threading.Barrier(count)

    def run(i):
        barrier.wait()
        return fn(i)

    with ThreadPoolExecutor(count) as pool:
        return list(pool.map(run, range(count)))


def fresh_client(app: App) -> httpx.Client:
    return httpx.Client(base_url=app.public_url, timeout=30)


def stop_worker(proc: subprocess.Popen, sig=signal.SIGTERM, timeout: float = 20) -> int:
    proc.send_signal(sig)
    return proc.wait(timeout)


@pytest.fixture(scope="session")
def hub():
    server, state = hubmod.start()
    yield state
    server.shutdown()


@pytest.fixture(autouse=True)
def _fresh_hub(hub):
    hub.reset()
    yield


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
def bare_app(hub):
    instance = App(hub, configure=False)
    yield instance
    instance.close()
