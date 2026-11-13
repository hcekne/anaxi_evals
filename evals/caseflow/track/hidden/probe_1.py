"""Probe 1 (familiar extension): ArchiveTap as another cursor-paged source."""

import time

from conftest import (
    EDITOR,
    OUTSIDER,
    VIEWER,
    by_external,
    expect_error,
    ok,
    uid,
)

RECORDS = [{"record_key": f"AT-{n}", "heading": f"Archive {n}", "content": f"archived {n} ✓",
            "edition": 1} for n in range(1, 6)]  # fmt: skip


def archive(app, hub, records=RECORDS, page_size=2, case=None, user="default"):
    account, secret = uid("acct-"), uid("sec-")
    hub.archivetap(account, secret, records, page_size=page_size)
    case = case or app.case()
    conn = app.connect(case["id"], "archivetap", {"account": account, "secret": secret}, user=user)
    return account, secret, case, conn


def test_import_follows_every_page(app, hub):
    account, secret, case, conn = archive(app, hub)
    assert (conn["source"], conn["status"]) == ("archivetap", "active")
    assert secret not in app.get(f"/api/cases/{case['id']}/connections").text
    done = app.wait_job(app.start_import(conn["id"])["id"])
    assert (done["imported"], done["unchanged"], done["source"]) == (5, 0, "archivetap")
    calls = hub.calls_to("archivetap", key=account)
    assert [c["page"] for c in calls] == [1, 2, 3] and calls[0]["cursor"] is None
    docs = by_external(app, case["id"])
    assert {"title": "Archive 1", "text": "archived 1 ✓", "source": "archivetap",
            "source_revision": 1, "connection_id": conn["id"], "version": 1,
            "responsible": app.user}.items() <= docs["AT-1"].items()  # fmt: skip
    found = ok(app.get(f"/api/cases/{case['id']}/search", params={"q": "ARCHIVED 3"}))
    assert [r["document_id"] for r in found["results"]] == [docs["AT-3"]["id"]]


def test_credentials_are_validated(app):
    case = app.case()
    path = f"/api/cases/{case['id']}/connections"
    for creds in ({}, {"account": "a"}, {"account": "", "secret": "s"}, {"account": "a", "secret": 5}):
        expect_error(app.post(path, json={"source": "archivetap", "credentials": creds}), 422,
                     "invalid_request")  # fmt: skip
    expect_error(app.post(path, json={"source": "parcelbox", "credentials": {"token": "t"}}), 422,
                 "unsupported_source")  # fmt: skip


def test_unchanged_and_new_editions(app, hub):
    account, secret, case, conn = archive(app, hub)
    app.wait_job(app.start_import(conn["id"])["id"])
    before = by_external(app, case["id"])
    again = app.wait_job(app.start_import(conn["id"])["id"])
    assert (again["imported"], again["unchanged"]) == (0, 5)
    changed = [dict(r) for r in RECORDS]
    changed[0] = {"record_key": "AT-1", "heading": "Archive 1b", "content": "new", "edition": 2}
    hub.archivetap(account, secret, changed, page_size=2)
    third = app.wait_job(app.start_import(conn["id"])["id"])
    assert (third["imported"], third["unchanged"]) == (1, 4)
    after = app.document(before["AT-1"]["id"])
    assert (after["version"], after["text"], after["source_revision"], after["review_status"]) == (
        2, "new", 2, None)  # fmt: skip
    old = ok(app.get(f"/api/documents/{after['id']}/versions"))["versions"]
    assert [v["text"] for v in old] == ["archived 1 ✓", "new"]


def test_rate_limit_waits_on_the_clock(app, hub):
    account, secret, case, conn = archive(app, hub)
    hub.fault("archivetap", account, page=2, status=429, retry_after=90)
    app.set_clock("2026-10-01T09:00:00Z")
    job = app.start_import(conn["id"])
    waiting = app.wait_job(job["id"], ("waiting",))
    assert waiting["retry_at"] == "2026-10-01T09:01:30Z" and waiting["imported"] == 2
    time.sleep(1.5)
    assert len(hub.calls_to("archivetap", key=account, page=2)) == 1
    app.advance(90)
    assert app.wait_job(job["id"])["imported"] == 5
    page2 = hub.calls_to("archivetap", key=account, page=2)
    assert len(page2) == 2 and page2[0]["cursor"] == page2[1]["cursor"]


