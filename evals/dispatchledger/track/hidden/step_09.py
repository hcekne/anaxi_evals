"""Request 9: returns — delivered-quantity limit, idempotent references, restock to the shipping
warehouse, remaining value in orders and the report."""

from conftest import CURRENCIES, expect_error, fresh_client, parallel, read_csv, uid


def ret(app, order_id, lines, reference=None):
    body = {"reference": reference or uid("RET"),
            "items": [{"product_id": p, "quantity": q} for p, q in lines]}  # fmt: skip
    return app.post(f"/api/orders/{order_id}/returns", json=body)


def shipped_order(app, lines_spec, price=450):
    pids = [app.product(price=price, stock=10, name=f"Ret {i}") for i in range(len(lines_spec))]
    order = app.order(list(zip(pids, lines_spec)))
    app.ship(order["id"])
    return order, pids


def test_record_return(app):
    order, (pid,) = shipped_order(app, [3])
    stock_before = app.get_product(pid)["stock"]
    response = ret(app, order["id"], [(pid, 1)], "RET-1042-" + uid("x")[-4:])
    assert response.status_code == 201, response.text
    record = response.json()
    assert record["order_id"] == order["id"] and record["value"] == 450
    assert [(i["product_id"], i["quantity"], i["unit_price"], i["value"], i["name"]) for i in record["items"]] == [
        (pid, 1, 450, 450, "Ret 0")]  # fmt: skip
    assert app.get_product(pid)["stock"] == stock_before + 1
    current = app.get_order(order["id"])
    assert current["returned_value"] == 450 and current["remaining_value"] == 900
    assert [r["reference"] for r in current["returns"]] == [record["reference"]]
    page = app.get(f"/orders/{order['id']}")
    assert record["reference"] in page.text and "£9.00" in page.text


def test_reference_is_idempotent(app):
    order, (pid,) = shipped_order(app, [3])
    reference = uid("R")
    first = ret(app, order["id"], [(pid, 1)], reference)
    assert first.status_code == 201
    again = ret(app, order["id"], [(pid, 1)], reference)
    assert again.status_code == 200 and again.json()["reference"] == reference
    expect_error(ret(app, order["id"], [(pid, 2)], reference), 409, "duplicate_reference")
    other, (other_pid,) = shipped_order(app, [1])
    expect_error(ret(app, other["id"], [(other_pid, 1)], reference), 409, "duplicate_reference")
    current = app.get_order(order["id"])
    assert current["returned_value"] == 450 and len(current["returns"]) == 1


def test_double_click_records_once(app):
    order, (pid,) = shipped_order(app, [2])
    before = app.get_product(pid)["stock"]
    body = {"reference": uid("R"), "items": [{"product_id": pid, "quantity": 1}]}
    headers = app.headers("main")
    clients = [fresh_client(app) for _ in range(5)]
    try:
        results = parallel(lambda i: clients[i].post(f"/api/orders/{order['id']}/returns", json=body,
                                                      headers=headers), 5)  # fmt: skip
    finally:
        for client in clients:
            client.close()
    assert sorted(r.status_code for r in results) == [200] * 4 + [201]
    assert app.get_product(pid)["stock"] == before + 1
    assert len(app.get_order(order["id"])["returns"]) == 1


def test_cannot_exceed_delivered(app):
    order, (pid,) = shipped_order(app, [3])
    assert ret(app, order["id"], [(pid, 2)]).status_code == 201
    expect_error(ret(app, order["id"], [(pid, 2)]), 422, "return_exceeds_delivered")
    assert ret(app, order["id"], [(pid, 1)]).status_code == 201
    expect_error(ret(app, order["id"], [(pid, 1)]), 422, "return_exceeds_delivered")
    unshipped = app.order()
    pid2 = unshipped["items"][0]["product_id"]
    expect_error(ret(app, unshipped["id"], [(pid2, 1)]), 422, "return_exceeds_delivered")
    expect_error(ret(app, order["id"], [(pid2, 1)]), 422, "return_exceeds_delivered")
    assert app.get_order(order["id"])["returned_value"] == 3 * 450


def test_return_validation(app):
    order, (pid,) = shipped_order(app, [2])
    expect_error(ret(app, order["id"], [(pid, 0)]), 422, "invalid_quantity")
    expect_error(ret(app, order["id"], [(pid, 1)], "bad ref!"), 422, "invalid_request")
    expect_error(ret(app, order["id"], []), 422, "invalid_request")
    expect_error(ret(app, order["id"], [(pid, 1), (pid, 1)]), 422, "invalid_request")
    expect_error(ret(app, "no-such-order", [(pid, 1)]), 404, "not_found")
    assert app.get_order(order["id"])["returns"] == []


def test_returns_across_shipments_restock_their_warehouse(app):
    a = app.product(price=1000, stock=1, south=2, name="Across A")
    order = app.order([(a, 3)])
    north, south = order["shipments"]
    assert (north["warehouse"], south["warehouse"]) == ("north", "south")
    app.ship(order["id"], shipment=north["id"])
    app.ship(order["id"], shipment=south["id"])
    assert app.get_product(a)["warehouses"] == {"north": 0, "south": 0}
    assert ret(app, order["id"], [(a, 2)]).status_code == 201
    assert app.get_product(a)["warehouses"] == {"north": 1, "south": 1}
    current = app.get_order(order["id"])
    assert (current["returned_value"], current["remaining_value"]) == (2000, 1000)


def test_partial_delivery_limits_returns(app):
    a = app.product(price=100, stock=1, south=1)
    order = app.order([(a, 2)])
    app.ship(order["id"], shipment=order["shipments"][1]["id"])
    expect_error(ret(app, order["id"], [(a, 2)]), 422, "return_exceeds_delivered")
    assert ret(app, order["id"], [(a, 1)]).status_code == 201


def test_report_shows_remaining_value(app):
    day = app.next_day()
    order, (pid,) = shipped_order(app, [4], price=250)
    app.order(price=1000)
    app.next_day()
    assert ret(app, order["id"], [(pid, 1)]).status_code == 201
    report = app.ok(app.get("/api/reports/daily", params={"from": day, "to": app_day(app)}))["days"]
    assert len(report) == 1
    entry = report[0]
    assert entry["date"] == day and entry["orders"] == 2 and entry["items"] == 5
    assert (entry["original_value"], entry["returned_value"], entry["remaining_value"]) == (2000, 250, 1750)
    assert entry["value"] == 2000
    rows = read_csv(app.get("/api/reports/daily.csv", params={"from": day, "to": day}).text)
    expected = ["date", "orders", "items", "original_value", "returned_value", "remaining_value"]
    if CURRENCIES:
        expected.insert(1, "currency")
    assert rows[0] == expected
    row = dict(zip(rows[0], rows[1]))
    assert (row["original_value"], row["returned_value"], row["remaining_value"]) == ("20.00", "2.50", "17.50")


def app_day(app):
    from conftest import day_of

    return day_of(app.now)


def test_returns_persist(fresh_app):
    order, (pid,) = shipped_order(fresh_app, [2])
    reference = uid("R")
    assert ret(fresh_app, order["id"], [(pid, 1)], reference).status_code == 201
    fresh_app.restart()
    assert fresh_app.get_order(order["id"])["returned_value"] == 450
    assert ret(fresh_app, order["id"], [(pid, 1)], reference).status_code == 200
    assert fresh_app.get_order(order["id"])["returned_value"] == 450
