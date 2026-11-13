"""Deterministic fake outside services for the DispatchLedger track.

One threaded HTTP server plays every outside service the requests document. Candidates never
see this file; they only get the documentation inside each request. Hidden tests drive the
`Hub` object directly (same process):

- ParcelFox  `/parcelfox/labels`, `/parcelfox/labels/by-key/{key}`      (request 2)
- MailPost   `/mailpost/messages`                                       (request 4)
- QuickCrate `/quickcrate/jobs`, `/quickcrate/jobs/{id}` + callbacks    (request 5)
- ParcelPine `/parcelpine/shipments`                                    (request 14)
- KiteCourier `/kitecourier/consignments...`                            (probe 2)

Every request is recorded in `calls`. Physical side effects (labels, delivered messages,
jobs, shipments) are recorded separately, so a test can count parcels independently of calls.

Faults are per operation target (for example `parcelfox.create`, `mailpost.send`):

- `fail_next` + `fail_status` (default 503): reply with an error **before** doing anything.
- `drop_after`: do the operation, then drop the connection without answering.
- `latency`: sleep this many seconds before doing the operation.
- `retry_after` (with `fail_status` 429): the `Retry-After` header value.
- `reject_next`: ParcelFox/QuickCrate reply 422 invalid_request (non-retryable).

Run standalone with `python hub.py --port 8765`.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import itertools
import json
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

import httpx

DROP = object()

TOKENS = {
    "parcelfox": {"pf-test-token": "main", "pf-harbour-token": "harbour"},
    "mailpost": {"mp-test-key": "main"},
    "quickcrate": {"qc-test-key": "main", "qc-harbour-key": "harbour"},
    "parcelpine": {"pp-test-token": "main", "pp-harbour-token": "harbour"},
    "kitecourier": {"kc-test-key": "main", "kc-harbour-key": "harbour"},
}
QC_SECRETS = {"qc-test-key": "qc-callback-secret", "qc-harbour-key": "qc-harbour-secret"}
PINE_COUNTRIES = {"GB", "IE", "FR", "DE", "NL", "BE"}
_rand = random.Random()


def _digits(n: int) -> str:
    return "".join(_rand.choice("0123456789") for _ in range(n))


def _json(status: int, value) -> tuple[int, bytes, dict]:
    return status, json.dumps(value).encode(), {}


def _str(value, limit: int = 100) -> bool:
    return isinstance(value, str) and 0 < len(value) <= limit


class Hub:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.url = ""
        self.reset()

    def reset(self) -> None:
        with self.lock:
            self.calls: list[dict] = []
            self.faults: dict[str, dict] = {}
            self.pf_labels: dict[tuple[str, str], dict] = {}  # (token, key) -> label
            self.pf_created: list[dict] = []
            self.mail: dict[tuple[str, str], dict] = {}
            self.delivered: list[dict] = []
            self.qc_jobs: dict[str, dict] = {}
            self.qc_by_ref: dict[tuple[str, str], str] = {}
            self.qc_created: list[dict] = []
            self.qc_auto: str | None = None  # "ready" makes new jobs ready immediately
            self.callbacks: list[dict] = []
            self.pine: dict[tuple[str, str], dict] = {}
            self.pine_created: list[dict] = []
            self.kite: dict[str, dict] = {}
            self.kite_by_ref: dict[tuple[str, str], str] = {}
            self.kite_created: list[dict] = []
            self.seq = itertools.count(1)

    # -- test controls -------------------------------------------------------------------
    def fault(self, target: str, **values) -> None:
        with self.lock:
            self.faults.setdefault(target, {}).update(values)

    def clear_faults(self) -> None:
        with self.lock:
            self.faults.clear()

    def calls_to(self, target: str) -> list[dict]:
        with self.lock:
            return [c for c in self.calls if c["target"] == target]

    def messages(self, to: str | None = None) -> list[dict]:
        with self.lock:
            return [m for m in self.delivered if to is None or m["to"] == to]

    def qc_set(self, job_id: str, status: str, send: bool = True) -> int | None:
        """Move a QuickCrate job to ready/failed; deliver its signed callback if registered."""
        with self.lock:
            job = self.qc_jobs[job_id]
            job["status"] = status
            job["sequence"] += 1
            if status == "ready":
                job["label"] = {
                    "tracking": "QC" + _digits(10),
                    "text": f"QUICKCRATE\n{job['recipient']['name']}\n{job['job_id']}",
                }
            elif status == "failed":
                job["failure"] = "address could not be verified"
            payload = self._qc_callback(job)
        return self.send_callback(payload) if send and payload else None

    def qc_callback(self, job_id: str, status: str | None = None, sequence: int | None = None):
        """A correctly signed callback for a job (optionally stale: older status/sequence)."""
        with self.lock:
            job = dict(self.qc_jobs[job_id])
        if status is not None:
            job.update(status=status, label=None if status == "pending" else job["label"])
        if sequence is not None:
            job["sequence"] = sequence
        return self._qc_callback(job)

    def _qc_callback(self, job: dict) -> dict | None:
        if not job.get("callback_url"):
            return None
        body = {
            "callback_id": f"cb_{next(self.seq)}",
            "job_id": job["job_id"],
            "client_ref": job["client_ref"],
            "status": job["status"],
            "sequence": job["sequence"],
            "label": job["label"],
            "failure": job["failure"],
        }
        raw = json.dumps(body).encode()
        secret = QC_SECRETS[job["token"]].encode()
        signature = "sha256=" + hmac.new(secret, raw, hashlib.sha256).hexdigest()
        return {"url": job["callback_url"], "raw": raw, "signature": signature, "body": body}

    def send_callback(self, callback: dict, signature: str | None = "keep") -> int | None:
        headers = {"Content-Type": "application/json"}
        sig = callback["signature"] if signature == "keep" else signature
        if sig is not None:
            headers["X-QuickCrate-Signature"] = sig
        try:
            response = httpx.post(callback["url"], content=callback["raw"], headers=headers, timeout=10)
        except httpx.HTTPError:
            status = None
        else:
            status = response.status_code
        with self.lock:
            self.callbacks.append({**callback, "status": status, "sent_signature": sig})
        return status

    def qc_job_for(self, client_ref_part: str = "") -> list[dict]:
        with self.lock:
            return [j for j in self.qc_jobs.values() if client_ref_part in j["client_ref"]]

    def kite_assign(self, consignment_id: str) -> str:
        with self.lock:
            item = self.kite[consignment_id]
            item["tracking_number"] = "KC" + _digits(9)
            return item["tracking_number"]

    # -- dispatch ------------------------------------------------------------------------
    def _take_fault(self, target: str) -> dict:
        with self.lock:
            fault = self.faults.get(target, {})
            out = {"latency": float(fault.get("latency", 0) or 0)}
            if fault.get("fail_next", 0) > 0:
                fault["fail_next"] -= 1
                out["status"] = int(fault.get("fail_status", 503))
                out["retry_after"] = fault.get("retry_after")
            elif fault.get("reject_next", 0) > 0:
                fault["reject_next"] -= 1
                out["reject"] = True
            elif fault.get("drop_after", 0) > 0:
                fault["drop_after"] -= 1
                out["drop"] = True
            return out

    def handle(self, method: str, path: str, headers: dict, raw: bytes):
        split = urlsplit(path)
        parts = [unquote(p) for p in split.path.split("/") if p]
        query = {k: v[0] for k, v in parse_qs(split.query).items()}
        headers = {k.lower(): v for k, v in headers.items()}
        try:
            body = json.loads(raw) if raw else None
        except ValueError:
            body = None
        route = self._route(method, parts)
        if route is None:
            return _json(404, {"error": "no such route"})
        service, op, handler = route
        target = f"{service}.{op}"
        fault = self._take_fault(target)
        record = {"service": service, "target": target, "method": method, "path": path,
                  "headers": headers, "raw": raw, "body": body, "at": time.monotonic()}  # fmt: skip
        with self.lock:
            self.calls.append(record)
        if fault["latency"]:
            time.sleep(fault["latency"])
        token = self._token(service, headers)
        if token is None:
            if service == "parcelpine":
                return _json(401, {"code": "unauthorized", "message": "bad token"})
            return _json(401, {"error": "unauthorized"})
        if "status" in fault:
            status = fault["status"]
            extra = {}
            if status == 429:
                extra["Retry-After"] = str(fault.get("retry_after") or 5)
            if service == "parcelpine":
                code = "rate_limited" if status == 429 else "unavailable"
                return status, json.dumps({"code": code, "message": "try later"}).encode(), extra
            return status, json.dumps({"error": "unavailable"}).encode(), extra
        if fault.get("reject"):
            return _json(422, {"error": "invalid_request", "detail": "rejected by test"})
        result = handler(token, parts, query, body)
        if fault.get("drop"):
            return DROP
        return result

    def _token(self, service: str, headers: dict) -> str | None:
        if service == "parcelfox":
            value = headers.get("authorization", "")
            token = value[7:] if value.startswith("Bearer ") else ""
        elif service == "mailpost":
            token = headers.get("x-mailpost-key", "")
        elif service == "quickcrate":
            token = headers.get("x-quickcrate-key", "")
        elif service == "parcelpine":
            value = headers.get("authorization", "")
            token = value[6:] if value.startswith("Token ") else ""
        else:
            token = headers.get("x-kite-key", "")
        return token if token in TOKENS[service] else None

    def _route(self, method: str, parts: list[str]):
        if parts[:2] == ["parcelfox", "labels"]:
            if method == "POST" and len(parts) == 2:
                return "parcelfox", "create", self._pf_create
            if method == "GET" and len(parts) == 4 and parts[2] == "by-key":
                return "parcelfox", "lookup", self._pf_lookup
        if parts[:2] == ["mailpost", "messages"] and len(parts) == 2:
            if method == "POST":
                return "mailpost", "send", self._mp_send
            if method == "GET":
                return "mailpost", "lookup", self._mp_lookup
        if parts[:2] == ["quickcrate", "jobs"]:
            if method == "POST" and len(parts) == 2:
                return "quickcrate", "create", self._qc_create
            if method == "GET" and len(parts) == 3:
                return "quickcrate", "get", self._qc_get
        if parts[:2] == ["parcelpine", "shipments"] and len(parts) == 2:
            if method == "POST":
                return "parcelpine", "create", self._pine_create
            if method == "GET":
                return "parcelpine", "lookup", self._pine_lookup
        if parts[:2] == ["kitecourier", "consignments"]:
            if method == "POST" and len(parts) == 2:
                return "kitecourier", "create", self._kite_create
            if method == "GET" and len(parts) == 2:
                return "kitecourier", "lookup", self._kite_lookup
            if method == "GET" and len(parts) == 4 and parts[3] == "tracking":
                return "kitecourier", "tracking", self._kite_tracking
        return None

    # -- ParcelFox ----------------------------------------------------------------------
    def _pf_create(self, token, parts, query, body):
        address = body.get("address") if isinstance(body, dict) else None
        ok = (
            isinstance(body, dict)
            and all(_str(body.get(k)) for k in ("order_ref", "shipment_ref", "idempotency_key"))
            and isinstance(address, dict)
            and all(_str(address.get(k)) for k in ("name", "line1", "city", "postcode", "country"))
            and type(body.get("weight_g")) is int
            and 1 <= body["weight_g"] <= 30000
        )
        if not ok:
            return _json(422, {"error": "invalid_request", "detail": "bad label request"})
        with self.lock:
            existing = self.pf_labels.get((token, body["idempotency_key"]))
            if existing:
                return _json(200, existing["label"])
            label = {
                "label_id": f"pfl_{next(self.seq)}",
                "tracking_code": "PF" + _digits(10),
                "label_text": f"PARCELFOX\nTO: {address['name']}\n{address['line1']}\n"
                f"{address['city']} {address['postcode']} {address['country']}\n"
                f"{body['weight_g']} g",
            }
            entry = {"token": token, "shop": TOKENS["parcelfox"][token], "body": body, "label": label}
            self.pf_labels[(token, body["idempotency_key"])] = entry
            self.pf_created.append(entry)
        return _json(201, label)

    def _pf_lookup(self, token, parts, query, body):
        with self.lock:
            existing = self.pf_labels.get((token, parts[3]))
        if not existing:
            return _json(404, {"error": "not_found"})
        return _json(200, existing["label"])

    # -- MailPost -----------------------------------------------------------------------
    def _mp_send(self, token, parts, query, body):
        if not (isinstance(body, dict) and all(_str(body.get(k), 100000) for k in ("to", "subject", "body"))
                and _str(body.get("dedup_key"))):  # fmt: skip
            return _json(422, {"error": "invalid_request"})
        with self.lock:
            existing = self.mail.get((token, body["dedup_key"]))
            if existing:
                return _json(200, {"message_id": existing["message_id"]})
            message = {"message_id": f"mp_{next(self.seq)}", **{k: body[k] for k in ("to", "subject", "body", "dedup_key")}}
            self.mail[(token, body["dedup_key"])] = message
            self.delivered.append(message)
        return _json(201, {"message_id": message["message_id"]})

    def _mp_lookup(self, token, parts, query, body):
        with self.lock:
            existing = self.mail.get((token, query.get("dedup_key", "")))
        return _json(200, {"messages": [existing] if existing else []})

    # -- QuickCrate ---------------------------------------------------------------------
    def _qc_create(self, token, parts, query, body):
        parcel = body.get("parcel") if isinstance(body, dict) else None
        recipient = parcel.get("recipient") if isinstance(parcel, dict) else None
        ok = (
            isinstance(body, dict)
            and _str(body.get("client_ref"))
            and (body.get("callback_url") is None or _str(body.get("callback_url"), 2000))
            and isinstance(parcel, dict)
            and type(parcel.get("weight_grams")) is int
            and parcel["weight_grams"] > 0
            and isinstance(recipient, dict)
            and all(_str(recipient.get(k)) for k in ("name", "city", "postcode", "country"))
            and isinstance(recipient.get("address_lines"), list)
            and recipient["address_lines"]
            and all(_str(line) for line in recipient["address_lines"])
        )
        if not ok:
            return _json(422, {"error": "invalid_request"})
        callback = None
        with self.lock:
            job_id = self.qc_by_ref.get((token, body["client_ref"]))
            if job_id:
                job = self.qc_jobs[job_id]
                return _json(200, {"job_id": job_id, "status": job["status"]})
            job_id = f"qcj_{next(self.seq)}"
            job = {"job_id": job_id, "client_ref": body["client_ref"], "token": token,
                   "shop": TOKENS["quickcrate"][token], "status": "pending", "sequence": 1,
                   "label": None, "failure": None, "callback_url": body.get("callback_url"),
                   "recipient": recipient, "body": body}  # fmt: skip
            self.qc_jobs[job_id] = job
            self.qc_by_ref[(token, body["client_ref"])] = job_id
            self.qc_created.append(job)
            auto = self.qc_auto
        if auto:
            threading.Timer(0.3, self.qc_set, args=(job_id, auto)).start()
        del callback
        return _json(202, {"job_id": job_id, "status": "pending"})

    def _qc_get(self, token, parts, query, body):
        with self.lock:
            job = self.qc_jobs.get(parts[2])
            if not job or job["token"] != token:
                return _json(404, {"error": "not_found"})
            view = {k: job[k] for k in ("job_id", "client_ref", "status", "label", "failure")}
        return _json(200, view)

    # -- ParcelPine ---------------------------------------------------------------------
    def _pine_create(self, token, parts, query, body):
        recipient = body.get("recipient") if isinstance(body, dict) else None
        weight = body.get("weight_kg") if isinstance(body, dict) else None
        ok = (
            isinstance(body, dict)
            and _str(body.get("client_reference"), 64)
            and isinstance(weight, str)
            and _valid_kg(weight)
            and isinstance(recipient, dict)
            and all(_str(recipient.get(k)) for k in ("name", "street", "city", "postal_code", "country_code"))
        )
        if not ok:
            return _json(422, {"code": "invalid_request", "message": "malformed shipment"})
        country = recipient["country_code"]
        if country not in PINE_COUNTRIES:
            return _json(422, {"code": "destination_unsupported",
                               "message": f"ParcelPine does not deliver to {country}"})  # fmt: skip
        with self.lock:
            existing = self.pine.get((token, body["client_reference"]))
            if existing:
                return _json(200, existing["shipment"])
            shipment = {
                "reference": f"PP-{next(self.seq)}",
                "document": {"format": "text", "content": f"PARCELPINE\n{recipient['name']}\n{weight} kg"},
                "tracking": "PP" + _digits(10),
            }
            entry = {"token": token, "shop": TOKENS["parcelpine"][token], "body": body, "shipment": shipment}
            self.pine[(token, body["client_reference"])] = entry
            self.pine_created.append(entry)
        return _json(201, shipment)

    def _pine_lookup(self, token, parts, query, body):
        with self.lock:
            existing = self.pine.get((token, query.get("client_reference", "")))
        if not existing:
            return _json(404, {"code": "not_found", "message": "no such shipment"})
        return _json(200, existing["shipment"])

    # -- KiteCourier (probe 2) ------------------------------------------------------------
    def _kite_create(self, token, parts, query, body):
        to = body.get("deliver_to") if isinstance(body, dict) else None
        ok = (
            isinstance(body, dict)
            and _str(body.get("request_id"))
            and type(body.get("mass_g")) is int
            and body["mass_g"] > 0
            and isinstance(to, dict)
            and all(_str(to.get(k)) for k in ("name", "line1", "city", "postcode", "country"))
        )
        if not ok:
            return _json(422, {"error": "invalid_request"})
        with self.lock:
            cid = self.kite_by_ref.get((token, body["request_id"]))
            if cid:
                item = self.kite[cid]
                return _json(200, {"consignment_id": cid, "label": item["label"]})
            cid = f"kc_{next(self.seq)}"
            item = {"consignment_id": cid, "token": token, "shop": TOKENS["kitecourier"][token],
                    "request_id": body["request_id"], "body": body, "tracking_number": None,
                    "label": {"format": "text", "content": f"KITECOURIER\n{to['name']}\n{cid}"}}  # fmt: skip
            self.kite[cid] = item
            self.kite_by_ref[(token, body["request_id"])] = cid
            self.kite_created.append(item)
        return _json(201, {"consignment_id": cid, "label": item["label"]})

    def _kite_lookup(self, token, parts, query, body):
        with self.lock:
            cid = self.kite_by_ref.get((token, query.get("request_id", "")))
            item = self.kite.get(cid) if cid else None
        if not item:
            return _json(404, {"error": "not_found"})
        return _json(200, {"consignment_id": cid, "label": item["label"]})

    def _kite_tracking(self, token, parts, query, body):
        with self.lock:
            item = self.kite.get(parts[2])
        if not item or item["token"] != token:
            return _json(404, {"error": "not_found"})
        if item["tracking_number"] is None:
            return _json(200, {"consignment_id": parts[2], "status": "awaiting_tracking", "tracking_number": None})
        return _json(200, {"consignment_id": parts[2], "status": "assigned",
                           "tracking_number": item["tracking_number"]})  # fmt: skip


def _valid_kg(value: str) -> bool:
    head, dot, tail = value.partition(".")
    return bool(dot) and head.isdigit() and len(tail) == 3 and tail.isdigit() and head == str(int(head))


def start(port: int = 0) -> tuple[ThreadingHTTPServer, Hub]:
    hub = Hub()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _serve(self, method: str) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            result = hub.handle(method, self.path, dict(self.headers), raw)
            if result is DROP:
                self.close_connection = True
                try:
                    self.connection.shutdown(2)
                except OSError:
                    pass
                return
            status, payload, extra = result
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                for key, value in extra.items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(payload)
            except OSError:
                pass

        def do_GET(self):  # noqa: N802
            self._serve("GET")

        def do_POST(self):  # noqa: N802
            self._serve("POST")

        def log_message(self, *args):  # silence
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    hub.url = f"http://127.0.0.1:{server.server_address[1]}"
    return server, hub


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    srv, _ = start(args.port)
    print(f"hub on {srv.server_address}")
    threading.Event().wait()
