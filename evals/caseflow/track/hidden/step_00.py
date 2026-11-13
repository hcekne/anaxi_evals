"""Request 0: cases, pasted documents, validation, pages and persistence."""

import html

from conftest import expect_error, ok, uid


def case_body(app, **body):
    if app.ws:
        body["workspace_id"] = app.ws
    return body


def test_create_and_list_cases(app):
    first = ok(app.post("/api/cases", json=case_body(app, name="Smith v. Jones")), 201)
    second = ok(app.post("/api/cases", json=case_body(app, name="  Ørsted  ")), 201)
    assert first["name"] == "Smith v. Jones" and second["name"] == "  Ørsted  "
    assert first["id"] != second["id"]
    listed = ok(app.get("/api/cases"))["cases"]
    ids = [c["id"] for c in listed]
    assert ids.index(first["id"]) < ids.index(second["id"])
    assert {"id": first["id"], "name": "Smith v. Jones"}.items() <= listed[
        ids.index(first["id"])
    ].items()
    detail = ok(app.get(f"/api/cases/{first['id']}"))
    assert detail["id"] == first["id"] and detail["name"] == "Smith v. Jones"
    assert detail["documents"] == []


def test_blank_case_name_is_refused(app):
    before = len(ok(app.get("/api/cases"))["cases"])
    for body in ({"name": ""}, {"name": "   "}, {"name": "\n\t"}, {}):
        expect_error(app.post("/api/cases", json=case_body(app, **body)), 422, "name_required")
    expect_error(app.post("/api/cases", json=case_body(app, name=5)), 422, "invalid_request")
    assert len(ok(app.get("/api/cases"))["cases"]) == before


def test_paste_and_open_documents(app):
    case = app.case()
    text = "  Første linje\nSecond line — «quoted»\n\n日本語 ✓  "
    first = ok(
        app.post(f"/api/cases/{case['id']}/documents", json={"title": " Brev ", "text": text}),
        201,
    )
    assert {"case_id": case["id"], "title": " Brev ", "text": text}.items() <= first.items()
    second = app.doc(case["id"], "Empty one", "")
    assert second["text"] == "" and second["id"] != first["id"]
    assert app.document(first["id"])["text"] == text
    assert app.document(first["id"])["title"] == " Brev "
    listed = app.case_docs(case["id"])
    assert [(d["id"], d["title"]) for d in listed] == [
        (first["id"], " Brev "),
        (second["id"], "Empty one"),
    ]


def test_blank_title_is_refused_and_nothing_saved(app):
    case = app.case()
    path = f"/api/cases/{case['id']}/documents"
    for body in ({"title": "", "text": "x"}, {"title": "  \n ", "text": "x"}, {"text": "x"}):
        response = app.post(path, json=body)
        expect_error(response, 422, "title_required")
        assert response.json()["error"]["message"].strip()
    expect_error(app.post(path, json={"title": "T"}), 422, "invalid_request")
    expect_error(app.post(path, json={"title": "T", "text": 7}), 422, "invalid_request")
    assert app.case_docs(case["id"]) == []


def test_documents_stay_in_their_case(app):
    a, b = app.case(), app.case()
    doc = app.doc(a["id"], "Only in A")
    assert [d["id"] for d in app.case_docs(a["id"])] == [doc["id"]]
    assert app.case_docs(b["id"]) == []


def test_unknown_ids_are_not_found(app):
    expect_error(app.get("/api/cases/nope-404"), 404, "not_found")
    expect_error(app.get("/api/documents/nope-404"), 404, "not_found")
    expect_error(
        app.post("/api/cases/nope-404/documents", json={"title": "t", "text": "x"}),
        404,
        "not_found",
    )


def test_pages_show_cases_and_documents(app):
    case = app.case(name=uid("Page case "))
    doc = app.doc(case["id"], "Contract <b>draft</b> & notes", "Clause 7: pay on time")
    home = app.get("/")
    assert home.status_code == 200 and html.escape(case["name"]) in home.text
    assert f"/cases/{case['id']}" in home.text
    page = app.get(f"/cases/{case['id']}")
    assert page.status_code == 200 and f"/documents/{doc['id']}" in page.text
    assert "<b>draft</b>" not in page.text and "&lt;b&gt;draft&lt;/b&gt;" in page.text
    shown = app.get(f"/documents/{doc['id']}")
    assert shown.status_code == 200 and "Clause 7: pay on time" in shown.text
    assert app.get("/documents/nope-404").status_code == 404
    assert app.get("/cases/nope-404").status_code == 404


def test_everything_survives_a_restart(fresh_app):
    app = fresh_app
    a, b = app.case(name="Alpha"), app.case(name="Beta")
    docs = {
        app.doc(a["id"], "A1", "first")["id"]: "first",
        app.doc(a["id"], "A2", "second\nline")["id"]: "second\nline",
        app.doc(b["id"], "B1", "ø")["id"]: "ø",
    }
    app.restart()
    names = {c["id"]: c["name"] for c in ok(app.get("/api/cases"))["cases"]}
    assert names[a["id"]] == "Alpha" and names[b["id"]] == "Beta"
    for doc_id, text in docs.items():
        assert app.document(doc_id)["text"] == text
    assert [d["title"] for d in app.case_docs(a["id"])] == ["A1", "A2"]
    assert [d["title"] for d in app.case_docs(b["id"])] == ["B1"]
