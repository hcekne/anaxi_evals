"""Request 15: per-shop currencies with minor units, orders that keep their currency, separate
report rows, and old orders/links/queued emails that still read correctly."""

import contextlib

import httpx

from conftest import GRACE, expect_error, money, plain, read_csv, shipment_of, uid

H = "harbour"


@contextlib.contextmanager
def currency(app, code, staff=H):
    response = app.put("/api/shop", staff=staff, json={"currency": code})
    assert response.status_code == 200 and response.json()["currency"] == code, response.text
    try:
        yield
    finally:
        app.ok(app.put("/api/shop", staff=staff, json={"currency": "GBP"}))


def harbour_ready(app):
    app.configure("parcelfox", staff=H)


def mails_for(hub, order_id):
    return [m for m in hub.messages() if order_id in m["subject"]]


def test_default_and_validation(app):
    shop = app.ok(app.get("/api/shop"))
    assert shop["currency"] == "GBP" and shop["id"] == "main"
    assert app.get_product("tea")["currency"] == "GBP"
    order = app.order()
    assert order["currency"] == "GBP"
    for bad in ("USD", "gbp", "", None, 1):
        expect_error(app.put("/api/shop", staff=H, json={"currency": bad}), 422, "unsupported_currency")
    assert app.ok(app.get("/api/shop", staff=H))["currency"] == "GBP"


def test_yen_shop_end_to_end(app, hub):
    harbour_ready(app)
    with currency(app, "JPY"):
        pid = app.product(price=1250, name="Yen Teapot", staff=H)
        product = app.get_product(pid, staff=H)
        assert product["currency"] == "JPY" and product["price"] == 1250
        page = httpx.get(f"{app.public_url}/", params={"shop": H}).text
        assert "¥1250" in page
        quote = app.ok(app.post("/api/quote", staff=None, shop=H, json={"items": [{"product_id": pid, "quantity": 2}]}))
        assert quote["currency"] == "JPY" and quote["total"] == 2500
        order = app.order([(pid, 2)], staff=H)
        assert order["currency"] == "JPY" and order["total"] == 2500
        app.ship(order["id"], staff=H)
        body = "\n".join(m["body"] for m in mails_for(hub, order["id"]))
        assert "2 x Yen Teapot ¥2500" in body and "Total: ¥2500" in body
        track = httpx.get(f"{app.public_url}/track/{order['id']}").text
        assert "¥2500" in track
        staff_page = app.get(f"/orders/{order['id']}", staff=H).text
        assert "¥2500" in staff_page


def test_euro_amounts(app, hub):
    with currency(app, "EUR"):
        pid = app.product(price=1250, name="Euro Basket", staff=H)
        order = app.order([(pid, 1)], staff=H)
        app.work()
        assert order["currency"] == "EUR"
        assert "Total: €12.50" in mails_for(hub, order["id"])[0]["body"]
        assert "€12.50" in httpx.get(f"{app.public_url}/", params={"shop": H}).text


def test_orders_keep_their_currency(app, hub):
    harbour_ready(app)
    pid = app.product(price=450, name="Steady Tea", staff=H)
    old = app.order([(pid, 2)], staff=H)
    assert old["currency"] == "GBP"
    with currency(app, "JPY"):
        app.work()  # accepted email still queued until now
        current = app.get_order(old["id"], H)
        assert current["currency"] == "GBP" and current["total"] == 900
        assert "Total: £9.00" in mails_for(hub, old["id"])[0]["body"]
        app.ship(old["id"], staff=H)
        track = httpx.get(f"{app.public_url}/track/{old['id']}").text
        assert "£9.00" in track and "¥" not in track
        new = app.order([(pid, 2)], staff=H)
        assert new["currency"] == "JPY" and new["total"] == 900
        record = app.ok(app.post(f"/api/orders/{old['id']}/returns", staff=H,
                                 json={"reference": uid("R"), "items": [{"product_id": pid, "quantity": 1}]}), 201)  # fmt: skip
        assert record["currency"] == "GBP" and record["value"] == 450


def test_reports_keep_currencies_apart(app):
    day = app.next_day()
    gbp = app.product(price=1250, staff=H)
    app.order([(gbp, 1)], staff=H)
    with currency(app, "JPY"):
        app.order([(gbp, 2)], staff=H)
        app.order([(gbp, 1)], staff=H)
    with currency(app, "EUR"):
        app.order([(gbp, 1)], staff=H)
    days = app.ok(app.get("/api/reports/daily", staff=H, params={"from": day, "to": day}))["days"]
    rows = [(d["date"], d["currency"], d["orders"], d["items"], d["original_value"]) for d in days]
    assert rows == [(day, "EUR", 1, 1, 1250), (day, "GBP", 1, 1, 1250), (day, "JPY", 2, 3, 3750)]
    table = read_csv(app.get("/api/reports/daily.csv", staff=H, params={"from": day, "to": day}).text)
    assert table[0] == ["date", "currency", "orders", "items", "original_value", "returned_value", "remaining_value"]
    assert table[1:] == [
        [day, "EUR", "1", "1", "12.50", "0.00", "12.50"],
        [day, "GBP", "1", "1", "12.50", "0.00", "12.50"],
        [day, "JPY", "2", "3", "3750", "0", "3750"],
    ]


def test_yen_returns_and_remaining_value(app):
    harbour_ready(app)
    day = app.next_day()
    with currency(app, "JPY"):
        pid = app.product(price=999, staff=H)
        order = app.order([(pid, 3)], staff=H)
        app.ship(order["id"], staff=H)
        app.ok(app.post(f"/api/orders/{order['id']}/returns", staff=H,
                        json={"reference": uid("R"), "items": [{"product_id": pid, "quantity": 1}]}), 201)  # fmt: skip
    current = app.get_order(order["id"], H)
    assert (current["currency"], current["returned_value"], current["remaining_value"]) == ("JPY", 999, 1998)
    table = read_csv(app.get("/api/reports/daily.csv", staff=H, params={"from": day, "to": day}).text)
    assert table[1] == [day, "JPY", "1", "3", "2997", "999", "1998"]
    assert plain(1998, "JPY") == "1998" and money(1998, "JPY") == "¥1998"


def test_imported_history_is_gbp(app):
    with currency(app, "EUR"):
        record = {"legacy_id": uid("TILL"), "created_at": "2026-01-15T10:30:00Z", "customer": GRACE,
                  "items": [{"product_id": "tea", "name": "Old Tea", "unit_price": 395, "quantity": 1}]}  # fmt: skip
        imported = app.ok(app.post("/api/orders/import", staff=H, json={"orders": [record]}))["orders"][0]
        order = app.get_order(imported["order_id"], H)
        assert order["currency"] == "GBP"
        assert "£3.95" in httpx.get(f"{app.public_url}/track/{order['id']}").text


def test_main_shop_unchanged(app, hub):
    order = app.order(price=1999)
    shipped = app.ship(order["id"])
    assert shipped["currency"] == "GBP" and shipment_of(shipped)["status"] == "done"
    assert "£19.99" in mails_for(hub, order["id"])[0]["body"]
