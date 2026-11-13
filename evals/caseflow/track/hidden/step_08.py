"""Request 8: responsibility and exactly-once approval messages through NoticeSink."""

import time

import pdfgen
from conftest import (
    EDITOR,
    OUTSIDER,
    OWNER,
    VIEWER,
    expect_error,
    import_from_source,
    ok,
    wait_for,
)


def notices(app, doc_id, user="default"):
    return ok(app.get(f"/api/documents/{doc_id}/notices", user=user))["notices"]


def sink_calls(hub, doc_id=None):
    return [
        c
        for c in hub.calls_to("noticesink")
        if doc_id is None or (c["body"] or {}).get("document_id") == doc_id
    ]


def wait_calls(hub, doc_id, count, timeout=5):
    assert wait_for(lambda: len(sink_calls(hub, doc_id)) >= count, timeout), sink_calls(hub, doc_id)
    return sink_calls(hub, doc_id)


def wait_notice(app, doc_id, status, index=0, timeout=5):
    found = wait_for(lambda: (n := notices(app, doc_id)) and len(n) > index
                     and n[index]["status"] == status and n, timeout)  # fmt: skip
    assert found, notices(app, doc_id)
    return found[index]


def test_responsible_defaults_to_whoever_added_it(app, hub):
    case = app.case()
    pasted = app.doc(case["id"], "Pasted", "p", user=EDITOR)
    assert pasted["responsible"] == EDITOR
    csv = ok(app.post(f"/api/cases/{case['id']}/csv", user=OWNER,
                      content="external_id,title,text\nR1,Row,r\n".encode()))  # fmt: skip
    assert app.document(csv["created"][0]["document_id"])["responsible"] == OWNER
    pdf = ok(app.post(f"/api/cases/{case['id']}/pdfs", user=EDITOR, json={"files": [
        {"name": "p.pdf", "content_base64": pdfgen.b64(pdfgen.build([["pdf"]]))}]}))  # fmt: skip
    assert app.document(pdf["results"][0]["document_id"])["responsible"] == EDITOR
    import_from_source(app, hub, case["id"], [("S1", "Imported", "i", 1)], user=OWNER)
    case2 = app.case()
    conn, _, key = import_from_source(app, hub, case2["id"], [("S2", "By editor", "e", 1)])
    import_from_source(app, hub, case2["id"], [("S2", "By editor", "e", 1), ("S3", "New", "n", 1)],
                       key=key, connection=conn, user=EDITOR)  # fmt: skip
    owners = {d["title"]: d["responsible"] for d in
              (app.document(x["id"]) for x in app.case_docs(case2["id"]))}  # fmt: skip
    assert owners == {"By editor": OWNER, "New": EDITOR}


def test_only_owners_reassign_and_only_to_members(app):
    case = app.case()
    doc = app.doc(case["id"], "Reassign me", "r", user=EDITOR)
    path = f"/api/documents/{doc['id']}/responsible"
    assert ok(app.put(path, user=OWNER, json={"user": VIEWER}))["responsible"] == VIEWER
    assert app.document(doc["id"])["responsible"] == VIEWER
    expect_error(app.put(path, user=EDITOR, json={"user": EDITOR}), 403, "forbidden")
    expect_error(app.put(path, user=OWNER, json={"user": OUTSIDER}), 422, "not_a_member")
    expect_error(app.put(path, user=OUTSIDER, json={"user": OUTSIDER}), 404, "not_found")
    expect_error(app.put("/api/documents/nope-404/responsible", user=OWNER, json={"user": OWNER}),
                 404, "not_found")  # fmt: skip
    assert app.document(doc["id"])["responsible"] == VIEWER


def test_an_approval_sends_one_message(app, hub):
    case = app.case()
    doc = app.doc(case["id"], "Lease agreement", "l", user=EDITOR)
    review = app.review(doc["id"], "approved", version=1, user=OWNER)
    calls = wait_calls(hub, doc["id"], 1)
    body = calls[0]["body"]
    assert {k: body[k] for k in ("workspace_id", "document_id", "revision", "recipient")} == {
        "workspace_id": case["workspace_id"],
        "document_id": doc["id"],
        "revision": 1,
        "recipient": EDITOR,
    }
    assert "Lease agreement" in body["text"] and len(body["message_id"]) <= 100
    notice = wait_notice(app, doc["id"], "sent")
    assert notice == {"message_id": body["message_id"], "review_id": review["id"],
                      "recipient": EDITOR, "revision": 1, "status": "sent", "attempts": 1}
    app.review(doc["id"], "changes_requested", version=1, user=OWNER)
    time.sleep(1.5)
    assert len(sink_calls(hub, doc["id"])) == 1
    assert notices(app, doc["id"], user=VIEWER) == [notice]
    expect_error(app.get(f"/api/documents/{doc['id']}/notices", user=OUTSIDER), 404, "not_found")


