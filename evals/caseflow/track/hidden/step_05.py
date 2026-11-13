"""Request 5: case-scoped, capital-insensitive search with snippets and stable links."""

from conftest import expect_error, ok


def search(app, case_id, q, user="default"):
    return ok(app.get(f"/api/cases/{case_id}/search", params={"q": q}, user=user))


def hits(app, case_id, q, user="default"):
    return [r["document_id"] for r in search(app, case_id, q, user)["results"]]


def test_sample_examples(app):
    case = app.case()
    lease = app.doc(case["id"], "Lease", "The LEASE ends in May.")
    plan = app.doc(case["id"], "Straßenplan", "Map of Oslo")
    note = app.doc(case["id"], "Note", "Die Straße ist gesperrt.")
    brev = app.doc(case["id"], "Brev", "Møte på ÉCOLE i Tromsø")
    assert hits(app, case["id"], "lease") == [lease["id"]]
    assert hits(app, case["id"], "STRASSE") == [plan["id"], note["id"]]
    assert hits(app, case["id"], "strasse") == [plan["id"], note["id"]]
    assert hits(app, case["id"], "école") == [brev["id"]]
    assert hits(app, case["id"], "TROMSØ") == [brev["id"]]
    assert hits(app, case["id"], "tromso") == []
    assert hits(app, case["id"], "  map OF  ") == [plan["id"]]
    result = search(app, case["id"], "lease")
    assert result["query"].strip() == "lease"
    row = result["results"][0]
    assert {"document_id": lease["id"], "title": "Lease",
            "url": f"/documents/{lease['id']}"}.items() <= row.items()  # fmt: skip
    assert "LEASE" in row["snippet"]


def test_snippets_are_short_exact_pieces_of_the_text(app):
    case = app.case()
    text = ("Preamble words. " * 20) + "The deposit of 900 EUR is REFUNDABLE in full. " + (
        "Trailing clause. " * 20
    )
    doc = app.doc(case["id"], "Long lease", text)
    title_only = app.doc(case["id"], "Refundable things", "x" * 300)
    short = app.doc(case["id"], "Refundable short", "Tiny.")
    rows = {r["document_id"]: r for r in search(app, case["id"], "refundable")["results"]}
    assert list(rows) == [doc["id"], title_only["id"], short["id"]]
    snippet = rows[doc["id"]]["snippet"]
    assert len(snippet) <= 120 and snippet in text and "refundable" in snippet.casefold()
    assert rows[title_only["id"]]["snippet"] == "x" * len(rows[title_only["id"]]["snippet"])
    assert 0 < len(rows[title_only["id"]]["snippet"]) <= 120
    assert "Tiny.".startswith(rows[short["id"]]["snippet"]) and rows[short["id"]]["snippet"]
    assert app.document(doc["id"])["text"] == text


def test_results_stay_in_their_case_and_links_open_the_document(app):
    mine, other = app.case(), app.case()
    first = app.doc(mine["id"], "Invoice March", "amount due")
    app.doc(other["id"], "Invoice April", "amount due")
    second = app.doc(mine["id"], "Reminder", "The invoice is late")
    result = search(app, mine["id"], "INVOICE")["results"]
    assert [r["document_id"] for r in result] == [first["id"], second["id"]]
    for row in result:
        page = app.get(row["url"])
        assert page.status_code == 200 and row["title"] in page.text
    html_page = app.get(f"/cases/{mine['id']}/search", params={"q": "reminder"})
    assert html_page.status_code == 200 and f"/documents/{second['id']}" in html_page.text


def test_bad_queries(app):
    case = app.case()
    for params in ({}, {"q": ""}, {"q": "   "}):
        expect_error(app.get(f"/api/cases/{case['id']}/search", params=params), 422, "invalid_request")
    expect_error(app.get("/api/cases/nope-404/search", params={"q": "x"}), 404, "not_found")


def test_uploaded_and_imported_documents_are_searchable(app):
    case = app.case()
    result = ok(
        app.post(
            f"/api/cases/{case['id']}/csv",
            content="external_id,title,text\nC1,From CSV,Quarterly ÜBERSICHT\n".encode(),
        )
    )
    doc_id = result["created"][0]["document_id"]
    assert hits(app, case["id"], "übersicht") == [doc_id]
