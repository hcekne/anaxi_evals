"""Probe 2 (new capability): ArchiveTap with ordered withdrawals and reappearances."""

import time

from conftest import (
    EDITOR,
    OWNER,
    VIEWER,
    by_external,
    expect_error,
    ok,
    uid,
    wait_for,
)


def rec(key, edition, heading=None, content=None):
    return {"record_key": key, "heading": heading or f"Heading {key}",
            "content": content or f"content of {key}", "edition": edition}  # fmt: skip


def gone(key, edition):
    return {"record_key": key, "edition": edition, "withdrawn": True}


def archive(app, hub, records, page_size=2):
    account, secret = uid("acct-"), uid("sec-")
    hub.archivetap(account, secret, records, page_size=page_size)
    case = app.case()
    conn = app.connect(case["id"], "archivetap", {"account": account, "secret": secret})
    return account, secret, case, conn


def visible(app, case_id, user="default"):
    return [d["id"] for d in ok(app.get(f"/api/cases/{case_id}", user=user))["documents"]]


def test_plain_records_still_import(app, hub):
    account, secret, case, conn = archive(app, hub, [rec("A", 1), rec("B", 1), rec("C", 2)])
    done = app.wait_job(app.start_import(conn["id"])["id"])
    assert (done["imported"], done["unchanged"]) == (3, 0)
    docs = by_external(app, case["id"])
    assert {"title": "Heading C", "source": "archivetap", "source_revision": 2,
            "withdrawn": False}.items() <= docs["C"].items()  # fmt: skip
    pasted = app.doc(case["id"], "Pasted", "p")
    assert pasted["withdrawn"] is False


def test_withdrawn_documents_leave_normal_views(app, hub):
    account, secret, case, conn = archive(app, hub, [rec("A", 1), rec("B", 1, content="zebra")])
    app.wait_job(app.start_import(conn["id"])["id"])
    docs = by_external(app, case["id"])
    a, b = docs["A"]["id"], docs["B"]["id"]
    app.review(b, "approved", version=1)
    hub.archivetap(account, secret, [rec("A", 1), rec("B", 1, content="zebra"), gone("B", 2),
                                     gone("NEVER", 1)])  # fmt: skip
    job = app.wait_job(app.start_import(conn["id"])["id"])
    assert (job["imported"], job["unchanged"]) == (1, 3)
    for user in (OWNER, EDITOR, VIEWER):
        assert visible(app, case["id"], user) == [a]
        hits = ok(app.get(f"/api/cases/{case['id']}/search", params={"q": "zebra"}, user=user))
        assert hits["results"] == []
    export = app.get(f"/api/cases/{case['id']}/export")
    if export.status_code == 200:
        assert [d["id"] for d in export.json()["documents"]] == [a]
    owner_view = app.document(b, OWNER)
    assert owner_view["withdrawn"] is True and owner_view["text"] == "zebra"
    assert len(ok(app.get(f"/api/documents/{b}/reviews", user=OWNER))["reviews"]) == 1
    assert ok(app.get(f"/api/documents/{b}/versions", user=OWNER))["versions"]
    assert app.get(f"/documents/{b}", user=OWNER).status_code == 200
    for user in (EDITOR, VIEWER):
        for path in (f"/api/documents/{b}", f"/api/documents/{b}/versions",
                     f"/api/documents/{b}/reviews", f"/api/documents/{b}/notices"):  # fmt: skip
            expect_error(app.get(path, user=user), 404, "not_found")
        assert app.get(f"/documents/{b}", user=user).status_code == 404
    expect_error(app.patch(f"/api/documents/{b}", user=EDITOR, json={"text": "x"}), 404, "not_found")
    expect_error(app.post(f"/api/documents/{b}/reviews", user=EDITOR,
                          json={"decision": "approved", "version": 1}), 404, "not_found")  # fmt: skip
    report = ok(app.get("/api/reports/approvals", params={"workspace_id": case["workspace_id"]}))
    assert report["total"] >= 1
    again = app.wait_job(app.start_import(conn["id"])["id"])
    # replaying the same feed: B reappears and is withdrawn again (two changes), A unchanged
    assert (again["imported"], again["unchanged"]) == (2, 2)
    assert visible(app, case["id"]) == [a] and app.document(b, OWNER)["withdrawn"] is True
    assert app.document(b, OWNER)["version"] == 1