def test_rejected_credentials_stay_rejected(app, hub):
    case = app.case()
    conn = app.connect(case["id"], "archivetap", {"account": "nobody", "secret": "wrong"})
    failed = app.wait_job(app.start_import(conn["id"])["id"], ("failed", "completed"))
    assert failed["error"]["code"] == "credentials_rejected"
    assert ok(app.get(f"/api/connections/{conn['id']}"))["status"] == "unauthorized"
    expect_error(app.post(f"/api/connections/{conn['id']}/imports"), 409, "credentials_rejected")
    account, secret = uid("acct-"), uid("sec-")
    hub.archivetap(account, secret, RECORDS[:1])
    ok(app.put(f"/api/connections/{conn['id']}/credentials",
               json={"account": account, "secret": secret}))  # fmt: skip
    assert app.wait_job(app.start_import(conn["id"])["id"])["imported"] == 1
    hub.fault("archivetap", account, page=1, status=500)
    broken = app.wait_job(app.start_import(conn["id"])["id"], ("failed", "completed"))
    assert broken["error"]["code"] == "upstream_error"


def test_restart_carries_on_and_cancel_finishes_the_request_in_flight(fresh_app, hub):
    app = fresh_app
    account, secret, case, conn = archive(app, hub)
    hold = hub.hold("archivetap", account, page=2)
    job = app.start_import(conn["id"])
    assert hold["entered"].wait(5)
    assert app.job(job["id"])["imported"] == 2 and len(app.case_docs(case["id"])) == 2
    app.stop()
    hub.release()
    app.start()
    assert app.wait_job(job["id"])["imported"] == 5
    assert len(hub.calls_to("archivetap", key=account, page=1)) == 1
    assert len(app.case_docs(case["id"])) == 5
    account2, _, case2, conn2 = archive(app, hub)
    hold = hub.hold("archivetap", account2, page=2)
    job2 = app.start_import(conn2["id"])
    assert hold["entered"].wait(5)
    assert ok(app.post(f"/api/jobs/{job2['id']}/cancel"), 202)["status"] == "cancelling"
    hub.release()
    assert app.wait_job(job2["id"], ("cancelled",))["imported"] == 4
    time.sleep(1.0)
    assert hub.calls_to("archivetap", key=account2, page=3) == []


def test_roles_and_neighbours(app, hub):
    case = app.case()
    creds = {"account": "a", "secret": "s"}
    expect_error(app.post(f"/api/cases/{case['id']}/connections", user=EDITOR,
                          json={"source": "archivetap", "credentials": creds}), 403, "forbidden")
    expect_error(app.post(f"/api/cases/{case['id']}/connections", user=OUTSIDER,
                          json={"source": "archivetap", "credentials": creds}), 404, "not_found")  # fmt: skip
    account, secret, _, conn = archive(app, hub, [{"record_key": "SAME", "heading": "From AT",
                                                   "content": "a", "edition": 1}], case=case)
    key = uid("bl-")
    hub.boxloop(key, [{"key": "SAME", "name": "From BL", "body": "b", "version": 1}])
    box = app.connect(case["id"], "boxloop", {"api_key": key})
    expect_error(app.post(f"/api/connections/{conn['id']}/imports", user=VIEWER), 403, "forbidden")
    app.wait_job(app.start_import(conn["id"], user=EDITOR)["id"])
    app.wait_job(app.start_import(box["id"])["id"])
    docs = [app.document(d["id"]) for d in app.case_docs(case["id"])]
    assert sorted(d["title"] for d in docs) == ["From AT", "From BL"]
    assert next(d for d in docs if d["title"] == "From AT")["responsible"] == EDITOR
