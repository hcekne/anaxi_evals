"""Request 9: Harbor jobs — submit once, poll at most once per (scaled) second, no streaming."""

from hub import ARTICLES

from conftest import SCALE, expect_error, provider_text, reply_calls, shows, wait_for


def polls(hub, job_id):
    return hub.calls_to("harbor", f"/harbor/jobs/{job_id}", "GET")


def test_harbor_is_offered(c):
    listed = {p["id"]: p for p in c.ok("GET", "/api/providers")["providers"]}
    assert listed["harbor"]["name"] == "Harbor" and listed["harbor"]["streaming"] is False
    assert c.ok("PUT", "/api/preferences", json={"provider": "harbor"})["provider"] == "harbor"
    c.ok("PUT", "/api/preferences", json={"provider": "pollen"})


def test_submits_once_and_polls_politely(c, hub):
    c.connect("harbor")
    a, b = c.tickets(2)
    hub.plan("harbor", polls=3, answer="Harbor says: your parcel is in Tromsø ✓")
    s = c.suggest(a["id"], provider="harbor")
    assert s["status"] == "completed" and s["text"] == "Harbor says: your parcel is in Tromsø ✓"
    (submit,) = reply_calls(hub, "harbor")
    assert submit["headers"]["authorization"] == "Bearer harbor-north-token"
    prompt = submit["body"]["prompt"]
    assert a["subject"] in prompt and a["body"] in prompt and b["body"] not in prompt
    job_id = submit["response"]["body"]["job_id"]
    seen = polls(hub, job_id)
    assert len(seen) == 4
    times = [submit["at"]] + [p["at"] for p in seen]
    assert all(later - earlier >= 0.9 * SCALE for earlier, later in zip(times, times[1:]))
    assert hub.calls_to("harbor", "/harbor/jobs", "DELETE") == []


def test_shows_working_until_the_answer(c, hub):
    c.connect("harbor")
    (a,) = c.tickets(1)
    hub.hold("harbor")
    r = c.ask(a["id"], provider="harbor")
    assert r.status_code in (201, 202), r.text
    ident = r.json()["id"]
    job_id = wait_for(lambda: reply_calls(hub, "harbor"))[0]["response"]["body"]["job_id"]
    assert wait_for(lambda: len(polls(hub, job_id)) >= 2)
    current = c.suggestion(ident)
    assert current["status"] == "running" and current["text"] == ""
    assert c.get(f"/tickets/{a['id']}").status_code == 200
    hub.release("harbor")
    done = c.wait(ident)
    assert done["status"] == "completed" and done["text"] == hub.jobs[job_id]["answer"]
    assert len(reply_calls(hub, "harbor")) == 1
    assert shows(c.page(f"/tickets/{a['id']}"), done["text"])


def test_prompt_carries_the_selected_context(c, hub):
    c.connect("harbor", "knowledge", "orders")
    (a,) = c.tickets(1)
    c.ok("POST", f"/api/tickets/{a['id']}/orders", status=201, json={"order_id": "A-1002"})
    c.ok("POST", f"/api/tickets/{a['id']}/orders", status=201, json={"order_id": "A-1003"})
    s = c.suggest(a["id"], provider="harbor", article_ids=["KB-101"], order_ids=["A-1002"])
    assert s["status"] == "completed"
    assert s["sources"][0]["id"] == "KB-101"
    prompt = provider_text(reply_calls(hub, "harbor")[0])
    north = {x["id"]: x for x in ARTICLES["north"]}
    assert north["KB-101"]["title"] in prompt and north["KB-101"]["text"] in prompt
    assert north["KB-100"]["text"] not in prompt
    assert "A-1002" in prompt and "$1,200.00" in prompt and "processing" in prompt
    assert "A-1003" not in prompt


def test_job_cancelled_by_harbor_is_a_failure(c, hub):
    c.connect("harbor")
    (a,) = c.tickets(1)
    hub.plan("harbor", polls=1, outcome="cancelled")
    s = c.suggest(a["id"], provider="harbor")
    assert s["status"] == "failed" and s["error"]["code"] == "provider_error"
    assert c.ticket(a["id"])["draft"]["text"] == ""


def test_submission_follows_the_retry_rules(c, hub):
    c.connect("harbor")
    (a,) = c.tickets(1)
    hub.fail("harbor", 429, retry_after=2)
    s = c.suggest(a["id"], provider="harbor")
    submits = reply_calls(hub, "harbor")
    assert s["status"] == "completed" and len(submits) == 2
    assert submits[1]["at"] - submits[0]["at"] >= 2 * SCALE * 0.9
    hub.fail("harbor", 401)
    s = c.suggest(a["id"], provider="harbor")
    assert s["error"]["code"] == "provider_auth_failed" and len(reply_calls(hub, "harbor")) == 3


def test_each_team_uses_its_harbor_token(south, hub):
    (b,) = south.tickets(1)
    expect_error(south.ask(b["id"], provider="harbor"), 409, "not_configured")
    south.connect("harbor")
    assert south.suggest(b["id"], provider="harbor")["status"] == "completed"
    assert {x["token"] for x in hub.calls_to("harbor")} == {"harbor-south-token"}
