"""Request 9: monthly approval counts in UTC with an inclusive start and exclusive end."""

from conftest import OUTSIDER, expect_error, ok, uid


def report(app, user, **params):
    params = {k: v for k, v in params.items() if v is not None}
    return ok(app.get("/api/reports/approvals", params=params, user=user))


def approve_at(app, doc_id, when, user, decision="approved"):
    app.set_clock(when)
    return app.review(doc_id, decision, user=user)


def seeded(app):
    """A workspace with approvals around month boundaries; returns (owner, ws, docs)."""
    owner = uid("rep")
    ws = app.workspace(owner=owner, members={"v" + owner: "viewer"})
    case = app.case(ws=ws, user=owner)
    a = app.doc(case["id"], "A", "a", user=owner)
    b = app.doc(case["id"], "B", "b", user=owner)
    approve_at(app, a["id"], "2026-01-31T23:59:59Z", owner)
    approve_at(app, a["id"], "2026-02-01T00:00:00Z", owner, "changes_requested")
    approve_at(app, a["id"], "2026-02-01T00:00:00Z", owner)  # re-approval counts again
    approve_at(app, b["id"], "2026-02-28T12:00:00Z", owner)
    approve_at(app, b["id"], "2026-03-31T23:59:59Z", owner)
    approve_at(app, b["id"], "2026-04-01T00:00:00Z", owner)
    return owner, ws, (a, b)


def only(result, ws):
    rows = [w for w in result["workspaces"] if w["workspace_id"] == ws]
    assert len(rows) == 1, result
    return rows[0]


def test_counts_decisions_per_utc_month(app):
    owner, ws, _ = seeded(app)
    result = report(app, owner, **{"from": "2026-01-01", "to": "2026-04-01"})
    assert (result["from"], result["to"]) == ("2026-01-01", "2026-04-01")
    row = only(result, ws)
    assert row["months"] == [
        {"month": "2026-01", "approvals": 1},
        {"month": "2026-02", "approvals": 2},
        {"month": "2026-03", "approvals": 1},
    ]
    assert row["total"] == 4 and result["total"] == 4
    assert row["name"]


def test_start_included_end_excluded(app):
    owner, ws, _ = seeded(app)
    feb = only(report(app, owner, **{"from": "2026-02-01", "to": "2026-03-01"}), ws)
    assert feb["months"] == [{"month": "2026-02", "approvals": 2}] and feb["total"] == 2
    upto = only(report(app, owner, **{"from": "2026-02-01", "to": "2026-03-31"}), ws)
    assert upto["total"] == 2
    everything = report(app, owner)
    assert (everything["from"], everything["to"]) == (None, None)
    assert only(everything, ws)["total"] == 5
    after = only(report(app, owner, **{"from": "2026-04-01"}), ws)
    assert after["months"] == [{"month": "2026-04", "approvals": 1}]
    same = only(report(app, owner, **{"from": "2026-02-01", "to": "2026-02-01"}), ws)
    assert (same["total"], same["months"]) == (0, [])


def test_bad_dates(app):
    owner, ws, _ = seeded(app)
    for params in ({"from": "2026-13-01"}, {"to": "2026-02-30"}, {"from": "20260101"},
                   {"from": "2026-03-01", "to": "2026-02-01"}, {"to": "2026-02-01T00:00:00Z"}):  # fmt: skip
        response = app.get("/api/reports/approvals", params=params, user=owner)
        expect_error(response, 422, "invalid_request")


def test_later_changes_never_change_old_totals(app):
    owner, ws, (a, b) = seeded(app)
    before = report(app, owner, **{"from": "2026-01-01", "to": "2026-05-01"})
    app.set_clock("2026-06-01T00:00:00Z")
    ok(app.patch(f"/api/documents/{a['id']}", json={"title": "A2", "text": "edited"}, user=owner))
    ok(app.put(f"/api/documents/{b['id']}/responsible", json={"user": "v" + owner}, user=owner))
    app.review(a["id"], "changes_requested", user=owner)
    assert report(app, owner, **{"from": "2026-01-01", "to": "2026-05-01"}) == before


def test_workspaces_listed_and_permissions_respected(app):
    owner, ws, _ = seeded(app)
    empty = app.workspace(owner=owner)
    result = report(app, owner, **{"from": "2026-01-01", "to": "2026-04-01"})
    assert [w["workspace_id"] for w in result["workspaces"]] == [ws, empty]
    assert only(result, empty) == {"workspace_id": empty, "name": only(result, empty)["name"],
                                   "total": 0, "months": []}  # fmt: skip
    assert result["total"] == 4
    viewer = report(app, "v" + owner, **{"from": "2026-01-01", "to": "2026-04-01"})
    assert [w["workspace_id"] for w in viewer["workspaces"]] == [ws] and viewer["total"] == 4
    filtered = report(app, owner, workspace_id=empty)
    assert [w["workspace_id"] for w in filtered["workspaces"]] == [empty]
    assert filtered["total"] == 0
    expect_error(app.get("/api/reports/approvals", params={"workspace_id": ws}, user=OUTSIDER),
                 404, "not_found")  # fmt: skip
    expect_error(app.get("/api/reports/approvals", params={"workspace_id": "nope-404"},
                         user=owner), 404, "not_found")  # fmt: skip
    assert ws not in str(report(app, OUTSIDER))


def test_report_page(app):
    owner, ws, _ = seeded(app)
    page = app.get("/reports", params={"from": "2026-01-01", "to": "2026-04-01"}, user=owner)
    assert page.status_code == 200
    assert "2026-02" in page.text
    assert "The start date is included; the report stops just before the end date." in page.text
