"""Request 8: split deliveries — allocation conservation, one label per parcel, mixed carriers,
partial failure, aggregate status and honest customer emails."""

from conftest import expect_error, shipment_of


def split_order(app, preferred="north"):
    a, b = app.product(stock=3, name="Split A", feed=True), app.product(stock=0, south=2, name="Split B")
    if preferred != "north":
        app.put("/api/warehouse-preference", json={"preferred": preferred})
    try:
        order = app.order([(a, 2), (b, 1)])
    finally:
        app.put("/api/warehouse-preference", json={"preferred": "north"})
    return order, a, b


def items(shipment):
    return {(i["product_id"], i["quantity"]) for i in shipment["items"]}


def test_split_allocation(app):
    a = app.product(stock=2, south=5)
    order = app.order([(a, 3)])
    assert len(order["shipments"]) == 1 and shipment_of(order)["warehouse"] == "south"
    b = app.product(stock=2, south=1)
    order = app.order([(b, 3)])
    assert [(s["warehouse"], items(s)) for s in order["shipments"]] == [
        ("north", {(b, 2)}), ("south", {(b, 1)})]  # fmt: skip
    product = app.get_product(b)
    assert product["stock"] == 0 and product["warehouses"] == {"north": 0, "south": 0}
    assert order["delivery_status"] == "not_shipped"
    assert all(s["status"] == "not_requested" for s in order["shipments"])
    assert len({s["id"] for s in order["shipments"]}) == 2


def test_split_by_line_and_preference_order(app):
    order, a, b = split_order(app)
    assert [(s["warehouse"], items(s)) for s in order["shipments"]] == [
        ("north", {(a, 2)}), ("south", {(b, 1)})]  # fmt: skip
    order, a, b = split_order(app, preferred="south")
    assert [(s["warehouse"], items(s)) for s in order["shipments"]] == [
        ("south", {(b, 1)}), ("north", {(a, 2)})]  # fmt: skip


def test_still_out_of_stock(app):
    a = app.product(stock=1, south=1)
    expect_error(app.checkout([(a, 3)]), 409, "out_of_stock")
    assert app.get_product(a)["warehouses"] == {"north": 1, "south": 1}


def test_order_level_label_needs_single_shipment(app):
    order, _, _ = split_order(app)
    expect_error(app.request_label(order["id"]), 409, "multiple_shipments")
    expect_error(app.request_label(order["id"], shipment="nope"), 404, "not_found")
    single = app.order()
    assert app.request_label(single["id"]).status_code == 202
    app.work()


def test_each_parcel_gets_its_own_label_and_carrier(app, hub):
    order, a, b = split_order(app)
    first, second = order["shipments"]
    app.request_label(order["id"], shipment=first["id"], weight=900)
    app.request_label(order["id"], shipment=second["id"], carrier="quickcrate", weight=400)
    app.work()
    current = app.get_order(order["id"])
    assert current["shipments"][0]["status"] == "done" and current["shipments"][1]["status"] == "preparing"
    assert current["delivery_status"] == "partially_shipped"
    assert len(hub.pf_created) == 1 and hub.pf_created[0]["body"]["shipment_ref"] == first["id"]
    assert hub.pf_created[0]["body"]["weight_g"] == 900
    hub.qc_set(hub.qc_created[0]["job_id"], "ready")
    app.advance(30)
    app.work()
    current = app.get_order(order["id"])
    assert [s["status"] for s in current["shipments"]] == ["done", "done"]
    assert current["delivery_status"] == "shipped"
    codes = [s["tracking_code"] for s in current["shipments"]]
    assert len(set(codes)) == 2
    page = app.get(f"/track/{order['id']}", staff=None)
    assert all(code in page.text for code in codes)


def test_customer_is_told_per_delivery(app, hub):
    order, a, b = split_order(app)
    first, second = order["shipments"]
    app.ship(order["id"], shipment=first["id"])
    app.work()
    mails = [m for m in hub.messages() if order["id"] in m["subject"] and "shipped" in m["subject"]]
    assert len(mails) == 1
    assert mails[0]["subject"] == f"Part of order {order['id']} has shipped"
    assert "2 x Split A" in mails[0]["body"] and "Split B" not in mails[0]["body"]
    assert app.get_order(order["id"])["delivery_status"] == "partially_shipped"
    app.ship(order["id"], shipment=second["id"])
    app.work()
    mails = [m for m in hub.messages() if order["id"] in m["subject"] and "shipped" in m["subject"]]
    assert len(mails) == 2
    last = mails[1]
    assert last["subject"] == f"Order {order['id']} has shipped"
    assert "1 x Split B" in last["body"] and "Split A" not in last["body"]
    tracking = app.get_order(order["id"])["shipments"][1]["tracking_code"]
    assert tracking in last["body"]
    shipped = [e for e in app.get_order(order["id"])["emails"] if e["kind"] == "shipped"]
    assert sorted(e["shipment_id"] for e in shipped) == sorted([first["id"], second["id"]])


def test_partial_failure_and_retry(app, hub):
    order, a, b = split_order(app)
    first, second = order["shipments"]
    hub.fault("parcelfox.create", fail_next=4)
    app.request_label(order["id"], shipment=first["id"])
    for delay in (1, 2, 4, 0):
        app.work()
        app.advance(delay)
    hub.clear_faults()
    app.ship(order["id"], shipment=second["id"])
    current = app.get_order(order["id"])
    assert [s["status"] for s in current["shipments"]] == ["needs_attention", "done"]
    assert current["delivery_status"] == "partially_shipped"
    response = app.request_label(order["id"], shipment=first["id"])
    assert response.status_code == 202
    app.work()
    current = app.get_order(order["id"])
    assert current["delivery_status"] == "shipped"
    keys = {c["body"]["idempotency_key"] for c in hub.calls_to("parcelfox.create")}
    assert len(keys) == 2 and len(hub.pf_created) == 2


def test_single_parcel_orders_unchanged(app, hub):
    order = app.order()
    assert len(order["shipments"]) == 1
    shipped = app.ship(order["id"])
    assert shipped["delivery_status"] == "shipped"
    mails = [m for m in hub.messages() if order["id"] in m["subject"] and "shipped" in m["subject"]]
    assert [m["subject"] for m in mails] == [f"Order {order['id']} has shipped"]
