"""Request 4: two teams with sign-in; everything is separated per team."""

import httpx

from conftest import SECOND, USERS, expect_error, reply_calls, shows


def anonymous(app) -> httpx.Client:
    return httpx.Client(base_url=app.base, timeout=30)


def test_sign_in_and_out(app):
    with anonymous(app) as browser:
        r = browser.post("/api/login", json={"username": "nils", "password": USERS["nils"][0]})
        assert r.status_code == 200, r.text
        assert r.json() == {"username": "nils", "team": "north"}
        assert browser.get("/api/me").json() == {"username": "nils", "team": "north"}
        assert browser.get("/api/tickets").status_code == 200
        assert browser.post("/api/logout").status_code == 200
        expect_error(browser.get("/api/tickets"), 401, "unauthenticated")
        expect_error(browser.get("/api/me"), 401, "unauthenticated")
    with anonymous(app) as browser:
        bad = browser.post("/api/login", json={"username": "nils", "password": "north-pass-1"})
        expect_error(bad, 401, "invalid_credentials")
        nobody = browser.post("/api/login", json={"username": "olaf", "password": "x"})
        expect_error(nobody, 401, "invalid_credentials")
        r = browser.post("/api/login", json={"username": "sara", "password": USERS["sara"][0]})
        assert r.json() == {"username": "sara", "team": "south"}


def test_api_needs_a_session(app, c):
    (a,) = c.tickets(1)
    with anonymous(app) as browser:
        assert browser.get("/api/health").status_code == 200
        expect_error(browser.get("/api/tickets"), 401, "unauthenticated")
        expect_error(browser.get(f"/api/tickets/{a['id']}"), 401, "unauthenticated")
        expect_error(browser.put(f"/api/tickets/{a['id']}/draft", json={"text": "x"}), 401,
                     "unauthenticated")  # fmt: skip
        expect_error(browser.post("/api/imports", content=b"id,customer_email,subject,body\n"),
                     401, "unauthenticated")  # fmt: skip
        expect_error(browser.get("/api/preferences"), 401, "unauthenticated")
    assert c.ticket(a["id"])["draft"]["text"] == ""


def test_pages_need_a_session(app, c):
    (a,) = c.tickets(1)
    with anonymous(app) as browser:
        for path in ("/", f"/tickets/{a['id']}"):
            r = browser.get(path)
            assert r.status_code != 200 or not shows(r.text, a["subject"]), path
            assert not shows(r.text, a["body"]), path
        assert browser.get("/login").status_code == 200


def test_teams_may_use_the_same_ticket_id(c, south):
    (mine,) = c.tickets(1, body="North's own words")
    theirs = dict(mine, body="South's own words", subject="South subject")
    r = south.import_rows([theirs])
    assert r.status_code == 200 and r.json()["imported"] == [mine["id"]], r.text
    assert c.ticket(mine["id"])["body"] == "North's own words"
    assert south.ticket(mine["id"])["body"] == "South's own words"
    south.ok("PUT", f"/api/tickets/{mine['id']}/draft", json={"text": "south draft"})
    assert c.ticket(mine["id"])["draft"]["text"] == ""
    south.ok("POST", f"/api/tickets/{mine['id']}/close")
    assert c.ticket(mine["id"])["status"] == "open"


def test_another_teams_ticket_does_not_exist(c, south):
    (a,) = c.tickets(1)
    ident = a["id"]
    expect_error(south.get(f"/api/tickets/{ident}"), 404, "not_found")
    expect_error(south.put(f"/api/tickets/{ident}/draft", json={"text": "x"}), 404, "not_found")
    expect_error(south.post(f"/api/tickets/{ident}/close"), 404, "not_found")
    expect_error(south.get(f"/api/tickets/{ident}/suggestions"), 404, "not_found")
    assert south.get(f"/tickets/{ident}").status_code == 404
    assert ident not in [t["id"] for t in south.ok("GET", "/api/tickets?status=all")["tickets"]]
    assert ident not in south.page("/") and not shows(south.page("/"), a["subject"])
    assert c.ticket(ident)["status"] == "open" and c.ticket(ident)["draft"]["text"] == ""


def test_another_teams_suggestion_does_not_exist(c, south):
    c.connect("pollen")
    south.connect("pollen")
    (a,) = c.tickets(1)
    s = c.suggest(a["id"], provider="pollen")
    expect_error(south.get(f"/api/suggestions/{s['id']}"), 404, "not_found")
    expect_error(south.post(f"/api/suggestions/{s['id']}/accept"), 404, "not_found")
    expect_error(south.ask(a["id"], provider="pollen"), 404, "not_found")
    assert c.ticket(a["id"])["draft"]["text"] == ""


def test_teammates_share_everything(app, c):
    (a,) = c.tickets(1)
    c.ok("PUT", f"/api/tickets/{a['id']}/draft", json={"text": "started by nora"})
    nils = app.client("nils")
    assert nils.ticket(a["id"])["draft"]["text"] == "started by nora"
    nils.ok("POST", f"/api/tickets/{a['id']}/close")
    assert c.ticket(a["id"])["status"] == "closed"


def test_each_team_uses_its_own_credentials(c, south, hub):
    c.connect("pollen", SECOND)
    south.connect("pollen", SECOND)
    (a,) = c.tickets(1)
    (b,) = south.tickets(1)
    for provider in ("pollen", SECOND):
        c.suggest(a["id"], provider=provider)
        south.suggest(b["id"], provider=provider)
        calls = reply_calls(hub, provider)
        assert [call["team"] for call in calls] == ["north", "south"], provider
        assert a["body"] in str(calls[0]["body"]) and b["body"] in str(calls[1]["body"])


def test_settings_are_per_team(fresh_app):
    north = fresh_app.c
    south = fresh_app.client("sara")
    north.connect("pollen")
    north.ok("PUT", "/api/preferences", json={"provider": SECOND})
    assert south.ok("GET", "/api/preferences")["provider"] == "pollen"
    configured = {e["service"]: e["configured"]
                  for e in south.ok("GET", "/api/connections")["connections"]}  # fmt: skip
    assert configured["pollen"] is False
    (b,) = south.tickets(1)
    expect_error(south.ask(b["id"], provider="pollen"), 409, "not_configured")
    south.ok("PUT", "/api/preferences", json={"provider": "pollen"})
    assert north.ok("GET", "/api/preferences")["provider"] == SECOND
