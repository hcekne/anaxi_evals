"""Request 13: ParcelBox retired; its history kept. The upgrade check starts the candidate's
previous release (the code as it stood when request 13 arrived) on a data directory, fills it
with ParcelBox connections, finished and unfinished jobs, then starts the current code on it."""

import time

import pytest

from conftest import (
    EDITOR,
    EXPORT_RETIRED,
    App,
    expect_error,
    ok,
    previous_release,
    uid,
    wait_for,
)

ITEMS = [{"id": f"OLD-{n}", "title": f"Old parcel {n}", "text": f"walrus text {n}", "revision": 2}
         for n in range(1, 4)]  # fmt: skip


def test_new_parcelbox_connections_are_refused(app):
    case = app.case()
    response = app.post(f"/api/cases/{case['id']}/connections",
                        json={"source": "parcelbox", "credentials": {"token": "pb-1"}})  # fmt: skip
    expect_error(response, 422, "unsupported_source")
    assert ok(app.get(f"/api/cases/{case['id']}/connections"))["connections"] == []


@pytest.fixture(scope="module")
def upgraded(hub):
    """(app on the current code, facts recorded while the previous release ran)."""
    hub.reset()
    old_code = previous_release(13)
    old = App(hub.url, code=old_code)
    old.set_clock("2026-03-01T09:00:00Z")
    case = old.case()
    facts = {"case": case}
    done_token, held_token, waiting_token, box_key = (uid("pb-") for _ in range(4))
    hub.parcelbox(done_token, ITEMS, page_size=2)
    hub.parcelbox(held_token, [dict(i, id=f"H-{i['id']}") for i in ITEMS], page_size=1)
    hub.parcelbox(waiting_token, [dict(i, id=f"W-{i['id']}") for i in ITEMS], page_size=1)
    hub.boxloop(box_key, [{"key": "B-1", "name": "Box doc", "body": "box", "version": 1}])
    done = old.connect(case["id"], "parcelbox", {"token": done_token})
    facts["done_job"] = old.wait_job(old.start_import(done["id"])["id"])
    docs = {d["external_id"]: d for d in (old.document(x["id"]) for x in old.case_docs(case["id"]))}
    facts["doc"] = docs["OLD-1"]
    facts["review"] = old.review(docs["OLD-1"]["id"], "approved", "ok", version=1, user=EDITOR)
    assert wait_for(lambda: ok(old.get(f"/api/documents/{docs['OLD-1']['id']}/notices"))
                    ["notices"][0]["status"] == "sent", 5)  # fmt: skip
    box = old.connect(case["id"], "boxloop", {"api_key": box_key})
    old.wait_job(old.start_import(box["id"])["id"])
    held = old.connect(case["id"], "parcelbox", {"token": held_token})
    hold = hub.hold("parcelbox", held_token, page=2)
    facts["held_job"] = old.start_import(held["id"])
    assert hold["entered"].wait(5)
    waiting = old.connect(case["id"], "parcelbox", {"token": waiting_token})
    hub.fault("parcelbox", waiting_token, page=1, status=429, retry_after=60)
    facts["waiting_job"] = old.start_import(waiting["id"])
    old.wait_job(facts["waiting_job"]["id"], ("waiting",))
    facts["connections"] = {"done": done, "held": held, "waiting": waiting, "box": box}
    facts["box_key"] = box_key
    old.stop()
    hub.release()
    time.sleep(0.3)
    facts["parcel_calls"] = len(hub.calls_to("parcelbox"))
    new = App(hub.url, data=old.data)
    new.clock = old.clock
    new._ws = old._ws
    time.sleep(2.5)
    facts["calls_after_upgrade"] = len(hub.calls_to("parcelbox")) - facts["parcel_calls"]
    yield new, facts
    new.close()
    old.close()


