"""Probe 4 (reversible feature): JSON downloads removed; everything else kept."""

from conftest import EDITOR, VIEWER, ok


def test_downloads_are_gone(app):
    case = app.case()
    app.doc(case["id"], "Kept", "k")
    for user in ("default", EDITOR, VIEWER):
        assert app.get(f"/api/cases/{case['id']}/export", user=user).status_code == 404
    page = app.get(f"/cases/{case['id']}")
    assert page.status_code == 200 and "/export" not in page.text


def test_the_rest_is_kept(app):
    app.set_clock("2026-11-02T10:00:00Z")
    case = app.case()
    doc = app.doc(case["id"], "Still here", "searchable OTTER")
    ok(app.patch(f"/api/documents/{doc['id']}", json={"text": "searchable OTTER v2"}))
    app.review(doc["id"], "approved", version=2)
    assert app.document(doc["id"])["review_status"] == "approved"
    assert len(ok(app.get(f"/api/documents/{doc['id']}/versions"))["versions"]) == 2
    found = ok(app.get(f"/api/cases/{case['id']}/search", params={"q": "otter"}))["results"]
    assert [r["document_id"] for r in found] == [doc["id"]]
    report = ok(app.get("/api/reports/approvals", params={"workspace_id": case["workspace_id"],
                                                          "from": "2026-11-01"}))  # fmt: skip
    assert report["total"] == 1
    assert app.get("/reports").status_code == 200
    assert app.get(f"/documents/{doc['id']}").status_code == 200
