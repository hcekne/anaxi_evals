"""Deterministic fake outside services for the RelayDesk track.

One threaded HTTP server plays every fictional outside service the requests document. Coding
agents never see this file; they only get the documentation inside each request. Hidden tests
drive the `Hub` object directly (same process):

- `plan(service, **plan)` queues the behaviour of the next request to a service
  (`pollen`, `pollen_stream`, `comet`, `harbor`, `quartz`, `nimbus`): `status` (+ `retry_after`)
  for an injected error, `text`/`deltas`/`answer`/`citations`, `interrupt` (stream ends without
  its terminal event), `hold` (wait for `release(service)`), `polls` (Harbor pending polls).
- `hold(service)` makes every following request of that service wait (streams: after their
  first delta; Harbor: jobs stay pending) until `release(service)`.
- `calls_to(service, part, method)` returns recorded calls, oldest first.

Every request is recorded, including requests to unknown routes (service = first path part),
so tests can prove that nothing was called. Run standalone with `python hub.py --port 8765`.
"""

from __future__ import annotations

import argparse
import itertools
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

HOLD_LIMIT = 60.0  # seconds a held request waits before giving up (never in a passing run)

TOKENS = {
    "pollen": {"pollen-demo-token": "demo", "pollen-north-token": "north", "pollen-south-token": "south"},
    "comet": {"comet-demo-key": "demo", "comet-north-key": "north", "comet-south-key": "south"},
    "knowledge": {"kb-north-token": "north", "kb-south-token": "south"},
    "orders": {"orders-north-token": "north", "orders-south-token": "south"},
    "harbor": {"harbor-north-token": "north", "harbor-south-token": "south"},
    "quartz": {"quartz-north-token": "north", "quartz-south-token": "south"},
    "nimbus": {"nimbus-north-key": "north", "nimbus-south-key": "south"},
}

ARTICLES = {
    "north": [
        {"id": "KB-100", "title": "Resetting your password",
         "text": "Open Settings, choose Security and press Reset. The link works for 30 minutes.",
         "url": "https://help.relaydesk.test/north/kb-100"},
        {"id": "KB-101", "title": "Refund timelines",
         "text": "Refunds reach the original card within 5 to 7 business days.",
         "url": "https://help.relaydesk.test/north/kb-101"},
        {"id": "KB-102", "title": "Frakt til Tromsø og Svalbard",
         "text": "Pakker til Svalbard tar 6–9 dager; tollgebyr betales ved levering.",
         "url": None},
    ],
    "south": [
        {"id": "KB-200", "title": "Changing a delivery address",
         "text": "Addresses can be changed until the parcel leaves the warehouse.",
         "url": "https://help.relaydesk.test/south/kb-200"},
        {"id": "KB-201", "title": "Password rules",
         "text": "Passwords need twelve characters; reset links expire after one hour.",
         "url": "https://help.relaydesk.test/south/kb-201"},
    ],
}

# order id -> (team, status, minor units, currency)
ORDERS = {
    "A-1001": ("north", "shipped", 4599, "USD"),
    "A-1002": ("north", "processing", 120000, "USD"),
    "A-1003": ("north", "delivered", 5, "USD"),
    "B-2001": ("south", "delivered", 999, "USD"),
    "E-3001": ("north", "shipped", 1234, "EUR"),
    "E-3002": ("north", "processing", 250075, "EUR"),
    "J-4001": ("north", "delivered", 1500, "JPY"),
    "J-4002": ("north", "shipped", 1234567, "JPY"),
    "E-5001": ("south", "shipped", 4200, "EUR"),
    "G-6001": ("north", "shipped", 500, "GBP"),
}
DECIMALS = {"USD": 2, "EUR": 2, "JPY": 0, "GBP": 2}


def _decimal(minor: int, currency: str) -> str:
    places = DECIMALS[currency]
    if not places:
        return str(minor)
    return f"{minor // 10**places}.{minor % 10**places:0{places}d}"


