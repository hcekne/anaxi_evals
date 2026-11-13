"""Request 2: the controllable clock, ParcelBox connections and background imports."""

import time

from conftest import (
    expect_error,
    ok,
    parcelbox_era,
    parse_iso,
    uid,
    wait_for,
)

ITEMS = [
    {"id": f"PB-{n}", "title": f"Parcel {n}", "text": f"Text {n} — ø", "revision": 1}
    for n in range(1, 6)
]


def parcel_connection(app, case_id, token):
    return app.connect(case_id, "parcelbox", {"token": token})


def test_clock_can_be_frozen_and_released(app):
    ok(app.http.delete("/api/clock"))
    clock = ok(app.http.get("/api/clock"))
    assert clock["frozen"] is False
    parse_iso(clock["now"])
    frozen = ok(app.http.put("/api/clock", json={"now": "2026-03-01T09:00:00Z"}))
    assert frozen == {"now": "2026-03-01T09:00:00Z", "frozen": True}
    time.sleep(1.1)
    assert ok(app.http.get("/api/clock")) == frozen
    back = ok(app.http.put("/api/clock", json={"now": "2025-12-31T23:59:59Z"}))
    assert back["now"] == "2025-12-31T23:59:59Z"
    for bad in ("2026-13-01T00:00:00Z", "yesterday", 5, None):
        expect_error(app.http.put("/api/clock", json={"now": bad}), 422, "invalid_request")
    released = ok(app.http.delete("/api/clock"))
    assert released["frozen"] is False


def test_clock_survives_restart(fresh_app):
    fresh_app.set_clock("2026-07-04T12:00:00Z")
    fresh_app.restart()
    assert ok(fresh_app.http.get("/api/clock")) == {"now": "2026-07-04T12:00:00Z", "frozen": True}


@parcelbox_era
def test_connections_hide_credentials(app):
    case = app.case()
    conn = parcel_connection(app, case["id"], "secret-token-123")
    assert {"case_id": case["id"], "source": "parcelbox", "status": "active"}.items() <= conn.items()
    listed = app.get(f"/api/cases/{case['id']}/connections")
    assert [c["id"] for c in ok(listed)["connections"]] == [conn["id"]]
    single = app.get(f"/api/connections/{conn['id']}")
    assert ok(single)["id"] == conn["id"]
    for response in (listed, single, app.get(f"/cases/{case['id']}")):
        assert "secret-token-123" not in str(response.text)
    path = f"/api/cases/{case['id']}/connections"
    expect_error(
        app.post(path, json={"source": "dropbox", "credentials": {"token": "x"}}),
        422,
        "unsupported_source",
    )
    for creds in ({}, {"token": ""}, {"token": 5}):
        expect_error(
            app.post(path, json={"source": "parcelbox", "credentials": creds}),
            422,
            "invalid_request",
        )
    expect_error(app.get("/api/connections/nope-404"), 404, "not_found")
    expect_error(app.get("/api/jobs/nope-404"), 404, "not_found")


@parcelbox_era
def test_import_follows_every_page(app, hub):
    token = uid("pb-")
    hub.parcelbox(token, ITEMS, page_size=2)
    case = app.case()
    conn = parcel_connection(app, case["id"], token)
    job = app.start_import(conn["id"])
    assert {"case_id": case["id"], "connection_id": conn["id"], "source": "parcelbox"}.items() <= job.items()
    assert job["status"] in ("queued", "running", "completed")
    done = app.wait_job(job["id"])
    assert (done["imported"], done["unchanged"], done["error"]) == (5, 0, None)
    calls = hub.calls_to("parcelbox", key=token)
    assert [c["page"] for c in calls] == [1, 2, 3]
    assert calls[0]["cursor"] is None and all(c["status"] == 200 for c in calls)
    docs = [app.document(d["id"]) for d in app.case_docs(case["id"])]
    assert sorted(d["external_id"] for d in docs) == [i["id"] for i in ITEMS]
    first = next(d for d in docs if d["external_id"] == "PB-1")
    assert {"title": "Parcel 1", "text": "Text 1 — ø", "source": "parcelbox",
            "source_revision": 1, "connection_id": conn["id"]}.items() <= first.items()  # fmt: skip
    pasted = app.doc(case["id"], "Pasted", "p")
    assert pasted["connection_id"] is None and pasted["source_revision"] is None
    jobs = ok(app.get(f"/api/cases/{case['id']}/jobs"))["jobs"]
    assert [j["id"] for j in jobs] == [job["id"]] and jobs[0]["status"] == "completed"


