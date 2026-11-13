"""Request 15: restricted editors see only the documents they are responsible for, everywhere,
and pending approval messages are cancelled when the recipient loses access."""

import time

from conftest import (
    EDITOR,
    EXPORT_RETIRED,
    RESTRICTED,
    VIEWER,
    expect_error,
    import_from_source,
    ok,
    uid,
    wait_for,
)


def team(app):
    ws = app.workspace(members={EDITOR: "editor", VIEWER: "viewer", RESTRICTED: "restricted_editor"})
    case = app.case(ws=ws)
    own = app.doc(case["id"], "Rita own " + uid(), "shared WORD own", user=RESTRICTED)
    other = app.doc(case["id"], "Owner secret " + uid(), "shared WORD secret")
    assigned = app.doc(case["id"], "Assigned " + uid(), "shared WORD assigned")
    ok(app.put(f"/api/documents/{assigned['id']}/responsible", json={"user": RESTRICTED}))
    return ws, case, own, other, assigned


def visible_ids(app, case_id, user):
    return [d["id"] for d in ok(app.get(f"/api/cases/{case_id}", user=user))["documents"]]


def test_role_can_be_set(app):
    ws = app.workspace()
    member = ok(app.put(f"/api/workspaces/{ws}/members/{RESTRICTED}", json={"role": "restricted_editor"}))
    assert member == {"user": RESTRICTED, "role": "restricted_editor"}
    roles = {m["user"]: m["role"] for m in ok(app.get(f"/api/workspaces/{ws}/members"))["members"]}
    assert roles[RESTRICTED] == "restricted_editor"


def test_other_documents_are_invisible_everywhere(app):
    ws, case, own, other, assigned = team(app)
    cid, oid = case["id"], other["id"]
    assert visible_ids(app, cid, RESTRICTED) == [own["id"], assigned["id"]]
    assert visible_ids(app, cid, EDITOR) == [own["id"], oid, assigned["id"]]
    assert visible_ids(app, cid, VIEWER) == [own["id"], oid, assigned["id"]]
    for path in (f"/api/documents/{oid}", f"/api/documents/{oid}/versions",
                 f"/api/documents/{oid}/versions/1", f"/api/documents/{oid}/reviews",
                 f"/api/documents/{oid}/notices"):  # fmt: skip
        expect_error(app.get(path, user=RESTRICTED), 404, "not_found")
    for response in (
        app.patch(f"/api/documents/{oid}", user=RESTRICTED, json={"text": "mine"}),
        app.post(f"/api/documents/{oid}/reviews", user=RESTRICTED,
                 json={"decision": "approved", "version": 1}),
        app.put(f"/api/documents/{oid}/responsible", user=RESTRICTED, json={"user": RESTRICTED}),
    ):  # fmt: skip
        expect_error(response, 404, "not_found")
    for path in (f"/documents/{oid}", f"/documents/{oid}/versions/1"):
        assert app.get(path, user=RESTRICTED).status_code == 404, path
    page = app.get(f"/cases/{cid}", user=RESTRICTED)
    assert page.status_code == 200 and other["title"] not in page.text and own["title"] in page.text
    found = ok(app.get(f"/api/cases/{cid}/search", params={"q": "word"}, user=RESTRICTED))
    assert [r["document_id"] for r in found["results"]] == [own["id"], assigned["id"]]
    found_page = app.get(f"/cases/{cid}/search", params={"q": "word"}, user=RESTRICTED)
    assert found_page.status_code == 200 and other["title"] not in found_page.text
    assert app.document(oid)["text"] == "shared WORD secret"
    for path in (f"/api/cases/{cid}", f"/api/cases/{cid}/connections", f"/api/cases/{cid}/jobs",
                 f"/api/workspaces/{ws}/members"):  # fmt: skip
        assert app.get(path, user=RESTRICTED).status_code == 200, path


def test_restricted_editors_work_on_their_own_documents(app, hub):
    ws, case, own, other, assigned = team(app)
    edited = ok(app.patch(f"/api/documents/{own['id']}", user=RESTRICTED, json={"text": "v2"}))
    assert edited["version"] == 2
    review = app.review(own["id"], "changes_requested", "fix", version=2, user=RESTRICTED)
    assert review["user"] == RESTRICTED
    expect_error(app.put(f"/api/documents/{own['id']}/responsible", user=RESTRICTED,
                         json={"user": RESTRICTED}), 403, "forbidden")  # fmt: skip
    new_case = app.case(ws=ws, user=RESTRICTED)
    added = app.doc(new_case["id"], "Added by rita", "a", user=RESTRICTED)
    assert added["responsible"] == RESTRICTED
    conn, _, key = import_from_source(app, hub, new_case["id"], [("RO-1", "Owner import", "o", 1)])
    import_from_source(app, hub, new_case["id"], [("RO-1", "Owner import", "o", 1),
                                                  ("RR-1", "Rita import", "r", 1)],
                       key=key, connection=conn, user=RESTRICTED)  # fmt: skip
    titles = sorted(app.document(d, RESTRICTED)["title"] for d in visible_ids(app, new_case["id"], RESTRICTED))
    assert titles == ["Added by rita", "Rita import"]


