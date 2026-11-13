"""Request 12: per-shop warehouse pause that lets the current parcel finish, graceful worker
shutdown, and queued work surviving a worker replacement."""

import signal
import time

from conftest import emails_of, expect_error, shipment_of, stop_worker, wait_for


def warehouses(app, staff="main"):
    return {w["id"]: w for w in app.ok(app.get("/api/warehouses", staff=staff))["warehouses"]}


def pause(app, warehouse, staff="main"):
    response = app.post(f"/api/warehouses/{warehouse}/pause", staff=staff)
    assert response.status_code == 200, response.text
    assert response.json()["id"] == warehouse and response.json()["paused"] is True
    return response.json()


def resume(app, warehouse, staff="main"):
    response = app.post(f"/api/warehouses/{warehouse}/resume", staff=staff)
    assert response.status_code == 200, response.text
    assert response.json()["paused"] is False
    return response.json()


def order_at(app, warehouse, staff="main"):
    pid = app.product(stock=5 if warehouse == "north" else 0, south=5 if warehouse == "south" else 0, staff=staff)
    order = app.order([(pid, 1)], staff=staff)
    assert shipment_of(order)["warehouse"] == warehouse
    return order


def state(app, order, staff="main"):
    return shipment_of(app.get_order(order["id"], staff))["status"]


def test_listing_and_errors(app):
    listed = warehouses(app)
    assert set(listed) == {"north", "south"}
    assert all(w["paused"] is False for w in listed.values())
    assert {"waiting", "working"} <= set(listed["north"])
    expect_error(app.post("/api/warehouses/east/pause"), 404, "not_found")
    expect_error(app.post("/api/warehouses/east/resume"), 404, "not_found")
    page = app.get("/warehouses")
    assert page.status_code == 200 and "north" in page.text and "south" in page.text


def test_pause_holds_only_that_warehouse(app, hub):
    north, south = order_at(app, "north"), order_at(app, "south")
    pause(app, "north")
    pause(app, "north")
    try:
        assert app.request_label(north["id"]).status_code == 202
        assert app.request_label(south["id"]).status_code == 202
        started = time.monotonic()
        app.work()
        assert time.monotonic() - started < 20
        assert (state(app, north), state(app, south)) == ("waiting", "done")
        listed = warehouses(app)
        assert listed["north"]["paused"] is True and listed["north"]["waiting"] >= 1
        assert listed["south"]["paused"] is False
        app.advance(120)
        app.work()
        assert state(app, north) == "waiting"
    finally:
        resume(app, "north")
        resume(app, "north")
    app.work()
    assert state(app, north) == "done"
    assert len(hub.pf_created) == 2


def test_emails_continue_while_paused(app, hub):
    pause(app, "north")
    try:
        order = order_at(app, "north")
        app.work()
        assert emails_of(app.get_order(order["id"]), "accepted")[0]["status"] == "sent"
    finally:
        resume(app, "north")


def test_pause_is_per_shop(app, hub):
    app.configure("parcelfox", staff="harbour")
    pause(app, "north", staff="harbour")
    try:
        assert warehouses(app)["north"]["paused"] is False
        mine, theirs = order_at(app, "north"), order_at(app, "north", staff="harbour")
        app.request_label(mine["id"])
        app.request_label(theirs["id"], staff="harbour")
        app.work()
        assert state(app, mine) == "done" and state(app, theirs, "harbour") == "waiting"
        assert warehouses(app, "harbour")["north"]["waiting"] == 1
    finally:
        resume(app, "north", staff="harbour")
    app.work()
    assert state(app, theirs, "harbour") == "done"


def test_current_parcel_finishes_when_paused(app, hub):
    first, second = order_at(app, "north"), order_at(app, "north")
    app.work()  # accepted emails out of the way
    hub.fault("parcelfox.create", latency=2.5)
    app.request_label(first["id"])
    worker = app.worker_bg()
    try:
        assert wait_for(lambda: state(app, first) == "working", timeout=8)
        pause(app, "north")
        app.request_label(second["id"])
        assert wait_for(lambda: state(app, first) == "done", timeout=15)
        assert wait_for(lambda: emails_of(app.get_order(first["id"]), "shipped")
                        and emails_of(app.get_order(first["id"]), "shipped")[0]["status"] == "sent", timeout=10)  # fmt: skip
        time.sleep(1.5)
        assert state(app, second) == "waiting"
        resume(app, "north")
        assert wait_for(lambda: state(app, second) == "done", timeout=15)
    finally:
        stop_worker(worker)
        resume(app, "north")
    assert len(hub.pf_created) == 2


def test_graceful_shutdown_finishes_current_attempt(app, hub):
    first, second = order_at(app, "south"), order_at(app, "south")
    app.work()
    hub.fault("parcelfox.create", latency=3)
    app.request_label(first["id"])
    app.request_label(second["id"])
    worker = app.worker_bg()
    assert wait_for(lambda: "working" in (state(app, first), state(app, second)), timeout=8)
    started = time.monotonic()
    code = stop_worker(worker, signal.SIGTERM, timeout=20)
    assert code == 0 and time.monotonic() - started < 15
    states = {state(app, first), state(app, second)}
    assert "working" not in states and "done" in states
    hub.clear_faults()
    app.work()
    assert {state(app, first), state(app, second)} == {"done"}
    assert len(hub.pf_created) == 2


def test_pause_and_queue_survive_restart(fresh_app, hub):
    order = order_at(fresh_app, "north")
    pause(fresh_app, "north")
    fresh_app.request_label(order["id"])
    fresh_app.restart()
    fresh_app.work()
    assert warehouses(fresh_app)["north"]["paused"] is True
    assert state(fresh_app, order) == "waiting"
    resume(fresh_app, "north")
    fresh_app.restart()
    fresh_app.work()
    assert state(fresh_app, order) == "done" and len(hub.pf_created) == 1


def test_killed_worker_after_acceptance_does_not_duplicate(app, hub):
    order = order_at(app, "south")
    app.work()
    hub.fault("parcelfox.create", latency=1.5)
    app.request_label(order["id"])
    worker = app.worker_bg()
    try:
        assert wait_for(lambda: state(app, order) == "working", timeout=8)
    finally:
        worker.kill()
        worker.wait()
    time.sleep(1.8)
    hub.clear_faults()
    app.advance(61)
    app.work()
    assert state(app, order) == "done" and len(hub.pf_created) == 1
