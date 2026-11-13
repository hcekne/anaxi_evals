"""Request 1: CSV upload with row-level outcomes and idempotent replay."""

from conftest import expect_error, ok

SAMPLE = (
    "external_id,title,text\n"
    'INV-001,Invoice 1,"Payment of 1,200 EUR received"\n'
    'INV-002,Brief,"Line one\nLine two"\n'
    "INV-003,Fødselsattest,Født i Tromsø\n"
)


def upload(app, case_id, text, status=200):
    data = text.encode("utf-8") if isinstance(text, str) else text
    response = app.post(
        f"/api/cases/{case_id}/csv", content=data, headers={"Content-Type": "text/csv"}
    )
    return ok(response, status) if status == 200 else response


def rows(result, key):
    return [(r["row"], r["external_id"]) for r in result[key]]


def test_sample_file_imports(app):
    case = app.case()
    result = upload(app, case["id"], SAMPLE)
    assert rows(result, "created") == [(1, "INV-001"), (2, "INV-002"), (3, "INV-003")]
    assert result["unchanged"] == [] and result["errors"] == []
    docs = {d["external_id"]: d for d in (app.document(r["document_id"]) for r in result["created"])}
    assert docs["INV-001"]["text"] == "Payment of 1,200 EUR received"
    assert docs["INV-002"]["text"] == "Line one\nLine two"
    assert docs["INV-003"]["title"] == "Fødselsattest" and docs["INV-003"]["text"] == "Født i Tromsø"
    assert all(d["source"] == "csv" and d["case_id"] == case["id"] for d in docs.values())
    listed = [d["id"] for d in app.case_docs(case["id"])]
    assert listed == [r["document_id"] for r in result["created"]]
    pasted = app.doc(case["id"], "Pasted", "x")
    assert pasted["source"] == "manual" and pasted["external_id"] is None


def test_bad_rows_are_reported_and_good_rows_kept(app):
    case = app.case()
    text = (
        "external_id,title,text\n"
        "A1,Good one,fine\n"  # 1
        "A2,Only two\n"  # 2
        " ,No id,x\n"  # 3
        "A4,  ,blank title\n"  # 4
        'A5,"Quoted, title","He said ""hi"""\n'  # 5
        "A6,Too,many,fields\n"  # 6
        'A7,Multi,"one\ntwo\nthree"\n'  # 7
        "A8,After multi,ok\n"  # 8
    )
    result = upload(app, case["id"], text)
    assert rows(result, "created") == [(1, "A1"), (5, "A5"), (7, "A7"), (8, "A8")]
    assert [(e["row"], e["external_id"], e["code"]) for e in result["errors"]] == [
        (2, "A2", "wrong_field_count"),
        (3, " ", "external_id_required"),
        (4, "A4", "title_required"),
        (6, "A6", "wrong_field_count"),
    ]
    assert all(e["message"] for e in result["errors"])
    created = {r["external_id"]: app.document(r["document_id"]) for r in result["created"]}
    assert created["A5"]["title"] == "Quoted, title" and created["A5"]["text"] == 'He said "hi"'
    assert created["A7"]["text"] == "one\ntwo\nthree"
    assert len(app.case_docs(case["id"])) == 4


def test_identical_upload_twice_creates_no_duplicates(app):
    case = app.case()
    first = upload(app, case["id"], SAMPLE)
    second = upload(app, case["id"], SAMPLE)
    assert second["created"] == [] and second["errors"] == []
    assert [(r["row"], r["external_id"], r["document_id"]) for r in second["unchanged"]] == [
        (r["row"], r["external_id"], r["document_id"]) for r in first["created"]
    ]
    assert len(app.case_docs(case["id"])) == 3


def test_conflicting_duplicates_are_rejected(app):
    case = app.case()
    first = upload(app, case["id"], "external_id,title,text\nX1,Title,original\n")
    doc_id = first["created"][0]["document_id"]
    again = upload(
        app,
        case["id"],
        "external_id,title,text\nX1,Title,changed\nX2,New,n\nX2,New,n\nX2,New,other\n",
    )
    assert [(e["row"], e["external_id"], e["code"]) for e in again["errors"]] == [
        (1, "X1", "conflicting_duplicate"),
        (4, "X2", "conflicting_duplicate"),
    ]
    assert rows(again, "created") == [(2, "X2")]
    assert rows(again, "unchanged") == [(3, "X2")]
    assert again["unchanged"][0]["document_id"] == again["created"][0]["document_id"]
    assert app.document(doc_id)["text"] == "original"
    assert len(app.case_docs(case["id"])) == 2


def test_external_ids_are_scoped_to_their_case(app):
    a, b = app.case(), app.case()
    in_a = upload(app, a["id"], "external_id,title,text\nS1,Same,one\n")
    in_b = upload(app, b["id"], "external_id,title,text\nS1,Same,two\n")
    assert rows(in_b, "created") == [(1, "S1")]
    assert in_a["created"][0]["document_id"] != in_b["created"][0]["document_id"]
    assert app.document(in_a["created"][0]["document_id"])["text"] == "one"


def test_whole_file_problems(app):
    case = app.case()
    for bad in (
        "id,title,text\nA,B,C\n",
        "external_id,title\nA,B\n",
        "external_id,title,text,extra\nA,B,C,D\n",
        b"external_id,title,text\nA,B,\xff\xfe\n",
    ):
        expect_error(upload(app, case["id"], bad, status=422), 422, "invalid_csv")
    assert app.case_docs(case["id"]) == []
    bom = "﻿external_id,title,text\r\nB1,With BOM,crlf line\r\n"
    result = upload(app, case["id"], bom)
    assert rows(result, "created") == [(1, "B1")]
    assert app.document(result["created"][0]["document_id"])["text"] == "crlf line"
    expect_error(upload(app, "nope-404", SAMPLE, status=404), 404, "not_found")