def test_reassignment_moves_visibility_immediately(app):
    ws, case, own, other, assigned = team(app)
    ok(app.put(f"/api/documents/{own['id']}/responsible", json={"user": EDITOR}))
    ok(app.put(f"/api/documents/{other['id']}/responsible", json={"user": RESTRICTED}))
    assert visible_ids(app, case["id"], RESTRICTED) == [other["id"], assigned["id"]]
    expect_error(app.get(f"/api/documents/{own['id']}", user=RESTRICTED), 404, "not_found")
    assert app.document(other["id"], RESTRICTED)["title"] == other["title"]


def test_report_totals_only_count_visible_documents(app):
    ws, case, own, other, assigned = team(app)
    app.set_clock("2026-08-10T10:00:00Z")
    app.review(own["id"], "approved", version=1)
    app.review(other["id"], "approved", version=1)
    app.review(other["id"], "approved", version=1)
    params = {"workspace_id": ws}
    assert ok(app.get("/api/reports/approvals", params=params, user=RESTRICTED))["total"] == 1
    assert ok(app.get("/api/reports/approvals", params=params, user=EDITOR))["total"] == 3
    ok(app.put(f"/api/documents/{other['id']}/responsible", json={"user": RESTRICTED}))
    assert ok(app.get("/api/reports/approvals", params=params, user=RESTRICTED))["total"] == 3


def test_download_only_contains_visible_documents(app):
    ws, case, own, other, assigned = team(app)
    response = app.get(f"/api/cases/{case['id']}/export", user=RESTRICTED)
    if EXPORT_RETIRED:
        assert response.status_code == 404
        return
    ids = [d["id"] for d in ok(response)["documents"]]
    assert ids == [own["id"], assigned["id"]]
    assert len(ok(app.get(f"/api/cases/{case['id']}/export", user=VIEWER))["documents"]) == 3


def notice_calls(hub, doc_id):
    return [c for c in hub.calls_to("noticesink") if (c["body"] or {}).get("document_id") == doc_id]


def notice_rows(app, doc_id):
    return ok(app.get(f"/api/documents/{doc_id}/notices"))["notices"]


def test_pending_message_is_cancelled_when_the_recipient_loses_access(app, hub):
    app.set_clock("2026-09-01T09:00:00Z")
    ws, case, own, other, assigned = team(app)
    hub.notice_fault(own["id"], 503)
    app.review(own["id"], "approved", version=1)  # recipient: the restricted editor
    assert wait_for(lambda: len(notice_calls(hub, own["id"])) == 1, 5)
    assert notice_rows(app, own["id"])[0]["recipient"] == RESTRICTED
    ok(app.put(f"/api/documents/{own['id']}/responsible", json={"user": EDITOR}))
    app.advance(60)
    rows = wait_for(lambda: (r := notice_rows(app, own["id"]))[0]["status"] == "cancelled" and r, 5)
    assert rows, notice_rows(app, own["id"])
    time.sleep(1.5)
    assert len(notice_calls(hub, own["id"])) == 1
    # a recipient who keeps access still gets theirs
    hub.notice_fault(assigned["id"], 503)
    app.review(assigned["id"], "approved", version=1)
    assert wait_for(lambda: len(notice_calls(hub, assigned["id"])) == 1, 5)
    app.advance(60)
    assert wait_for(lambda: notice_rows(app, assigned["id"])[0]["status"] == "sent", 5)


def test_removed_member_is_not_messaged_even_after_restart(fresh_app, hub):
    app = fresh_app
    app.set_clock("2026-09-01T09:00:00Z")
    ws = app.workspace(members={EDITOR: "editor"})
    case = app.case(ws=ws)
    doc = app.doc(case["id"], "Leaving", "l", user=EDITOR)
    hub.notice_fault(doc["id"], 503)
    app.review(doc["id"], "approved", version=1)
    assert wait_for(lambda: len(notice_calls(hub, doc["id"])) == 1, 5)
    assert app.delete(f"/api/workspaces/{ws}/members/{EDITOR}").status_code == 204
    app.restart()
    app.advance(60)
    assert wait_for(lambda: notice_rows(app, doc["id"])[0]["status"] == "cancelled", 5)
    time.sleep(1.0)
    assert len(notice_calls(hub, doc["id"])) == 1
