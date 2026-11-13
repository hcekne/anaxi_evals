"""Deterministic fake outside services for the CaseFlow track.

One threaded HTTP server plays every outside service the requests mention. Candidates never see
this file; they only get the documentation inside each request. Hidden tests drive the `Hub`
object directly (same process):

- ParcelBox (request 2): `GET /parcelbox/documents[?cursor=]`, bearer token per library.
- NoticeSink (request 8): `POST /noticesink/messages`, deduplicating by `message_id`.
- BoxLoop (request 10): `POST /boxloop/exports`, `GET /boxloop/exports/{id}`, downloads.
- ArchiveTap (probes): `GET /archivetap/records[?page=]`, account/secret headers.

Faults are explicit and counted: `fault(service, key, page, status, retry_after, times)` answers
the next `times` matching requests with `status`; `hold(service, key, page)` keeps the next
matching request open until `release()`; NoticeSink follows a per-document plan
(`notice_fault`: 503, 400 or "drop" = accept, then close the connection without answering). Every request is recorded in `calls`.

Run standalone with `python hub.py --port 8765`.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

DROP = object()  # answer by closing the connection without a response
HOLD_LIMIT = 60.0


class Hub:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.url = ""
        self.holds: list[dict] = []
        self.reset()

    def reset(self) -> None:
        self.release()
        with self.lock:
            self.calls: list[dict] = []
            self.faults: list[dict] = []
            self.holds = []
            self.parcel: dict[str, dict] = {}
            self.archive: dict[tuple, dict] = {}
            self.cursors: dict[str, tuple[str, int]] = {}
            self.notices: dict[str, dict] = {}
            self.notice_plan: dict[str, list] = {}
            self.box: dict[str, dict] = {}
            self.exports: dict[str, dict] = {}
            self.downloads: dict[str, str] = {}
            self.export_seq = 0

    # -- configuration -----------------------------------------------------------------------
    def parcelbox(self, token: str, items: list[dict], page_size: int = 2) -> None:
        with self.lock:
            self.parcel[token] = {"items": [dict(i) for i in items], "page_size": page_size}

    def archivetap(self, account: str, secret: str, records: list[dict], page_size: int = 2):
        with self.lock:
            self.archive[(account, secret)] = {
                "items": [dict(r) for r in records],
                "page_size": page_size,
            }

    def boxloop(self, key: str, items: list[dict], ready_after: int = 0, fail: bool = False):
        """`ready_after`: number of status checks answered `pending` before `ready`."""
        with self.lock:
            self.box[key] = {"items": [dict(i) for i in items], "ready_after": ready_after,
                             "fail": fail}  # fmt: skip

    def notice_fault(self, document_id: str, *outcomes) -> None:
        """Answer the next NoticeSink requests about `document_id` with `outcomes` in order:
        an HTTP status (503 offline, 400 malformed) or "drop" (accept, then lose the reply)."""
        with self.lock:
            self.notice_plan.setdefault(document_id, []).extend(outcomes)

    def messages_for(self, document_id: str) -> list[dict]:
        with self.lock:
            return [m for m in self.notices.values() if m.get("document_id") == document_id]

    def forget_exports(self) -> None:
        """BoxLoop restarted: every export id and download URL it handed out is gone (404)."""
        with self.lock:
            self.exports.clear()
            self.downloads.clear()

    def fault(self, service, key=None, page=None, status=500, retry_after=None, times=1):
        with self.lock:
            self.faults.append({"service": service, "key": key, "page": page, "status": status,
                                "retry_after": retry_after, "times": times})  # fmt: skip

    def hold(self, service, key=None, page=None) -> dict:
        entry = {"service": service, "key": key, "page": page, "event": threading.Event(),
                 "used": False, "entered": threading.Event()}  # fmt: skip
        with self.lock:
            self.holds.append(entry)
        return entry

    def release(self) -> None:
        for entry in list(getattr(self, "holds", [])):
            entry["event"].set()

    # -- inspection --------------------------------------------------------------------------
    def calls_to(self, service: str, **match) -> list[dict]:
        with self.lock:
            return [
                c
                for c in self.calls
                if c["service"] == service and all(c.get(k) == v for k, v in match.items())
            ]

    # -- internals ---------------------------------------------------------------------------
    def _cursor(self, key: str, offset: int) -> str:
        raw = hashlib.sha256(f"{key}:{offset}".encode()).digest()[:9] + b"\xfb\xff"
        cursor = base64.b64encode(raw).decode() + "=="
        self.cursors[cursor] = (key, offset)
        return cursor

    def _take_fault(self, service, key, page):
        with self.lock:
            for fault in self.faults:
                if (
                    fault["times"] > 0
                    and fault["service"] == service
                    and fault["key"] in (None, key)
                    and fault["page"] in (None, page)
                ):
                    fault["times"] -= 1
                    return fault
        return None

    def _take_hold(self, service, key, page):
        with self.lock:
            for entry in self.holds:
                if (
                    not entry["used"]
                    and entry["service"] == service
                    and entry["key"] in (None, key)
                    and entry["page"] in (None, page)
                ):
                    entry["used"] = True
                    return entry
        return None

    def _record(self, **record) -> dict:
        record["at"] = time.monotonic()
        with self.lock:
            self.calls.append(record)
        return record

    def _pause(self, service, key, page) -> None:
        entry = self._take_hold(service, key, page)
        if entry:
            entry["entered"].set()
            entry["event"].wait(HOLD_LIMIT)

    def handle(self, method: str, target: str, headers: dict, raw: bytes):
        parts = urlsplit(target)
        path = [p for p in parts.path.split("/") if p]
        query = {k: v[0] for k, v in parse_qs(parts.query, keep_blank_values=True).items()}
        headers = {k.lower(): v for k, v in headers.items()}
        try:
            body = json.loads(raw) if raw else None
        except ValueError:
            body = None
        if path[:2] == ["parcelbox", "documents"] and len(path) == 2 and method == "GET":
            return self._paged("parcelbox", headers, query, "cursor")
        if path[:2] == ["archivetap", "records"] and len(path) == 2 and method == "GET":
            return self._paged("archivetap", headers, query, "page")
        if path == ["noticesink", "messages"] and method == "POST":
            return self._notice(headers, raw, body)
        if path and path[0] == "boxloop":
            return self._boxloop(method, path[1:], headers, body)
        self._record(service="unknown", method=method, path=target)
        return 404, {"error": "no such route"}, {}

    def _paged(self, service, headers, query, param):
        if service == "parcelbox":
            auth = headers.get("authorization", "")
            key = auth[7:] if auth.startswith("Bearer ") else None
            library = self.parcel.get(key) if key else None
        else:
            key = (headers.get("x-archive-account"), headers.get("x-archive-secret"))
            library = self.archive.get(key)
            key = key[0]
        cursor = query.get(param)
        offset = 0
        if cursor is not None:
            known = self.cursors.get(cursor)
            if not known or known[0] != key:
                self._record(service=service, key=key, page=None, cursor=cursor, status=400)
                return 400, {"error": "unknown cursor"}, {}
            offset = known[1]
        size = library["page_size"] if library else 1
        page = offset // size + 1
        record = self._record(service=service, key=key, page=page, cursor=cursor, status=None)
        self._pause(service, key, page)
        fault = self._take_fault(service, key, page)
        if fault:
            record["status"] = fault["status"]
            extra = {}
            if fault["retry_after"] is not None:
                extra["Retry-After"] = str(fault["retry_after"])
            return fault["status"], {"error": "injected"}, extra
        if library is None:
            record["status"] = 401
            return 401, {"error": "unauthorized"}, {}
        items = library["items"][offset : offset + size]
        following = offset + size
        with self.lock:
            nxt = self._cursor(key, following) if following < len(library["items"]) else None
        record["status"] = 200
        if service == "parcelbox":
            return 200, {"items": items, "next_cursor": nxt}, {}
        return 200, {"records": items, "next_page": nxt}, {}

    def _notice(self, headers, raw, body):
        record = self._record(service="noticesink", body=body, raw=raw, status=None)
        doc = body.get("document_id") if isinstance(body, dict) else None
        with self.lock:
            plan = self.notice_plan.get(doc) or []
            outcome = plan.pop(0) if plan else None
            if isinstance(outcome, int):
                record["status"] = outcome
                return outcome, {"error": "injected"}, {}
            fields = {"message_id", "workspace_id", "document_id", "revision", "recipient", "text"}
            if not isinstance(body, dict) or set(body) != fields:
                record["status"] = 400
                return 400, {"error": "malformed"}, {}
            ident = body["message_id"]
            if ident in self.notices:
                record["status"] = 200
                return 200, {"status": "duplicate"}, {}
            self.notices[ident] = body
            if outcome == "drop":
                record["status"] = "dropped"
                return DROP, None, {}
            record["status"] = 202
            return 202, {"status": "accepted"}, {}

    def _boxloop(self, method, path, headers, body):
        key = headers.get("x-boxloop-key")
        account = self.box.get(key)
        if path == ["exports"] and method == "POST":
            record = self._record(service="boxloop", op="create", key=key, status=None)
            self._pause("boxloop", key, "create")
            fault = self._take_fault("boxloop", key, "create")
            if fault:
                record["status"] = fault["status"]
                return fault["status"], {"error": "injected"}, {}
            if account is None:
                record["status"] = 401
                return 401, {"error": "unauthorized"}, {}
            with self.lock:
                self.export_seq += 1
                ident = f"exp-{self.export_seq}-{hashlib.sha256(key.encode()).hexdigest()[:6]}"
                self.exports[ident] = {"key": key, "polls": 0}
            record["status"] = 201
            record["export"] = ident
            return 201, {"id": ident, "status": "pending"}, {}
        if len(path) == 2 and path[0] == "exports" and method == "GET":
            ident = path[1]
            record = self._record(service="boxloop", op="status", key=key, export=ident,
                                  status=None)  # fmt: skip
            self._pause("boxloop", key, "status")
            fault = self._take_fault("boxloop", key, "status")
            if fault:
                record["status"] = fault["status"]
                return fault["status"], {"error": "injected"}, {}
            if account is None:
                record["status"] = 401
                return 401, {"error": "unauthorized"}, {}
            with self.lock:
                export = self.exports.get(ident)
                if export is None or export["key"] != key:
                    record["status"] = 404
                    return 404, {"error": "no such export"}, {}
                export["polls"] += 1
                record["status"] = 200
                if account["fail"]:
                    return 200, {"id": ident, "status": "failed", "reason": "quota"}, {}
                if export["polls"] <= account["ready_after"]:
                    return 200, {"id": ident, "status": "pending"}, {}
                token = hashlib.sha256(f"dl:{ident}".encode()).hexdigest()[:16]
                self.downloads[token] = ident
                url = f"{self.url}/boxloop/downloads/{token}"
                return 200, {"id": ident, "status": "ready", "download_url": url}, {}
        if len(path) == 2 and path[0] == "downloads" and method == "GET":
            record = self._record(service="boxloop", op="download", key=key, status=None)
            self._pause("boxloop", key, "download")
            if account is None:
                record["status"] = 401
                return 401, {"error": "unauthorized"}, {}
            with self.lock:
                ident = self.downloads.get(path[1])
                export = self.exports.get(ident) if ident else None
            if export is None or export["key"] != key:
                record["status"] = 404
                return 404, {"error": "no such download"}, {}
            record["status"] = 200
            return 200, account["items"], {}
        self._record(service="boxloop", op="unknown", key=key, status=404)
        return 404, {"error": "no such route"}, {}


def start(port: int = 0) -> tuple[ThreadingHTTPServer, Hub]:
    hub = Hub()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _serve(self, method: str) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            status, payload, extra = hub.handle(method, self.path, dict(self.headers), raw)
            if status is DROP:
                self.close_connection = True
                return
            data = json.dumps(payload, ensure_ascii=False).encode()
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                for name, value in extra.items():
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(data)
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