@parcelbox_era
def test_reimport_is_a_no_op_and_revisions_update_in_place(app, hub):
    token = uid("pb-")
    hub.parcelbox(token, ITEMS, page_size=2)
    case = app.case()
    conn = parcel_connection(app, case["id"], token)
    app.wait_job(app.start_import(conn["id"])["id"])
    before = {d["external_id"]: d for d in (app.document(x["id"]) for x in app.case_docs(case["id"]))}
    again = app.wait_job(app.start_import(conn["id"])["id"])
    assert (again["imported"], again["unchanged"]) == (0, 5)
    changed = [dict(i) for i in ITEMS]
    changed[2] = {"id": "PB-3", "title": "Parcel 3 v2", "text": "New text", "revision": 2}
    hub.parcelbox(token, changed, page_size=2)
    third = app.wait_job(app.start_import(conn["id"])["id"])
    assert (third["imported"], third["unchanged"]) == (1, 4)
    after = {d["external_id"]: d for d in (app.document(x["id"]) for x in app.case_docs(case["id"]))}
    assert len(after) == 5 and after["PB-3"]["id"] == before["PB-3"]["id"]
    assert (after["PB-3"]["title"], after["PB-3"]["text"], after["PB-3"]["source_revision"]) == (
        "Parcel 3 v2",
        "New text",
        2,
    )
    assert after["PB-1"] == before["PB-1"]


@parcelbox_era
def test_rate_limit_waits_on_the_clock(app, hub):
    token = uid("pb-")
    hub.parcelbox(token, ITEMS, page_size=2)
    hub.fault("parcelbox", token, page=2, status=429, retry_after=120)
    app.set_clock("2026-03-01T09:00:00Z")
    case = app.case()
    conn = parcel_connection(app, case["id"], token)
    job = app.start_import(conn["id"])
    waiting = app.wait_job(job["id"], ("waiting",))
    assert waiting["retry_at"] == "2026-03-01T09:02:00Z"
    assert waiting["imported"] == 2
    app.set_clock("2026-03-01T09:01:30Z")
    time.sleep(2.5)
    assert len(hub.calls_to("parcelbox", key=token, page=2)) == 1
    assert app.job(job["id"])["status"] == "waiting"
    app.set_clock("2026-03-01T09:02:00Z")
    done = app.wait_job(job["id"], timeout=6)
    assert done["imported"] == 5 and done["retry_at"] is None
    page2 = hub.calls_to("parcelbox", key=token, page=2)
    assert len(page2) == 2 and page2[0]["cursor"] == page2[1]["cursor"]
    assert len(app.case_docs(case["id"])) == 5


@parcelbox_era
def test_rejected_token_stays_rejected_until_changed(app, hub):
    good = uid("pb-")
    hub.parcelbox(good, ITEMS[:1])
    case = app.case()
    conn = parcel_connection(app, case["id"], "wrong-token")
    failed = app.wait_job(app.start_import(conn["id"])["id"], ("failed", "completed"))
    assert failed["status"] == "failed" and failed["error"]["code"] == "credentials_rejected"
    assert ok(app.get(f"/api/connections/{conn['id']}"))["status"] == "unauthorized"
    calls = len(hub.calls_to("parcelbox"))
    expect_error(app.post(f"/api/connections/{conn['id']}/imports"), 409, "credentials_rejected")
    time.sleep(0.5)
    assert len(hub.calls_to("parcelbox")) == calls
    fixed = ok(app.put(f"/api/connections/{conn['id']}/credentials", json={"token": good}))
    assert fixed["status"] == "active" and good not in str(fixed)
    done = app.wait_job(app.start_import(conn["id"])["id"])
    assert done["imported"] == 1


@parcelbox_era
def test_other_failures_fail_the_job(app, hub):
    token = uid("pb-")
    hub.parcelbox(token, ITEMS)
    hub.fault("parcelbox", token, page=1, status=500)
    case = app.case()
    conn = parcel_connection(app, case["id"], token)
    failed = app.wait_job(app.start_import(conn["id"])["id"], ("failed", "completed"))
    assert failed["status"] == "failed" and failed["error"]["code"] == "upstream_error"
    assert ok(app.get(f"/api/connections/{conn['id']}"))["status"] == "active"


@parcelbox_era
def test_one_unfinished_job_per_connection(app, hub):
    token = uid("pb-")
    hub.parcelbox(token, ITEMS)
    hold = hub.hold("parcelbox", token, page=1)
    case = app.case()
    conn = parcel_connection(app, case["id"], token)
    job = app.start_import(conn["id"])
    assert hold["entered"].wait(5)
    started = time.monotonic()
    assert ok(app.get(f"/api/cases/{case['id']}"))["id"] == case["id"]  # app stays responsive
    assert time.monotonic() - started < 2
    expect_error(app.post(f"/api/connections/{conn['id']}/imports"), 409, "import_in_progress")
    assert app.job(job["id"])["status"] == "running"
    hub.release()
    assert app.wait_job(job["id"])["imported"] == 5


@parcelbox_era
def test_same_item_ids_in_two_connections_are_different_documents(app, hub):
    one, two = uid("pb-"), uid("pb-")
    hub.parcelbox(one, [{"id": "SAME", "title": "From one", "text": "1", "revision": 1}])
    hub.parcelbox(two, [{"id": "SAME", "title": "From two", "text": "2", "revision": 1}])
    case = app.case()
    for token in (one, two):
        conn = parcel_connection(app, case["id"], token)
        app.wait_job(app.start_import(conn["id"])["id"])
    docs = [app.document(d["id"]) for d in app.case_docs(case["id"])]
    assert sorted(d["title"] for d in docs) == ["From one", "From two"]
    page = app.get(f"/cases/{case['id']}")
    assert page.status_code == 200 and "completed" in page.text
    assert wait_for(lambda: True)
