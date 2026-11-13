"""Probe 4: a carrier cut-off pause that ends by itself; old pauses and queued work unchanged."""

from conftest import expect_error, iso, shipment_of


def warehouses(app, staff="main"):
    return {w["id"]: w for w in app.ok(app.get("/api/warehouses", staff=staff))["warehouses"]}


def south_order(app, staff="main"):
    pid = app.product(stock=0, south=5, staff=staff)
    order = app.order([(pid, 1)], staff=staff)
    assert shipment_of(order)["warehouse"] == "south"
    return order


def state(app, order, staff="main"):
    return shipment_of(app.get_order(order["id"], staff))["status"]


def test_cutoff_ends_by_itself(app, hub):
    order = south_order(app)
    until = iso(app.now + 300)
    response = app.post("/api/warehouses/south/pause", json={"reason": "carrier_cutoff", "until": until})
    assert response.status_code == 200, response.text
    entry = response.json()
    assert (entry["paused"], entry["reason"], entry["until"]) == (True, "carrier_cutoff", until)
    app.request_label(order["id"])
    app.work()
    assert state(app, order) == "waiting"
    app.advance(299)
    app.work()
    assert state(app, order) == "waiting" and warehouses(app)["south"]["paused"] is True
    app.advance(1)
    entry = warehouses(app)["south"]
    assert (entry["paused"], entry["reason"], entry["until"]) == (False, None, None)
    app.work()
    assert state(app, order) == "done" and len(hub.pf_created) == 1


def test_manual_pause_is_unchanged(app):
    order = south_order(app)
    response = app.post("/api/warehouses/south/pause")
    assert response.status_code == 200
    assert (response.json()["reason"], response.json()["until"]) == ("manual", None)
    try:
        app.request_label(order["id"])
        app.advance(3600)
        app.work()
        assert state(app, order) == "waiting"
    finally:
        entry = app.ok(app.post("/api/warehouses/south/resume"))
    assert (entry["paused"], entry["reason"], entry["until"]) == (False, None, None)
    app.work()
    assert state(app, order) == "done"


def test_resume_ends_a_cutoff_early(app):
    order = south_order(app)
    app.ok(app.post("/api/warehouses/south/pause", json={"reason": "carrier_cutoff", "until": iso(app.now + 900)}))
    app.request_label(order["id"])
    app.work()
    assert state(app, order) == "waiting"
    app.ok(app.post("/api/warehouses/south/resume"))
    app.work()
    assert state(app, order) == "done"


def test_validation(app):
    for body in ({"reason": "lunch"}, {"reason": "carrier_cutoff"}, {"reason": "carrier_cutoff", "until": "soon"},
                 {"reason": "carrier_cutoff", "until": iso(app.now - 10)},
                 {"reason": "manual", "until": iso(app.now + 10)}):
        expect_error(app.post("/api/warehouses/north/pause", json=body), 422, "invalid_request")
    assert warehouses(app)["north"]["paused"] is False


def test_cutoff_is_per_shop_and_survives_restart(fresh_app):
    fresh_app.configure("parcelfox", staff="harbour")
    until = iso(fresh_app.now + 120)
    fresh_app.ok(fresh_app.post("/api/warehouses/south/pause", staff="harbour",
                                json={"reason": "carrier_cutoff", "until": until}))
    mine, theirs = south_order(fresh_app), south_order(fresh_app, staff="harbour")
    fresh_app.request_label(mine["id"])
    fresh_app.request_label(theirs["id"], staff="harbour")
    fresh_app.restart()
    fresh_app.work()
    assert state(fresh_app, mine) == "done" and state(fresh_app, theirs, "harbour") == "waiting"
    assert warehouses(fresh_app, "harbour")["south"]["until"] == until
    fresh_app.advance(120)
    fresh_app.work()
    assert state(fresh_app, theirs, "harbour") == "done"
