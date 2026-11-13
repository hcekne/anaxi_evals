"""Request 7: order lookups on request only, formatted dollars, optional inclusion in replies.
From request 15 orders carry `money` instead of `total_cents` and come from the v2 API."""

from hub import ORDERS

from conftest import MONEY, SECOND, expect_error, provider_text, reply_calls, shows

TOTALS = {"A-1001": "$45.99", "A-1002": "$1,200.00", "A-1003": "$0.05", "B-2001": "$9.99"}


def expected(order_id: str) -> dict:
    _, status, minor, currency = ORDERS[order_id]
    out = {"order_id": order_id, "status": status, "total": TOTALS[order_id]}
    if MONEY:
        out["money"] = {"minor_units": minor, "currency": currency}
    else:
        out["total_cents"] = minor
    return out


def order_view(order: dict) -> dict:
    keys = ("order_id", "status", "total", "money" if MONEY else "total_cents")
    return {k: order.get(k) for k in keys}


def lookup(c, ident, order_id, status=201):
    return c.ok("POST", f"/api/tickets/{ident}/orders", status=status, json={"order_id": order_id})


def test_not_connected(south, hub):
    (b,) = south.tickets(1)
    r = south.post(f"/api/tickets/{b['id']}/orders", json={"order_id": "B-2001"})
    expect_error(r, 409, "not_configured")
    assert hub.calls_to("orders") == []


def test_lookup_shows_dollars(c, hub):
    c.connect("orders")
    (a,) = c.tickets(1)
    for order_id in ("A-1001", "A-1002", "A-1003"):
        assert order_view(lookup(c, a["id"], order_id)) == expected(order_id)
    calls = hub.calls_to("orders")
    assert len(calls) == 3
    if MONEY:  # request 15 retired this API version; later versions are fine
        assert calls[0]["path"].startswith("/orders/v") and calls[0]["path"].endswith("/A-1001")
    else:
        assert calls[0]["path"] == "/orders/orders/A-1001"
    assert calls[0]["headers"]["authorization"] == "Bearer orders-north-token"


def test_ticket_keeps_its_orders(c, hub):
    c.connect("orders")
    a, b = c.tickets(2)
    lookup(c, a["id"], "A-1002")
    lookup(c, a["id"], "A-1001")
    lookup(c, a["id"], "A-1002")
    orders = c.ticket(a["id"])["orders"]
    assert [order_view(o) for o in orders] == [expected("A-1002"), expected("A-1001")]
    assert len(hub.calls_to("orders")) == 3
    assert c.ticket(b["id"])["orders"] == []


def test_unknown_orders(c, hub):
    c.connect("orders")
    (a,) = c.tickets(1)
    for order_id in ("Z-0000", "B-2001"):
        r = c.post(f"/api/tickets/{a['id']}/orders", json={"order_id": order_id})
        expect_error(r, 404, "order_not_found")
    assert c.ticket(a["id"])["orders"] == []
    expect_error(c.post(f"/api/tickets/{a['id']}/orders", json={"order_id": ""}), 422,
                 "invalid_request")  # fmt: skip
    expect_error(c.post("/api/tickets/no-such/orders", json={"order_id": "A-1001"}), 404,
                 "not_found")  # fmt: skip


def test_service_failure_is_an_upstream_error(c):
    (a,) = c.tickets(1)
    c.ok("PUT", "/api/connections/orders", json={"token": "expired-token"})
    try:
        r = c.post(f"/api/tickets/{a['id']}/orders", json={"order_id": "A-1001"})
        expect_error(r, 502, "upstream_error")
        assert c.ticket(a["id"])["orders"] == []
    finally:
        c.connect("orders")


def test_chosen_orders_are_sent_and_others_are_not(c, hub):
    c.connect("orders", "pollen")
    (a,) = c.tickets(1)
    lookup(c, a["id"], "A-1001")
    lookup(c, a["id"], "A-1002")
    before = len(hub.calls_to("orders"))
    s = c.suggest(a["id"], provider="pollen", order_ids=["A-1002"])
    assert s["status"] == "completed"
    sent = provider_text(reply_calls(hub, "pollen")[0])
    assert "A-1002" in sent and "processing" in sent and "$1,200.00" in sent
    assert "A-1001" not in sent and "$45.99" not in sent
    c.suggest(a["id"], provider="pollen")
    assert "A-1002" not in provider_text(reply_calls(hub, "pollen")[1])
    assert len(hub.calls_to("orders")) == before


def test_other_services_get_the_order_too(c, hub):
    c.connect("orders", SECOND)
    (a,) = c.tickets(1)
    lookup(c, a["id"], "A-1003")
    c.suggest(a["id"], provider=SECOND, order_ids=["A-1003"])
    sent = provider_text(reply_calls(hub, SECOND)[0])
    assert "A-1003" in sent and "delivered" in sent and "$0.05" in sent


def test_only_looked_up_orders_can_be_chosen(c, hub):
    c.connect("orders", "pollen")
    a, b = c.tickets(2)
    lookup(c, b["id"], "A-1001")
    for ids in (["A-1001"], ["A-1003"]):
        expect_error(c.ask(a["id"], provider="pollen", order_ids=ids), 422, "unknown_order")
    assert c.ok("GET", f"/api/tickets/{a['id']}/suggestions") == {"suggestions": []}
    assert reply_calls(hub, "pollen") == []


def test_orders_are_never_fetched_unasked(c, hub):
    c.connect("orders", "pollen")
    (a,) = c.tickets(1, body="Order A-1001 is late, please check it.")
    c.page("/")
    c.page(f"/tickets/{a['id']}")
    c.ticket(a["id"])
    c.suggest(a["id"], provider="pollen")
    assert hub.calls_to("orders") == []


def test_teams_see_only_their_orders(south, hub):
    south.connect("orders")
    (b,) = south.tickets(1)
    assert order_view(lookup(south, b["id"], "B-2001")) == expected("B-2001")
    expect_error(south.post(f"/api/tickets/{b['id']}/orders", json={"order_id": "A-1001"}), 404,
                 "order_not_found")  # fmt: skip
    assert hub.calls_to("orders")[0]["headers"]["authorization"] == "Bearer orders-south-token"


def test_page_shows_the_total(c):
    c.connect("orders")
    (a,) = c.tickets(1)
    lookup(c, a["id"], "A-1002")
    page = c.page(f"/tickets/{a['id']}")
    assert "A-1002" in page and shows(page, "$1,200.00")
