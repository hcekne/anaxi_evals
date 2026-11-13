"""Request 10: background batches of up to ten tickets that survive restarts."""

from conftest import SECOND, TERMINAL, expect_error, reply_calls, reply_text, wait_for

ITEM_STATES = {"queued", "running", "completed", "failed"}


def batch(c, ident) -> dict:
    return c.ok("GET", f"/api/batches/{ident}")


def finished(c, ident, timeout=15) -> dict:
    done = wait_for(lambda: (b := batch(c, ident))["status"] == "completed" and b, timeout)
    assert done, batch(c, ident)
    return done


def start(c, ticket_ids, **body) -> dict:
    r = c.post("/api/batches", json={"ticket_ids": ticket_ids, **body})
    assert r.status_code == 201, r.text
    return r.json()


def test_batch_runs_in_the_background(c, hub):
    c.connect("pollen")
    rows = c.tickets(3)
    ids = [r["id"] for r in rows]
    created = start(c, ids, provider="pollen")
    assert created["provider"] == "pollen" and created["status"] in ("running", "completed")
    assert [i["ticket_id"] for i in created["items"]] == ids
    assert all(i["status"] in ITEM_STATES for i in created["items"])
    done = finished(c, created["id"])
    calls = reply_calls(hub, "pollen")
    assert len(calls) == 3
    for item, row in zip(done["items"], rows):
        s = c.suggestion(item["suggestion_id"])
        assert item["status"] == s["status"] == "completed" and s["ticket_id"] == row["id"]
        assert s["provider"] == "pollen"
        (call,) = [x for x in calls if row["body"] in str(x["body"])]
        assert s["text"] == reply_text(hub, call)
        listed = c.ok("GET", f"/api/tickets/{row['id']}/suggestions")["suggestions"]
        assert [x["id"] for x in listed] == [item["suggestion_id"]]
    assert created["id"] in [b["id"] for b in c.ok("GET", "/api/batches")["batches"]]


def test_batch_uses_the_saved_choice(c, hub):
    c.connect(SECOND)
    c.ok("PUT", "/api/preferences", json={"provider": SECOND})
    try:
        rows = c.tickets(2)
        created = start(c, [r["id"] for r in rows])
        assert created["provider"] == SECOND
        finished(c, created["id"])
        assert len(reply_calls(hub, SECOND)) == 2
    finally:
        c.ok("PUT", "/api/preferences", json={"provider": "pollen"})


def test_ten_tickets_at_most(c):
    c.connect("pollen")
    rows = c.tickets(11)
    ids = [r["id"] for r in rows]
    for bad in ([], ids, [ids[0], ids[0]], "T-1", [5]):
        expect_error(c.post("/api/batches", json={"ticket_ids": bad, "provider": "pollen"}), 422,
                     "invalid_request")  # fmt: skip
    expect_error(c.post("/api/batches", json={"ticket_ids": ids[:2] + ["no-such"],
                                              "provider": "pollen"}), 404, "not_found")  # fmt: skip
    assert c.ok("GET", f"/api/tickets/{ids[0]}/suggestions") == {"suggestions": []}
    done = finished(c, start(c, ids[:10], provider="pollen")["id"])
    assert [i["status"] for i in done["items"]] == ["completed"] * 10


def test_batches_belong_to_the_team(c, south):
    c.connect("pollen")
    rows = c.tickets(1)
    created = start(c, [rows[0]["id"]], provider="pollen")
    expect_error(south.get(f"/api/batches/{created['id']}"), 404, "not_found")
    assert created["id"] not in [b["id"] for b in south.ok("GET", "/api/batches")["batches"]]
    expect_error(south.post("/api/batches", json={"ticket_ids": [rows[0]["id"]],
                                                  "provider": "pollen"}), 404, "not_found")  # fmt: skip
    (b,) = south.tickets(1)
    expect_error(south.post("/api/batches", json={"ticket_ids": [b["id"]], "provider": "pollen"}),
                 409, "not_configured")  # fmt: skip
    finished(c, created["id"])


def test_items_are_accepted_the_usual_way(c):
    c.connect("pollen")
    rows = c.tickets(2)
    c.ok("PUT", f"/api/tickets/{rows[1]['id']}/draft", json={"text": "untouched"})
    done = finished(c, start(c, [r["id"] for r in rows], provider="pollen")["id"])
    first = c.suggestion(done["items"][0]["suggestion_id"])
    ticket = c.ok("POST", f"/api/suggestions/{first['id']}/accept")
    assert ticket["id"] == rows[0]["id"] and ticket["draft"]["text"] == first["text"]
    assert c.ticket(rows[1]["id"])["draft"]["text"] == "untouched"


def test_unfinished_work_carries_on_after_a_crash(fresh_app, hub):
    c = fresh_app.c
    c.connect("harbor", "pollen")
    rows = c.tickets(3)
    hub.plan("harbor", polls=0, answer="first answer")
    hub.plan("harbor", hold=True, answer="second answer")
    hub.plan("harbor", hold=True, answer="third answer")
    created = start(c, [r["id"] for r in rows], provider="harbor")
    (single,) = c.tickets(1)
    hub.plan("pollen_stream", deltas=["Half ", "a ", "reply"], hold=True)
    lone = c.ask(single["id"], provider="pollen").json()
    items = [i["suggestion_id"] for i in created["items"]]
    first = wait_for(lambda: [s for i in items if (s := c.suggestion(i))["status"] == "completed"])
    assert len(first) == 1, first
    assert wait_for(lambda: len({x["path"] for x in hub.calls_to("harbor", "/jobs/", "GET")}) >= 2)
    assert wait_for(lambda: c.suggestion(lone["id"])["text"] == "Half ")
    fresh_app.restart(abrupt=True)
    hub.release("harbor")
    hub.release("pollen_stream")
    c = fresh_app.c
    done = finished(c, created["id"])
    answers = [c.suggestion(i["suggestion_id"])["text"] for i in done["items"]]
    assert sorted(answers) == ["first answer", "second answer", "third answer"]
    assert c.suggestion(first[0]["id"]) == first[0]
    assert len(reply_calls(hub, "harbor")) == 3
    for row in rows:
        assert len(c.ok("GET", f"/api/tickets/{row['id']}/suggestions")["suggestions"]) == 1
    resumed = c.wait(lone["id"])
    assert resumed["status"] == "completed"
    assert resumed["text"] == reply_text(hub, reply_calls(hub, "pollen")[-1])
    assert len(c.ok("GET", f"/api/tickets/{single['id']}/suggestions")["suggestions"]) == 1
    assert {"completed"} == {c.suggestion(i["suggestion_id"])["status"] for i in done["items"]}
    assert all(i["status"] in TERMINAL for i in done["items"])
