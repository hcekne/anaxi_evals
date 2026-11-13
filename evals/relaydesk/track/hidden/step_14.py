"""Request 14: two supplied fonts, a per-browser font choice in a cookie, and a release that lets
running reply jobs finish. The release test starts the code from just before request 14."""

import hashlib
import re

import httpx
import pytest

from conftest import POLLEN, reply_calls, upgrade, wait_for

FONTS = {
    "fjord-sans": ("Fjord Sans",
                   "9249636a5ac1125f05b8cb3f7a32d8644a6dec922137aab2302342515f87f345"),
    "larch-serif": ("Larch Serif",
                    "3f72506896a158d60772132f844e829d00b88691a01fbecac4b72470447c1c68"),
}  # fmt: skip


def with_stylesheets(c, page: str) -> str:
    """The page plus every same-origin stylesheet it links."""
    texts = [page]
    for tag in re.findall(r"<link\b[^>]*>", page, re.I):
        if not re.search(r"rel\s*=\s*[\"']?stylesheet", tag, re.I):
            continue
        href = re.search(r"href\s*=\s*[\"']([^\"']+)", tag, re.I)
        if href and not href.group(1).startswith(("http://", "https://", "//")):
            r = c.get(href.group(1))
            if r.status_code == 200:
                texts.append(r.text)
    return "\n".join(texts)


def body_font(page: str) -> str | None:
    found = re.search(r"<body\b[^>]*\bdata-font\s*=\s*[\"']?([a-z-]+)", page, re.I)
    return found.group(1) if found else None


def test_font_files_are_served_exactly(app):
    with httpx.Client(base_url=app.base, timeout=30) as anonymous:
        for name, (_, digest) in FONTS.items():
            r = anonymous.get(f"/static/fonts/{name}.woff2")
            assert r.status_code == 200, name
            assert r.headers["content-type"].split(";")[0].strip() == "font/woff2"
            assert hashlib.sha256(r.content).hexdigest() == digest


def test_inbox_declares_both_fonts(c):
    text = with_stylesheets(c, c.page("/"))
    assert "@font-face" in text
    for name, (family, _) in FONTS.items():
        assert family in text and f"/static/fonts/{name}.woff2" in text


def test_the_browser_cookie_picks_the_font(app, c):
    c.tickets(1)
    assert body_font(c.page("/")) == "fjord-sans"
    c.http.cookies.set("relaydesk_font", "larch-serif")
    try:
        assert body_font(c.page("/")) == "larch-serif"
        nils = app.client("nils")
        assert body_font(nils.page("/")) == "fjord-sans"
        c.http.cookies.set("relaydesk_font", "comic-sans")
        assert body_font(c.page("/")) == "fjord-sans"
    finally:
        c.http.cookies.delete("relaydesk_font")


@pytest.fixture
def released(hub):
    def prepare(old):
        c = old.c
        c.connect("harbor", "pollen")
        a, b = c.tickets(2)
        hub.hold("harbor")
        hub.hold(POLLEN[0])
        harbor = c.ask(a["id"], provider="harbor").json()
        submitted = wait_for(lambda: reply_calls(hub, "harbor"))
        job_id = submitted[0]["response"]["body"]["job_id"]
        assert wait_for(lambda: hub.calls_to("harbor", f"/jobs/{job_id}", "GET"))
        r = c.post("/api/batches", json={"ticket_ids": [b["id"]], "provider": "pollen"})
        assert r.status_code == 201, r.text
        assert wait_for(lambda: reply_calls(hub, "pollen"))
        return {"harbor": harbor, "batch": r.json(), "job_id": job_id, "tickets": (a, b)}

    new, before = upgrade(hub, "14-*.md", prepare)
    yield new, before
    new.close()


def test_running_jobs_finish_after_the_release(released, hub):
    new, before = released
    c = new.c
    hub.release("harbor")
    hub.release(POLLEN[0])
    done = c.wait(before["harbor"]["id"], timeout=15)
    assert done["status"] == "completed" and done["text"] == hub.jobs[before["job_id"]]["answer"]
    assert len(reply_calls(hub, "harbor")) == 1  # resumed by polling, not submitted again
    assert hub.calls_to("harbor", f"/jobs/{before['job_id']}", "GET")
    batch = wait_for(lambda: (b := c.ok("GET", f"/api/batches/{before['batch']['id']}"))[
        "status"] == "completed" and b, timeout=15)
    assert batch and batch["items"][0]["status"] == "completed"
    a, b = before["tickets"]
    assert len(c.ok("GET", f"/api/tickets/{b['id']}/suggestions")["suggestions"]) == 1
    assert c.ticket(a["id"])["draft"]["text"] == ""
