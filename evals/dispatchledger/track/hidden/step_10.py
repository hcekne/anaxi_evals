"""Request 10: second shop with staff login; every staff surface, export, carrier credential,
worker job and callback stays scoped to its shop; main's data is kept."""

import httpx

from conftest import ADDRESS, emails_of, expect_error, shipment_of, subset, uid


def anon(app, method, path, **kw):
    return app.http.request(method, path, **kw)


def test_login(app):
    response = anon(app, "POST", "/api/login", json={"username": "rowan", "password": "rowan-test-pass"})
    assert response.status_code == 200 and response.json()["shop_id"] == "harbour"
    assert response.json()["token"]
    main = anon(app, "POST", "/api/login", json={"username": "morgan", "password": "morgan-test-pass"})
    assert main.json()["shop_id"] == "main"
    expect_error(anon(app, "POST", "/api/login", json={"username": "rowan", "password": "nope"}), 401,
                 "invalid_credentials")  # fmt: skip
    expect_error(anon(app, "POST", "/api/login", json={"username": "ghost", "password": "x"}), 401,
                 "invalid_credentials")  # fmt: skip
    assert subset(app.ok(app.get("/api/shop", staff="harbour")), {"id": "harbour", "name": "DispatchLedger Harbour"})
    assert app.ok(app.get("/api/shop"))["id"] == "main"


def test_staff_endpoints_need_login(app):
    order = app.order()
    for method, path, body in (
        ("GET", "/api/orders", None),
        ("GET", f"/api/orders/{order['id']}", None),
        ("POST", "/api/products", {"id": uid("p"), "name": "x", "price": 1}),
        ("POST", f"/api/orders/{order['id']}/label", {"address": ADDRESS, "weight_g": 100}),
        ("GET", "/api/reports/daily", None),
        ("POST", "/api/warehouse-feed", {"snapshots": []}),
        ("PUT", "/api/carriers/parcelfox/credentials", {"token": "pf-test-token"}),
        ("GET", "/api/carriers", None),
    ):
        expect_error(anon(app, method, path, json=body), 401, "unauthorized")
        expect_error(anon(app, method, path, json=body, headers={"Authorization": "Bearer forged"}), 401,
                     "unauthorized")  # fmt: skip
    page = anon(app, "GET", "/orders")
    assert order["id"] not in page.text
    assert anon(app, "GET", "/api/products").status_code == 200


def test_harbour_starts_empty_and_has_own_catalogue(app):
    products = app.ok(app.get("/api/products", staff=None, shop="harbour"))["products"]
    assert products == []
    assert app.ok(app.get("/api/orders", staff="harbour"))["orders"] == []
    expect_error(app.get("/api/products", staff=None, shop="nowhere"), 404, "not_found")
    pid = uid("tea")
    app.ok(app.post("/api/products", staff="harbour", json={"id": pid, "name": "Harbour Tea", "price": 600}), 201)
    app.ok(app.post("/api/products", staff="main", json={"id": pid, "name": "Main Tea", "price": 450}), 201)
    assert app.get_product(pid, staff="harbour")["name"] == "Harbour Tea"
    assert app.get_product(pid)["name"] == "Main Tea"
    app.feed([("north", pid, 4)], staff="harbour")
    assert app.get_product(pid, staff="harbour")["stock"] == 4
    assert app.get_product(pid)["stock"] == 0
    order = app.ok(app.checkout([(pid, 1)], staff="harbour"), 201)
    assert order["total"] == 600
    assert app.get_product(pid)["stock"] == 0


def test_staff_cannot_reach_other_shop(app):
    main_order = app.order()
    harbour_order = app.order(staff="harbour")
    expect_error(app.get(f"/api/orders/{main_order['id']}", staff="harbour"), 404, "not_found")
    expect_error(app.get(f"/api/orders/{harbour_order['id']}", staff="main"), 404, "not_found")
    expect_error(app.request_label(main_order["id"], staff="harbour"), 404, "not_found")
    expect_error(app.post(f"/api/orders/{main_order['id']}/returns", staff="harbour",
                          json={"reference": "R1", "items": [{"product_id": "tea", "quantity": 1}]}), 404,
                 "not_found")  # fmt: skip
    email = emails_of(app.get_order(main_order["id"]))[0]
    expect_error(app.post(f"/api/emails/{email['id']}/retry", staff="harbour"), 404, "not_found")
    harbour_ids = [o["id"] for o in app.ok(app.get("/api/orders", staff="harbour"))["orders"]]
    main_ids = [o["id"] for o in app.ok(app.get("/api/orders"))["orders"]]
    assert harbour_order["id"] in harbour_ids and main_order["id"] not in harbour_ids
    assert main_order["id"] in main_ids and harbour_order["id"] not in main_ids
    page = app.get("/orders", staff="harbour")
    assert harbour_order["id"] in page.text and main_order["id"] not in page.text
    assert app.get(f"/orders/{main_order['id']}", staff="harbour").status_code == 404