def test_unfinished_parcelbox_jobs_are_cancelled_and_stay_quiet(upgraded, hub):
    app, facts = upgraded
    assert facts["calls_after_upgrade"] == 0
    for name in ("held_job", "waiting_job"):
        assert app.wait_job(facts[name]["id"], ("cancelled",))["status"] == "cancelled"
    app.advance(600)
    time.sleep(2.5)
    assert app.job(facts["done_job"]["id"])["status"] == "completed"
    assert hub.calls_to("parcelbox") == []
    app.restart()
    app.advance(600)
    time.sleep(2.0)
    assert hub.calls_to("parcelbox") == []
    assert app.job(facts["waiting_job"]["id"])["status"] == "cancelled"


def test_saved_parcelbox_connections_are_retired(upgraded, hub):
    app, facts = upgraded
    conns = facts["connections"]
    for name in ("done", "held", "waiting"):
        conn = ok(app.get(f"/api/connections/{conns[name]['id']}"))
        assert (conn["source"], conn["status"]) == ("parcelbox", "retired")
        expect_error(app.post(f"/api/connections/{conn['id']}/imports"), 409, "source_retired")
        expect_error(app.put(f"/api/connections/{conn['id']}/credentials", json={"token": "x"}),
                     409, "source_retired")  # fmt: skip
    listed = ok(app.get(f"/api/cases/{facts['case']['id']}/connections"))["connections"]
    assert [c["id"] for c in listed] == [conns[n]["id"] for n in ("done", "box", "held", "waiting")]
    assert ok(app.get(f"/api/connections/{conns['box']['id']}"))["status"] == "active"
    time.sleep(0.5)
    assert hub.calls_to("parcelbox") == []


def test_everything_parcelbox_brought_in_is_kept(upgraded):
    app, facts = upgraded
    case_id, before = facts["case"]["id"], facts["doc"]
    doc = app.document(before["id"])
    for key in ("title", "text", "source", "external_id", "source_revision", "connection_id",
                "version", "responsible"):  # fmt: skip
        assert doc[key] == before[key], key
    assert doc["review_status"] == "approved"
    history = ok(app.get(f"/api/documents/{doc['id']}/reviews"))["reviews"]
    assert history == [facts["review"]]
    assert [v["text"] for v in ok(app.get(f"/api/documents/{doc['id']}/versions"))["versions"]] == [
        before["text"]]  # fmt: skip
    notices = ok(app.get(f"/api/documents/{doc['id']}/notices"))["notices"]
    assert [(n["status"], n["revision"]) for n in notices] == [("sent", 1)]
    found = ok(app.get(f"/api/cases/{case_id}/search", params={"q": "WALRUS"}))["results"]
    assert len(found) == 4  # three finished plus page 1 of the interrupted import
    titles = {d["title"] for d in app.case_docs(case_id)}
    assert {"Old parcel 1", "Old parcel 2", "Old parcel 3", "Box doc"} <= titles
    if not EXPORT_RETIRED:
        exported = ok(app.get(f"/api/cases/{case_id}/export"))
        assert before["id"] in [d["id"] for d in exported["documents"]]
    report = ok(app.get("/api/reports/approvals", params={"workspace_id": facts["case"]["workspace_id"]}))
    assert report["total"] == 1
    assert app.get(f"/documents/{doc['id']}").status_code == 200


def test_other_sources_carry_on(upgraded, hub):
    app, facts = upgraded
    hub.boxloop(facts["box_key"], [{"key": "B-1", "name": "Box doc", "body": "box", "version": 1},
                                   {"key": "B-2", "name": "Box two", "body": "2", "version": 1}])  # fmt: skip
    job = app.wait_job(app.start_import(facts["connections"]["box"]["id"])["id"])
    assert (job["imported"], job["unchanged"]) == (1, 1)
    result = ok(app.post(f"/api/cases/{facts['case']['id']}/csv",
                         content="external_id,title,text\nC1,After upgrade,c\n".encode()))  # fmt: skip
    assert len(result["created"]) == 1
    pasted = app.doc(facts["case"]["id"], "Pasted after upgrade", "p")
    assert pasted["source"] == "manual"
