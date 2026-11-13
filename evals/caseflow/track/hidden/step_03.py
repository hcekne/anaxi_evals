"""Request 3: durable imports across restarts, cancellation and honest progress."""

import time

from conftest import expect_error, ok, parcelbox_era, uid

ITEMS = [
    {"id": f"D-{n}", "title": f"Doc {n}", "text": f"Body {n}", "revision": 1} for n in range(1, 7)
]


def setup(app, hub, page_size=2):
    token = uid("pb-")
    hub.parcelbox(token, ITEMS, page_size=page_size)
    case = app.case()
    conn = app.connect(case["id"], "parcelbox", {"token": token})
    return token, case, conn


def external_ids(app, case_id):
    return sorted(app.document(d["id"])["external_id"] for d in app.case_docs(case_id))


@parcelbox_era
def test_restart_carries_on_after_the_last_saved_page(fresh_app, hub):
    app = fresh_app
    token, case, conn = setup(app, hub)
    hold = hub.hold("parcelbox", token, page=2)
    job = app.start_import(conn["id"])
    assert hold["entered"].wait(5)
    running = app.job(job["id"])
    assert running["status"] == "running" and running["imported"] == 2
    assert len(app.case_docs(case["id"])) == 2  # progress never ahead of what is saved
    app.stop()
    hub.release()
    app.start()
    done = app.wait_job(job["id"])
    assert done["imported"] == 6 and done["status"] == "completed"
    assert external_ids(app, case["id"]) == [i["id"] for i in ITEMS]
    assert len(hub.calls_to("parcelbox", key=token, page=1)) == 1
    assert len(hub.calls_to("parcelbox", key=token, page=2)) == 2
    assert len(hub.calls_to("parcelbox", key=token, page=3)) == 1


@parcelbox_era
def test_cancel_lets_the_request_in_flight_finish_then_stops(app, hub):
    token, case, conn = setup(app, hub)
    hold = hub.hold("parcelbox", token, page=2)
    job = app.start_import(conn["id"])
    assert hold["entered"].wait(5)
    cancelling = ok(app.post(f"/api/jobs/{job['id']}/cancel"), 202)
    assert cancelling["status"] == "cancelling"
    hub.release()
    done = app.wait_job(job["id"], ("cancelled",))
    assert done["imported"] == 4
    time.sleep(1.0)
    assert hub.calls_to("parcelbox", key=token, page=3) == []
    assert external_ids(app, case["id"]) == ["D-1", "D-2", "D-3", "D-4"]
    again = app.wait_job(app.start_import(conn["id"])["id"])
    assert (again["imported"], again["unchanged"]) == (2, 4)
    assert len(app.case_docs(case["id"])) == 6


@parcelbox_era
def test_cancel_while_waiting_is_immediate(app, hub):
    token, case, conn = setup(app, hub)
    hub.fault("parcelbox", token, page=2, status=429, retry_after=300)
    app.set_clock("2026-03-01T09:00:00Z")
    job = app.start_import(conn["id"])
    app.wait_job(job["id"], ("waiting",))
    cancelled = ok(app.post(f"/api/jobs/{job['id']}/cancel"), 202)
    assert cancelled["status"] == "cancelled"
    app.advance(600)
    time.sleep(2.5)
    assert len(hub.calls_to("parcelbox", key=token, page=2)) == 1
    assert app.job(job["id"])["status"] == "cancelled"
    assert len(app.case_docs(case["id"])) == 2
    expect_error(app.post(f"/api/jobs/{job['id']}/cancel"), 409, "conflict")
    expect_error(app.post("/api/jobs/nope-404/cancel"), 404, "not_found")


@parcelbox_era
def test_finished_jobs_cannot_be_cancelled(app, hub):
    token, case, conn = setup(app, hub, page_size=10)
    job = app.wait_job(app.start_import(conn["id"])["id"])
    expect_error(app.post(f"/api/jobs/{job['id']}/cancel"), 409, "conflict")
    assert app.job(job["id"])["status"] == "completed"


@parcelbox_era
def test_waiting_job_keeps_waiting_across_a_restart(fresh_app, hub):
    app = fresh_app
    token, case, conn = setup(app, hub)
    hub.fault("parcelbox", token, page=2, status=429, retry_after=60)
    app.set_clock("2026-03-01T09:00:00Z")
    job = app.start_import(conn["id"])
    assert app.wait_job(job["id"], ("waiting",))["retry_at"] == "2026-03-01T09:01:00Z"
    app.restart()
    time.sleep(1.0)
    after = app.job(job["id"])
    assert after["status"] == "waiting" and after["retry_at"] == "2026-03-01T09:01:00Z"
    assert len(hub.calls_to("parcelbox", key=token, page=2)) == 1
    app.advance(60)
    assert app.wait_job(job["id"])["imported"] == 6
    assert len(hub.calls_to("parcelbox", key=token, page=1)) == 1
    assert len(app.case_docs(case["id"])) == 6


@parcelbox_era
def test_cancelling_job_interrupted_by_restart_ends_cancelled(fresh_app, hub):
    app = fresh_app
    token, case, conn = setup(app, hub)
    hold = hub.hold("parcelbox", token, page=2)
    job = app.start_import(conn["id"])
    assert hold["entered"].wait(5)
    ok(app.post(f"/api/jobs/{job['id']}/cancel"), 202)
    app.stop()
    hub.release()
    app.start()
    assert app.wait_job(job["id"], ("cancelled",))["status"] == "cancelled"
    time.sleep(1.0)
    assert len(hub.calls_to("parcelbox", key=token, page=2)) == 1
    assert hub.calls_to("parcelbox", key=token, page=3) == []
    assert len(app.case_docs(case["id"])) == 2
