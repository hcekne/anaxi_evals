"""Probe 3: a three-decimal currency through every consumer, old orders untouched."""

import contextlib

import httpx

from conftest import GRACE, read_csv, uid

H = "harbour"


@contextlib.contextmanager
def currency(app, code, staff=H):
    response = app.put("/api/shop", staff=staff, json={"currency": code})
    assert response.status_code == 200 and response.json()["currency"] == code, response.text
    try:
        yield
    finally:
        app.ok(app.put("/api/shop", staff=staff, json={"currency": "GBP"}))


def mails(hub, order_id):
    return [m for m in hub.messages() if order_id in m["subject"]]


def test_dinar_everywhere(app, hub):
    app.configure("parcelfox", staff=H)
    with currency(app, "KWD"):
        pid = app.product(price=12500, name="Dinar Lamp", staff=H)
        assert app.get_product(pid, staff=H)["currency"] == "KWD"
        assert "KWD 12.500" in httpx.get(f"{app.public_url}/", params={"shop": H}).text
        order = app.order([(pid, 2)], staff=H)
        assert order["currency"] == "KWD" and order["total"] == 25000
        app.ship(order["id"], staff=H)
        body = "\n".join(m["body"] for m in mails(hub, order["id"]))
        assert "2 x Dinar Lamp KWD 25.000" in body and "Total: KWD 25.000" in body
        assert "KWD 25.000" in httpx.get(f"{app.public_url}/track/{order['id']}").text
        record = app.ok(app.post(f"/api/orders/{order['id']}/returns", staff=H,
                                 json={"reference": uid("R"), "items": [{"product_id": pid, "quantity": 1}]}), 201)
        assert record["currency"] == "KWD" and record["value"] == 12500


def test_small_and_large_amounts(app, hub):
    with currency(app, "KWD"):
        cheap, dear = app.product(price=5, name="Pin", staff=H), app.product(price=1234567, name="Car", staff=H)
        order = app.order([(cheap, 1), (dear, 1)], staff=H)
        app.work()
        body = mails(hub, order["id"])[0]["body"]
        assert "1 x Pin KWD 0.005" in body and "1 x Car KWD 1234.567" in body and "Total: KWD 1234.572" in body


def test_reports_and_csv(app):
    day = app.next_day()
    pid = app.product(price=1250, staff=H)
    app.order([(pid, 1)], staff=H)
    with currency(app, "KWD"):
        app.order([(pid, 2)], staff=H)
    with currency(app, "JPY"):
        app.order([(pid, 1)], staff=H)
    days = app.ok(app.get("/api/reports/daily", staff=H, params={"from": day, "to": day}))["days"]
    assert [(d["currency"], d["original_value"]) for d in days] == [("GBP", 1250), ("JPY", 1250), ("KWD", 2500)]
    table = read_csv(app.get("/api/reports/daily.csv", staff=H, params={"from": day, "to": day}).text)
    assert table[1:] == [
        [day, "GBP", "1", "1", "12.50", "0.00", "12.50"],
        [day, "JPY", "1", "1", "1250", "0", "1250"],
        [day, "KWD", "1", "2", "2.500", "0.000", "2.500"],
    ]


def test_old_orders_and_queued_work_keep_their_currency(app, hub):
    app.configure("parcelfox", staff=H)
    pid = app.product(price=450, name="Old Tea", staff=H)
    old = app.order([(pid, 1)], staff=H)
    app.request_label(old["id"], staff=H)
    with currency(app, "KWD"):
        app.work()
        assert app.get_order(old["id"], H)["currency"] == "GBP"
        body = "\n".join(m["body"] for m in mails(hub, old["id"]))
        assert "Total: £4.50" in body and "KWD" not in body
        assert "£4.50" in httpx.get(f"{app.public_url}/track/{old['id']}").text
        record = {"legacy_id": uid("TILL"), "created_at": "2026-01-15T10:30:00Z", "customer": GRACE,
                  "items": [{"product_id": "tea", "name": "Old Tea", "unit_price": 395, "quantity": 1}]}
        imported = app.ok(app.post("/api/orders/import", staff=H, json={"orders": [record]}))["orders"][0]
        assert app.get_order(imported["order_id"], H)["currency"] == "GBP"


def test_other_currencies_unchanged(app):
    for code, shown in (("EUR", "€12.50"), ("JPY", "¥1250"), ("GBP", "£12.50")):
        with currency(app, code):
            pid = app.product(price=1250, staff=H)
            assert shown in httpx.get(f"{app.public_url}/", params={"shop": H}).text
            assert app.order([(pid, 1)], staff=H)["currency"] == code
    response = app.put("/api/shop", staff=H, json={"currency": "BHD"})
    assert response.status_code == 422
