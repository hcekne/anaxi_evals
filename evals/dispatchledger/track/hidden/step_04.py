"""Request 4: MailPost emails on acceptance and shipping — exactly once, retried off the
shipping path, failure visible and retryable."""

from conftest import ADA, GRACE, emails_of, expect_error, money, shipment_of


def mails(hub, order_id, subject_part=""):
    return [m for m in hub.messages() if order_id in m["subject"] and subject_part in m["subject"]]


def test_accepted_email(app, hub):
    a, b = app.product(price=450, name="Breakfast Tea X"), app.product(price=1250, name="Enamel Mug X")
    order = app.order([(a, 2), (b, 1)], customer=GRACE)
    queued = emails_of(order, "accepted") or emails_of(app.get_order(order["id"]), "accepted")
    assert len(queued) == 1 and queued[0]["status"] in ("waiting", "working")
    assert hub.calls_to("mailpost.send") == []
    app.work()
    sent = mails(hub, order["id"])
    assert len(sent) == 1
    message = sent[0]
    assert message["to"] == GRACE["email"]
    assert message["subject"] == f"Order {order['id']} accepted"
    assert "2 x Breakfast Tea X £9.00" in message["body"]
    assert "1 x Enamel Mug X £12.50" in message["body"]
    assert f"Total: {money(2150)}" in message["body"]
    assert f"{app.public_url}/track/{order['id']}" in message["body"]
    assert hub.calls_to("mailpost.send")[0]["headers"]["x-mailpost-key"] == "mp-test-key"
    record = emails_of(app.get_order(order["id"]), "accepted")[0]
    assert record["status"] == "sent" and record["shipment_id"] is None


def test_shipped_email(app, hub):
    pid = app.product(name="Canvas Apron X")
    order = app.order([(pid, 3)])
    shipped = app.ship(order["id"])
    shipment = shipment_of(shipped)
    app.work()
    sent = mails(hub, order["id"], "has shipped")
    assert len(sent) == 1
    message = sent[0]
    assert message["subject"] == f"Order {order['id']} has shipped"
    assert message["to"] == ADA["email"]
    assert "ParcelFox" in message["body"] and shipment["tracking_code"] in message["body"]
    assert "3 x Canvas Apron X" in message["body"]
    assert f"/track/{order['id']}" in message["body"]
    record = emails_of(app.get_order(order["id"]), "shipped")
    assert len(record) == 1 and record[0]["shipment_id"] == shipment["id"] and record[0]["status"] == "sent"


def test_each_email_once_across_runs_and_restarts(fresh_app, hub):
    order = fresh_app.order()
    fresh_app.work()
    fresh_app.restart()
    fresh_app.work()
    fresh_app.ship(fresh_app.get_order(order["id"])["id"])
    fresh_app.work()
    fresh_app.restart()
    fresh_app.work()
    assert len(mails(hub, order["id"], "accepted")) == 1
    assert len(mails(hub, order["id"], "has shipped")) == 1


def test_email_retry_schedule_and_dedup(app, hub):
    order = app.order()
    hub.fault("mailpost.send", fail_next=2, fail_status=503)
    app.work()
    record = emails_of(app.get_order(order["id"]), "accepted")[0]
    assert record["status"] == "waiting" and record["attempts"] == 1
    app.advance(0.5)
    app.work()
    assert len(hub.calls_to("mailpost.send")) == 1
    app.advance(0.5)
    app.work()
    app.advance(2)
    app.work()
    assert len(mails(hub, order["id"])) == 1
    keys = {c["body"]["dedup_key"] for c in hub.calls_to("mailpost.send")}
    assert len(keys) == 1 and len(hub.calls_to("mailpost.send")) == 3
    assert emails_of(app.get_order(order["id"]), "accepted")[0]["status"] == "sent"


def test_lost_acknowledgement_does_not_duplicate(app, hub):
    order = app.order()
    hub.fault("mailpost.send", drop_after=1)
    app.work()
    app.advance(1)
    app.work()
    app.advance(5)
    app.work()
    assert len(mails(hub, order["id"])) == 1
    assert emails_of(app.get_order(order["id"]), "accepted")[0]["status"] == "sent"


def test_shipping_continues_during_email_outage(app, hub):
    order = app.order()
    hub.fault("mailpost.send", fail_next=100, fail_status=503)
    app.request_label(order["id"])
    app.work()
    current = app.get_order(order["id"])
    assert shipment_of(current)["status"] == "done"
    assert len(hub.pf_created) == 1
    for delay in (1, 2, 4):
        app.advance(delay)
        app.work()
    current = app.get_order(order["id"])
    states = {e["kind"]: e["status"] for e in emails_of(current)}
    assert states == {"accepted": "needs_attention", "shipped": "needs_attention"}
    assert mails(hub, order["id"]) == []
    page = app.get(f"/orders/{order['id']}")
    assert "needs attention" in page.text.lower()
    hub.clear_faults()
    for email in emails_of(current):
        response = app.post(f"/api/emails/{email['id']}/retry")
        assert response.status_code == 202, response.text
        assert response.json()["status"] == "waiting" and response.json()["attempts"] == 0
    app.work()
    assert len(mails(hub, order["id"])) == 2
    sent = emails_of(app.get_order(order["id"]))[0]
    expect_error(app.post(f"/api/emails/{sent['id']}/retry"), 409, "conflict")
    expect_error(app.post("/api/emails/nope/retry"), 404, "not_found")


def test_email_fails_after_label_created(app, hub):
    order = app.order()
    app.work()
    hub.fault("mailpost.send", fail_next=1, fail_status=503)
    app.request_label(order["id"])
    app.work()
    shipped = emails_of(app.get_order(order["id"]), "shipped")
    assert shipment_of(app.get_order(order["id"]))["status"] == "done"
    assert shipped and shipped[0]["status"] == "waiting"
    app.advance(1)
    app.work()
    assert len(mails(hub, order["id"], "has shipped")) == 1
    assert len(hub.pf_created) == 1


def test_customer_tracking_page(app):
    pid = app.product(price=275, name="Tin Whistle")
    order = app.order([(pid, 2)])
    shipped = app.ship(order["id"])
    page = app.get(f"/track/{order['id']}", staff=None)
    assert page.status_code == 200
    assert "Tin Whistle" in page.text and money(550) in page.text
    assert shipment_of(shipped)["tracking_code"] in page.text
    assert app.get("/track/no-such-order", staff=None).status_code == 404