class Hub:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.url = ""
        self.gates: dict[str, threading.Event] = {}
        self.reset()

    def reset(self) -> None:
        with self.lock:
            for gate in self.gates.values():
                gate.set()  # never leave a request of a previous test hanging
            self.calls: list[dict] = []
            self.plans: dict[str, list[dict]] = {}
            self.gates = {}
            self.held: set[str] = set()
            self.jobs: dict[str, dict] = {}
            self.counter = itertools.count(1)
            self.orders_v1 = True
            self.orders_v2 = True
            self.quartz_text_event = "text_delta"

    # -- scripting -------------------------------------------------------------------------
    def plan(self, service: str, **plan) -> None:
        with self.lock:
            self.plans.setdefault(service, []).append(plan)

    def fail(self, service: str, *statuses: int, retry_after: int | None = None) -> None:
        for status in statuses:
            self.plan(service, status=status, retry_after=retry_after)

    def hold(self, service: str) -> None:
        with self.lock:
            self.held.add(service)
            self.gates.setdefault(service, threading.Event()).clear()

    def release(self, service: str) -> None:
        with self.lock:
            self.held.discard(service)
            self.gates.setdefault(service, threading.Event()).set()

    def calls_to(self, service: str, part: str = "", method: str | None = None) -> list[dict]:
        with self.lock:
            return [
                c
                for c in self.calls
                if c["service"] == service
                and part in c["path"]
                and (method is None or c["method"] == method)
            ]

    def _next_plan(self, service: str) -> dict:
        with self.lock:
            queue = self.plans.get(service) or []
            plan = dict(queue.pop(0)) if queue else {}
            plan.setdefault("hold", service in self.held)
            return plan

    def _gate(self, service: str) -> threading.Event:
        with self.lock:
            return self.gates.setdefault(service, threading.Event())  # new gates are closed

    def _wait(self, service: str) -> None:
        self._gate(service).wait(HOLD_LIMIT)

    # -- request handling ------------------------------------------------------------------
    def handle(self, handler: "BaseHTTPRequestHandler", method: str) -> None:
        split = urlsplit(handler.path)
        parts = [p for p in split.path.split("/") if p]
        query = {k: v[0] for k, v in parse_qs(split.query, keep_blank_values=True).items()}
        length = int(handler.headers.get("Content-Length") or 0)
        raw = handler.rfile.read(length) if length else b""
        try:
            body = json.loads(raw) if raw else None
        except ValueError:
            body = None
        headers = {k.lower(): v for k, v in handler.headers.items()}
        service = parts[0] if parts else ""
        if service == "pollen" and parts[1:] == ["draft", "stream"]:
            service_key = "pollen_stream"
        else:
            service_key = service
        token = None
        auth = headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
        if service == "comet":
            token = headers.get("x-api-key")
        if service == "nimbus":
            token = headers.get("x-nimbus-key")
        team = TOKENS.get(service, {}).get(token or "")
        record = {
            "service": service,
            "method": method,
            "path": split.path,
            "query": query,
            "headers": headers,
            "raw": raw,
            "body": body,
            "token": token,
            "team": team,
            "at": time.monotonic(),
            "response": None,
        }
        with self.lock:
            record["n"] = next(self.counter)
            self.calls.append(record)
        reply = Reply(handler, record)
        if service not in TOKENS:
            return reply.json(404, {"error": "no such service"})
        if team is None:
            return reply.json(401, {"error": "invalid_token"})
        route = getattr(self, f"_{service}", None)
        route(reply, service_key, method, parts[1:], query, body, team)

    # Pollen ---------------------------------------------------------------------------------
    def _pollen(self, reply, key, method, parts, query, body, team):
        if method != "POST" or parts not in (["draft"], ["draft", "stream"]):
            return reply.json(404, {"error": "no such route"})
        if not _valid_messages(body):
            return reply.json(400, {"error": "messages must be [{role, content}]"})
        plan = self._next_plan(key)
        if plan.get("status"):
            return reply.error(plan)
        n = reply.record["n"]
        text = plan.get("text", f"Hi, thanks for writing — Pollen draft {n} ✓")
        if key == "pollen":
            if plan["hold"]:
                self._wait(key)
            return reply.json(200, {"text": text, "request_id": f"pol-{n}"})
        deltas = plan.get("deltas") or _chunks(text)
        events = [("delta", {"text": d}) for d in deltas]
        if not plan.get("interrupt"):
            events.append(("done", {"request_id": f"pol-{n}"}))
        reply.stream(events, hold=key if plan["hold"] else None, hub=self)

    # Comet ----------------------------------------------------------------------------------
    def _comet(self, reply, key, method, parts, query, body, team):
        if method != "POST" or parts != ["compose"]:
            return reply.json(404, {"error": "no such route"})
        conversation = (body or {}).get("conversation") if isinstance(body, dict) else None
        if not isinstance(conversation, list) or not conversation or not all(
            isinstance(e, dict) and isinstance(e.get("speaker"), str)
            and isinstance(e.get("text"), str) for e in conversation
        ):
            return reply.json(400, {"error": "conversation must be [{speaker, text}]"})
        plan = self._next_plan(key)
        if plan.get("status"):
            return reply.error(plan)
        if plan["hold"]:
            self._wait(key)
        n = reply.record["n"]
        text = plan.get("text", f"Comet reply {n}: vi ser på saken — takk!")
        reply.json(200, {"completion": {"body": text}, "id": f"cmt-{n}"})

    # Knowledge ------------------------------------------------------------------------------
    def _knowledge(self, reply, key, method, parts, query, body, team):
        if method != "GET" or not parts or parts[0] != "articles" or len(parts) > 2:
            return reply.json(404, {"error": "no such route"})
        if query.get("team") != team:
            return reply.json(403, {"error": "token does not belong to that team"})
        articles = ARTICLES.get(team, [])
        if len(parts) == 2:
            found = [a for a in articles if a["id"] == parts[1]]
            if not found:
                return reply.json(404, {"error": "no such article"})
            return reply.json(200, _article(found[0]))
        q = query.get("q", "").casefold()
        hits = [_article(a) for a in articles
                if q in a["title"].casefold() or q in a["text"].casefold()]
        reply.json(200, {"articles": hits})

    # Orders ---------------------------------------------------------------------------------
    def _orders(self, reply, key, method, parts, query, body, team):
        if method != "GET":
            return reply.json(404, {"error": "no such route"})
        version = parts[0] if parts and parts[0] in ("v2", "v3") else "v1"
        rest = parts[1:] if version != "v1" else parts
        if len(rest) != 2 or rest[0] != "orders":
            return reply.json(404, {"error": "no such route"})
        if (version == "v1" and not self.orders_v1) or (version == "v2" and not self.orders_v2):
            return reply.json(410, {"error": "this API version has been retired"})
        found = ORDERS.get(rest[1])
        if (
            not found
            or found[0] != team
            or (version == "v1" and found[3] != "USD")
            or (version == "v2" and found[3] == "GBP")
        ):
            return reply.json(404, {"error": "no such order"})
        _, status, minor, currency = found
        if version == "v1":
            return reply.json(200, {"id": rest[1], "status": status, "total_cents": minor})
        if version == "v2":
            money = {"minor_units": minor, "currency": currency}
            return reply.json(200, {"id": rest[1], "status": status, "money": money})
        total = {"amount": _decimal(minor, currency), "currency": currency}
        reply.json(200, {"id": rest[1], "status": status, "total": total})

    # Harbor ---------------------------------------------------------------------------------
    def _harbor(self, reply, key, method, parts, query, body, team):
        if parts == ["jobs"] and method == "POST":
            if not isinstance(body, dict) or not isinstance(body.get("prompt"), str):
                return reply.json(400, {"error": "prompt must be a string"})
            plan = self._next_plan(key)
            if plan.get("status"):
                return reply.error(plan)
            n = reply.record["n"]
            job = {
                "id": f"hj-{n}",
                "team": team,
                "state": "pending",
                "polls": int(plan.get("polls", 1)),
                "answer": plan.get("answer", f"Harbor answer {n}: we have checked your case."),
                "hold": plan["hold"],
                "outcome": plan.get("outcome", "complete"),
            }
            with self.lock:
                self.jobs[job["id"]] = job
            return reply.json(202, {"job_id": job["id"]})
        if len(parts) == 2 and parts[0] == "jobs" and method in ("GET", "DELETE"):
            with self.lock:
                job = self.jobs.get(parts[1])
                if not job or job["team"] != team:
                    job = None
                elif method == "DELETE":
                    if job["state"] == "pending":
                        job["state"] = "cancelled"
                    state = {"state": job["state"]}
                else:
                    held = job["hold"] and not self.gates.setdefault("harbor", threading.Event()).is_set()
                    if job["state"] == "pending" and not held:
                        if job["polls"] > 0:
                            job["polls"] -= 1
                        else:
                            job["state"] = job["outcome"]
                    state = {"state": job["state"]}
                    if job["state"] == "complete":
                        state["answer"] = job["answer"]
            if job is None:
                return reply.json(404, {"error": "no such job"})
            return reply.json(200, state)
        reply.json(404, {"error": "no such route"})

    # Quartz ---------------------------------------------------------------------------------
    def _quartz(self, reply, key, method, parts, query, body, team):
        if method != "POST" or parts != ["responses"]:
            return reply.json(404, {"error": "no such route"})
        items = body.get("input") if isinstance(body, dict) else None
        if not isinstance(items, list) or not items or not all(
            isinstance(i, dict) and i.get("type") == "text" and isinstance(i.get("text"), str)
            for i in items
        ):
            return reply.json(400, {"error": "input must be [{type: text, text}]"})
        plan = self._next_plan(key)
        if plan.get("status"):
            return reply.error(plan)
        n = reply.record["n"]
        deltas = plan.get("deltas") or _chunks(f"Quartz response {n}: here is what to do — ✓")
        citations = plan.get("citations")
        if citations is None:
            citations = [{"article_id": "KB-100", "title": "Resetting your password",
                          "url": "https://help.relaydesk.test/north/kb-100"}]
        events = [(self.quartz_text_event, {"text": deltas[0]})]
        events += [("citation", c) for c in citations]
        events += [(self.quartz_text_event, {"text": d}) for d in deltas[1:]]
        if not plan.get("interrupt"):
            events.append(("completed", {"response_id": f"qz-{n}"}))
        reply.stream(events, hold=key if plan["hold"] else None, hub=self)

    # Nimbus (probe 1) -----------------------------------------------------------------------
    def _nimbus(self, reply, key, method, parts, query, body, team):
        if method == "POST" and parts == ["v1", "replies"]:
            ok = isinstance(body, dict) and isinstance(body.get("instructions"), str) and (
                isinstance(body.get("context"), list)
                and all(isinstance(c, str) for c in body["context"])
            )
            if not ok:
                return reply.json(400, {"error": "need instructions and context"})
            plan = self._next_plan(key)
            if plan.get("status"):
                return reply.error(plan)
            n = reply.record["n"]
            deltas = plan.get("deltas") or _chunks(f"Nimbus reply {n}: all sorted — ✓")
            events = [("start", {"reply_id": f"nr-{n}"})]
            events += [("chunk", {"delta": d}) for d in deltas]
            if not plan.get("interrupt"):
                events.append(("end", {"reply_id": f"nr-{n}"}))
            # held streams pause after the start event and first chunk
            return reply.stream(events, hold=key if plan["hold"] else None, hub=self, after=2)
        if method == "POST" and len(parts) == 4 and parts[:2] == ["v1", "replies"] \
                and parts[3] == "cancel":
            return reply.json(200, {"reply_id": parts[2], "cancelled": True})
        reply.json(404, {"error": "no such route"})


