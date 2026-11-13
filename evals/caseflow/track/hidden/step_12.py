"""Request 12: the strict JSON case download."""

import json

from conftest import (
    EDITOR,
    OUTSIDER,
    VIEWER,
    expected_export,
    export_era,
    import_from_source,
    ok,
)


def download(app, case_id, user="default"):
    response = app.get(f"/api/cases/{case_id}/export", user=user)
    assert response.status_code == 200, response.text[:300]
    return response


@export_era
def test_export_matches_the_published_format(app, hub):
    app.set_clock("2026-06-01T08:00:00Z")
    case = app.case(name='Case "Ø" \\ test')
    tricky = 'He said "stop"\\n\nBackslash \\ and </script> ✓ \u2028 end'
    pasted = app.doc(case["id"], "Tricky \"title\"", tricky, user=EDITOR)
    app.review(pasted["id"], "approved", "fine \"really\"", version=1)
    app.set_clock("2026-06-02T09:30:00Z")
    ok(app.patch(f"/api/documents/{pasted['id']}", json={"text": tricky + " v2"}))
    app.review(pasted["id"], "changes_requested", "again", version=2, user=EDITOR)
    import_from_source(app, hub, case["id"], [("EXT-1", "Imported", "from source", 5)])
    app.doc(case["id"], "Empty", "")
    response = download(app, case["id"], user=VIEWER)
    assert response.headers["content-type"].startswith("application/json")
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment") and f'filename="case-{case["id"]}.json"' in disposition
    body = json.loads(response.content.decode("utf-8"))
    assert body == expected_export(app, case["id"])
    pasted_out = body["documents"][0]
    assert pasted_out["text"] == tricky + " v2" and pasted_out["version"] == 2
    assert [v["text"] for v in pasted_out["versions"]] == [tricky, tricky + " v2"]
    assert [(r["version"], r["decision"]) for r in pasted_out["reviews"]] == [
        (1, "approved"), (2, "changes_requested")]  # fmt: skip
    assert body["documents"][1]["external_id"] == "EXT-1"
    assert body["documents"][1]["versions"][0]["source_revision"] == 5
    assert set(body) == {"format", "case", "documents"}
    assert all(set(d) == {"id", "title", "text", "version", "source", "external_id",
                          "responsible", "versions", "reviews"} for d in body["documents"])  # fmt: skip


@export_era
def test_empty_case_exports_empty_collections(app):
    case = app.case()
    body = download(app, case["id"]).json()
    assert body == {
        "format": "caseflow-case/1",
        "case": {"id": case["id"], "name": case["name"], "workspace_id": case["workspace_id"]},
        "documents": [],
    }


@export_era
def test_only_this_case_and_only_members(app):
    mine, other = app.case(), app.case()
    kept = app.doc(mine["id"], "Mine", "m")
    app.doc(other["id"], "Other", "o")
    body = download(app, mine["id"], user=VIEWER).json()
    assert [d["id"] for d in body["documents"]] == [kept["id"]]
    assert app.get(f"/api/cases/{mine['id']}/export", user=OUTSIDER).status_code == 404
    assert app.get("/api/cases/nope-404/export").status_code == 404
    page = app.get(f"/cases/{mine['id']}")
    assert f"/api/cases/{mine['id']}/export" in page.text
