"""Request 6: identities, workspaces, the role matrix and cross-workspace isolation."""

import pdfgen
from conftest import (
    EDITOR,
    OUTSIDER,
    OWNER,
    SOURCE,
    VIEWER,
    credentials,
    expect_error,
    import_from_source,
    ok,
    uid,
)


def test_identity_is_required(app):
    case = app.case()
    doc = app.doc(case["id"], "Private", "x")
    for path in ("/api/cases", "/api/workspaces", f"/api/documents/{doc['id']}",
                 f"/api/cases/{case['id']}"):  # fmt: skip
        expect_error(app.get(path, user=None), 401, "unauthenticated")
        expect_error(app.get(path, user="Not A User!"), 401, "unauthenticated")
    expect_error(app.post("/api/workspaces", user=None, json={"name": "x"}), 401, "unauthenticated")
    assert app.get("/", user=None).status_code == 401
    assert app.get(f"/documents/{doc['id']}", user=None).status_code == 401
    assert app.http.get("/api/health").status_code == 200
    assert app.http.get("/api/clock").status_code == 200


def test_workspaces_and_members(app):
    created = ok(app.post("/api/workspaces", user="nora", json={"name": "Team N"}), 201)
    assert {"name": "Team N", "role": "owner"}.items() <= created.items()
    ws = created["id"]
    expect_error(app.post("/api/workspaces", user="nora", json={"name": "  "}), 422, "name_required")
    mine = ok(app.get("/api/workspaces", user="nora"))["workspaces"]
    assert [w["id"] for w in mine] == [ws] and mine[0]["role"] == "owner"
    members = f"/api/workspaces/{ws}/members"
    assert ok(app.put(f"{members}/ben", user="nora", json={"role": "viewer"})) == {
        "user": "ben",
        "role": "viewer",
    }
    ok(app.put(f"{members}/amy", user="nora", json={"role": "editor"}))
    expect_error(app.put(f"{members}/cy", user="nora", json={"role": "admin"}), 422, "invalid_request")
    listed = ok(app.get(members, user="ben"))["members"]
    assert listed == [
        {"user": "amy", "role": "editor"},
        {"user": "ben", "role": "viewer"},
        {"user": "nora", "role": "owner"},
    ]
    assert ok(app.get("/api/workspaces", user="ben"))["workspaces"][0]["role"] == "viewer"
    expect_error(app.put(f"{members}/nora", user="nora", json={"role": "editor"}), 409, "last_owner")
    expect_error(app.delete(f"{members}/nora", user="nora"), 409, "last_owner")
    ok(app.put(f"{members}/amy", user="nora", json={"role": "owner"}))
    assert ok(app.put(f"{members}/nora", user="amy", json={"role": "viewer"}))["role"] == "viewer"
    assert app.delete(f"{members}/ben", user="amy").status_code == 204
    expect_error(app.delete(f"{members}/ben", user="amy"), 404, "not_found")
    expect_error(app.get(members, user="ben"), 404, "not_found")
    assert ok(app.get("/api/workspaces", user="ben"))["workspaces"] == []


def setup_workspace(app, hub):
    ws = app.workspace(members={EDITOR: "editor", VIEWER: "viewer"})
    case = app.case(ws=ws)
    doc = app.doc(case["id"], "Contract", "Signed text")
    conn, job, key = import_from_source(app, hub, case["id"], [("E1", "Imported", "t", 1)])
    return ws, case, doc, conn, job, key


def test_role_matrix(app, hub):
    ws, case, doc, conn, job, key = setup_workspace(app, hub)
    cid = case["id"]
    pdf = {"files": [{"name": "a.pdf", "content_base64": pdfgen.b64(pdfgen.build([["a"]]))}]}
    csv = "external_id,title,text\nR1,Row,text\n".encode()
    for user in (OWNER, EDITOR, VIEWER):
        for path in (f"/api/cases/{cid}", f"/api/documents/{doc['id']}",
                     f"/api/cases/{cid}/search?q=signed", f"/api/cases/{cid}/connections",
                     f"/api/connections/{conn['id']}", f"/api/jobs/{job['id']}",
                     f"/api/cases/{cid}/jobs", f"/api/workspaces/{ws}/members",
                     f"/cases/{cid}", f"/documents/{doc['id']}"):  # fmt: skip
            assert app.get(path, user=user).status_code == 200, (user, path)
        assert cid in [c["id"] for c in ok(app.get("/api/cases", user=user))["cases"]]
    writes = {
        "case": lambda u: app.post("/api/cases", user=u, json={"name": "N", "workspace_id": ws}),
        "doc": lambda u: app.post(f"/api/cases/{cid}/documents", user=u,
                                  json={"title": "T", "text": "x"}),  # fmt: skip
        "csv": lambda u: app.post(f"/api/cases/{cid}/csv", user=u, content=csv),
        "pdf": lambda u: app.post(f"/api/cases/{cid}/pdfs", user=u, json=pdf),
        "edit": lambda u: app.patch(f"/api/documents/{doc['id']}", user=u, json={"text": uid()}),
        "import": lambda u: app.post(f"/api/connections/{conn['id']}/imports", user=u),
    }
    owner_only = {
        "connect": lambda u: app.post(f"/api/cases/{cid}/connections", user=u,
                                      json={"source": SOURCE, "credentials": credentials(key)}),
        "credentials": lambda u: app.put(f"/api/connections/{conn['id']}/credentials", user=u,
                                         json=credentials(key)),
        "member": lambda u: app.put(f"/api/workspaces/{ws}/members/newbie", user=u,
                                    json={"role": "viewer"}),
        "remove": lambda u: app.delete(f"/api/workspaces/{ws}/members/newbie", user=u),
    }  # fmt: skip
    for name, action in {**writes, **owner_only}.items():
        expect_error(action(VIEWER), 403, "forbidden")
    for name, action in owner_only.items():
        expect_error(action(EDITOR), 403, "forbidden")
    for name, action in writes.items():
        response = action(EDITOR)
        assert response.status_code in (200, 201, 202), (name, response.text)
        if name == "import":
            app.wait_job(response.json()["id"], ("completed", "failed"))
    for name, action in owner_only.items():
        assert action(OWNER).status_code in (200, 201, 204), name
    started = app.start_import(conn["id"], user=EDITOR)
    expect_error(app.post(f"/api/jobs/{started['id']}/cancel", user=VIEWER), 403, "forbidden")
    response = app.post(f"/api/jobs/{started['id']}/cancel", user=EDITOR)
    assert response.status_code in (202, 409), response.text


