"""Request 11: stopping unfinished suggestions (queued, streaming, Harbor polling), alone or in a
batch; late answers never appear and Harbor is told to cancel."""

import time

from conftest import POLLEN, expect_error, reply_calls, wait_for


def cancel(c, ident) -> dict:
    r = c.post(f"/api/suggestions/{ident}/cancel")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled" and r.json()["id"] == ident
    return r.json()


def harbor_job(hub) -> str:
    calls = wait_for(lambda: reply_calls(hub, "harbor"))
    return calls[0]["response"]["body"]["job_id"]


def polls(hub, job_id):
    return hub.calls_to("harbor", f"/harbor/jobs/{job_id}", "GET")


def test_stopping_a_stream_keeps_the_late_text_out(c, hub):
    c.connect("pollen")
    (a,) = c.tickets(1)
    c.ok("PUT", f"/api/tickets/{a['id']}/draft", json={"text": "my own draft"})
    hub.plan(POLLEN[0], deltas=["Part one ", "LATE PART"], hold=True)
    ident = c.ask(a["id"], provider="pollen").json()["id"]
    assert wait_for(lambda: c.suggestion(ident)["text"] == "Part one ")
    stopped = cancel(c, ident)
    hub.release(POLLEN[0])
    time.sleep(0.4)
    after = c.suggestion(ident)
    assert after["status"] == "cancelled" and after["text"] == stopped["text"]
    assert "LATE PART" not in after["text"]
    expect_error(c.post(f"/api/suggestions/{ident}/accept"), 409, "conflict")
    assert c.ticket(a["id"])["draft"]["text"] == "my own draft"


def test_stopping_harbor_cancels_the_job(c, hub):
    c.connect("harbor")
    (a,) = c.tickets(1)
    hub.hold("harbor")
    ident = c.ask(a["id"], provider="harbor").json()["id"]
    job_id = harbor_job(hub)
    assert wait_for(lambda: polls(hub, job_id))
    cancel(c, ident)
    deletes = wait_for(lambda: hub.calls_to("harbor", f"/harbor/jobs/{job_id}", "DELETE"))
    assert len(deletes) == 1 and deletes[0]["token"] == "harbor-north-token"
    time.sleep(0.15)
    seen = len(polls(hub, job_id))
    hub.release("harbor")
    time.sleep(0.4)
    assert len(polls(hub, job_id)) == seen
    assert len(hub.calls_to("harbor", f"/harbor/jobs/{job_id}", "DELETE")) == 1
    after = c.suggestion(ident)
    assert after["status"] == "cancelled" and after["text"] == ""
    assert len(reply_calls(hub, "harbor")) == 1


def test_finished_suggestions_cannot_be_stopped(c, hub):
    c.connect("pollen")
    (a,) = c.tickets(1)
    done = c.suggest(a["id"], provider="pollen")
    expect_error(c.post(f"/api/suggestions/{done['id']}/cancel"), 409, "conflict")
    assert c.suggestion(done["id"]) == done
    hub.fail(POLLEN[0], 401)
    failed = c.suggest(a["id"], provider="pollen")
    expect_error(c.post(f"/api/suggestions/{failed['id']}/cancel"), 409, "conflict")
    assert c.suggestion(failed["id"])["status"] == "failed"
    hub.hold(POLLEN[0])
    ident = c.ask(a["id"], provider="pollen").json()["id"]
    cancel(c, ident)
    expect_error(c.post(f"/api/suggestions/{ident}/cancel"), 409, "conflict")
    assert c.ok("POST", f"/api/suggestions/{done['id']}/accept")["draft"]["text"] == done["text"]


def test_unknown_or_foreign_suggestions(c, south, hub):
    expect_error(c.post("/api/suggestions/no-such/cancel"), 404, "not_found")
    c.connect("pollen")
    (a,) = c.tickets(1)
    hub.hold(POLLEN[0])
    ident = c.ask(a["id"], provider="pollen").json()["id"]
    expect_error(south.post(f"/api/suggestions/{ident}/cancel"), 404, "not_found")
    assert c.suggestion(ident)["status"] in ("queued", "running")
    hub.release(POLLEN[0])
    assert c.wait(ident)["status"] == "completed"


def test_stopping_one_batch_item_leaves_the_others(c, hub):
    c.connect("pollen")
    rows = c.tickets(10)
    hub.hold(POLLEN[0])
    r = c.post("/api/batches", json={"ticket_ids": [x["id"] for x in rows], "provider": "pollen"})
    assert r.status_code == 201, r.text
    batch = r.json()
    assert wait_for(lambda: reply_calls(hub, "pollen"))
    victims = [batch["items"][1], batch["items"][-1]]
    queued = []
    for item in victims:
        was = c.suggestion(item["suggestion_id"])["status"]
        cancel(c, item["suggestion_id"])
        if was == "queued":
            queued.append(item["ticket_id"])
    hub.release(POLLEN[0])
    done = wait_for(lambda: (b := c.ok("GET", f"/api/batches/{batch['id']}"))["status"]
                    == "completed" and b, timeout=20)  # fmt: skip
    assert done, c.ok("GET", f"/api/batches/{batch['id']}")
    stopped = {v["suggestion_id"] for v in victims}
    for item in done["items"]:
        s = c.suggestion(item["suggestion_id"])
        expected = "cancelled" if item["suggestion_id"] in stopped else "completed"
        assert item["status"] == s["status"] == expected, item
    bodies = {x["id"]: x["body"] for x in rows}
    for ticket_id in queued:
        assert not any(bodies[ticket_id] in str(x["body"]) for x in reply_calls(hub, "pollen"))
    for item in victims:
        listed = c.ok("GET", f"/api/tickets/{item['ticket_id']}/suggestions")["suggestions"]
        assert [x["status"] for x in listed] == ["cancelled"]


def test_cancelled_stays_cancelled_after_a_restart(app, hub):
    c = app.c
    c.connect("harbor")
    (a,) = c.tickets(1)
    hub.hold("harbor")
    ident = c.ask(a["id"], provider="harbor").json()["id"]
    job_id = harbor_job(hub)
    cancel(c, ident)
    wait_for(lambda: hub.calls_to("harbor", "/harbor/jobs/", "DELETE"))
    app.restart(abrupt=True)
    hub.release("harbor")
    time.sleep(0.5)
    assert app.c.suggestion(ident)["status"] == "cancelled"
    assert len(reply_calls(hub, "harbor")) == 1
    deleted_at = hub.calls_to("harbor", f"/harbor/jobs/{job_id}", "DELETE")[0]["at"]
    assert [x for x in polls(hub, job_id) if x["at"] > deleted_at + 0.2] == []
