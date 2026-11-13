"""Request 7: two warehouses, stock feed revisions, reservations survive snapshots,
preferred/fallback whole-order allocation."""

import itertools

from conftest import ADA, expect_error, fresh_client, parallel, shipment_of

REV = itertools.count(5000)


def snap(warehouse, sku, available, revision=None):
    return {"warehouse": warehouse, "sku": sku, "available": available,
            "revision": next(REV) if revision is None else revision}  # fmt: skip


def push(app, *snapshots, staff="main"):
    return app.post("/api/warehouse-feed", staff=staff, json={"snapshots": list(snapshots)})


def levels(app, pid):
    product = app.get_product(pid)
    return product["stock"], product["warehouses"]


def prefer(app, warehouse):
    response = app.put("/api/warehouse-preference", json={"preferred": warehouse})
    assert response.status_code == 200 and response.json() == {"preferred": warehouse}, response.text


def test_feed_applies_newer_revisions_only(app):
    pid = app.product(feed=False)
    result = app.ok(push(app, snap("north", pid, 5, 10), snap("south", pid, 2, 3)))
    assert result == {"applied": 2, "ignored": 0}
    assert levels(app, pid) == (7, {"north": 5, "south": 2})
    result = app.ok(push(app, snap("north", pid, 9, 9), snap("north", pid, 8, 10), snap("south", pid, 4, 4)))
    assert result == {"applied": 1, "ignored": 2}
    assert levels(app, pid) == (9, {"north": 5, "south": 4})


def test_new_product_has_no_stock(app):
    pid = app.product(feed=False)
    assert levels(app, pid) == (0, {"north": 0, "south": 0})
    expect_error(app.checkout([(pid, 1)]), 409, "out_of_stock")


def test_snapshots_do_not_erase_reservations(app):
    pid = app.product(feed=False)
    app.ok(push(app, snap("north", pid, 5, 1)))
    order = app.order([(pid, 2)])
    assert shipment_of(order)["warehouse"] == "north"
    assert levels(app, pid)[1]["north"] == 3
    app.ok(push(app, snap("north", pid, 5, 2)))
    assert levels(app, pid)[1]["north"] == 3
    app.ok(push(app, snap("north", pid, 5, 2)))
    app.ok(push(app, snap("north", pid, 4, 3)))
    assert levels(app, pid)[1]["north"] == 2
    app.ship(order["id"])
    assert levels(app, pid)[1]["north"] == 2
    app.ok(push(app, snap("north", pid, 2, 4)))
    assert levels(app, pid)[1]["north"] == 2


def test_stale_snapshot_never_puts_stock_back(app):
    pid = app.product(feed=False)
    app.ok(push(app, snap("south", pid, 1, 7)))
    app.ok(push(app, snap("south", pid, 0, 8)))
    app.ok(push(app, snap("south", pid, 6, 7)))
    app.ok(push(app, snap("south", pid, 6, 5)))
    assert levels(app, pid) == (0, {"north": 0, "south": 0})


def test_preferred_warehouse_and_fallback(app):
    a, b = app.product(feed=False), app.product(feed=False)
    app.ok(push(app, snap("north", a, 5), snap("north", b, 5), snap("south", a, 5), snap("south", b, 1)))
    assert app.ok(app.get("/api/warehouse-preference")) == {"preferred": "north"}
    try:
        prefer(app, "south")
        first = app.order([(a, 1), (b, 1)])
        assert shipment_of(first)["warehouse"] == "south"
        second = app.order([(a, 1), (b, 1)])
        assert shipment_of(second)["warehouse"] == "north"
        assert levels(app, a)[1] == {"north": 4, "south": 4}
        assert levels(app, b)[1] == {"north": 4, "south": 0}
        expect_error(app.put("/api/warehouse-preference", json={"preferred": "east"}), 422, "unknown_warehouse")
    finally:
        prefer(app, "north")
    third = app.order([(a, 2)])
    assert shipment_of(third)["warehouse"] == "north"


def test_not_enough_anywhere(app):
    a, b = app.product(feed=False), app.product(feed=False)
    app.ok(push(app, snap("north", a, 2), snap("south", a, 1), snap("north", b, 1)))
    expect_error(app.checkout([(a, 4)]), 409, "out_of_stock")
    expect_error(app.checkout([(a, 1), (b, 2)]), 409, "out_of_stock")
    assert levels(app, a) == (3, {"north": 2, "south": 1})
    assert levels(app, b) == (1, {"north": 1, "south": 0})


def test_feed_validation_is_atomic(app):
    pid = app.product(feed=False)
    expect_error(push(app, snap("north", pid, 3), snap("east", pid, 3)), 422, "unknown_warehouse")
    expect_error(push(app, snap("north", pid, 3), snap("north", "ghost-sku", 3)), 422, "unknown_product")
    for bad in (snap("north", pid, -1), snap("north", pid, "3"), {"warehouse": "north", "sku": pid, "available": 1}):
        expect_error(push(app, snap("south", pid, 2), bad), 422, "invalid_request")
    expect_error(app.post("/api/warehouse-feed", json={}), 422, "invalid_request")
    assert levels(app, pid) == (0, {"north": 0, "south": 0})


def test_sample_stock_moved_to_north(fresh_app):
    product = fresh_app.get_product("apron")
    assert product["stock"] == 3 and product["warehouses"] == {"north": 3, "south": 0}


def test_concurrent_checkouts_across_warehouses(app):
    pid = app.product(feed=False)
    app.ok(push(app, snap("north", pid, 1), snap("south", pid, 1)))
    clients = [fresh_client(app) for _ in range(6)]
    body = {"customer": ADA, "items": [{"product_id": pid, "quantity": 1}]}
    try:
        results = parallel(lambda i: clients[i].post("/api/orders", json=body), 6)
    finally:
        for client in clients:
            client.close()
    created = [r.json() for r in results if r.status_code == 201]
    assert len(created) == 2 and sum(r.status_code == 409 for r in results) == 4
    assert sorted(shipment_of(o)["warehouse"] for o in created) == ["north", "south"]
    assert levels(app, pid) == (0, {"north": 0, "south": 0})
