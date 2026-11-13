"""Request 15: orders in USD, EUR and JPY from the v2 order API; old saved (dollar) orders and
waiting replies keep working across the update. The upgrade test starts the code from just
before request 15 (which still uses the v1 order API)."""

from conftest import POLLEN, expect_error, provider_text, reply_calls, shows, upgrade, wait_for

EXPECTED = {
    "A-1001": ("shipped", 4599, "USD", "$45.99"),
    "A-1002": ("processing", 120000, "USD", "$1,200.00"),
    "E-3001": ("shipped", 1234, "EUR", "€12.34"),
    "E-3002": ("processing", 250075, "EUR", "€2,500.75"),
    "J-4001": ("delivered", 1500, "JPY", "¥1,500"),
    "J-4002": ("shipped", 1234567, "JPY", "¥1,234,567"),
    "E-5001": ("shipped", 4200, "EUR", "€42.00"),
}


def order(order_id: str) -> dict:
    status, minor, currency, total = EXPECTED[order_id]
    return {"order_id": order_id, "status": status,
            "money": {"minor_units": minor, "currency": currency}, "total": total}  # fmt: skip


def lookup(c, ticket_id, order_id) -> dict:
    return c.ok("POST", f"/api/tickets/{ticket_id}/orders", status=201, json={"order_id": order_id})


def view(found: dict) -> dict:
    return {k: found.get(k) for k in ("order_id", "status", "money", "total")}


def test_orders_show_their_own_currency(c, hub):
    c.connect("orders")
    (a,) = c.tickets(1)
    ids = ["E-3001", "E-3002", "J-4001", "J-4002", "A-1001"]
    for order_id in ids:
        found = lookup(c, a["id"], order_id)
        assert view(found) == order(order_id) and "total_cents" not in found
    assert [view(o) for o in c.ticket(a["id"])["orders"]] == [order(i) for i in ids]
    paths = [x["path"] for x in hub.calls_to("orders")]
    assert len(paths) == len(ids) and all(p.startswith("/orders/v") for p in paths)


def test_the_reply_service_gets_the_same_amounts(c, hub):
    c.connect("orders", "pollen", "harbor")
    (a,) = c.tickets(1)
    for order_id in ("E-3001", "J-4001", "A-1002"):
        lookup(c, a["id"], order_id)
    c.suggest(a["id"], provider="pollen", order_ids=["E-3001", "J-4001"])
    sent = provider_text(reply_calls(hub, "pollen")[0])
    assert "€12.34" in sent and "¥1,500" in sent
    assert "$12.34" not in sent and "¥15.00" not in sent and "A-1002" not in sent
    c.suggest(a["id"], provider="harbor", order_ids=["J-4001"])
    assert "¥1,500" in provider_text(reply_calls(hub, "harbor")[0])


def test_ticket_page_shows_currencies(c):
    c.connect("orders")
    (a,) = c.tickets(1)
    lookup(c, a["id"], "E-3002")
    lookup(c, a["id"], "J-4002")
    page = c.page(f"/tickets/{a['id']}")
    assert shows(page, "€2,500.75") or "&euro;2,500.75" in page
    assert shows(page, "¥1,234,567") or "&yen;1,234,567" in page


def test_teams_and_unknown_orders(c, south):
    south.connect("orders")
    (b,) = south.tickets(1)
    assert view(lookup(south, b["id"], "E-5001")) == order("E-5001")
    expect_error(south.post(f"/api/tickets/{b['id']}/orders", json={"order_id": "J-4001"}), 404,
                 "order_not_found")  # fmt: skip


def test_saved_dollar_orders_and_waiting_replies_survive_the_update(hub):
    def prepare(old):
        hub.orders_v1 = True
        c = old.c
        c.connect("orders", "pollen")
        (a,) = c.tickets(1)
        lookup_old = [c.ok("POST", f"/api/tickets/{a['id']}/orders", status=201,
                           json={"order_id": i}) for i in ("A-1001", "A-1002")]  # fmt: skip
        assert lookup_old[0]["total"] == "$45.99"
        hub.hold(POLLEN[0])
        waiting = c.ask(a["id"], provider="pollen", order_ids=["A-1001"]).json()
        assert wait_for(lambda: reply_calls(hub, "pollen"))
        return a, waiting, len(reply_calls(hub, "pollen"))

    new, (a, waiting, before) = upgrade(hub, "15-*.md", prepare, abrupt=True)
    try:
        hub.orders_v1 = False
        hub.release(POLLEN[0])
        c = new.c
        done = c.wait(waiting["id"], timeout=15)
        assert done["status"] == "completed"
        resent = reply_calls(hub, "pollen")[before:]
        assert resent, "the waiting reply was not sent again after the update"
        sent = provider_text(resent[-1])
        assert "A-1001" in sent and "$45.99" in sent and "A-1002" not in sent
        assert [view(o) for o in c.ticket(a["id"])["orders"]] == [order("A-1001"), order("A-1002")]
        page = c.page(f"/tickets/{a['id']}")
        assert shows(page, "$45.99") and shows(page, "$1,200.00")
        lookup(c, a["id"], "E-3001")
        assert [o["total"] for o in c.ticket(a["id"])["orders"]] == ["$45.99", "$1,200.00",
                                                                     "€12.34"]  # fmt: skip
        c.suggest(a["id"], provider="pollen", order_ids=["A-1002", "E-3001"])
        sent = provider_text(reply_calls(hub, "pollen")[-1])
        assert "$1,200.00" in sent and "€12.34" in sent
    finally:
        new.close()
