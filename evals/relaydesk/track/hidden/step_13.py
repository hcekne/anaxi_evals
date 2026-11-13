"""Request 13: Comet retired for new work; old Comet suggestions stay readable; a saved Comet
choice must be replaced explicitly. The upgrade test starts the code from just before request 13,
makes Comet history there, then runs the current code on the same data."""

import pytest

from conftest import expect_error, reply_calls, shows, upgrade


def choice(c) -> tuple:
    found = c.ok("GET", "/api/preferences")
    return found["provider"], found["needs_choice"]


@pytest.fixture(scope="module")
def upgraded(hub):
    def prepare(old):
        c = old.c
        c.connect("comet", "pollen")
        c.ok("PUT", "/api/preferences", json={"provider": "comet"})
        a, b = c.tickets(2)
        made = c.suggest(a["id"], provider="comet")
        assert made["status"] == "completed", made
        c.ok("POST", f"/api/suggestions/{made['id']}/accept")
        return {"ticket": a, "other": b, "suggestion": made, "comet_calls": len(hub.calls)}

    new, before = upgrade(hub, "13-*.md", prepare)
    yield new, before
    new.close()


def test_comet_is_not_offered(c, hub):
    ids = [p["id"] for p in c.ok("GET", "/api/providers")["providers"]]
    assert "comet" not in ids and {"pollen", "harbor", "quartz"} <= set(ids)
    expect_error(c.put("/api/preferences", json={"provider": "comet"}), 422, "provider_retired")
    c.connect("pollen")
    (a,) = c.tickets(1)
    expect_error(c.ask(a["id"], provider="comet"), 422, "provider_retired")
    expect_error(c.post("/api/batches", json={"ticket_ids": [a["id"]], "provider": "comet"}), 422,
                 "provider_retired")  # fmt: skip
    assert c.ok("GET", f"/api/tickets/{a['id']}/suggestions") == {"suggestions": []}
    assert hub.calls_to("comet") == []


def test_other_services_need_no_comet(south, hub):
    assert choice(south) == ("pollen", False)
    south.connect("pollen", "quartz")
    (b,) = south.tickets(1)
    assert south.suggest(b["id"])["provider"] == "pollen"
    assert south.suggest(b["id"], provider="quartz")["status"] == "completed"
    assert hub.calls_to("comet") == []


def test_old_comet_suggestions_stay_readable(upgraded, hub):
    new, before = upgraded
    c, made = new.c, before["suggestion"]
    ticket = before["ticket"]
    kept = c.suggestion(made["id"])
    assert kept["provider"] == "comet" and kept["text"] == made["text"]
    assert kept["status"] == "completed" and kept["accepted"] is True
    listed = c.ok("GET", f"/api/tickets/{ticket['id']}/suggestions")["suggestions"]
    assert [(x["id"], x["provider"]) for x in listed] == [(made["id"], "comet")]
    assert c.ticket(ticket["id"])["draft"]["text"] == made["text"]
    page = c.page(f"/tickets/{ticket['id']}")
    assert shows(page, made["text"]) and "Comet" in page
    assert hub.calls_to("comet") == []


def test_a_saved_comet_choice_must_be_replaced(upgraded, hub):
    new, before = upgraded
    c = new.c
    ticket, other = before["ticket"], before["other"]
    assert choice(c) == (None, True)
    expect_error(c.ask(other["id"]), 409, "choose_provider")
    expect_error(c.post("/api/batches", json={"ticket_ids": [other["id"]]}), 409,
                 "choose_provider")  # fmt: skip
    assert c.ok("GET", f"/api/tickets/{other['id']}/suggestions") == {"suggestions": []}
    assert c.ok("GET", "/api/batches")["batches"] == []
    assert hub.calls == []
    assert c.ok("PUT", "/api/preferences", json={"provider": "pollen"})["provider"] == "pollen"
    assert choice(c) == ("pollen", False)
    s = c.suggest(other["id"])
    assert s["provider"] == "pollen" and s["status"] == "completed"
    assert len(reply_calls(hub, "pollen")) == 1 and hub.calls_to("comet") == []
    assert c.suggestion(before["suggestion"]["id"])["provider"] == "comet"
    assert c.ticket(ticket["id"])["draft"]["text"] == before["suggestion"]["text"]