def test_events_apply_in_order_and_documents_reappear(app, hub):
    records = [rec("K", 1, content="first"), gone("K", 1), rec("K", 2, content="second"),
               rec("L", 1), gone("L", 1)]  # fmt: skip
    account, secret, case, conn = archive(app, hub, records, page_size=1)
    done = app.wait_job(app.start_import(conn["id"])["id"])
    assert done["imported"] == 5
    docs = {d["external_id"]: d for d in
            (app.document(x, OWNER) for x in _all_ids(app, case["id"]))}  # fmt: skip
    assert visible(app, case["id"]) == [docs["K"]["id"]]
    k = app.document(docs["K"]["id"])
    assert (k["withdrawn"], k["text"], k["version"]) == (False, "second", 2)
    assert docs["L"]["withdrawn"] is True
    hub.archivetap(account, secret, [rec("L", 1)], page_size=1)
    back = app.wait_job(app.start_import(conn["id"])["id"])
    assert back["imported"] == 1
    l_doc = app.document(docs["L"]["id"], EDITOR)
    assert (l_doc["withdrawn"], l_doc["version"]) == (False, 1)
    assert len(visible(app, case["id"])) == 2


def test_only_owners_can_list_withdrawn_documents(app, hub):
    account, secret, case, conn = archive(app, hub, [rec("W", 1), gone("W", 1), rec("V", 1)])
    app.wait_job(app.start_import(conn["id"])["id"])
    params = {"include_withdrawn": "true"}
    owner_list = ok(app.get(f"/api/cases/{case['id']}", params=params, user=OWNER))["documents"]
    assert [(d["title"], d["withdrawn"]) for d in owner_list] == [("Heading W", True),
                                                                   ("Heading V", False)]
    editor_list = ok(app.get(f"/api/cases/{case['id']}", params=params, user=EDITOR))["documents"]
    assert [d["title"] for d in editor_list] == ["Heading V"]


def _all_ids(app, case_id):
    """Every document id of the case, withdrawn ones included (owners only)."""
    detail = ok(app.get(f"/api/cases/{case_id}", params={"include_withdrawn": "true"}, user=OWNER))
    return [d["id"] for d in detail["documents"]]


def test_pending_message_to_a_non_owner_is_cancelled_on_withdrawal(app, hub):
    app.set_clock("2026-10-01T09:00:00Z")
    account, secret, case, conn = archive(app, hub, [rec("M", 1)])
    app.wait_job(app.start_import(conn["id"], user=EDITOR)["id"])
    doc = by_external(app, case["id"])["M"]
    assert doc["responsible"] == EDITOR
    hub.notice_fault(doc["id"], 503)
    app.review(doc["id"], "approved", version=1)
    assert wait_for(lambda: len([c for c in hub.calls_to("noticesink")
                                 if c["body"]["document_id"] == doc["id"]]) == 1, 5)  # fmt: skip
    hub.archivetap(account, secret, [gone("M", 2)])
    app.wait_job(app.start_import(conn["id"])["id"])
    app.advance(60)
    rows = lambda: ok(app.get(f"/api/documents/{doc['id']}/notices", user=OWNER))["notices"]  # noqa: E731
    assert wait_for(lambda: rows()[0]["status"] == "cancelled", 5), rows()
    time.sleep(1.0)
    assert len([c for c in hub.calls_to("noticesink") if c["body"]["document_id"] == doc["id"]]) == 1
