"""Request 10: BoxLoop's request-and-poll exports next to ParcelBox."""

import time

from conftest import PARCEL_RETIRED, by_external, expect_error, ok, uid, wait_for

ENTRIES = [
    {"key": "case/lease.txt", "name": "Lease", "body": "Lease body ✓", "version": 7},
    {"key": "case/notes.txt", "name": "Notes", "body": "Notes body", "version": 1},
    {"key": "case/extra.txt", "name": "Extra", "body": "", "version": 3},
]


def box(app, hub, entries=ENTRIES, ready_after=0, fail=False, case=None):
    key = uid("bl-")
    hub.boxloop(key, entries, ready_after=ready_after, fail=fail)
    case = case or app.case()
    conn = app.connect(case["id"], "boxloop", {"api_key": key})
    return key, case, conn


def ops(hub, key, op):
    return hub.calls_to("boxloop", key=key, op=op)


def test_export_is_polled_on_the_clock_until_ready(app, hub):
    app.set_clock("2026-03-01T09:00:00Z")
    key, case, conn = box(app, hub, ready_after=2)
    assert conn["source"] == "boxloop" and conn["status"] == "active"
    job = app.start_import(conn["id"])
    assert wait_for(lambda: len(ops(hub, key, "status")) == 1, 5)
    preparing = app.job(job["id"])
    assert (preparing["status"], preparing["stage"]) == ("running", "preparing")
    time.sleep(1.5)
    assert len(ops(hub, key, "status")) == 1
    app.advance(5)
    assert wait_for(lambda: len(ops(hub, key, "status")) == 2, 5)
    assert app.job(job["id"])["stage"] == "preparing"
    app.advance(5)
    done = app.wait_job(job["id"])
    assert (done["imported"], done["unchanged"]) == (3, 0)
    assert len(ops(hub, key, "create")) == 1 and len(ops(hub, key, "download")) == 1
    exports = {c["export"] for c in ops(hub, key, "status")}
    assert exports == {ops(hub, key, "create")[0]["export"]}
    docs = by_external(app, case["id"])
    assert {"title": "Lease", "text": "Lease body ✓", "source": "boxloop", "source_revision": 7,
            "connection_id": conn["id"]}.items() <= docs["case/lease.txt"].items()  # fmt: skip
    assert docs["case/extra.txt"]["text"] == ""


def test_unchanged_entries_are_skipped_and_new_versions_update(app, hub):
    key, case, conn = box(app, hub)
    app.wait_job(app.start_import(conn["id"])["id"])
    before = by_external(app, case["id"])
    again = app.wait_job(app.start_import(conn["id"])["id"])
    assert (again["imported"], again["unchanged"]) == (0, 3)
    changed = [dict(e) for e in ENTRIES]
    changed[1] = {"key": "case/notes.txt", "name": "Notes v2", "body": "Changed", "version": 2}
    hub.boxloop(key, changed + [{"key": "new.txt", "name": "New", "body": "n", "version": 1}])
    third = app.wait_job(app.start_import(conn["id"])["id"])
    assert (third["imported"], third["unchanged"]) == (2, 2)
    after = by_external(app, case["id"])
    notes = after["case/notes.txt"]
    assert notes["id"] == before["case/notes.txt"]["id"]
    assert (notes["title"], notes["text"], notes["source_revision"], notes["version"]) == (
        "Notes v2", "Changed", 2, 2)  # fmt: skip
    assert len(after) == 4


def test_failed_export_and_rejected_key(app, hub):
    key, case, conn = box(app, hub, fail=True)
    failed = app.wait_job(app.start_import(conn["id"])["id"], ("failed", "completed"))
    assert failed["status"] == "failed" and failed["error"]["code"] == "export_failed"
    assert app.case_docs(case["id"]) == []
    bad = app.connect(case["id"], "boxloop", {"api_key": "nobody-has-this"})
    rejected = app.wait_job(app.start_import(bad["id"])["id"], ("failed", "completed"))
    assert rejected["error"]["code"] == "credentials_rejected"
    assert ok(app.get(f"/api/connections/{bad['id']}"))["status"] == "unauthorized"
    expect_error(app.post(f"/api/connections/{bad['id']}/imports"), 409, "credentials_rejected")
    good = uid("bl-")
    hub.boxloop(good, ENTRIES[:1])
    fixed = ok(app.put(f"/api/connections/{bad['id']}/credentials", json={"api_key": good}))
    assert fixed["status"] == "active"
    assert app.wait_job(app.start_import(bad["id"])["id"])["imported"] == 1


