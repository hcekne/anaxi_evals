"""Request 5: QuickCrate with asynchronous label readiness (polling and/or verified callbacks),
carrier choice, and ParcelFox unchanged."""

import time

from conftest import ADDRESS, emails_of, expect_error, shipment_of


def status(app, order_id):
    return shipment_of(app.get_order(order_id))


def start_job(app, hub):
    order = app.order()
    response = app.request_label(order["id"], carrier="quickcrate", weight=2500)
    assert response.status_code == 202, response.text
    assert shipment_of(response.json())["carrier"] == "quickcrate"
    app.work()
    jobs = hub.qc_created
    assert len(jobs) == 1, jobs
    return order, jobs[0]


def test_carriers_listed_and_chosen(app):
    carriers = {c["id"]: c for c in app.ok(app.get("/api/carriers"))["carriers"]}
    assert carriers["quickcrate"]["name"] == "QuickCrate" and carriers["quickcrate"]["configured"]
    assert carriers["parcelfox"]["configured"]
    assert "qc-callback-secret" not in app.get("/api/carriers").text
    order = app.order()
    expect_error(app.request_label(order["id"], carrier="pigeon"), 422, "unknown_carrier")


def test_not_configured(bare_app):
    order = bare_app.order()
    expect_error(bare_app.request_label(order["id"], carrier="quickcrate"), 409, "not_configured")


def test_job_mapping_and_preparing(app, hub):
    order, job = start_job(app, hub)
    body = job["body"]
    parcel = body["parcel"]
    assert job["token"] == "qc-test-key"
    assert parcel["weight_grams"] == 2500
    assert parcel["recipient"] == {"name": ADDRESS["name"], "address_lines": [ADDRESS["line1"]],
                                   "city": ADDRESS["city"], "postcode": ADDRESS["postcode"],
                                   "country": ADDRESS["country"]}  # fmt: skip
    shipment = status(app, order["id"])
    assert shipment["status"] == "preparing" and shipment["tracking_code"] is None
    page = app.get(f"/orders/{order['id']}")
    assert "preparing" in page.text.lower()


def test_ready_label_completes(app, hub):
    order, job = start_job(app, hub)
    started = time.monotonic()
    app.work()
    assert time.monotonic() - started < 10, "--until-idle waited for a pending label"
    assert status(app, order["id"])["status"] == "preparing"
    hub.qc_set(job["job_id"], "ready")
    app.advance(30)
    app.work()
    shipment = status(app, order["id"])
    label = hub.qc_jobs[job["job_id"]]["label"]
    assert shipment["status"] == "done"
    assert (shipment["tracking_code"], shipment["label_text"], shipment["label_id"]) == (
        label["tracking"], label["text"], job["job_id"])  # fmt: skip
    app.work()
    shipped = [m for m in hub.messages() if order["id"] in m["subject"] and "shipped" in m["subject"]]
    assert len(shipped) == 1 and "QuickCrate" in shipped[0]["body"] and label["tracking"] in shipped[0]["body"]
    assert len(hub.qc_created) == 1


def test_failed_job_needs_attention(app, hub):
    order, job = start_job(app, hub)
    hub.qc_set(job["job_id"], "failed")
    app.advance(30)
    app.work()
    shipment = status(app, order["id"])
    assert shipment["status"] == "needs_attention"
    assert shipment["last_error"]["code"] == "label_failed"


def test_callbacks_are_verified(app, hub):
    order, job = start_job(app, hub)
    if not job["callback_url"]:
        return  # polling only: nothing is exposed
    with hub.lock:
        hub.qc_jobs[job["job_id"]]["status"] = "ready"
        hub.qc_jobs[job["job_id"]]["sequence"] += 1
        hub.qc_jobs[job["job_id"]]["label"] = {"tracking": "QCFORGED1", "text": "forged"}
    callback = hub.qc_callback(job["job_id"])
    assert hub.send_callback(callback, signature=None) == 401
    assert hub.send_callback(callback, signature="sha256=" + "0" * 64) == 401
    wrong = dict(callback, raw=callback["raw"].replace(b"QCFORGED1", b"QCFORGED2"))
    assert hub.send_callback(wrong) == 401
    shipment = status(app, order["id"])
    assert shipment["status"] == "preparing" and shipment["tracking_code"] is None


def test_duplicate_and_stale_callbacks(app, hub):
    order, job = start_job(app, hub)
    hub.qc_set(job["job_id"], "ready")
    app.advance(30)
    app.work()
    done = status(app, order["id"])
    assert done["status"] == "done"
    if job["callback_url"]:
        delivered = [c for c in hub.callbacks if c["body"]["job_id"] == job["job_id"]]
        assert delivered and delivered[-1]["status"] in range(200, 300)
        assert 200 <= hub.send_callback(delivered[-1]) < 300
        stale = hub.qc_callback(job["job_id"], status="pending", sequence=1)
        assert 200 <= hub.send_callback(stale) < 300
    app.advance(30)
    app.work()
    again = status(app, order["id"])
    assert again["status"] == "done" and again["tracking_code"] == done["tracking_code"]
    shipped = [e for e in emails_of(app.get_order(order["id"]), "shipped")]
    assert len(shipped) == 1


def test_create_retries_and_one_job(app, hub):
    order = app.order()
    hub.fault("quickcrate.create", fail_next=1, fail_status=503)
    app.request_label(order["id"], carrier="quickcrate")
    app.work()
    assert status(app, order["id"])["status"] == "waiting"
    hub.fault("quickcrate.create", drop_after=1)
    app.advance(1)
    app.work()
    app.advance(2)
    app.work()
    assert len(hub.qc_created) == 1
    refs = {c["body"]["client_ref"] for c in hub.calls_to("quickcrate.create")}
    assert len(refs) == 1
    assert status(app, order["id"])["status"] == "preparing"


def test_parcelfox_still_works(app, hub):
    order = app.order()
    shipped = app.ship(order["id"], carrier="parcelfox")
    assert shipment_of(shipped)["status"] == "done" and shipment_of(shipped)["carrier"] == "parcelfox"
    other = app.order()
    shipped = app.ship(other["id"])
    assert shipment_of(shipped)["carrier"] == "parcelfox" and len(hub.pf_created) == 2
    assert hub.qc_created == []
