"""Request 1: persistence across restarts, search, closing and reopening tickets."""

import uuid

from conftest import expect_error, shows


def ids(c, **params):
    r = c.get("/api/tickets", params=params)
    assert r.status_code == 200, r.text
    return [t["id"] for t in r.json()["tickets"]]


def test_restart_keeps_tickets_drafts_and_status(fresh_app):
    c = fresh_app.c
    a, b, d = c.tickets(3)
    c.ok("PUT", f"/api/tickets/{a['id']}/draft", json={"text": "Utkast — æøå"})
    c.ok("POST", f"/api/tickets/{b['id']}/close")
    fresh_app.restart()
    c = fresh_app.c
    assert c.ticket(a["id"])["draft"]["text"] == "Utkast — æøå"
    assert c.ticket(b["id"])["status"] == "closed"
    assert ids(c, status="all") == [a["id"], b["id"], d["id"]]
    assert c.ticket(d["id"])["body"] == d["body"]


def test_search_matches_subject_ignoring_case(c):
    marker = uuid.uuid4().hex[:6]
    a, b = c.tickets(2, subject=f"Damaged Kettle {marker}")
    (other,) = c.tickets(1)
    assert ids(c, q=f"damaged KETTLE {marker}") == [a["id"], b["id"]]
    assert other["id"] not in ids(c, q=marker)


def test_search_matches_customer_email(c):
    marker = uuid.uuid4().hex[:6]
    (a,) = c.tickets(1, customer_email=f"Kari.{marker}@Example.no")
    (b,) = c.tickets(1)
    assert ids(c, q=f"kari.{marker}@EXAMPLE") == [a["id"]]
    assert b["id"] not in ids(c, q=f"kari.{marker}")


def test_empty_search_lists_everything_open(c):
    c.tickets(2)
    everything = ids(c)
    assert ids(c, q="") == everything
    assert ids(c, q="no-ticket-matches-this-" + uuid.uuid4().hex) == []


def test_closing_and_reopening(c):
    a, b = c.tickets(2)
    r = c.post(f"/api/tickets/{a['id']}/close")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "closed" and r.json()["id"] == a["id"]
    assert c.ok("POST", f"/api/tickets/{a['id']}/close")["status"] == "closed"
    assert a["id"] not in ids(c) and b["id"] in ids(c)
    assert a["id"] in ids(c, status="closed") and b["id"] not in ids(c, status="closed")
    assert a["id"] in ids(c, status="all") and b["id"] in ids(c, status="all")
    assert c.ok("POST", f"/api/tickets/{a['id']}/reopen")["status"] == "open"
    assert c.ok("POST", f"/api/tickets/{a['id']}/reopen")["status"] == "open"
    assert a["id"] in ids(c) and a["id"] not in ids(c, status="closed")


def test_reopened_ticket_keeps_its_place(c):
    rows = c.tickets(3)
    order = [r["id"] for r in rows]
    c.ok("POST", f"/api/tickets/{order[0]}/close")
    c.ok("POST", f"/api/tickets/{order[0]}/reopen")
    assert [i for i in ids(c) if i in order] == order


def test_closed_ticket_keeps_draft_and_page(c):
    (a,) = c.tickets(1)
    c.ok("PUT", f"/api/tickets/{a['id']}/draft", json={"text": "half-written reply"})
    c.ok("POST", f"/api/tickets/{a['id']}/close")
    ticket = c.ticket(a["id"])
    assert ticket["status"] == "closed" and ticket["draft"]["text"] == "half-written reply"
    page = c.page(f"/tickets/{a['id']}")
    assert shows(page, a["body"]) and shows(page, "half-written reply")


def test_search_combines_with_status(c):
    marker = uuid.uuid4().hex[:6]
    a, b = c.tickets(2, subject=f"Invoice {marker}")
    c.ok("POST", f"/api/tickets/{a['id']}/close")
    assert ids(c, q=marker) == [b["id"]]
    assert ids(c, q=marker, status="closed") == [a["id"]]
    assert ids(c, q=marker, status="all") == [a["id"], b["id"]]


def test_status_errors(c):
    expect_error(c.get("/api/tickets", params={"status": "archived"}), 422, "invalid_request")
    expect_error(c.post("/api/tickets/no-such-ticket/close"), 404, "not_found")
    expect_error(c.post("/api/tickets/no-such-ticket/reopen"), 404, "not_found")
