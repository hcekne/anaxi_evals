"""Request 2: Pollen suggestions, reviewed before they replace the draft."""

from conftest import ASYNC, POLLEN, STEP, expect_error, provider_text, reply_calls, reply_text, shows


def test_connections_never_reveal_the_token(fresh_app):
    c = fresh_app.c
    listed = c.ok("GET", "/api/connections")["connections"]
    assert {"service": "pollen", "configured": False} in listed
    assert [e["service"] for e in listed] == sorted(e["service"] for e in listed)
    r = c.put("/api/connections/pollen", json={"token": c.token("pollen")})
    assert r.status_code == 200, r.text
    assert r.json() == {"service": "pollen", "configured": True}
    r = c.get("/api/connections")
    assert {"service": "pollen", "configured": True} in r.json()["connections"]
    assert c.token("pollen") not in r.text
    expect_error(c.put("/api/connections/pollen", json={"token": ""}), 422, "invalid_request")
    expect_error(c.put("/api/connections/pollen", json={}), 422, "invalid_request")
    expect_error(c.put("/api/connections/carrier-pigeon", json={"token": "x"}), 404, "not_found")


def test_not_connected_records_nothing(fresh_app, hub):
    c = fresh_app.c
    (a,) = c.tickets(1)
    expect_error(c.ask(a["id"], provider="pollen"), 409, "not_configured")
    assert c.ok("GET", f"/api/tickets/{a['id']}/suggestions") == {"suggestions": []}
    assert hub.calls == []


def test_pollen_gets_the_ticket_and_its_text_comes_back(c, hub):
    c.connect("pollen")
    a, b = c.tickets(2)
    r = c.ask(a["id"], provider="pollen")
    assert r.status_code in ((201, 202) if ASYNC else (201,)), r.text
    created = r.json()
    assert created["ticket_id"] == a["id"] and created["provider"] == "pollen"
    done = c.wait(created["id"])
    calls = reply_calls(hub, "pollen")
    assert len(calls) == 1 and calls[0]["path"] == POLLEN[1]
    call = calls[0]
    assert call["headers"]["authorization"] == f"Bearer {c.token('pollen')}"
    users = [m["content"] for m in call["body"]["messages"] if m["role"] == "user"]
    assert any(a["subject"] in m for m in users) and any(a["body"] in m for m in users)
    assert b["body"] not in provider_text(call) and b["subject"] not in provider_text(call)
    assert done["status"] == "completed" and done["error"] is None
    assert done["text"] == reply_text(hub, call) and done["accepted"] is False


def test_draft_is_kept_until_the_suggestion_is_accepted(c):
    c.connect("pollen")
    (a,) = c.tickets(1)
    c.ok("PUT", f"/api/tickets/{a['id']}/draft", json={"text": "What I typed myself"})
    s = c.suggest(a["id"], provider="pollen")
    assert s["status"] == "completed"
    assert c.ticket(a["id"])["draft"]["text"] == "What I typed myself"
    r = c.post(f"/api/suggestions/{s['id']}/accept")
    assert r.status_code == 200, r.text
    assert r.json()["id"] == a["id"] and r.json()["draft"]["text"] == s["text"]
    assert c.suggestion(s["id"])["accepted"] is True
    again = c.post(f"/api/suggestions/{s['id']}/accept")
    assert again.status_code == 200 and again.json()["draft"]["text"] == s["text"]


def test_suggestions_are_listed_oldest_first(c):
    c.connect("pollen")
    (a,) = c.tickets(1)
    first = c.suggest(a["id"], provider="pollen")
    second = c.suggest(a["id"], provider="pollen")
    listed = c.ok("GET", f"/api/tickets/{a['id']}/suggestions")["suggestions"]
    assert [s["id"] for s in listed] == [first["id"], second["id"]]
    assert listed[1]["text"] == second["text"] != first["text"]
    assert c.suggestion(first["id"])["text"] == first["text"]


def test_bad_token_fails_clearly_and_keeps_the_draft(c, hub):
    c.connect("pollen")
    (a,) = c.tickets(1)
    c.ok("PUT", f"/api/tickets/{a['id']}/draft", json={"text": "keep this"})
    hub.fail(POLLEN[0], 401)
    s = c.suggest(a["id"], provider="pollen")
    assert s["status"] == "failed" and s["text"] == ""
    assert s["error"]["code"] == "provider_auth_failed" and s["error"]["message"]
    expect_error(c.post(f"/api/suggestions/{s['id']}/accept"), 409, "conflict")
    assert c.ticket(a["id"])["draft"]["text"] == "keep this"
    assert len(reply_calls(hub, "pollen")) == 1


def test_other_failures_are_provider_errors(c, hub):
    c.connect("pollen")
    (a,) = c.tickets(1)
    hub.fail(POLLEN[0], 500)
    s = c.suggest(a["id"], provider="pollen")
    assert s["status"] == "failed" and s["error"]["code"] == "provider_error"
    assert c.ticket(a["id"])["draft"]["text"] == ""


def test_request_errors(c):
    c.connect("pollen")
    (a,) = c.tickets(1)
    expect_error(c.ask(a["id"], provider="owl-post"), 422, "invalid_request")
    if STEP < 3:
        expect_error(c.ask(a["id"]), 422, "invalid_request")
    expect_error(c.ask("no-such-ticket", provider="pollen"), 404, "not_found")
    expect_error(c.get("/api/suggestions/no-such-suggestion"), 404, "not_found")
    expect_error(c.post("/api/suggestions/no-such-suggestion/accept"), 404, "not_found")
    assert c.ok("GET", f"/api/tickets/{a['id']}/suggestions") == {"suggestions": []}


def test_ticket_page_shows_the_suggestion(c):
    c.connect("pollen")
    (a,) = c.tickets(1)
    s = c.suggest(a["id"], provider="pollen")
    assert shows(c.page(f"/tickets/{a['id']}"), s["text"])


def test_suggestions_survive_a_restart(fresh_app):
    c = fresh_app.c
    c.connect("pollen")
    (a,) = c.tickets(1)
    s = c.suggest(a["id"], provider="pollen")
    c.ok("POST", f"/api/suggestions/{s['id']}/accept")
    fresh_app.restart()
    c = fresh_app.c
    kept = c.suggestion(s["id"])
    assert kept["text"] == s["text"] and kept["accepted"] is True
    assert c.ticket(a["id"])["draft"]["text"] == s["text"]
    assert {"service": "pollen", "configured": True} in c.ok("GET", "/api/connections")["connections"]
