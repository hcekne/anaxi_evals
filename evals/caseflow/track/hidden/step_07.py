"""Request 7: immutable, versioned review decisions with actor and clock time."""

from conftest import EDITOR, OUTSIDER, OWNER, VIEWER, expect_error, ok


def reviews(app, doc_id, user="default"):
    return ok(app.get(f"/api/documents/{doc_id}/reviews", user=user))["reviews"]


def test_decisions_are_recorded_with_who_when_and_version(app):
    case = app.case()
    doc = app.doc(case["id"], "Lease", "text")
    app.set_clock("2026-03-01T09:00:00Z")
    first = app.review(doc["id"], "approved", "Looks complete", version=1, user=EDITOR)
    assert first == {
        "id": first["id"],
        "document_id": doc["id"],
        "version": 1,
        "decision": "approved",
        "comment": "Looks complete",
        "user": EDITOR,
        "decided_at": "2026-03-01T09:00:00Z",
    }
    assert app.document(doc["id"])["review_status"] == "approved"
    app.set_clock("2026-03-02T10:30:00Z")
    second = app.review(doc["id"], "changes_requested", "Missing page 2", version=1, user=OWNER)
    assert app.document(doc["id"])["review_status"] == "changes_requested"
    history = reviews(app, doc["id"], user=VIEWER)
    assert history == [first, second]
    assert second["decided_at"] == "2026-03-02T10:30:00Z" and second["user"] == OWNER


def test_same_time_decisions_keep_their_order(app):
    case = app.case()
    doc = app.doc(case["id"], "Tie", "t")
    app.set_clock("2026-03-05T12:00:00Z")
    made = [
        app.review(doc["id"], d, version=1, user=EDITOR)
        for d in ("approved", "changes_requested", "approved", "changes_requested")
    ]
    assert [r["id"] for r in reviews(app, doc["id"])] == [r["id"] for r in made]
    assert made[0]["comment"] == ""
    assert app.document(doc["id"])["review_status"] == "changes_requested"


def test_bad_decisions(app):
    case = app.case()
    doc = app.doc(case["id"], "Bad", "b")
    path = f"/api/documents/{doc['id']}/reviews"
    for body in (
        {"decision": "maybe", "version": 1},
        {"decision": "approved"},
        {"decision": "approved", "version": "1"},
        {"decision": "approved", "version": 1, "comment": 5},
        {"version": 1},
    ):
        expect_error(app.post(path, json=body), 422, "invalid_request")
    expect_error(app.post(path, json={"decision": "approved", "version": 2}), 409, "stale_version")
    ok(app.patch(f"/api/documents/{doc['id']}", json={"text": "changed"}))
    expect_error(app.post(path, json={"decision": "approved", "version": 1}), 409, "stale_version")
    expect_error(app.post("/api/documents/nope-404/reviews", json={"decision": "approved",
                                                                  "version": 1}), 404, "not_found")
    assert reviews(app, doc["id"]) == []
    assert app.document(doc["id"])["review_status"] is None


def test_a_new_version_starts_unreviewed(app):
    case = app.case()
    doc = app.doc(case["id"], "Versioned", "v1")
    approved = app.review(doc["id"], "approved", version=1, user=EDITOR)
    ok(app.patch(f"/api/documents/{doc['id']}", json={"text": "v2"}, user=EDITOR))
    current = app.document(doc["id"])
    assert (current["version"], current["review_status"]) == (2, None)
    again = app.review(doc["id"], "changes_requested", "Typo", version=2, user=EDITOR)
    assert [r["version"] for r in reviews(app, doc["id"])] == [1, 2]
    assert reviews(app, doc["id"]) == [approved, again]


def test_who_may_decide_and_read(app):
    case = app.case()
    doc = app.doc(case["id"], "Perms", "p")
    body = {"decision": "approved", "comment": "", "version": 1}
    expect_error(app.post(f"/api/documents/{doc['id']}/reviews", user=VIEWER, json=body), 403,
                 "forbidden")  # fmt: skip
    made = app.review(doc["id"], version=1, user=EDITOR)
    assert reviews(app, doc["id"], user=VIEWER) == [made]
    expect_error(app.get(f"/api/documents/{doc['id']}/reviews", user=OUTSIDER), 404, "not_found")
    expect_error(app.post(f"/api/documents/{doc['id']}/reviews", user=OUTSIDER, json=body), 404,
                 "not_found")  # fmt: skip
    assert len(reviews(app, doc["id"])) == 1


def test_history_survives_restart_and_shows_on_the_page(fresh_app):
    app = fresh_app
    case = app.case()
    doc = app.doc(case["id"], "Kept", "k")
    app.set_clock("2026-04-01T08:00:00Z")
    made = [
        app.review(doc["id"], "changes_requested", "Needs stamp", version=1, user=EDITOR),
        app.review(doc["id"], "approved", "Stamped now", version=1, user=OWNER),
    ]
    app.restart()
    assert reviews(app, doc["id"], user=VIEWER) == made
    page = app.get(f"/documents/{doc['id']}", user=VIEWER)
    assert page.status_code == 200 and "Needs stamp" in page.text and "Stamped now" in page.text
