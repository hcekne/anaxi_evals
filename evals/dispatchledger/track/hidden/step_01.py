"""Request 1: stock levels, no overselling under concurrency, atomic failure, submission keys."""

from conftest import ADA, WAREHOUSES, expect_error, fresh_client, parallel, uid


def stock(app, pid):
    return app.get_product(pid)["stock"]


def test_sample_stock_and_display(app):
    products = {p["id"]: p for p in app.ok(app.get("/api/products", staff=None))["products"]}
    assert {k: products[k]["stock"] for k in ("tea", "mug", "apron")} == {"tea": 10, "mug": 5, "apron": 3}
    pid = app.product(stock=7, name="Shown Stock")
    assert stock(app, pid) == 7
    assert app.get("/", staff=None).status_code == 200


def test_checkout_takes_stock(app):
    pid = app.product(stock=5)
    app.order([(pid, 2)])
    assert stock(app, pid) == 3
    expect_error(app.checkout([(pid, 4)]), 409, "out_of_stock")
    assert stock(app, pid) == 3
    app.order([(pid, 3)])
    assert stock(app, pid) == 0
    expect_error(app.checkout([(pid, 1)]), 409, "out_of_stock")


def test_failed_checkout_changes_nothing(app):
    plenty, scarce = app.product(stock=10), app.product(stock=1)
    before = len(app.ok(app.get("/api/orders"))["orders"])
    expect_error(app.checkout([(plenty, 3), (scarce, 2)]), 409, "out_of_stock")
    assert (stock(app, plenty), stock(app, scarce)) == (10, 1)
    assert len(app.ok(app.get("/api/orders"))["orders"]) == before


def test_quote_does_not_take_stock(app):
    pid = app.product(stock=2)
    response = app.post("/api/quote", staff=None, json={"items": [{"product_id": pid, "quantity": 2}]})
    assert response.status_code == 200 and stock(app, pid) == 2


def test_set_stock_and_validation(app):
    pid = app.product(stock=1)
    app.set_stock(pid, 9)
    assert stock(app, pid) == 9
    if not WAREHOUSES:
        assert app.ok(app.put(f"/api/products/{pid}/stock", json={"stock": 4}))["stock"] == 4
        for bad in ({"stock": -1}, {"stock": "3"}, {"stock": 1.5}, {}):
            expect_error(app.put(f"/api/products/{pid}/stock", json=bad), 422, "invalid_request")
        expect_error(app.put("/api/products/ghost-x/stock", json={"stock": 1}), 404, "not_found")


def race(app, pid, buyers, quantity=1):
    clients = [fresh_client(app) for _ in range(buyers)]
    path, params = "/api/orders", {}

    def buy(i):
        body = {"customer": ADA, "items": [{"product_id": pid, "quantity": quantity}]}
        return clients[i].post(path, params=params, json=body)

    try:
        return parallel(buy, buyers)
    finally:
        for client in clients:
            client.close()


def test_last_item_race(app):
    for _ in range(3):
        pid = app.product(stock=1)
        results = race(app, pid, 8)
        statuses = sorted(r.status_code for r in results)
        assert statuses == [201] + [409] * 7, statuses
        assert stock(app, pid) == 0


def test_many_buyers_few_units(app):
    pid = app.product(stock=5)
    results = race(app, pid, 12, quantity=2)
    created = [r.json() for r in results if r.status_code == 201]
    assert len(created) == 2 and all(r.status_code in (201, 409) for r in results)
    assert stock(app, pid) == 1
    assert len({o["id"] for o in created}) == 2


def test_submission_key_returns_same_order(app):
    pid = app.product(stock=5)
    key = uid("press")
    first = app.checkout([(pid, 2)], key=key)
    assert first.status_code == 201, first.text
    again = app.checkout([(pid, 2)], key=key)
    assert again.status_code == 200 and again.json()["id"] == first.json()["id"]
    different = app.checkout([(pid, 1)], key=key)
    assert different.status_code == 200 and different.json()["id"] == first.json()["id"]
    assert stock(app, pid) == 3
    ids = [o["id"] for o in app.ok(app.get("/api/orders"))["orders"]]
    assert ids.count(first.json()["id"]) == 1


def test_simultaneous_resubmission(app):
    pid = app.product(stock=10)
    key = uid("double")
    clients = [fresh_client(app) for _ in range(6)]
    body = {"customer": ADA, "items": [{"product_id": pid, "quantity": 1}], "submission_key": key}
    try:
        results = parallel(lambda i: clients[i].post("/api/orders", json=body), 6)
    finally:
        for client in clients:
            client.close()
    assert sorted(r.status_code for r in results) == [200] * 5 + [201]
    assert len({r.json()["id"] for r in results}) == 1
    assert stock(app, pid) == 9


def test_failed_checkout_keeps_key_usable(app):
    pid = app.product(stock=1)
    key = uid("retry")
    expect_error(app.checkout([(pid, 2)], key=key), 409, "out_of_stock")
    app.set_stock(pid, 2)
    assert app.checkout([(pid, 2)], key=key).status_code == 201