def test_unexpected_answers_fail_the_job(app, hub):
    key, case, conn = box(app, hub)
    hub.fault("boxloop", key, page="create", status=500)
    failed = app.wait_job(app.start_import(conn["id"])["id"], ("failed", "completed"))
    assert failed["error"]["code"] == "upstream_error"


def test_restart_keeps_checking_the_same_export(fresh_app, hub):
    app = fresh_app
    app.set_clock("2026-03-01T09:00:00Z")
    key, case, conn = box(app, hub, ready_after=1)
    job = app.start_import(conn["id"])
    assert wait_for(lambda: len(ops(hub, key, "status")) == 1, 5)
    app.restart()
    app.advance(5)
    done = app.wait_job(job["id"])
    assert done["imported"] == 3
    assert len(ops(hub, key, "create")) == 1
    assert {c["export"] for c in ops(hub, key, "status")} == {ops(hub, key, "create")[0]["export"]}
    assert len(app.case_docs(case["id"])) == 3


def test_cancel_while_preparing_is_immediate(app, hub):
    app.set_clock("2026-03-01T09:00:00Z")
    key, case, conn = box(app, hub, ready_after=10)
    job = app.start_import(conn["id"])
    assert wait_for(lambda: len(ops(hub, key, "status")) == 1, 5)
    time.sleep(0.3)
    cancelled = ok(app.post(f"/api/jobs/{job['id']}/cancel"), 202)
    assert cancelled["status"] == "cancelled"
    app.advance(60)
    time.sleep(2.5)
    assert len(ops(hub, key, "status")) == 1 and ops(hub, key, "download") == []
    assert app.job(job["id"])["status"] == "cancelled"


def test_two_sources_in_one_case_keep_separate_documents(app, hub):
    case = app.case()
    key, _, boxconn = box(app, hub, [{"key": "SAME", "name": "From BoxLoop", "body": "b",
                                      "version": 1}], case=case)  # fmt: skip
    if PARCEL_RETIRED:
        key2, _, other = box(app, hub, [{"key": "SAME", "name": "From other", "body": "o",
                                         "version": 1}], case=case)  # fmt: skip
        expected = ["From BoxLoop", "From other"]
    else:
        token = uid("pb-")
        hub.parcelbox(token, [{"id": "SAME", "title": "From ParcelBox", "text": "p", "revision": 1}])
        other = app.connect(case["id"], "parcelbox", {"token": token})
        expected = ["From BoxLoop", "From ParcelBox"]
    for conn in (boxconn, other):
        app.wait_job(app.start_import(conn["id"])["id"])
    for conn in (boxconn, other):
        assert app.wait_job(app.start_import(conn["id"])["id"])["unchanged"] == 1
    titles = sorted(app.document(d["id"])["title"] for d in app.case_docs(case["id"]))
    assert titles == expected
    listed = ok(app.get(f"/api/cases/{case['id']}/connections"))["connections"]
    assert [c["id"] for c in listed] == [boxconn["id"], other["id"]]


def test_boxloop_credentials_are_validated_and_hidden(app):
    case = app.case()
    path = f"/api/cases/{case['id']}/connections"
    for creds in ({}, {"api_key": ""}, {"token": "x"}):
        expect_error(app.post(path, json={"source": "boxloop", "credentials": creds}), 422,
                     "invalid_request")  # fmt: skip
    conn = app.connect(case["id"], "boxloop", {"api_key": "very-secret-key"})
    assert "very-secret-key" not in app.get(path).text
    assert "very-secret-key" not in app.get(f"/cases/{case['id']}").text
    assert conn["source"] == "boxloop"
