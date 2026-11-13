"""Probe 3: Quartz renamed `text_delta` to `output_text`; both names must work and saved
Quartz suggestions stay intact (upgrade from the code just before this probe)."""

from conftest import reply_calls, upgrade, wait_for

CITATION = {"article_id": "KB-101", "title": "Refund timelines",
            "url": "https://help.relaydesk.test/north/kb-101"}  # fmt: skip


def test_new_event_name(c, hub):
    c.connect("quartz")
    (a,) = c.tickets(1)
    hub.quartz_text_event = "output_text"
    hub.plan("quartz", deltas=["Refunds ", "take a week ✓"], citations=[CITATION])
    s = c.suggest(a["id"], provider="quartz")
    assert s["status"] == "completed" and s["text"] == "Refunds take a week ✓"
    assert s["citations"] == [CITATION]
    assert reply_calls(hub, "quartz")[0]["response"]["events"][0][0] == "output_text"


def test_new_event_name_streams(c, hub):
    c.connect("quartz")
    (a,) = c.tickets(1)
    hub.quartz_text_event = "output_text"
    hub.plan("quartz", deltas=["First ", "second"], citations=[], hold=True)
    ident = c.ask(a["id"], provider="quartz").json()["id"]
    partial = wait_for(lambda: (x := c.suggestion(ident))["text"] == "First " and x)
    assert partial and partial["status"] == "running"
    hub.release("quartz")
    assert c.wait(ident)["text"] == "First second"


def test_old_event_name_still_works(c, hub):
    c.connect("quartz")
    (a,) = c.tickets(1)
    hub.plan("quartz", deltas=["Old ", "name"], citations=[CITATION])
    s = c.suggest(a["id"], provider="quartz")
    assert s["text"] == "Old name" and s["citations"] == [CITATION]


def test_saved_quartz_suggestions_are_untouched(hub):
    def prepare(old):
        c = old.c
        c.connect("quartz")
        (a,) = c.tickets(1)
        hub.plan("quartz", deltas=["Saved ", "before"], citations=[CITATION])
        made = c.suggest(a["id"], provider="quartz")
        assert made["status"] == "completed"
        return made

    new, made = upgrade(hub, "probe-p3-*.md", prepare)
    try:
        kept = new.c.suggestion(made["id"])
        assert kept == made
    finally:
        new.close()
