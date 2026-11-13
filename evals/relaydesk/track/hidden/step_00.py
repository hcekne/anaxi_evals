"""Request 0: import a tickets CSV, inbox, ticket pages and per-ticket drafts."""

from conftest import App, csv_bytes, expect_error, shows, uid

ATTACHED = (
    "id,customer_email,subject,body\r\n"
    "T-1001,ola.nordmann@example.no,Where is my order?,\"Hi, I ordered a kettle last week and "
    "still have no tracking number. Can you help?\"\r\n"
    "T-1002,jalal.haddad@example.com,Refund for broken lamp,\"The lamp arrived cracked.\n"
    "I would like a refund, please.\"\r\n"
    "T-1003,søren.ærø@example.dk,Glemt passord,\"Jeg får ikke logget inn — kan dere hjelpe meg "
    "å nullstille passordet?\"\r\n"
).encode()


def ids(c, **params):
    return [t["id"] for t in c.ok("GET", "/api/tickets", params=params)["tickets"]]


def test_attached_file_imports_three_tickets(hub):
    app = App(hub)
    try:
        c = app.c
        r = c.post("/api/imports", content=ATTACHED, headers={"Content-Type": "text/csv"})
        assert r.status_code == 200, r.text
        assert r.json() == {"imported": ["T-1001", "T-1002", "T-1003"], "skipped": []}
        listed = c.ok("GET", "/api/tickets")["tickets"]
        assert [t["id"] for t in listed] == ["T-1001", "T-1002", "T-1003"]
        expected = {"id": "T-1003", "customer_email": "søren.ærø@example.dk",
                    "subject": "Glemt passord", "status": "open"}  # fmt: skip
        assert {k: listed[2].get(k) for k in expected} == expected
        lamp = c.ticket("T-1002")
        assert lamp["body"] == "The lamp arrived cracked.\nI would like a refund, please."
        assert lamp["subject"] == "Refund for broken lamp" and lamp["status"] == "open"
        assert lamp["draft"]["text"] == ""
    finally:
        app.close()


def test_listing_keeps_import_order(c):
    first = c.tickets(2)
    second = c.tickets(1)
    order = [r["id"] for r in first + second]
    listed = [i for i in ids(c) if i in order]
    assert listed == order


def test_opening_a_ticket_shows_its_own_text(c):
    rows = c.tickets(3)
    for row in rows:
        ticket = c.ticket(row["id"])
        assert {k: ticket[k] for k in ("id", "customer_email", "subject", "body")} == row


def test_drafts_belong_to_one_ticket(c):
    a, b = c.tickets(2)
    r = c.put(f"/api/tickets/{a['id']}/draft", json={"text": "Hei Ola — vi sjekker saken."})
    assert r.status_code == 200, r.text
    assert r.json()["draft"]["text"] == "Hei Ola — vi sjekker saken."
    assert r.json()["id"] == a["id"]
    assert c.ticket(a["id"])["draft"]["text"] == "Hei Ola — vi sjekker saken."
    assert c.ticket(b["id"])["draft"]["text"] == ""
    assert c.ok("PUT", f"/api/tickets/{a['id']}/draft", json={"text": ""})["draft"]["text"] == ""


def test_draft_and_ticket_errors(c):
    (a,) = c.tickets(1)
    expect_error(c.put(f"/api/tickets/{a['id']}/draft", json={}), 422, "invalid_request")
    expect_error(c.put(f"/api/tickets/{a['id']}/draft", json={"text": 5}), 422, "invalid_request")
    expect_error(c.get("/api/tickets/no-such-ticket"), 404, "not_found")
    expect_error(c.put("/api/tickets/no-such-ticket/draft", json={"text": "x"}), 404, "not_found")


def test_reimport_keeps_existing_ticket_and_draft(c):
    (a,) = c.tickets(1)
    c.ok("PUT", f"/api/tickets/{a['id']}/draft", json={"text": "my words"})
    fresh = uid()
    changed = dict(a, subject="Changed subject")
    rows = [changed, {"id": fresh, "customer_email": "x@example.com", "subject": "s", "body": "b"}]
    r = c.import_rows(rows)
    assert r.status_code == 200, r.text
    assert r.json() == {"imported": [fresh], "skipped": [a["id"]]}
    kept = c.ticket(a["id"])
    assert kept["subject"] == a["subject"] and kept["draft"]["text"] == "my words"


def test_unreadable_files_keep_the_tickets_already_there(c):
    (a,) = c.tickets(1)
    c.ok("PUT", f"/api/tickets/{a['id']}/draft", json={"text": "keep me"})
    before = ids(c)
    good = {"id": uid(), "customer_email": "g@example.com", "subject": "ok", "body": "ok"}
    bad_files = {
        "latin-1": "id,customer_email,subject,body\nX-1,a@b.no,Bl\xe5,b\n".encode("latin-1"),
        "empty": b"",
        "header": b"id,email,subject,body\r\n" + csv_bytes([good]).split(b"\r\n", 1)[1],
        "fields": csv_bytes([good]) + b"Y-2,a@b.no,only three\r\n",
        "empty field": csv_bytes([good]) + b"Y-3,a@b.no,,body\r\n",
        "bad id": csv_bytes([good]) + b"bad id!,a@b.no,s,b\r\n",
        "repeat": csv_bytes([good, good]),
        "overwrite": csv_bytes([dict(a, subject="hijack")]) + b"Y-4,a@b.no\r\n",
    }
    for name, data in bad_files.items():
        r = c.post("/api/imports", content=data, headers={"Content-Type": "text/csv"})
        expect_error(r, 422, "invalid_csv")
        assert r.json()["error"]["message"], name
        assert ids(c) == before, name
    assert c.ticket(a["id"])["draft"]["text"] == "keep me"
    assert c.ticket(a["id"])["subject"] == a["subject"]


def test_quotes_byte_order_mark_and_blank_lines(c):
    ident = uid()
    data = (
        "﻿id,customer_email,subject,body\r\n"
        f'{ident},"a.b@example.com","Commas, ""quotes"" and more","Line one\r\nLine two, ok"\r\n'
        "\r\n\r\n"
    ).encode()
    r = c.post("/api/imports", content=data, headers={"Content-Type": "text/csv"})
    assert r.status_code == 200, r.text
    assert r.json()["imported"] == [ident]
    ticket = c.ticket(ident)
    assert ticket["subject"] == 'Commas, "quotes" and more'
    assert ticket["body"].replace("\r\n", "\n") == "Line one\nLine two, ok"


def test_pages_show_inbox_and_ticket(c):
    a, b = c.tickets(2, body="Ærlig talt: pakken kom aldri fram.")
    c.ok("PUT", f"/api/tickets/{a['id']}/draft", json={"text": "Draft for the first one"})
    inbox = c.page("/")
    for row in (a, b):
        assert shows(inbox, row["subject"]) and shows(inbox, row["customer_email"])
    page = c.page(f"/tickets/{a['id']}")
    assert shows(page, a["subject"]) and shows(page, a["body"])
    assert shows(page, "Draft for the first one")
    assert "Draft for the first one" not in c.page(f"/tickets/{b['id']}")
    assert c.get("/tickets/no-such-ticket").status_code == 404


def test_nothing_is_sent_anywhere(c, hub):
    (a,) = c.tickets(1)
    c.ok("PUT", f"/api/tickets/{a['id']}/draft", json={"text": "reply"})
    c.page(f"/tickets/{a['id']}")
    assert hub.calls == []
