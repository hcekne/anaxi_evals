"""Request 14: ParcelPine — exact kilogram conversion, unsupported destinations, rate-limit
delays, deduplication, per-shop credentials, existing carriers unchanged."""

from conftest import ADDRESS, emails_of, expect_error, parse_time, shipment_of, subset


def pine(app, order_id, weight=1250, address=None, staff="main", shipment=None):
    response = app.request_label(order_id, carrier="parcelpine", weight=weight, address=address,
                                 staff=staff, shipment=shipment)  # fmt: skip
    assert response.status_code == 202, response.text
    return response


def status(app, order, staff="main"):
    return shipment_of(app.get_order(order["id"], staff))


def test_listed_and_configurable(app, bare_app):
    carriers = {c["id"]: c for c in app.ok(app.get("/api/carriers"))["carriers"]}
    assert subset(carriers["parcelpine"], {"id": "parcelpine", "name": "ParcelPine", "configured": True})
    assert {"parcelfox", "quickcrate"} <= set(carriers)
    order = bare_app.order()
    expect_error(bare_app.request_label(order["id"], carrier="parcelpine"), 409, "not_configured")


def test_label_mapping_and_weight(app, hub):
    for grams, kg in ((1250, "1.250"), (5, "0.005"), (30000, "30.000"), (1000, "1.000"), (999, "0.999")):
        order = app.order()
        pine(app, order["id"], weight=grams)
        app.work()
        entry = hub.pine_created[-1]
        assert entry["body"]["weight_kg"] == kg
        shipment = status(app, order)
        assert shipment["status"] == "done", shipment
        assert (shipment["tracking_code"], shipment["label_text"], shipment["label_id"]) == (
            entry["shipment"]["tracking"], entry["shipment"]["document"]["content"], entry["shipment"]["reference"])  # fmt: skip
    body = hub.pine_created[0]["body"]
    assert body["recipient"] == {"name": ADDRESS["name"], "street": ADDRESS["line1"], "city": ADDRESS["city"],
                                 "postal_code": ADDRESS["postcode"], "country_code": ADDRESS["country"]}  # fmt: skip
    assert hub.pine_created[0]["token"] == "pp-test-token"


def test_unsupported_destination(app, hub):
    order = app.order()
    pine(app, order["id"], address={**ADDRESS, "country": "US"})
    app.work()
    app.advance(30)
    app.work()
    shipment = status(app, order)
    assert shipment["status"] == "needs_attention"
    assert shipment["last_error"]["code"] == "destination_unsupported"
    assert "US" in shipment["last_error"]["message"]
    assert len(hub.calls_to("parcelpine.create")) <= 1 and hub.pine_created == []
    page = app.get(f"/orders/{order['id']}")
    assert "needs attention" in page.text.lower()


def test_rate_limit_waits_for_retry_after(app, hub):
    order = app.order()
    hub.fault("parcelpine.create", fail_next=1, fail_status=429, retry_after=7)
    pine(app, order["id"])
    replied = app.now
    app.work()
    shipment = status(app, order)
    assert shipment["status"] == "waiting"
    assert parse_time(shipment["next_attempt_at"]) == replied + 7
    app.advance(4)
    app.work()
    assert len(hub.calls_to("parcelpine.create")) == 1
    app.advance(3)
    app.work()
    assert status(app, order)["status"] == "done" and len(hub.calls_to("parcelpine.create")) == 2


def test_rate_limits_count_towards_four_attempts(app, hub):
    order = app.order()
    hub.fault("parcelpine.create", fail_next=10, fail_status=429, retry_after=3)
    pine(app, order["id"])
    for _ in range(4):
        app.work()
        app.advance(3)
    shipment = status(app, order)
    assert shipment["status"] == "needs_attention" and shipment["last_error"]["code"] == "carrier_unavailable"
    assert shipment["last_error"]["message"]
    assert len(hub.calls_to("parcelpine.create")) == 4


def test_no_duplicate_parcels(app, hub):
    order = app.order()
    hub.fault("parcelpine.create", drop_after=1)
    pine(app, order["id"])
    app.work()
    app.advance(1)
    app.work()
    hub.fault("parcelpine.create", fail_next=1, fail_status=503)
    again = app.request_label(order["id"], carrier="parcelpine")
    assert again.status_code == 200
    app.work()
    shipment = status(app, order)
    assert shipment["status"] == "done" and len(hub.pine_created) == 1
    assert shipment["tracking_code"] == hub.pine_created[0]["shipment"]["tracking"]


def test_shipped_email_and_split_parcels(app, hub):
    pid = app.product(stock=1, south=1, name="Pine Split")
    order = app.order([(pid, 2)])
    first, second = order["shipments"]
    pine(app, order["id"], shipment=first["id"])
    app.ship(order["id"], shipment=second["id"])
    current = app.get_order(order["id"])
    assert current["delivery_status"] == "shipped"
    assert [s["carrier"] for s in current["shipments"]] == ["parcelpine", "parcelfox"]
    mails = [m for m in hub.messages() if order["id"] in m["subject"] and "shipped" in m["subject"]]
    assert any("ParcelPine" in m["body"] for m in mails) and len(mails) == 2
    assert len(emails_of(current, "shipped")) == 2


def test_per_shop_credentials(app, hub):
    order = app.order(staff="harbour")
    expect_error(app.request_label(order["id"], carrier="parcelpine", staff="harbour"), 409, "not_configured")
    app.configure("parcelpine", staff="harbour")
    pine(app, order["id"], staff="harbour")
    app.work()
    assert status(app, order, "harbour")["status"] == "done"
    assert [e["token"] for e in hub.pine_created] == ["pp-harbour-token"]


def test_existing_carriers_unchanged(app, hub):
    a, b = app.order(), app.order()
    app.ship(a["id"], carrier="parcelfox")
    app.request_label(b["id"], carrier="quickcrate")
    app.work()
    hub.qc_set(hub.qc_created[0]["job_id"], "ready")
    app.advance(30)
    app.work()
    assert status(app, a)["status"] == "done" and status(app, b)["status"] == "done"
    assert hub.pine_created == []