def test_reports_and_exports_are_scoped(app):
    day = app.next_day()
    app.order(price=1000)
    app.order(price=7, staff="harbour")
    app.order(price=8, staff="harbour")
    main = app.ok(app.get("/api/reports/daily", params={"from": day, "to": day}))["days"]
    harbour = app.ok(app.get("/api/reports/daily", staff="harbour", params={"from": day, "to": day}))["days"]
    assert [(d["orders"], d["value"]) for d in main] == [(1, 1000)]
    assert [(d["orders"], d["value"]) for d in harbour] == [(2, 15)]
    csv = app.get("/api/reports/daily.csv", staff="harbour", params={"from": day, "to": day}).text
    assert "0.15" in csv and "10.00" not in csv


def test_carrier_credentials_per_shop(app, hub):
    order = app.order(staff="harbour")
    expect_error(app.request_label(order["id"], staff="harbour"), 409, "not_configured")
    carriers = {c["id"]: c for c in app.ok(app.get("/api/carriers", staff="harbour"))["carriers"]}
    assert carriers["parcelfox"]["configured"] is False
    app.configure("parcelfox", staff="harbour")
    shipped = app.ship(order["id"], staff="harbour")
    assert shipment_of(shipped)["status"] == "done"
    assert [c["token"] for c in hub.pf_created] == ["pf-harbour-token"]
    main_order = app.order()
    app.ship(main_order["id"])
    assert [c["token"] for c in hub.pf_created] == ["pf-harbour-token", "pf-test-token"]


def test_quickcrate_jobs_and_callbacks_per_shop(app, hub):
    app.configure("quickcrate", staff="harbour")
    order = app.order(staff="harbour")
    app.request_label(order["id"], carrier="quickcrate", staff="harbour")
    app.work()
    job = hub.qc_created[0]
    assert job["token"] == "qc-harbour-key"
    if job["callback_url"]:
        with hub.lock:
            hub.qc_jobs[job["job_id"]].update(status="ready", sequence=2,
                                              label={"tracking": "QCX", "text": "x"})  # fmt: skip
        forged = hub.qc_callback(job["job_id"])
        import hashlib
        import hmac

        wrong = "sha256=" + hmac.new(b"qc-callback-secret", forged["raw"], hashlib.sha256).hexdigest()
        assert hub.send_callback(forged, signature=wrong) == 401
        assert shipment_of(app.get_order(order["id"], staff="harbour"))["status"] == "preparing"
    hub.qc_set(job["job_id"], "ready")
    app.advance(30)
    app.work()
    assert shipment_of(app.get_order(order["id"], staff="harbour"))["status"] == "done"


def test_warehouse_preference_per_shop(app):
    app.ok(app.put("/api/warehouse-preference", staff="harbour", json={"preferred": "south"}))
    try:
        assert app.ok(app.get("/api/warehouse-preference"))["preferred"] == "north"
        pid = app.product(stock=5, south=5, staff="harbour")
        assert shipment_of(app.order([(pid, 1)], staff="harbour"))["warehouse"] == "south"
    finally:
        app.ok(app.put("/api/warehouse-preference", staff="harbour", json={"preferred": "north"}))


def test_customer_pages_and_emails_for_harbour(app, hub):
    pid = app.product(price=321, name="Harbour Rope", staff="harbour")
    order = app.order([(pid, 1)], staff="harbour")
    app.work()
    page = httpx.get(f"{app.public_url}/track/{order['id']}")
    assert page.status_code == 200 and "Harbour Rope" in page.text
    shop = httpx.get(f"{app.public_url}/", params={"shop": "harbour"})
    assert shop.status_code == 200 and "Harbour Rope" in shop.text
    mails = [m for m in hub.messages() if order["id"] in m["subject"]]
    assert len(mails) == 1 and "£3.21" in mails[0]["body"]


def test_main_data_is_kept(app):
    products = {p["id"] for p in app.ok(app.get("/api/products", staff=None))["products"]}
    assert {"tea", "mug", "apron"} <= products
