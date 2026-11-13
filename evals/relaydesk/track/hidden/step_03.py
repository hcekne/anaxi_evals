"""Request 3: Comet as a second service, a saved usual choice. After request 13 retired Comet,
the tests that need a second service use Harbor and Comet itself must be refused."""

from conftest import RETIRED, SECOND, expect_error, reply_calls, reply_text, shows

NAMES = {"pollen": "Pollen", "comet": "Comet", "harbor": "Harbor"}


def preference(c) -> str | None:
    return c.ok("GET", "/api/preferences")["provider"]


def test_providers_are_listed(c):
    listed = c.ok("GET", "/api/providers")["providers"]
    ids = [p["id"] for p in listed]
    assert ids == sorted(ids) and "pollen" in ids
    assert ("comet" in ids) is not RETIRED
    for entry in listed:
        if entry["id"] in NAMES:
            assert entry["name"] == NAMES[entry["id"]]


def test_comet_gets_its_own_protocol(c, hub):
    (a, b) = c.tickets(2)
    if RETIRED:
        expect_error(c.ask(a["id"], provider="comet"), 422, "provider_retired")
        return
    c.connect("comet")
    s = c.suggest(a["id"], provider="comet")
    (call,) = reply_calls(hub, "comet")
    assert call["headers"]["x-api-key"] == c.token("comet")
    assert "authorization" not in call["headers"]
    customer = [e["text"] for e in call["body"]["conversation"] if e["speaker"] == "customer"]
    assert any(a["subject"] in t for t in customer) and any(a["body"] in t for t in customer)
    assert b["body"] not in str(call["body"])
    assert s["provider"] == "comet" and s["status"] == "completed"
    assert s["text"] == reply_text(hub, call)
    assert reply_calls(hub, "pollen") == []


def test_usual_choice_is_used_and_kept(fresh_app, hub):
    c = fresh_app.c
    c.connect("pollen", SECOND)
    (a,) = c.tickets(1)
    assert preference(c) == "pollen"
    s = c.suggest(a["id"])
    assert s["provider"] == "pollen" and len(reply_calls(hub, "pollen")) == 1
    r = c.put("/api/preferences", json={"provider": SECOND})
    assert r.status_code == 200, r.text
    assert r.json()["provider"] == SECOND
    s = c.suggest(a["id"])
    assert s["provider"] == SECOND and len(reply_calls(hub, SECOND)) == 1
    explicit = c.suggest(a["id"], provider="pollen")
    assert explicit["provider"] == "pollen" and preference(c) == SECOND
    fresh_app.restart()
    assert preference(fresh_app.c) == SECOND
    assert fresh_app.c.suggest(a["id"])["provider"] == SECOND


def test_unknown_choice_is_refused(c):
    expect_error(c.put("/api/preferences", json={"provider": "owl-post"}), 422, "invalid_request")
    expect_error(c.put("/api/preferences", json={}), 422, "invalid_request")


def test_switching_services_keeps_the_draft(c, hub):
    c.connect("pollen", SECOND)
    (a,) = c.tickets(1)
    c.ok("PUT", f"/api/tickets/{a['id']}/draft", json={"text": "Mine, not theirs"})
    first = c.suggest(a["id"], provider="pollen")
    second = c.suggest(a["id"], provider=SECOND)
    assert first["status"] == second["status"] == "completed"
    assert c.ticket(a["id"])["draft"]["text"] == "Mine, not theirs"
    listed = c.ok("GET", f"/api/tickets/{a['id']}/suggestions")["suggestions"]
    assert [(s["id"], s["provider"]) for s in listed] == [
        (first["id"], "pollen"),
        (second["id"], SECOND),
    ]
    assert c.ok("POST", f"/api/suggestions/{second['id']}/accept")["draft"]["text"] == second["text"]
    assert c.suggestion(first["id"])["accepted"] is False


def test_comet_errors_map_like_pollen(c, hub):
    (a,) = c.tickets(1)
    if RETIRED:
        expect_error(c.put("/api/preferences", json={"provider": "comet"}), 422, "provider_retired")
        return
    c.connect("comet")
    hub.fail("comet", 401)
    s = c.suggest(a["id"], provider="comet")
    assert s["status"] == "failed" and s["error"]["code"] == "provider_auth_failed"
    hub.fail("comet", 500)
    s = c.suggest(a["id"], provider="comet")
    assert s["status"] == "failed" and s["error"]["code"] == "provider_error"
    assert c.ticket(a["id"])["draft"]["text"] == ""


def test_page_names_the_service(c):
    c.connect("pollen", SECOND)
    (a,) = c.tickets(1)
    s = c.suggest(a["id"], provider=SECOND)
    page = c.page(f"/tickets/{a['id']}")
    assert shows(page, s["text"]) and NAMES[SECOND] in page
