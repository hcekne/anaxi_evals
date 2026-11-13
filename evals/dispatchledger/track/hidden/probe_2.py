"""Probe 2: KiteCourier — label first, tracking reference later."""

from conftest import ADDRESS, emails_of, expect_error, shipment_of, subset


def configure(app, staff="main"):
    key = "kc-test-key" if staff == "main" else "kc-harbour-key"
    response = app.put("/api/carriers/kitecourier/credentials", staff=staff, json={"api_key": key})
    assert response.status_code in (200, 204), response.text


def status(app, order, staff="main"):
    return shipment_of(app.get_order(order["id"], staff))


def kite_label(app, order, staff="main", **kw):
    response = app.request_label(order["id"], carrier="kitecourier", staff=staff, **kw)
    assert response.status_code == 202, response.text


def test_listed_and_not_configured(app):
    order = app.order(staff="harbour")
    expect_error(app.request_label(order["id"], carrier="kitecourier", staff="harbour"), 409, "not_configured")
    configure(app)
    carriers = {c["id"]: c for c in app.ok(app.get("/api/carriers"))["carriers"]}
    assert subset(carriers["kitecourier"], {"id": "kitecourier", "name": "KiteCourier", "configured": True})
    assert {"parcelfox", "quickcrate", "parcelpine"} <= set(carriers)


def test_label_then_tracking(app, hub):
    configure(app)
    order = app.order()
    kite_label(app, order, weight=1750)
    app.work()
    assert len(hub.kite_created) == 1
    item = hub.kite_created[0]
    assert item["body"]["mass_g"] == 1750 and item["body"]["deliver_to"] == ADDRESS
    assert item["token"] == "kc-test-key"
    shipment = status(app, order)
    assert shipment["status"] == "awaiting_tracking" and shipment["tracking_code"] is None
    assert shipment["label_text"] == item["label"]["content"] and shipment["label_id"] == item["consignment_id"]
    current = app.get_order(order["id"])
    assert current["delivery_status"] == "not_shipped"
    assert not [m for m in hub.messages() if order["id"] in m["subject"] and "shipped" in m["subject"]]
    assert "awaiting tracking" in app.get(f"/orders/{order['id']}").text.lower()
    app.advance(60)
    app.work()
    assert status(app, order)["status"] == "awaiting_tracking"
    tracking = hub.kite_assign(item["consignment_id"])
    app.advance(60)
    app.work()
    shipment = status(app, order)
    assert shipment["status"] == "done" and shipment["tracking_code"] == tracking
    assert app.get_order(order["id"])["delivery_status"] == "shipped"
    app.work()
    mails = [m for m in hub.messages() if order["id"] in m["subject"] and "shipped" in m["subject"]]
    assert len(mails) == 1 and tracking in mails[0]["body"] and "KiteCourier" in mails[0]["body"]
    assert len(emails_of(app.get_order(order["id"]), "shipped")) == 1
    assert len(hub.kite_created) == 1


def test_retries_and_no_duplicates(app, hub):
    configure(app)
    order = app.order()
    hub.fault("kitecourier.create", fail_next=1, fail_status=503)
    kite_label(app, order)
    app.work()
    assert status(app, order)["status"] == "waiting"
    hub.fault("kitecourier.create", drop_after=1)
    app.advance(1)
    app.work()
    app.advance(2)
    app.work()
    assert len(hub.kite_created) == 1
    assert status(app, order)["status"] == "awaiting_tracking"
    assert len({c["body"]["request_id"] for c in hub.calls_to("kitecourier.create")}) == 1


def test_per_shop_keys(app, hub):
    configure(app, staff="harbour")
    order = app.order(staff="harbour")
    kite_label(app, order, staff="harbour")
    app.work()
    assert [k["token"] for k in hub.kite_created] == ["kc-harbour-key"]
    hub.kite_assign(hub.kite_created[0]["consignment_id"])
    app.advance(60)
    app.work()
    assert status(app, order, "harbour")["status"] == "done"


def test_other_carriers_unchanged(app, hub):
    a, b = app.order(), app.order()
    app.ship(a["id"])
    app.ship(b["id"], carrier="parcelpine")
    assert status(app, a)["status"] == "done" and status(app, b)["status"] == "done"
    assert hub.kite_created == []
