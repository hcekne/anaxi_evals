"""Request 12: Quartz — typed input, streamed text with separate citations, no order tools."""

import time

from hub import ARTICLES

from conftest import expect_error, provider_text, reply_calls, shows, wait_for

NORTH = {a["id"]: a for a in ARTICLES["north"]}
CITATIONS = [
    {"article_id": "KB-101", "title": "Refund timelines",
     "url": "https://help.relaydesk.test/north/kb-101"},
    {"article_id": "KB-102", "title": "Frakt til Tromsø og Svalbard"},
]  # fmt: skip
EXPECTED = [CITATIONS[0], {**CITATIONS[1], "url": None}]


def test_quartz_is_offered(c):
    listed = {p["id"]: p for p in c.ok("GET", "/api/providers")["providers"]}
    assert listed["quartz"]["name"] == "Quartz" and listed["quartz"]["streaming"] is True
    assert c.ok("PUT", "/api/preferences", json={"provider": "quartz"})["provider"] == "quartz"
    c.ok("PUT", "/api/preferences", json={"provider": "pollen"})


def test_text_and_citations_arrive_separately(c, hub):
    c.connect("quartz", "knowledge", "orders")
    a, b = c.tickets(2)
    for order_id in ("A-1001", "A-1002"):
        c.ok("POST", f"/api/tickets/{a['id']}/orders", status=201, json={"order_id": order_id})
    lookups = len(hub.calls_to("orders"))
    hub.plan("quartz", deltas=["Hi, ", "refunds take ", "5–7 days ✓"], citations=CITATIONS)
    s = c.suggest(a["id"], provider="quartz", article_ids=["KB-101"], order_ids=["A-1002"])
    assert s["status"] == "completed" and s["provider"] == "quartz"
    assert s["text"] == "Hi, refunds take 5–7 days ✓"
    assert s["citations"] == EXPECTED
    assert s["sources"] == [{"id": "KB-101", "title": "Refund timelines",
                             "url": NORTH["KB-101"]["url"]}]  # fmt: skip
    (call,) = reply_calls(hub, "quartz")
    assert call["headers"]["authorization"] == "Bearer quartz-north-token"
    assert all(item["type"] == "text" for item in call["body"]["input"])
    sent = provider_text(call)
    assert a["subject"] in sent and a["body"] in sent and b["body"] not in sent
    assert NORTH["KB-101"]["title"] in sent and NORTH["KB-101"]["text"] in sent
    assert NORTH["KB-100"]["text"] not in sent
    assert "A-1002" in sent and "processing" in sent and "$1,200.00" in sent
    assert "A-1001" not in sent
    assert len(hub.calls_to("orders")) == lookups
    assert [x["path"] for x in hub.calls_to("quartz")] == ["/quartz/responses"]


def test_text_shows_while_it_arrives(c, hub):
    c.connect("quartz")
    (a,) = c.tickets(1)
    hub.plan("quartz", deltas=["First words ", "and the rest"], citations=CITATIONS[:1], hold=True)
    r = c.ask(a["id"], provider="quartz")
    assert r.status_code in (201, 202), r.text
    ident = r.json()["id"]
    partial = wait_for(lambda: (x := c.suggestion(ident))["text"] == "First words " and x)
    assert partial and partial["status"] == "running"
    hub.release("quartz")
    done = c.wait(ident)
    assert done["text"] == "First words and the rest" and done["citations"] == EXPECTED[:1]


def test_other_services_have_no_citations(c):
    c.connect("pollen")
    (a,) = c.tickets(1)
    s = c.suggest(a["id"], provider="pollen")
    assert s["citations"] == [] and c.suggestion(s["id"])["citations"] == []


def test_cut_off_and_busy_streams(c, hub):
    c.connect("quartz")
    (a,) = c.tickets(1)
    hub.plan("quartz", interrupt=True)
    s = c.suggest(a["id"], provider="quartz")
    assert s["status"] == "failed" and s["error"]["code"] == "stream_interrupted"
    expect_error(c.post(f"/api/suggestions/{s['id']}/accept"), 409, "conflict")
    hub.fail("quartz", 429, retry_after=2)
    s = c.suggest(a["id"], provider="quartz")
    calls = reply_calls(hub, "quartz")
    assert s["status"] == "completed" and len(calls) == 3
    hub.fail("quartz", 401)
    assert c.suggest(a["id"], provider="quartz")["error"]["code"] == "provider_auth_failed"
    assert len(reply_calls(hub, "quartz")) == 4


def test_stopping_quartz(c, hub):
    c.connect("quartz")
    (a,) = c.tickets(1)
    hub.plan("quartz", deltas=["Early ", "LATE"], hold=True)
    ident = c.ask(a["id"], provider="quartz").json()["id"]
    assert wait_for(lambda: c.suggestion(ident)["text"] == "Early ")
    assert c.ok("POST", f"/api/suggestions/{ident}/cancel")["status"] == "cancelled"
    hub.release("quartz")
    time.sleep(0.3)
    after = c.suggestion(ident)
    assert after["status"] == "cancelled" and "LATE" not in after["text"]


def test_quartz_batches(c, hub):
    c.connect("quartz")
    rows = c.tickets(2)
    r = c.post("/api/batches", json={"ticket_ids": [x["id"] for x in rows], "provider": "quartz"})
    assert r.status_code == 201, r.text
    done = wait_for(lambda: (b := c.ok("GET", f"/api/batches/{r.json()['id']}"))["status"]
                    == "completed" and b)  # fmt: skip
    assert done and [i["status"] for i in done["items"]] == ["completed", "completed"]
    s = c.suggestion(done["items"][0]["suggestion_id"])
    assert s["citations"] and s["citations"][0]["article_id"] == "KB-100"
    assert len(reply_calls(hub, "quartz")) == 2


def test_page_shows_citations_and_they_are_kept(app, c, hub):
    c.connect("quartz")
    (a,) = c.tickets(1)
    hub.plan("quartz", deltas=["Answer ", "text"], citations=CITATIONS)
    s = c.suggest(a["id"], provider="quartz")
    page = c.page(f"/tickets/{a['id']}")
    assert shows(page, "Answer text") and CITATIONS[0]["url"] in page
    assert shows(page, CITATIONS[1]["title"])
    accepted = c.ok("POST", f"/api/suggestions/{s['id']}/accept")
    assert accepted["draft"]["text"] == "Answer text"
    app.restart()
    assert app.c.suggestion(s["id"])["citations"] == EXPECTED


def test_each_team_uses_its_quartz_token(south, hub):
    (b,) = south.tickets(1)
    expect_error(south.ask(b["id"], provider="quartz"), 409, "not_configured")
    south.connect("quartz")
    assert south.suggest(b["id"], provider="quartz")["status"] == "completed"
    assert {x["token"] for x in hub.calls_to("quartz")} == {"quartz-south-token"}
