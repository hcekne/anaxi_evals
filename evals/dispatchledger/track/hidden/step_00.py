"""Request 0: catalogue, basket quote, checkout, orders, pages, input rules, persistence."""

from conftest import ADA, GRACE, STOCK, WAREHOUSES, expect_error, iso, money, subset, uid

SAMPLES = {"tea": ("Breakfast Tea", 450), "mug": ("Enamel Mug", 1250), "apron": ("Canvas Apron", 2200)}


def test_sample_products(app):
    response = app.get("/api/products", staff=None)
    assert response.status_code == 200, response.text
    products = {p["id"]: p for p in response.json()["products"]}
    for pid, (name, price) in SAMPLES.items():
        assert subset(products[pid], {"id": pid, "name": name, "price": price})
    ids = [p["id"] for p in response.json()["products"]]
    assert ids == sorted(ids)
    assert subset(app.get_product("mug"), {"id": "mug", "name": "Enamel Mug", "price": 1250})
    expect_error(app.get("/api/products/nope", staff=None), 404, "not_found")


def test_add_product_and_validation(app):
    pid = uid("scarf")
    body = {"id": pid, "name": "Wool Scarf", "price": 1800}
    if STOCK and not WAREHOUSES:
        body["stock"] = 4
    created = app.ok(app.post("/api/products", json=body), 201)
    assert subset(created, {"id": pid, "name": "Wool Scarf", "price": 1800})
    expect_error(app.post("/api/products", json=body), 409, "conflict")
    for bad in (
        {"id": "Bad Id", "name": "x", "price": 1},
        {"id": uid("b"), "name": "", "price": 1},
        {"id": uid("b"), "name": "x" * 101, "price": 1},
        {"id": uid("b"), "name": "x", "price": -1},
        {"id": uid("b"), "name": "x", "price": 1.5},
        {"id": uid("b"), "name": "x", "price": True},
        {"id": uid("b"), "name": "x"},
    ):
        expect_error(app.post("/api/products", json=bad), 422, "invalid_request")


def test_quote_totals(app):
    a, b = app.product(price=450), app.product(price=1250)
    response = app.post("/api/quote", staff=None, json={"items": [
        {"product_id": b, "quantity": 3}, {"product_id": a, "quantity": 2}]})  # fmt: skip
    assert response.status_code == 200, response.text
    quote = response.json()
    assert quote["total"] == 3 * 1250 + 2 * 450
    assert [(i["product_id"], i["quantity"], i["unit_price"], i["line_total"]) for i in quote["items"]] == [
        (b, 3, 1250, 3750), (a, 2, 450, 900)]  # fmt: skip
    assert quote["items"][0]["name"] == f"Item {b}"


def test_checkout_creates_order(app):
    a, b = app.product(price=450), app.product(price=2200)
    response = app.checkout([(a, 2), (b, 1)], customer=GRACE)
    assert response.status_code == 201, response.text
    order = response.json()
    assert isinstance(order["id"], str) and order["id"]
    assert order["customer"] == GRACE
    assert order["total"] == 3100
    assert order["created_at"] == iso(app.now)
    lines = [(i["product_id"], i["name"], i["unit_price"], i["quantity"], i["line_total"]) for i in order["items"]]
    assert lines == [(a, f"Item {a}", 450, 2, 900), (b, f"Item {b}", 2200, 1, 2200)]
    fetched = app.get_order(order["id"])
    assert fetched["total"] == 3100 and fetched["items"] == order["items"]
    listed = app.ok(app.get("/api/orders"))["orders"]
    assert listed[-1]["id"] == order["id"]
    second = app.order()
    ids = [o["id"] for o in app.ok(app.get("/api/orders"))["orders"]]
    assert ids.index(order["id"]) < ids.index(second["id"]) and second["id"] != order["id"]
    expect_error(app.get("/api/orders/does-not-exist"), 404, "not_found")


def test_invalid_quantities_rejected(app):
    pid = app.product()
    before = len(app.ok(app.get("/api/orders"))["orders"])
    for quantity in (0, -1, 1.5, "2", True, None):
        body = {"customer": ADA, "items": [{"product_id": pid, "quantity": quantity}]}
        expect_error(app.post("/api/orders", staff=None, json=body), 422, "invalid_quantity")
        expect_error(app.post("/api/quote", staff=None, json={"items": body["items"]}), 422, "invalid_quantity")
    body = {"customer": ADA, "items": [{"product_id": pid}]}
    expect_error(app.post("/api/orders", staff=None, json=body), 422, "invalid_quantity")
    assert len(app.ok(app.get("/api/orders"))["orders"]) == before


def test_unknown_products_rejected(app):
    pid = app.product()
    before = len(app.ok(app.get("/api/orders"))["orders"])
    items = [{"product_id": pid, "quantity": 1}, {"product_id": uid("ghost"), "quantity": 1}]
    expect_error(app.post("/api/orders", staff=None, json={"customer": ADA, "items": items}), 422, "unknown_product")
    expect_error(app.post("/api/quote", staff=None, json={"items": items}), 422, "unknown_product")
    assert len(app.ok(app.get("/api/orders"))["orders"]) == before


def test_other_input_rules(app):
    pid = app.product()
    line = {"product_id": pid, "quantity": 1}
    for body in (
        {"customer": ADA, "items": []},
        {"customer": ADA},
        {"customer": ADA, "items": [line, dict(line)]},
        {"customer": {"name": "", "email": "a@b.test"}, "items": [line]},
        {"customer": {"name": "Ada", "email": "no-at-sign"}, "items": [line]},
        {"items": [line]},
    ):
        expect_error(app.post("/api/orders", staff=None, json=body), 422, "invalid_request")
    expect_error(app.post("/api/quote", staff=None, json={"items": []}), 422, "invalid_request")


def test_pages(app):
    pid = app.product(price=123450, name="Brass Lantern")
    order = app.order([(pid, 1)])
    shop = app.get("/", staff=None)
    assert shop.status_code == 200 and "text/html" in shop.headers["content-type"]
    for name, price in SAMPLES.values():
        assert name in shop.text and money(price) in shop.text
    assert "Brass Lantern" in shop.text and "£1234.50" in shop.text
    assert "<form" in shop.text.lower() or "<button" in shop.text.lower()
    orders = app.get("/orders")
    assert orders.status_code == 200 and order["id"] in orders.text
    detail = app.get(f"/orders/{order['id']}")
    assert detail.status_code == 200 and "Brass Lantern" in detail.text and "£1234.50" in detail.text


def test_orders_survive_restart(fresh_app):
    pid = fresh_app.product(price=999, name="Keeper")
    order = fresh_app.order([(pid, 2)])
    fresh_app.restart()
    again = fresh_app.get_order(order["id"])
    assert again["total"] == 1998 and again["items"] == order["items"]
    assert fresh_app.get_product(pid)["name"] == "Keeper"
    assert order["id"] in [o["id"] for o in fresh_app.ok(fresh_app.get("/api/orders"))["orders"]]
