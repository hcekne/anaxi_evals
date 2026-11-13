"""Probe 3 (debugging handoff): BoxLoop forgets its exports when it restarts; an import that
was waiting on a forgotten export must start a fresh one instead of failing."""

from conftest import by_external, ok, uid, wait_for

ENTRIES = [{"key": f"K{n}", "name": f"Box {n}", "body": f"body {n}", "version": 1}
           for n in range(1, 4)]  # fmt: skip


def setup(app, hub, ready_after):
    key = uid("bl-")
    hub.boxloop(key, ENTRIES, ready_after=ready_after)
    case = app.case()
    conn = app.connect(case["id"], "boxloop", {"api_key": key})
    return key, case, conn


def ops(hub, key, op):
    return hub.calls_to("boxloop", key=key, op=op)


def test_both_restarts_then_a_fresh_export(fresh_app, hub):
    app = fresh_app
    app.set_clock("2026-11-01T09:00:00Z")
    key, case, conn = setup(app, hub, ready_after=1)
    job = app.start_import(conn["id"])
    assert wait_for(lambda: len(ops(hub, key, "status")) == 1, 5)
    app.restart()
    hub.forget_exports()
    app.advance(5)
    assert wait_for(lambda: len(ops(hub, key, "create")) == 2, 5), app.job(job["id"])
    running = app.job(job["id"])
    assert running["status"] == "running" and running["error"] is None
    assert wait_for(lambda: len(ops(hub, key, "status")) == 3, 5)  # checked right after creating
    assert app.job(job["id"])["stage"] == "preparing"
    app.advance(5)
    done = app.wait_job(job["id"])
    assert done["imported"] == 3
    statuses = [c["status"] for c in ops(hub, key, "status")]
    assert statuses.count(404) == 1
    assert len(by_external(app, case["id"])) == 3


def test_forgotten_download_url_starts_over_without_duplicates(app, hub):
    app.set_clock("2026-11-01T09:00:00Z")
    key, case, conn = setup(app, hub, ready_after=0)
    app.wait_job(app.start_import(conn["id"])["id"])
    hold = hub.hold("boxloop", key, page="download")
    job = app.start_import(conn["id"])
    assert hold["entered"].wait(5)
    hub.forget_exports()
    hub.release()
    done = app.wait_job(job["id"], timeout=15)
    assert (done["imported"], done["unchanged"]) == (0, 3)
    assert len(ops(hub, key, "create")) == 3
    assert len(app.case_docs(case["id"])) == 3


def test_other_answers_keep_their_meaning(app, hub):
    key, case, conn = setup(app, hub, ready_after=0)
    hub.fault("boxloop", key, page="status", status=500)
    failed = app.wait_job(app.start_import(conn["id"])["id"], ("failed", "completed"))
    assert failed["error"]["code"] == "upstream_error"
    key2, case2, conn2 = setup(app, hub, ready_after=0)
    hub.boxloop(key2, ENTRIES, fail=True)
    failed = app.wait_job(app.start_import(conn2["id"])["id"], ("failed", "completed"))
    assert failed["error"]["code"] == "export_failed"
    assert ok(app.get(f"/api/connections/{conn2['id']}"))["status"] == "active"
