"""Request 2: ParcelFox labels — mapping, validation, persisted association, one parcel per
shipment under duplicate clicks and uncertain outcomes. From request 3 labels are queued, so
the same guarantees are checked through the worker."""

from conftest import ADDRESS, QUEUED, expect_error, fresh_client, parallel, shipment_of


def label_status_ok(response):
    assert response.status_code == (202 if QUEUED else 201), response.text[:500]


def test_new_order_has_unrequested_shipment(app):
    order = app.order()
    shipment = shipment_of(order)
    assert len(order["shipments"]) == 1 and shipment["status"] == "not_requested"
    assert shipment["tracking_code"] is None and shipment["carrier"] is None
    assert shipment["items"] == [{"product_id": order["items"][0]["product_id"], "quantity": 1}]
    carriers = {c["id"]: c for c in app.ok(app.get("/api/carriers"))["carriers"]}
    assert carriers["parcelfox"]["name"] == "ParcelFox" and carriers["parcelfox"]["configured"] is True


def test_label_maps_address_and_weight(app, hub):
    order = app.order()
    response = app.request_label(order["id"], weight=1234)
    label_status_ok(response)
    if QUEUED:
        app.work()
    shipment = shipment_of(app.get_order(order["id"]))
    created = hub.pf_created
    assert len(created) == 1
    sent = created[0]["body"]
    assert sent["address"] == ADDRESS and sent["weight_g"] == 1234
    assert sent["order_ref"] == order["id"] and sent["shipment_ref"] == shipment["id"]
    assert created[0]["token"] == "pf-test-token"
    label = created[0]["label"]
    assert shipment["status"] == "done" and shipment["carrier"] == "parcelfox"
    assert (shipment["tracking_code"], shipment["label_id"], shipment["label_text"]) == (
        label["tracking_code"], label["label_id"], label["label_text"])  # fmt: skip
    assert shipment["address"] == ADDRESS and shipment["weight_g"] == 1234


def test_label_persists_and_shows(fresh_app, hub):
    order = fresh_app.order()
    shipped = fresh_app.ship(order["id"])
    code = shipment_of(shipped)["tracking_code"]
    assert code and code == hub.pf_created[0]["label"]["tracking_code"]
    fresh_app.restart()
    assert shipment_of(fresh_app.get_order(order["id"]))["tracking_code"] == code
    page = fresh_app.get(f"/orders/{order['id']}")
    assert page.status_code == 200 and code in page.text


def test_validation_errors(app, hub):
    order = app.order()
    for field, value in (("name", ""), ("line1", "x" * 101), ("city", None), ("postcode", "1234567890123"),
                         ("country", "gb"), ("country", "GBR")):  # fmt: skip
        address = {**ADDRESS, field: value}
        response = app.request_label(order["id"], address=address)
        expect_error(response, 422, "invalid_address")
        assert response.json()["error"]["message"]
    missing = {k: v for k, v in ADDRESS.items() if k != "postcode"}
    expect_error(app.request_label(order["id"], address=missing), 422, "invalid_address")
    for weight in (0, 30001, 1.5, "100", True):
        expect_error(app.request_label(order["id"], weight=weight), 422, "invalid_weight")
    expect_error(app.request_label("no-such-order"), 404, "not_found")
    if QUEUED:
        app.work()
    assert hub.calls_to("parcelfox.create") == []
    assert shipment_of(app.get_order(order["id"]))["status"] == "not_requested"


def test_not_configured(bare_app, hub):
    order = bare_app.order()
    expect_error(bare_app.request_label(order["id"]), 409, "not_configured")
    carriers = {c["id"]: c for c in bare_app.ok(bare_app.get("/api/carriers"))["carriers"]}
    assert carriers["parcelfox"]["configured"] is False
    bad = bare_app.put("/api/carriers/parcelfox/credentials", json={"token": ""})
    expect_error(bad, 422, "invalid_request")
    bare_app.configure("parcelfox")
    assert "pf-test-token" not in bare_app.get("/api/carriers").text
    label_status_ok(bare_app.request_label(order["id"]))


def test_second_click_returns_existing_label(app, hub):
    order = app.order()
    first = app.ship(order["id"])
    again = app.request_label(order["id"], weight=999)
    assert again.status_code == 200, again.text
    if QUEUED:
        app.work()
    assert shipment_of(app.get_order(order["id"]))["tracking_code"] == shipment_of(first)["tracking_code"]
    assert len(hub.pf_created) == 1


def test_simultaneous_clicks_one_parcel(app, hub):
    order = app.order()
    clients = [fresh_client(app) for _ in range(5)]
    headers = app.headers("main")
    body = {"address": ADDRESS, "weight_g": 800}
    try:
        results = parallel(lambda i: clients[i].post(f"/api/orders/{order['id']}/label", json=body,
                                                      headers=headers), 5)  # fmt: skip
    finally:
        for client in clients:
            client.close()
    assert all(r.status_code in (200, 201, 202) for r in results), [r.text for r in results]
    if QUEUED:
        app.work()
    assert len(hub.pf_created) == 1
    assert shipment_of(app.get_order(order["id"]))["status"] == "done"


def test_unavailable_then_retry_one_parcel(app, hub):
    order = app.order()
    hub.fault("parcelfox.create", fail_next=1, fail_status=503)
    response = app.request_label(order["id"])
    if QUEUED:
        label_status_ok(response)
        app.work()
        assert shipment_of(app.get_order(order["id"]))["status"] == "waiting"
        app.advance(1)
        app.work()
    else:
        expect_error(response, 502, "carrier_unavailable")
        assert shipment_of(app.get_order(order["id"]))["status"] == "not_requested"
        assert app.request_label(order["id"]).status_code == 201
    assert shipment_of(app.get_order(order["id"]))["status"] == "done"
    assert len(hub.pf_created) == 1


def test_dropped_connection_after_creation(app, hub):
    order = app.order()
    hub.fault("parcelfox.create", drop_after=1)
    response = app.request_label(order["id"])
    if QUEUED:
        app.work()
        app.advance(1)
        app.work()
    else:
        expect_error(response, 502, "carrier_unavailable")
        assert app.request_label(order["id"]).status_code == 201
    shipment = shipment_of(app.get_order(order["id"]))
    assert len(hub.pf_created) == 1
    assert shipment["status"] == "done"
    assert shipment["tracking_code"] == hub.pf_created[0]["label"]["tracking_code"]


def test_carrier_refusal(app, hub):
    order = app.order()
    hub.fault("parcelfox.create", reject_next=1)
    response = app.request_label(order["id"])
    if QUEUED:
        app.work()
        shipment = shipment_of(app.get_order(order["id"]))
        assert shipment["status"] == "needs_attention"
        assert shipment["last_error"]["code"] == "carrier_rejected"
    else:
        expect_error(response, 502, "carrier_rejected")
    assert hub.pf_created == []
