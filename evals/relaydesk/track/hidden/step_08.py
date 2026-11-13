"""Request 8: two retries for 429/503 with Retry-After on the scaled clock; no retry on 401."""

import time

from conftest import POLLEN, SCALE, SECOND, expect_error, reply_calls, wait_for

OTHERS = ("comet", "harbor", "quartz")


def gaps(calls) -> list[float]:
    return [b["at"] - a["at"] for a, b in zip(calls, calls[1:])]


def waited(gap: float, seconds: float) -> bool:
    """At least `seconds` on the scaled clock, and clearly not real seconds."""
    return seconds * SCALE * 0.9 <= gap < seconds * 0.6


def test_retry_after_is_respected(c, hub):
    c.connect("pollen")
    (a,) = c.tickets(1)
    hub.fail(POLLEN[0], 429, retry_after=4)
    s = c.suggest(a["id"], provider="pollen")
    calls = reply_calls(hub, "pollen")
    assert s["status"] == "completed" and len(calls) == 2
    assert waited(gaps(calls)[0], 4), gaps(calls)


def test_unavailable_without_header_waits_one_second(c, hub):
    c.connect("pollen")
    (a,) = c.tickets(1)
    hub.fail(POLLEN[0], 503)
    hub.fail(POLLEN[0], 503, retry_after=3)
    s = c.suggest(a["id"], provider="pollen")
    calls = reply_calls(hub, "pollen")
    assert s["status"] == "completed" and len(calls) == 3
    assert waited(gaps(calls)[0], 1) and waited(gaps(calls)[1], 3), gaps(calls)
    assert s["text"] and c.ticket(a["id"])["draft"]["text"] == ""


def test_third_temporary_failure_gives_up_clearly(c, hub):
    c.connect("pollen")
    (a,) = c.tickets(1)
    hub.fail(POLLEN[0], 429, 503, 429, retry_after=1)
    s = c.suggest(a["id"], provider="pollen")
    assert s["status"] == "failed" and s["text"] == ""
    assert s["error"]["code"] == "provider_unavailable" and s["error"]["message"]
    time.sleep(0.3)
    assert len(reply_calls(hub, "pollen")) == 3
    expect_error(c.post(f"/api/suggestions/{s['id']}/accept"), 409, "conflict")


def test_bad_key_is_not_retried(c, hub):
    c.connect("pollen")
    (a,) = c.tickets(1)
    hub.fail(POLLEN[0], 401)
    s = c.suggest(a["id"], provider="pollen")
    assert s["error"]["code"] == "provider_auth_failed"
    time.sleep(0.3)
    assert len(reply_calls(hub, "pollen")) == 1


def test_unexpected_status_is_not_retried(c, hub):
    c.connect("pollen")
    (a,) = c.tickets(1)
    hub.fail(POLLEN[0], 500)
    s = c.suggest(a["id"], provider="pollen")
    assert s["error"]["code"] == "provider_error"
    time.sleep(0.3)
    assert len(reply_calls(hub, "pollen")) == 1


def test_suggestion_runs_while_waiting(c, hub):
    c.connect("pollen")
    (a,) = c.tickets(1)
    hub.fail(POLLEN[0], 429, retry_after=10)
    r = c.ask(a["id"], provider="pollen")
    assert r.status_code in (201, 202), r.text
    assert wait_for(lambda: reply_calls(hub, "pollen"))
    assert c.suggestion(r.json()["id"])["status"] == "running"
    assert c.wait(r.json()["id"])["status"] == "completed"


def test_never_switches_service(c, hub):
    c.connect("pollen", SECOND)
    (a,) = c.tickets(1)
    hub.fail(POLLEN[0], 503, 503, 503)
    s = c.suggest(a["id"], provider="pollen")
    assert s["provider"] == "pollen" and s["error"]["code"] == "provider_unavailable"
    time.sleep(0.2)
    assert all(hub.calls_to(other) == [] for other in OTHERS)
    assert [x["provider"] for x in c.ok("GET", f"/api/tickets/{a['id']}/suggestions")[
        "suggestions"]] == ["pollen"]


def test_work_is_kept_safe(c, hub):
    c.connect("pollen")
    (a,) = c.tickets(1)
    good = c.suggest(a["id"], provider="pollen")
    c.ok("POST", f"/api/suggestions/{good['id']}/accept")
    c.ok("PUT", f"/api/tickets/{a['id']}/draft", json={"text": "edited after accepting"})
    hub.fail(POLLEN[0], 429, 429, 429, retry_after=1)
    bad = c.suggest(a["id"], provider="pollen")
    assert bad["status"] == "failed"
    assert c.ticket(a["id"])["draft"]["text"] == "edited after accepting"
    kept = c.suggestion(good["id"])
    assert kept["status"] == "completed" and kept["text"] == good["text"] and kept["accepted"]


def test_other_services_retry_the_same_way(c, hub):
    c.connect(SECOND)
    (a,) = c.tickets(1)
    hub.fail(SECOND, 503)
    hub.fail(SECOND, 429, retry_after=2)
    s = c.suggest(a["id"], provider=SECOND)
    calls = reply_calls(hub, SECOND)
    assert s["status"] == "completed" and len(calls) == 3
    assert waited(gaps(calls)[0], 1) and waited(gaps(calls)[1], 2), gaps(calls)
    hub.fail(SECOND, 401)
    s = c.suggest(a["id"], provider=SECOND)
    assert s["error"]["code"] == "provider_auth_failed" and len(reply_calls(hub, SECOND)) == 4
