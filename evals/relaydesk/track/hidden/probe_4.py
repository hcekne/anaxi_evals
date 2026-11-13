"""Probe 4: order API v3 (decimal strings, GBP); saved orders, drafts and waiting replies keep
working (upgrade from the code just before this probe)."""

from conftest import POLLEN, provider_text, reply_calls, shows, upgrade, wait_for

EXPECTED = {
    "A-1001": ("shipped", 4599, "USD", "$45.99"),
    "E-3001": ("shipped", 1234, "EUR", "€12.34"),
    "J-4001": ("delivered", 1500, "JPY", "¥1,500"),
    "G-6001": ("shipped", 500, "GBP", "£5.00"),
}


def order(order_id: str) -> dict:
    status, minor, currency, total = EXPECTED[order_id]
    return {"order_id": order_id, "status": status,
            "money": {"minor_units": minor, "currency": currency}, "total": total}  # fmt: skip


def view(found: dict) -> dict:
    return {k: found.get(k) for k in ("order_id", "status", "money", "total")}


def lookup(c, ticket_id, order_id) -> dict:
    return c.ok("POST", f"/api/tickets/{ticket_id}/orders", status=201, json={"order_id": order_id})


def test_v3_orders_including_pounds(c, hub):
    hub.orders_v2 = False
    c.connect("orders", "pollen")
    (a,) = c.tickets(1)
    for order_id in EXPECTED:
        assert view(lookup(c, a["id"], order_id)) == order(order_id)
    assert all(x["path"].startswith("/orders/v3/") for x in hub.calls_to("orders"))
    c.suggest(a["id"], provider="pollen", order_ids=["G-6001", "J-4001"])
    sent = provider_text(reply_calls(hub, "pollen")[0])
    assert "£5.00" in sent and "¥1,500" in sent
    page = c.page(f"/tickets/{a['id']}")
    assert shows(page, "£5.00") or "&pound;5.00" in page


def test_saved_orders_drafts_and_waiting_replies_survive(hub):
    def prepare(old):
        c = old.c
        c.connect("orders", "pollen")
        (a,) = c.tickets(1)
        lookup(c, a["id"], "E-3001")
        lookup(c, a["id"], "A-1001")
        c.ok("PUT", f"/api/tickets/{a['id']}/draft", json={"text": "Refund of €12.34 is coming"})
        hub.hold(POLLEN[0])
        waiting = c.ask(a["id"], provider="pollen", order_ids=["E-3001"]).json()
        assert wait_for(lambda: reply_calls(hub, "pollen"))
        return a, waiting, len(reply_calls(hub, "pollen"))

    new, (a, waiting, before) = upgrade(hub, "probe-p4-*.md", prepare, abrupt=True)
    try:
        hub.orders_v2 = False
        hub.release(POLLEN[0])
        c = new.c
        assert c.wait(waiting["id"], timeout=15)["status"] == "completed"
        resent = reply_calls(hub, "pollen")[before:]
        assert resent and "€12.34" in provider_text(resent[-1])
        assert "$45.99" not in provider_text(resent[-1])
        ticket = c.ticket(a["id"])
        assert [view(o) for o in ticket["orders"]] == [order("E-3001"), order("A-1001")]
        assert ticket["draft"]["text"] == "Refund of €12.34 is coming"
        assert view(lookup(c, a["id"], "G-6001")) == order("G-6001")
    finally:
        new.close()
