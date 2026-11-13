"""Request 11: product edits never rewrite history — orders, emails, returns, reports — and
imported historical records keep their purchase-time names and prices."""

from conftest import GRACE, expect_error, money, uid


def rename(app, pid, staff="main", **changes):
    response = app.patch(f"/api/products/{pid}", staff=staff, json=changes)
    assert response.status_code == 200, response.text
    return response.json()


def test_edit_product(app):
    pid = app.product(price=450, name="Breakfast Tea Old")
    edited = rename(app, pid, name="Breakfast Tea New", price=520)
    assert edited["name"] == "Breakfast Tea New" and edited["price"] == 520
    assert rename(app, pid, price=530)["name"] == "Breakfast Tea New"
    quote = app.ok(app.post("/api/quote", staff=None, json={"items": [{"product_id": pid, "quantity": 1}]}))
    assert quote["total"] == 530 and quote["items"][0]["name"] == "Breakfast Tea New"
    assert "Breakfast Tea New" in app.get("/", staff=None).text
    for bad in ({"price": -1}, {"name": ""}, {"price": "5"}):
        expect_error(app.patch(f"/api/products/{pid}", json=bad), 422, "invalid_request")
    expect_error(app.patch("/api/products/ghost-x", json={"price": 1}), 404, "not_found")
    expect_error(app.patch(f"/api/products/{pid}", staff="harbour", json={"price": 1}), 404, "not_found")


def test_existing_orders_keep_what_was_bought(app):
    pid = app.product(price=450, name="Old Name A")
    old = app.order([(pid, 2)])
    rename(app, pid, name="New Name A", price=999)
    current = app.get_order(old["id"])
    assert current["items"][0]["name"] == "Old Name A" and current["items"][0]["unit_price"] == 450
    assert current["total"] == 900
    new = app.order([(pid, 2)])
    assert new["items"][0]["name"] == "New Name A" and new["total"] == 1998
    page = app.get(f"/orders/{old['id']}")
    assert "Old Name A" in page.text and money(900) in page.text
    track = app.get(f"/track/{old['id']}", staff=None)
    assert "Old Name A" in track.text and "New Name A" not in track.text


def test_emails_sent_later_use_purchase_details(app, hub):
    pid = app.product(price=1250, name="Old Mug")
    order = app.order([(pid, 1)])
    rename(app, pid, name="New Mug", price=1500)
    app.ship(order["id"])
    mails = [m for m in hub.messages() if order["id"] in m["subject"]]
    assert len(mails) == 2
    body = "\n".join(m["body"] for m in mails)
    assert "Old Mug" in body and "New Mug" not in body
    assert money(1250) in body and money(1500) not in body


def test_returns_and_reports_use_purchase_prices(app):
    day = app.next_day()
    pid = app.product(price=800, name="Old Price")
    order = app.order([(pid, 2)])
    app.ship(order["id"])
    rename(app, pid, price=100, name="Cheap Now")
    record = app.ok(app.post(f"/api/orders/{order['id']}/returns",
                             json={"reference": uid("R"), "items": [{"product_id": pid, "quantity": 1}]}), 201)  # fmt: skip
    assert record["value"] == 800 and record["items"][0]["name"] == "Old Price"
    report = app.ok(app.get("/api/reports/daily", params={"from": day, "to": day}))["days"]
    assert (report[0]["original_value"], report[0]["returned_value"], report[0]["remaining_value"]) == (1600, 800, 800)


def legacy(legacy_id=None, created_at="2026-01-15T10:30:00Z", **extra):
    record = {"legacy_id": legacy_id or uid("TILL"), "created_at": created_at, "customer": GRACE,
              "items": [{"product_id": "tea", "name": "Breakfast Tea (Assam)", "unit_price": 395, "quantity": 2},
                        {"product_id": "retired-x", "name": "Copper Kettle", "unit_price": 4100, "quantity": 1}]}  # fmt: skip
    record.update(extra)
    return record


def test_import_keeps_historical_values(app, hub):
    tea_before = app.get_product("tea")["stock"]
    first, second = legacy(), legacy(created_at="2026-01-16T23:59:59Z")
    response = app.post("/api/orders/import", json={"orders": [first, second]})
    assert response.status_code == 200, response.text
    mapping = response.json()["orders"]
    assert [m["legacy_id"] for m in mapping] == [first["legacy_id"], second["legacy_id"]]
    order = app.get_order(mapping[0]["order_id"])
    assert order["legacy_id"] == first["legacy_id"] and order["created_at"] == "2026-01-15T10:30:00Z"
    assert [(i["name"], i["unit_price"], i["quantity"], i["line_total"]) for i in order["items"]] == [
        ("Breakfast Tea (Assam)", 395, 2, 790), ("Copper Kettle", 4100, 1, 4100)]  # fmt: skip
    assert order["total"] == 4890 and order["customer"] == GRACE
    assert order["shipments"] == [] and order["delivery_status"] == "not_shipped"
    assert app.get_product("tea")["stock"] == tea_before
    app.work()
    assert [m for m in hub.messages() if mapping[0]["order_id"] in m["subject"]] == []
    again = app.ok(app.post("/api/orders/import", json={"orders": [first]}))
    assert again["orders"][0]["order_id"] == mapping[0]["order_id"]
    ids = [o["id"] for o in app.ok(app.get("/api/orders"))["orders"]]
    assert ids.count(mapping[0]["order_id"]) == 1
    report = app.ok(app.get("/api/reports/daily", params={"from": "2026-01-15", "to": "2026-01-16"}))["days"]
    assert [(d["date"], d["orders"], d["items"], d["original_value"]) for d in report] == [
        ("2026-01-15", 1, 3, 4890), ("2026-01-16", 1, 3, 4890)]  # fmt: skip
    track = app.get(f"/track/{mapping[0]['order_id']}", staff=None)
    assert track.status_code == 200 and "Copper Kettle" in track.text and money(4890) in track.text
    native = app.order()
    assert app.get_order(native["id"])["legacy_id"] is None


def test_import_validation_is_all_or_nothing(app):
    good = legacy()
    for bad in (
        legacy(created_at="15/01/2026"),
        legacy(items=[]),
        legacy(items=[{"product_id": "tea", "name": "", "unit_price": 1, "quantity": 1}]),
        legacy(items=[{"product_id": "tea", "name": "x", "unit_price": -1, "quantity": 1}]),
        legacy(items=[{"product_id": "tea", "name": "x", "unit_price": 1, "quantity": 0}]),
        legacy(customer={"name": "x", "email": "no-at"}),
        {"legacy_id": uid("T")},
    ):
        expect_error(app.post("/api/orders/import", json={"orders": [good, bad]}), 422, "invalid_request")
    listed = app.ok(app.get("/api/orders"))["orders"]
    assert good["legacy_id"] not in [o.get("legacy_id") for o in listed]
    imported = app.ok(app.post("/api/orders/import", json={"orders": [good]}))["orders"][0]
    assert app.get_order(imported["order_id"])["created_at"] == good["created_at"]
