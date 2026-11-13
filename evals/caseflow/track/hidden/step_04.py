"""Request 4: text PDFs with explicit unsupported/corrupt outcomes."""

import zlib

import pdfgen
from conftest import expect_error, ok

LEASE = "Lease agreement\nTenant: Ana Lima\nRent: 1 200 EUR (monthly)\nSigned in Tromsø, café"
NOTES = "Meeting notes\nBudget  approved\nNext review: 2026-06-01"


def upload(app, case_id, files, status=200):
    body = {"files": [{"name": n, "content_base64": pdfgen.b64(d) if isinstance(d, bytes) else d}
                      for n, d in files]}  # fmt: skip
    response = app.post(f"/api/cases/{case_id}/pdfs", json=body)
    return ok(response)["results"] if status == 200 else response


def text_of(app, result):
    assert result["status"] == "imported", result
    return app.document(result["document_id"])["text"]


def test_sample_pack(app):
    case = app.case()
    pack = pdfgen.sample_pack()
    results = upload(app, case["id"], list(pack.items()))
    assert [(r["name"], r["status"]) for r in results] == [
        ("lease.pdf", "imported"),
        ("notes.pdf", "imported"),
        ("scan.pdf", "unsupported"),
        ("broken.pdf", "corrupt"),
    ]
    lease = app.document(results[0]["document_id"])
    assert {"title": "lease", "text": LEASE, "source": "pdf", "external_id": None,
            "case_id": case["id"]}.items() <= lease.items()  # fmt: skip
    assert text_of(app, results[1]) == NOTES
    assert results[2]["document_id"] is None and results[2]["message"]
    assert results[3]["document_id"] is None and results[3]["message"]
    assert [d["id"] for d in app.case_docs(case["id"])] == [
        results[0]["document_id"],
        results[1]["document_id"],
    ]


def test_text_operators_and_strings(app):
    case = app.case()
    lines = ["Første (linje)", "Back\\slash", "  padded  "]
    files = [
        ("hex.pdf", pdfgen.build([lines], style="hex")),
        ("quote.pdf", pdfgen.build([lines], style="quote")),
        ("tjarray.pdf", pdfgen.build([lines], style="TJ", compress=True)),
    ]
    expected = "Første (linje)\nBack\\slash\npadded"
    for result in upload(app, case["id"], files):
        assert text_of(app, result) == expected, result["name"]
    raw = (
        b"BT /F1 12 Tf 72 720 Td (Balanced (inner) parens) Tj T* (Tab\\there) Tj\n"
        b"0 -14 TD (Octal \\101\\102C and \\3706) Tj 0 -14 Td (Joined \\\n"
        b"line) Tj ( and more) Tj ET\n"
        b"BT <48 65 6C 6C 6F 2> Tj ET\n"
    )
    result = upload(app, case["id"], [("raw.pdf", pdfgen.build(None, streams=[[raw]]))])[0]
    assert text_of(app, result) == (
        "Balanced (inner) parens\nTab\there\nOctal ABC and ø6\nJoined line and more\nHello"
    )


def test_page_order_follows_the_page_tree(app):
    case = app.case()
    pages = [["Page one"], ["Page two"], ["Page three"]]
    files = [
        ("shuffled.pdf", pdfgen.build(pages, shuffle=True)),
        ("nested.pdf", pdfgen.build(pages, nested=True, shuffle=True, compress=True)),
        ("noxref.pdf", pdfgen.build(pages, xref=False)),
        ("split.pdf", pdfgen.build(None, streams=[[b"BT (Part) Tj ", b"( one) Tj ET"],
                                                  [b"BT (Part two) Tj ET"]])),  # fmt: skip
    ]
    results = upload(app, case["id"], files)
    for result in results[:3]:
        assert text_of(app, result) == "Page one\nPage two\nPage three", result["name"]
    assert text_of(app, results[3]) == "Part one\nPart two"


def test_unreadable_files_are_reported_and_others_continue(app):
    case = app.case()
    good = pdfgen.build([["Still imported"]])
    blank = pdfgen.build(None, streams=[[b"BT (   ) Tj ( ) ' ET"]])
    files = [
        ("garbage.pdf", b"this is not a pdf at all"),
        ("truncated.pdf", good[:-20]),
        ("badflate.pdf", pdfgen.build([["x"]], filter_name="FlateDecode")),
        ("notbase64.pdf", "%%% not base64 ***"),
        ("nocatalog.pdf", pdfgen.build([["x"]], catalog=False)),
        ("ok.PDF", good),
        ("image.pdf", pdfgen.build([["x"]], image_only=True, compress=True)),
        ("blank.pdf", blank),
        ("lzw.pdf", pdfgen.build([["x"]], filter_name="LZWDecode")),
        ("locked.pdf", pdfgen.build([["x"]], encrypt=True)),
    ]
    results = upload(app, case["id"], files)
    assert [(r["name"], r["status"]) for r in results] == [
        ("garbage.pdf", "corrupt"),
        ("truncated.pdf", "corrupt"),
        ("badflate.pdf", "corrupt"),
        ("notbase64.pdf", "corrupt"),
        ("nocatalog.pdf", "corrupt"),
        ("ok.PDF", "imported"),
        ("image.pdf", "unsupported"),
        ("blank.pdf", "unsupported"),
        ("lzw.pdf", "unsupported"),
        ("locked.pdf", "unsupported"),
    ]
    imported = app.document(results[5]["document_id"])
    assert (imported["title"], imported["text"]) == ("ok", "Still imported")
    assert [d["id"] for d in app.case_docs(case["id"])] == [results[5]["document_id"]]
    assert all(r["message"] for r in results if r["status"] != "imported")


def test_same_file_twice_makes_two_documents(app):
    case = app.case()
    data = pdfgen.build([["Twice"]])
    first = upload(app, case["id"], [("twice.pdf", data)])[0]
    second = upload(app, case["id"], [("twice.pdf", data)])[0]
    assert first["document_id"] != second["document_id"]
    assert len(app.case_docs(case["id"])) == 2


def test_bad_requests(app):
    case = app.case()
    path = f"/api/cases/{case['id']}/pdfs"
    good = {"name": "a.pdf", "content_base64": pdfgen.b64(pdfgen.build([["a"]]))}
    for body in (
        {"files": []},
        {"files": "a.pdf"},
        {},
        {"files": [{"content_base64": good["content_base64"]}]},
        {"files": [{"name": "", "content_base64": good["content_base64"]}]},
        {"files": [{"name": "a.pdf", "content_base64": 5}]},
        {"files": [good] * 21},
    ):
        expect_error(app.post(path, json=body), 422, "invalid_request")
    assert app.case_docs(case["id"]) == []
    expect_error(app.post("/api/cases/nope-404/pdfs", json={"files": [good]}), 404, "not_found")
    assert zlib  # stdlib only
