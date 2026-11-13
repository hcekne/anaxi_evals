"""Request 3: separate worker, queued labels, statuses, bounded retries on the virtual clock,
reconciliation after lost acknowledgements, durability and abandoned work."""

import signal
import time

from conftest import (ADDRESS, expect_error, iso, parse_time, shipment_of, stop_worker,
                      wait_for)  # fmt: skip


def status(app, order_id, index=0):
    return shipment_of(app.get_order(order_id), index)


def test_label_is_queued_not_sent(app, hub):
    order = app.order()
    response = app.request_label(order["id"], weight=700)
    assert response.status_code == 202, response.text
    shipment = shipment_of(response.json())
    assert shipment["status"] == "waiting" and shipment["address"] == ADDRESS and shipment["weight_g"] == 700
    assert hub.calls_to("parcelfox.create") == []
    again = app.request_label(order["id"])
    assert again.status_code == 200
    app.work()
    done = status(app, order["id"])
    assert done["status"] == "done" and done["tracking_code"] == hub.pf_created[0]["label"]["tracking_code"]
    assert len(hub.pf_created) == 1
    assert app.request_label(order["id"]).status_code == 200


def test_checkout_and_label_requests_stay_fast_while_carrier_hangs(app, hub):
    hub.fault("parcelfox.create", latency=2.5)
    first = app.order()
    app.request_label(first["id"])
    worker = app.worker_bg()
    try:
        assert wait_for(lambda: status(app, first["id"])["status"] == "working", timeout=8)
        started = time.monotonic()
        second = app.order()
        assert app.request_label(second["id"]).status_code == 202
        assert time.monotonic() - started < 2.0
        page = app.get(f"/orders/{first['id']}")
        assert page.status_code == 200 and "working" in page.text.lower()
        assert wait_for(lambda: status(app, first["id"])["status"] == "done", timeout=15)
        assert wait_for(lambda: status(app, second["id"])["status"] == "done", timeout=15)
    finally:
        stop_worker(worker)
    assert len(hub.pf_created) == 2


def test_continuous_worker_picks_up_new_work(app, hub):
    worker = app.worker_bg()
    try:
        time.sleep(1.0)
        order = app.order()
        app.request_label(order["id"])
        assert wait_for(lambda: status(app, order["id"])["status"] == "done", timeout=10)
    finally:
        stop_worker(worker, signal.SIGINT)
    assert len(hub.pf_created) == 1


def test_retry_schedule_on_virtual_clock(app, hub):
    order = app.order()
    hub.fault("parcelfox.create", fail_next=3, fail_status=503)
    app.request_label(order["id"])
    for attempt, delay in ((1, 1), (2, 2), (3, 4)):
        failed_at = app.now
        app.work()
        shipment = status(app, order["id"])
        assert shipment["status"] == "waiting", shipment
        assert shipment["attempts"] == attempt
        assert parse_time(shipment["next_attempt_at"]) == failed_at + delay
        assert shipment["last_error"] and shipment["last_error"]["code"]
        app.advance(delay - 0.5)
        app.work()
        assert len(hub.calls_to("parcelfox.create")) == attempt, "retried before its delay"
        app.advance(0.5)
    app.work()
    shipment = status(app, order["id"])
    assert shipment["status"] == "done" and len(hub.calls_to("parcelfox.create")) == 4
    assert len(hub.pf_created) == 1


def test_needs_attention_after_four_failures_and_requeue(app, hub):
    order = app.order()
    hub.fault("parcelfox.create", fail_next=10, fail_status=500)
    app.request_label(order["id"])
    for delay in (1, 2, 4, 0):
        app.work()
        app.advance(delay)
    shipment = status(app, order["id"])
    assert shipment["status"] == "needs_attention"
    assert shipment["last_error"]["code"] == "carrier_unavailable"
    assert len(hub.calls_to("parcelfox.create")) == 4
    app.advance(60)
    app.work()
    assert len(hub.calls_to("parcelfox.create")) == 4
    page = app.get(f"/orders/{order['id']}")
    assert "needs attention" in page.text.lower()
    hub.clear_faults()
    again = app.request_label(order["id"])
    assert again.status_code == 202 and shipment_of(again.json())["status"] == "waiting"
    assert shipment_of(again.json())["attempts"] == 0
    app.work()
    assert status(app, order["id"])["status"] == "done"
    keys = {c["body"]["idempotency_key"] for c in hub.calls_to("parcelfox.create")}
    assert len(keys) == 1 and len(hub.pf_created) == 1


def test_lost_acknowledgement_is_reconciled(app, hub):
    order = app.order()
    hub.fault("parcelfox.create", drop_after=1)
    app.request_label(order["id"])
    app.work()
    shipment = status(app, order["id"])
    assert shipment["status"] == "waiting" and len(hub.pf_created) == 1
    app.advance(1)
    app.work()
    shipment = status(app, order["id"])
    assert shipment["status"] == "done"
    assert shipment["tracking_code"] == hub.pf_created[0]["label"]["tracking_code"]
    assert len(hub.pf_created) == 1


def test_rate_limit_is_transient(app, hub):
    order = app.order()
    hub.fault("parcelfox.create", fail_next=1, fail_status=429, retry_after=1)
    app.request_label(order["id"])
    app.work()
    assert status(app, order["id"])["status"] == "waiting"
    app.advance(1)
    app.work()
    assert status(app, order["id"])["status"] == "done"


def test_queue_survives_restarts(fresh_app, hub):
    order = fresh_app.order()
    fresh_app.request_label(order["id"])
    fresh_app.restart()
    assert shipment_of(fresh_app.get_order(order["id"]))["status"] == "waiting"
    fresh_app.stop()
    try:
        fresh_app.work()
    finally:
        fresh_app.start()
    assert shipment_of(fresh_app.get_order(order["id"]))["status"] == "done"
    assert len(hub.pf_created) == 1


def test_abandoned_work_is_taken_up_after_60_seconds(app, hub):
    order = app.order()
    hub.fault("parcelfox.create", latency=1.5)
    app.request_label(order["id"])
    worker = app.worker_bg()
    try:
        assert wait_for(lambda: status(app, order["id"])["status"] == "working", timeout=8)
    finally:
        worker.kill()
        worker.wait()
    time.sleep(1.8)  # the carrier finishes creating the label nobody hears about
    hub.clear_faults()
    assert status(app, order["id"])["status"] == "working"
    app.advance(30)
    app.work()
    assert status(app, order["id"])["status"] == "working"
    app.advance(31)
    app.work()
    shipment = status(app, order["id"])
    assert shipment["status"] == "done"
    assert len(hub.pf_created) == 1
    assert shipment["tracking_code"] == hub.pf_created[0]["label"]["tracking_code"]


def test_validation_unchanged(app):
    order = app.order()
    expect_error(app.request_label(order["id"], weight=0), 422, "invalid_weight")
    expect_error(app.request_label(order["id"], address={**ADDRESS, "country": "x"}), 422, "invalid_address")
    assert shipment_of(app.get_order(order["id"]))["next_attempt_at"] is None
    assert iso(app.now)