def test_outsiders_see_nothing(app, hub):
    ws, case, doc, conn, job, key = setup_workspace(app, hub)
    cid = case["id"]
    own_ws = app.workspace(owner=OUTSIDER)
    reads = [f"/api/cases/{cid}", f"/api/documents/{doc['id']}", f"/api/cases/{cid}/search?q=x",
             f"/api/cases/{cid}/connections", f"/api/connections/{conn['id']}",
             f"/api/jobs/{job['id']}", f"/api/cases/{cid}/jobs", f"/api/workspaces/{ws}/members",
             f"/api/cases?workspace_id={ws}"]  # fmt: skip
    for path in reads:
        expect_error(app.get(path, user=OUTSIDER), 404, "not_found")
    for path in (f"/cases/{cid}", f"/documents/{doc['id']}", f"/cases/{cid}/search?q=x"):
        assert app.get(path, user=OUTSIDER).status_code == 404, path
    for response in (
        app.post("/api/cases", user=OUTSIDER, json={"name": "Sneaky", "workspace_id": ws}),
        app.post(f"/api/cases/{cid}/documents", user=OUTSIDER, json={"title": "t", "text": "x"}),
        app.post(f"/api/cases/{cid}/csv", user=OUTSIDER, content=b"external_id,title,text\n"),
        app.patch(f"/api/documents/{doc['id']}", user=OUTSIDER, json={"title": "Mine now"}),
        app.post(f"/api/connections/{conn['id']}/imports", user=OUTSIDER),
        app.put(f"/api/connections/{conn['id']}/credentials", user=OUTSIDER, json=credentials("k")),
        app.post(f"/api/cases/{cid}/connections", user=OUTSIDER,
                 json={"source": SOURCE, "credentials": credentials("k")}),
        app.post(f"/api/jobs/{job['id']}/cancel", user=OUTSIDER),
        app.put(f"/api/workspaces/{ws}/members/{OUTSIDER}", user=OUTSIDER, json={"role": "owner"}),
    ):  # fmt: skip
        expect_error(response, 404, "not_found")
    assert cid not in [c["id"] for c in ok(app.get("/api/cases", user=OUTSIDER))["cases"]]
    assert app.document(doc["id"])["title"] == "Contract"
    assert ok(app.get(f"/api/workspaces/{own_ws}/members", user=OUTSIDER))["members"] == [
        {"user": OUTSIDER, "role": "owner"}
    ]


def test_case_lists_follow_membership(app):
    a = app.workspace(owner="kim")
    b = app.workspace(owner="lee", members={"kim": "viewer"})
    in_a = app.case(ws=a, user="kim")
    in_b = app.case(ws=b, user="lee")
    assert in_a["workspace_id"] == a and in_b["workspace_id"] == b
    kim = [c["id"] for c in ok(app.get("/api/cases", user="kim"))["cases"]]
    assert kim == [in_a["id"], in_b["id"]]
    only_b = ok(app.get("/api/cases", params={"workspace_id": b}, user="kim"))["cases"]
    assert [c["id"] for c in only_b] == [in_b["id"]]
    assert [c["id"] for c in ok(app.get("/api/cases", user="lee"))["cases"]] == [in_b["id"]]
    detail = ok(app.get(f"/api/cases/{in_b['id']}", user="kim"))
    assert detail["workspace_id"] == b


def test_edits_count_versions(app):
    case = app.case()
    doc = app.doc(case["id"], "Draft", "one")
    assert doc["version"] == 1
    path = f"/api/documents/{doc['id']}"
    edited = ok(app.patch(path, json={"title": "Final"}))
    assert (edited["title"], edited["text"], edited["version"]) == ("Final", "one", 2)
    assert ok(app.patch(path, json={"title": "Final", "text": "one"}))["version"] == 2
    assert ok(app.patch(path, json={"text": "two"}))["version"] == 3
    expect_error(app.patch(path, json={"title": " "}), 422, "title_required")
    expect_error(app.patch(path, json={"text": 5}), 422, "invalid_request")
    expect_error(app.patch("/api/documents/nope-404", json={"text": "x"}), 404, "not_found")
    assert app.document(doc["id"])["version"] == 3


def test_source_revisions_count_versions(app, hub):
    case = app.case()
    conn, _, key = import_from_source(app, hub, case["id"], [("V1", "Old", "old", 1)])
    import_from_source(app, hub, case["id"], [("V1", "Old", "old", 1)], key=key, connection=conn)
    doc = next(iter(app.case_docs(case["id"])))
    assert app.document(doc["id"])["version"] == 1
    import_from_source(app, hub, case["id"], [("V1", "New", "new", 2)], key=key, connection=conn)
    assert (app.document(doc["id"])["version"], app.document(doc["id"])["text"]) == (2, "new")
