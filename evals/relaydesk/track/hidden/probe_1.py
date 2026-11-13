"""Probe 1: a fifth reply service (Nimbus) — familiar streaming, plus a remote cancel call."""

import time

from hub import ARTICLES

from conftest import expect_error, provider_text, reply_calls, shows, wait_for

KB = {a["id"]: a for a in ARTICLES["north"]}


def test_nimbus_is_offered(c):
    listed = {p["id"]: p for p in c.ok("GET", "/api/providers")["providers"]}
    assert listed["nimbus"]["name"] == "Nimbus" and listed["nimbus"]["streaming"] is True
    assert c.ok("PUT", "/api/preferences", json={"provider": "nimbus"})["provider"] == "nimbus"
    c.ok("PUT", "/api/preferences", json={"provider": "pollen"})


def test_nimbus_protocol_and_context(c, hub):
    c.connect("nimbus", "knowledge", "orders")
    a, b = c.tickets(2)
    c.ok("POST", f"/api/tickets/{a['id']}/orders", status=201, json={"order_id": "A-1002"})
    c.ok("POST", f"/api/tickets/{a['id']}/orders", status=201, json={"order_id": "A-1001"})
    hub.plan("nimbus", deltas=["Hei ", "Ola — ", "alt i orden ✓"])
    s = c.suggest(a["id"], provider="nimbus", article_ids=["KB-101"], order_ids=["A-1002"])
    assert s["status"] == "completed" and s["provider"] == "nimbus"
    assert s["text"] == "Hei Ola — alt i orden ✓" and s["citations"] == []
    assert [x["id"] for x in s["sources"]] == ["KB-101"]
    (call,) = reply_calls(hub, "nimbus")
    assert call["headers"]["x-nimbus-key"] == "nimbus-north-key"
    assert isinstance(call["body"]["instructions"], str)
    context = "\n".join(call["body"]["context"])
    assert a["subject"] in context and a["body"] in context and b["body"] not in context
    assert KB["KB-101"]["title"] in context and KB["KB-101"]["text"] in context
    assert KB["KB-100"]["text"] not in provider_text(call)
    assert "A-1002" in context and "$1,200.00" in context and "processing" in context
    assert "A-1001" not in provider_text(call)


def test_text_arrives_and_stopping_cancels_remotely(c, hub):
    c.connect("nimbus")
    (a,) = c.tickets(1)
    c.ok("PUT", f"/api/tickets/{a['id']}/draft", json={"text": "mine"})
    hub.plan("nimbus", deltas=["Early ", "LATE"], hold=True)
    ident = c.ask(a["id"], provider="nimbus").json()["id"]
    partial = wait_for(lambda: (x := c.suggestion(ident))["text"] == "Early " and x)
    assert partial and partial["status"] == "running"
    assert c.ok("POST", f"/api/suggestions/{ident}/cancel")["status"] == "cancelled"
    reply_id = reply_calls(hub, "nimbus")[0]["response"]["events"][0][1]["reply_id"]
    hub.release("nimbus")
    cancels = wait_for(lambda: hub.calls_to("nimbus", f"/v1/replies/{reply_id}/cancel", "POST"))
    assert len(cancels) == 1 and cancels[0]["headers"]["x-nimbus-key"] == "nimbus-north-key"
    time.sleep(0.3)
    after = c.suggestion(ident)
    assert after["status"] == "cancelled" and "LATE" not in after["text"]
    assert len(hub.calls_to("nimbus", "/cancel")) == 1
    assert c.ticket(a["id"])["draft"]["text"] == "mine"


def test_busy_bad_key_and_cut_off(c, hub):
    c.connect("nimbus")
    (a,) = c.tickets(1)
    hub.fail("nimbus", 429, retry_after=2)
    s = c.suggest(a["id"], provider="nimbus")
    assert s["status"] == "completed" and len(reply_calls(hub, "nimbus")) == 2
    hub.fail("nimbus", 401)
    assert c.suggest(a["id"], provider="nimbus")["error"]["code"] == "provider_auth_failed"
    hub.plan("nimbus", interrupt=True)
    s = c.suggest(a["id"], provider="nimbus")
    assert s["status"] == "failed" and s["error"]["code"] == "stream_interrupted"
    expect_error(c.post(f"/api/suggestions/{s['id']}/accept"), 409, "conflict")
    assert len(reply_calls(hub, "nimbus")) == 4


def test_batches_and_teams(south, hub):
    rows = south.tickets(2)
    expect_error(south.ask(rows[0]["id"], provider="nimbus"), 409, "not_configured")
    south.connect("nimbus")
    r = south.post("/api/batches", json={"ticket_ids": [x["id"] for x in rows],
                                         "provider": "nimbus"})  # fmt: skip
    assert r.status_code == 201, r.text
    done = wait_for(lambda: (b := south.ok("GET", f"/api/batches/{r.json()['id']}"))["status"]
                    == "completed" and b)  # fmt: skip
    assert done and [i["status"] for i in done["items"]] == ["completed", "completed"]
    assert {x["token"] for x in reply_calls(hub, "nimbus")} == {"nimbus-south-key"}


def test_page_names_nimbus(c):
    c.connect("nimbus")
    (a,) = c.tickets(1)
    s = c.suggest(a["id"], provider="nimbus")
    page = c.page(f"/tickets/{a['id']}")
    assert shows(page, s["text"]) and "Nimbus" in page