def test_offline_sink_is_retried_on_the_clock(app, hub):
    app.set_clock("2026-03-01T09:00:00Z")
    case = app.case()
    doc = app.doc(case["id"], "Retry me", "r")
    hub.notice_fault(doc["id"], 503)
    started = time.monotonic()
    app.review(doc["id"], "approved", version=1)
    assert time.monotonic() - started < 2
    wait_calls(hub, doc["id"], 1)
    pending = wait_notice(app, doc["id"], "pending")
    assert pending["attempts"] == 1
    time.sleep(1.5)
    assert len(sink_calls(hub, doc["id"])) == 1
    app.advance(30)
    time.sleep(1.5)
    assert len(sink_calls(hub, doc["id"])) == 1
    app.advance(30)
    calls = wait_calls(hub, doc["id"], 2)
    assert calls[0]["raw"] == calls[1]["raw"]
    sent = wait_notice(app, doc["id"], "sent")
    assert sent["attempts"] == 2


def test_lost_response_is_retried_with_the_same_id(app, hub):
    app.set_clock("2026-03-01T09:00:00Z")
    case = app.case()
    doc = app.doc(case["id"], "Lost reply", "r")
    hub.notice_fault(doc["id"], "drop")
    app.review(doc["id"], "approved", version=1)
    wait_calls(hub, doc["id"], 1)
    assert wait_notice(app, doc["id"], "pending")["attempts"] == 1
    app.advance(60)
    calls = wait_calls(hub, doc["id"], 2)
    assert calls[1]["status"] == 200 and calls[0]["body"] == calls[1]["body"]
    assert wait_notice(app, doc["id"], "sent")["attempts"] == 2
    assert [m["message_id"] for m in hub.messages_for(doc["id"])] == [
        calls[0]["body"]["message_id"]
    ]


def test_restarts_neither_lose_nor_repeat_messages(fresh_app, hub):
    app = fresh_app
    app.set_clock("2026-03-01T09:00:00Z")
    case = app.case()
    doc = app.doc(case["id"], "Durable", "d")
    hub.notice_fault(doc["id"], "drop")
    app.review(doc["id"], "approved", version=1)
    wait_calls(hub, doc["id"], 1)
    wait_notice(app, doc["id"], "pending")
    app.restart()
    app.advance(60)
    wait_calls(hub, doc["id"], 2)
    wait_notice(app, doc["id"], "sent")
    app.restart()
    app.advance(600)
    time.sleep(2.5)
    calls = sink_calls(hub, doc["id"])
    assert len(calls) == 2 and len({c["body"]["message_id"] for c in calls}) == 1
    assert len(hub.messages_for(doc["id"])) == 1


def test_separate_approvals_get_separate_messages(app, hub):
    case = app.case()
    doc = app.doc(case["id"], "Twice approved", "t")
    first = app.review(doc["id"], "approved", version=1)
    wait_notice(app, doc["id"], "sent", 0)
    app.review(doc["id"], "changes_requested", version=1)
    second = app.review(doc["id"], "approved", version=1)
    wait_notice(app, doc["id"], "sent", 1)
    rows = notices(app, doc["id"])
    assert [r["review_id"] for r in rows] == [first["id"], second["id"]]
    assert rows[0]["message_id"] != rows[1]["message_id"]
    assert len(sink_calls(hub, doc["id"])) == 2 and len(hub.messages_for(doc["id"])) == 2


def test_the_recipient_is_fixed_at_approval_time(app, hub):
    app.set_clock("2026-03-01T09:00:00Z")
    case = app.case()
    doc = app.doc(case["id"], "Snapshot", "s", user=EDITOR)
    hub.notice_fault(doc["id"], 503)
    app.review(doc["id"], "approved", version=1)
    wait_calls(hub, doc["id"], 1)
    ok(app.put(f"/api/documents/{doc['id']}/responsible", json={"user": VIEWER}))
    app.advance(60)
    calls = wait_calls(hub, doc["id"], 2)
    assert calls[1]["body"]["recipient"] == EDITOR
    app.review(doc["id"], "approved", version=1)
    calls = wait_calls(hub, doc["id"], 3)
    assert calls[2]["body"]["recipient"] == VIEWER
    assert [n["recipient"] for n in notices(app, doc["id"])] == [EDITOR, VIEWER]


def test_malformed_is_not_retried(app, hub):
    app.set_clock("2026-03-01T09:00:00Z")
    case = app.case()
    doc = app.doc(case["id"], "Rejected", "r")
    hub.notice_fault(doc["id"], 400)
    app.review(doc["id"], "approved", version=1)
    assert wait_notice(app, doc["id"], "failed")["attempts"] == 1
    app.advance(600)
    time.sleep(2.5)
    assert len(sink_calls(hub, doc["id"])) == 1
