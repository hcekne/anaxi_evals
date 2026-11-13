"""Request 6: daily report and CSV — UTC day boundaries, integer arithmetic, no double counts."""

from conftest import (CURRENCIES, DAY, RETURNS, day_of, expect_error, fresh_client, parallel,
                      parse_time, read_csv, shipment_of, uid)  # fmt: skip


def days(app, frm, to, staff="main"):
    response = app.get("/api/reports/daily", staff=staff, params={"from": frm, "to": to})
    assert response.status_code == 200, response.text
    return response.json()["days"]


def csv_rows(app, frm, to, staff="main"):
    response = app.get("/api/reports/daily.csv", staff=staff, params={"from": frm, "to": to})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    return read_csv(response.text)


def header():
    if CURRENCIES:
        return ["date", "currency", "orders", "items", "original_value", "returned_value", "remaining_value"]
    if RETURNS:
        return ["date", "orders", "items", "original_value", "returned_value", "remaining_value"]
    return ["date", "orders", "items", "value"]


def plus(date, n):
    return day_of(parse_time(date + "T00:00:00Z") + n * DAY)


def test_utc_day_boundaries(app):
    day = app.next_day(hour=0)
    start = app.now
    a, b = app.product(price=1999), app.product(price=1)
    app.order([(a, 2), (b, 3)])  # 00:00:00
    app.set_clock(start + DAY - 1)  # 23:59:59
    app.order([(a, 1)])
    app.set_clock(start + DAY)  # next day 00:00:00
    app.order([(b, 5)])
    report = days(app, day, plus(day, 1))
    assert [d["date"] for d in report] == [day, plus(day, 1)]
    first, second = report
    assert (first["orders"], first["items"], first["value"]) == (2, 6, 2 * 1999 + 3 + 1999)
    assert (second["orders"], second["items"], second["value"]) == (1, 5, 5)
    only_second = days(app, plus(day, 1), plus(day, 1))
    assert len(only_second) == 1 and only_second[0]["orders"] == 1


def test_csv(app):
    day = app.next_day()
    pid = app.product(price=1250)
    app.order([(pid, 3)])
    app.order([(pid, 1)])
    rows = csv_rows(app, day, day)
    assert rows[0] == header()
    assert len(rows) == 2
    row = dict(zip(rows[0], rows[1]))
    assert row["date"] == day and row["orders"] == "2" and row["items"] == "4"
    value = row.get("value", row.get("original_value"))
    assert value == "50.00"
    if RETURNS:
        assert row["returned_value"] == "0.00" and row["remaining_value"] == "50.00"
    if CURRENCIES:
        assert row["currency"] == "GBP"


def test_empty_days_are_left_out(app):
    day = app.next_day()
    app.next_day()
    app.order()
    report = days(app, day, plus(day, 1))
    assert [d["date"] for d in report] == [plus(day, 1)]
    assert days(app, day, day) == []
    assert csv_rows(app, day, day) == [header()]


def test_rejected_checkouts_never_count(app):
    day = app.next_day()
    pid = app.product(price=700, stock=1)
    app.order([(pid, 1)])
    expect_error(app.checkout([(pid, 1)]), 409, "out_of_stock")
    expect_error(app.checkout([(pid, 0)]), 422, "invalid_quantity")
    expect_error(app.checkout([("ghost-" + uid("x"), 1)]), 422, "unknown_product")
    report = days(app, day, day)
    assert (report[0]["orders"], report[0]["items"], report[0]["value"]) == (1, 1, 700)


def test_repeated_submission_counts_once(app):
    day = app.next_day()
    pid = app.product(price=300)
    key = uid("k")
    body = {"customer": {"name": "Ada", "email": "ada@example.test"},
            "items": [{"product_id": pid, "quantity": 2}], "submission_key": key}  # fmt: skip
    clients = [fresh_client(app) for _ in range(4)]
    try:
        parallel(lambda i: clients[i].post("/api/orders", json=body), 4)
    finally:
        for client in clients:
            client.close()
    app.checkout([(pid, 2)], key=key)
    report = days(app, day, day)
    assert (report[0]["orders"], report[0]["items"], report[0]["value"]) == (1, 2, 600)


def test_shipping_and_email_retries_do_not_count(app, hub):
    day = app.next_day()
    first, second = app.order(price=1000), app.order(price=2000)
    hub.fault("parcelfox.create", fail_next=10)
    hub.fault("mailpost.send", fail_next=3, drop_after=1)
    app.request_label(first["id"])
    for delay in (1, 2, 4, 8):
        app.work()
        app.advance(delay)
    assert shipment_of(app.get_order(first["id"]))["status"] == "needs_attention"
    hub.clear_faults()
    app.ship(second["id"])
    report = days(app, day, day)
    assert (report[0]["orders"], report[0]["value"]) == (2, 3000)


def test_report_validation(app):
    for params in ({}, {"from": "2026-03-02"}, {"from": "2026-3-2", "to": "2026-03-02"},
                   {"from": "2026-03-05", "to": "2026-03-02"}, {"from": "yesterday", "to": "2026-03-02"}):  # fmt: skip
        expect_error(app.get("/api/reports/daily", params=params), 422, "invalid_request")
        expect_error(app.get("/api/reports/daily.csv", params=params), 422, "invalid_request")


def test_report_page(app):
    page = app.get("/reports")
    assert page.status_code == 200 and "daily.csv" in page.text
