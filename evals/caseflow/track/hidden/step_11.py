"""Request 11: every content change keeps the old version; reviews stay with their version."""

from conftest import EDITOR, OUTSIDER, VIEWER, expect_error, import_from_source, ok, wait_for


def versions(app, doc_id, user="default"):
    return ok(app.get(f"/api/documents/{doc_id}/versions", user=user))["versions"]


def test_edits_keep_old_versions(app):
    case = app.case()
    app.set_clock("2026-05-01T10:00:00Z")
    doc = app.doc(case["id"], "Memo", "first draft")
    app.set_clock("2026-05-02T11:00:00Z")
    ok(app.patch(f"/api/documents/{doc['id']}", json={"title": "Memo v2", "text": "second"}))
    ok(app.patch(f"/api/documents/{doc['id']}", json={"title": "Memo v2", "text": "second"}))
    assert versions(app, doc["id"], user=VIEWER) == [
        {"version": 1, "title": "Memo", "text": "first draft", "source_revision": None,
         "created_at": "2026-05-01T10:00:00Z"},
        {"version": 2, "title": "Memo v2", "text": "second", "source_revision": None,
         "created_at": "2026-05-02T11:00:00Z"},
    ]  # fmt: skip
    one = ok(app.get(f"/api/documents/{doc['id']}/versions/1"))
    assert (one["version"], one["text"]) == (1, "first draft")
    expect_error(app.get(f"/api/documents/{doc['id']}/versions/3"), 404, "not_found")
    expect_error(app.get(f"/api/documents/{doc['id']}/versions", user=OUTSIDER), 404, "not_found")
    latest = app.document(doc["id"])
    assert (latest["title"], latest["text"], latest["version"]) == ("Memo v2", "second", 2)
    assert [d["title"] for d in app.case_docs(case["id"])] == ["Memo v2"]


def test_new_source_revision_becomes_the_unreviewed_latest(app, hub):
    case = app.case()
    conn, _, key = import_from_source(app, hub, case["id"], [("R1", "Deed", "old deed", 3)])
    doc = app.case_docs(case["id"])[0]
    approved = app.review(doc["id"], "approved", version=1, user=EDITOR)
    import_from_source(app, hub, case["id"], [("R1", "Deed", "old deed", 3)], key=key,
                       connection=conn)  # fmt: skip
    assert app.document(doc["id"])["version"] == 1
    import_from_source(app, hub, case["id"], [("R1", "Deed v2", "new deed", 4)], key=key,
                       connection=conn)  # fmt: skip
    latest = app.document(doc["id"])
    assert (latest["version"], latest["text"], latest["source_revision"]) == (2, "new deed", 4)
    assert latest["review_status"] is None
    assert [(v["version"], v["text"], v["source_revision"]) for v in versions(app, doc["id"])] == [
        (1, "old deed", 3),
        (2, "new deed", 4),
    ]
    history = ok(app.get(f"/api/documents/{doc['id']}/reviews"))["reviews"]
    assert history == [approved]
    expect_error(app.post(f"/api/documents/{doc['id']}/reviews",
                          json={"decision": "approved", "version": 1}), 409, "stale_version")  # fmt: skip
    app.review(doc["id"], "changes_requested", version=2)
    assert app.document(doc["id"])["review_status"] == "changes_requested"
    assert len(app.case_docs(case["id"])) == 1


def test_search_only_sees_the_latest_version(app):
    case = app.case()
    doc = app.doc(case["id"], "Policy", "contains WALRUS")
    ok(app.patch(f"/api/documents/{doc['id']}", json={"text": "contains PENGUIN"}))
    found = lambda q: [r["document_id"] for r in  # noqa: E731
                       ok(app.get(f"/api/cases/{case['id']}/search", params={"q": q}))["results"]]
    assert found("walrus") == [] and found("penguin") == [doc["id"]]


def test_messages_keep_the_revision_they_were_decided_on(app):
    case = app.case()
    doc = app.doc(case["id"], "Notice me", "v1")
    app.review(doc["id"], "approved", version=1)
    assert wait_for(lambda: ok(app.get(f"/api/documents/{doc['id']}/notices"))["notices"])
    ok(app.patch(f"/api/documents/{doc['id']}", json={"text": "v2"}))
    app.review(doc["id"], "approved", version=2)
    rows = wait_for(lambda: len(n := ok(app.get(f"/api/documents/{doc['id']}/notices"))["notices"])
                    == 2 and n)  # fmt: skip
    assert [r["revision"] for r in rows] == [1, 2]


def test_version_pages(app):
    case = app.case()
    doc = app.doc(case["id"], "Paged", "the original words")
    ok(app.patch(f"/api/documents/{doc['id']}", json={"text": "the replacement words"}))
    current = app.get(f"/documents/{doc['id']}")
    assert current.status_code == 200 and "the replacement words" in current.text
    assert f"/documents/{doc['id']}/versions/1" in current.text
    old = app.get(f"/documents/{doc['id']}/versions/1", user=VIEWER)
    assert old.status_code == 200 and "the original words" in old.text
    assert app.get(f"/documents/{doc['id']}/versions/9").status_code == 404
    assert app.get(f"/documents/{doc['id']}/versions/1", user=OUTSIDER).status_code == 404
