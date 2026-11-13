"""Request 5: suggestions answer at once; Pollen streams its text, Comet shows a working state."""

from conftest import POLLEN, SECOND, UNFINISHED, expect_error, reply_calls, reply_text, shows, wait_for


def start(c, ident, **body) -> dict:
    r = c.post(f"/api/tickets/{ident}/suggestions", json=body, timeout=5)
    assert r.status_code == 202, r.text
    assert r.json()["status"] in UNFINISHED
    return r.json()


def test_pollen_text_is_visible_while_it_arrives(c, hub):
    c.connect("pollen")
    (a,) = c.tickets(1)
    hub.plan(POLLEN[0], deltas=["Hei Ola, ", "pakken er ", "på vei ✓"], hold=True)
    s = start(c, a["id"], provider="pollen")
    partial = wait_for(lambda: (x := c.suggestion(s["id"]))["text"] == "Hei Ola, " and x)
    assert partial and partial["status"] == "running", c.suggestion(s["id"])
    page = c.page(f"/tickets/{a['id']}")
    assert shows(page, "Hei Ola,")
    hub.release(POLLEN[0])
    done = c.wait(s["id"])
    assert done["status"] == "completed" and done["text"] == "Hei Ola, pakken er på vei ✓"
    assert [x["path"] for x in reply_calls(hub, "pollen")] == ["/pollen/draft/stream"]


def test_streamed_pieces_are_joined_exactly_once(c, hub):
    c.connect("pollen")
    (a,) = c.tickets(1)
    pieces = ["A", "B", "A", "", "C — ✓", " end"]
    hub.plan(POLLEN[0], deltas=pieces)
    s = c.suggest(a["id"], provider="pollen")
    assert s["status"] == "completed" and s["text"] == "".join(pieces)
    accepted = c.ok("POST", f"/api/suggestions/{s['id']}/accept")
    assert accepted["draft"]["text"] == "".join(pieces)


def test_non_streaming_service_shows_a_working_state(c, hub):
    c.connect(SECOND)
    (a,) = c.tickets(1)
    hub.hold(SECOND)
    s = start(c, a["id"], provider=SECOND)
    wait_for(lambda: reply_calls(hub, SECOND))
    current = c.suggestion(s["id"])
    assert current["status"] == "running" and current["text"] == ""
    hub.release(SECOND)
    done = c.wait(s["id"])
    (call,) = reply_calls(hub, SECOND)
    assert done["status"] == "completed" and done["text"] == reply_text(hub, call)
    assert all("stream" not in x["path"] for x in hub.calls_to(SECOND))


def test_cut_off_stream_fails_and_cannot_be_used(c, hub):
    c.connect("pollen")
    (a,) = c.tickets(1)
    c.ok("PUT", f"/api/tickets/{a['id']}/draft", json={"text": "original draft"})
    hub.plan(POLLEN[0], deltas=["This reply never ", "finishes"], interrupt=True)
    s = c.suggest(a["id"], provider="pollen")
    assert s["status"] == "failed" and s["error"]["code"] == "stream_interrupted"
    expect_error(c.post(f"/api/suggestions/{s['id']}/accept"), 409, "conflict")
    assert c.ticket(a["id"])["draft"]["text"] == "original draft"
    assert len(reply_calls(hub, "pollen")) == 1


def test_failures_keep_the_original_draft(c, hub):
    c.connect("pollen")
    (a,) = c.tickets(1)
    c.ok("PUT", f"/api/tickets/{a['id']}/draft", json={"text": "original draft"})
    hub.fail(POLLEN[0], 401)
    s = c.suggest(a["id"], provider="pollen")
    assert s["status"] == "failed" and s["error"]["code"] == "provider_auth_failed"
    assert c.ticket(a["id"])["draft"]["text"] == "original draft"


def test_providers_say_whether_they_stream(c):
    flags = {p["id"]: p["streaming"] for p in c.ok("GET", "/api/providers")["providers"]}
    assert flags["pollen"] is True and flags[SECOND] is False


def test_request_errors_answer_at_once(c, south, hub):
    (a,) = c.tickets(1)
    expect_error(c.post(f"/api/tickets/{a['id']}/suggestions", json={"provider": "owl"},
                        timeout=5), 422, "invalid_request")  # fmt: skip
    (b,) = south.tickets(1)
    expect_error(south.post(f"/api/tickets/{b['id']}/suggestions", json={"provider": "pollen"},
                            timeout=5), 409, "not_configured")  # fmt: skip
    assert south.ok("GET", f"/api/tickets/{b['id']}/suggestions") == {"suggestions": []}
    assert c.ok("GET", f"/api/tickets/{a['id']}/suggestions") == {"suggestions": []}
    assert hub.calls == []