def _valid_messages(body) -> bool:
    messages = body.get("messages") if isinstance(body, dict) else None
    return isinstance(messages, list) and bool(messages) and all(
        isinstance(m, dict) and m.get("role") in ("system", "user", "assistant")
        and isinstance(m.get("content"), str) for m in messages
    )


def _chunks(text: str) -> list[str]:
    third = max(1, len(text) // 3)
    return [text[:third], text[third:2 * third], text[2 * third:]]


def _article(a: dict) -> dict:
    out = {"id": a["id"], "title": a["title"], "text": a["text"]}
    if a["url"]:
        out["url"] = a["url"]
    return out


class Reply:
    def __init__(self, handler, record) -> None:
        self.handler, self.record = handler, record

    def json(self, status: int, payload, headers: dict | None = None) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.record["response"] = {"status": status, "body": payload}
        h = self.handler
        try:
            h.send_response(status)
            h.send_header("Content-Type", "application/json")
            h.send_header("Content-Length", str(len(data)))
            for name, value in (headers or {}).items():
                h.send_header(name, value)
            h.end_headers()
            h.wfile.write(data)
        except OSError:
            pass

    def error(self, plan: dict) -> None:
        headers = {}
        if plan.get("retry_after") is not None:
            headers["Retry-After"] = str(plan["retry_after"])
        self.json(int(plan["status"]), {"error": "injected failure"}, headers)

    def stream(self, events, hold=None, hub=None, after=1) -> None:
        self.record["response"] = {"status": 200, "events": events}
        h = self.handler
        h.close_connection = True
        try:
            h.send_response(200)
            h.send_header("Content-Type", "text/event-stream")
            h.send_header("Cache-Control", "no-cache")
            h.send_header("Connection", "close")
            h.end_headers()
            for index, (name, data) in enumerate(events):
                if hold and index == after:
                    hub._wait(hold)
                chunk = f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                h.wfile.write(chunk.encode())
                h.wfile.flush()
        except OSError:
            pass


def start(port: int = 0) -> tuple[ThreadingHTTPServer, Hub]:
    hub = Hub()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):  # noqa: N802
            hub.handle(self, "GET")

        def do_POST(self):  # noqa: N802
            hub.handle(self, "POST")

        def do_PUT(self):  # noqa: N802
            hub.handle(self, "PUT")

        def do_DELETE(self):  # noqa: N802
            hub.handle(self, "DELETE")

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
