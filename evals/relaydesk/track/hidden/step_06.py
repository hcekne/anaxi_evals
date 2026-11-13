"""Request 6: help-article search; selected articles go to the provider and become sources."""

from hub import ARTICLES

from conftest import SECOND, expect_error, provider_text, reply_calls, shows

NORTH = {a["id"]: a for a in ARTICLES["north"]}


def source(article: dict) -> dict:
    return {"id": article["id"], "title": article["title"], "url": article["url"]}


def public(article: dict) -> dict:
    return {**source(article), "text": article["text"]}


def test_not_connected(south):
    expect_error(south.get("/api/articles", params={"q": "x"}), 409, "not_configured")
    (b,) = south.tickets(1)
    south.connect("pollen")
    r = south.ask(b["id"], provider="pollen", article_ids=["KB-200"])
    expect_error(r, 409, "not_configured")
    assert south.ok("GET", f"/api/tickets/{b['id']}/suggestions") == {"suggestions": []}


def test_search_uses_the_teams_token(c, hub):
    c.connect("knowledge")
    r = c.ok("GET", "/api/articles", params={"q": "REFUND"})
    assert r == {"articles": [public(NORTH["KB-101"])]}
    (call,) = hub.calls_to("knowledge")
    assert call["headers"]["authorization"] == "Bearer kb-north-token"
    assert call["query"]["team"] == "north" and call["query"]["q"].lower() == "refund"


def test_all_articles_and_missing_links(c):
    c.connect("knowledge")
    listed = c.ok("GET", "/api/articles", params={"q": ""})["articles"]
    assert listed == [public(a) for a in ARTICLES["north"]]
    assert listed[2]["url"] is None
    assert c.ok("GET", "/api/articles/KB-102") == public(NORTH["KB-102"])
    expect_error(c.get("/api/articles/KB-999"), 404, "not_found")


def test_teams_see_only_their_articles(c, south):
    c.connect("knowledge")
    south.connect("knowledge")
    ids = [a["id"] for a in south.ok("GET", "/api/articles", params={"q": ""})["articles"]]
    assert ids == ["KB-200", "KB-201"]
    expect_error(south.get("/api/articles/KB-100"), 404, "not_found")
    expect_error(c.get("/api/articles/KB-200"), 404, "not_found")


def test_selected_articles_are_sent_and_listed(c, hub):
    c.connect("pollen", "knowledge")
    (a,) = c.tickets(1)
    s = c.suggest(a["id"], provider="pollen", article_ids=["KB-102", "KB-101"])
    (call,) = reply_calls(hub, "pollen")
    sent = provider_text(call)
    for ident in ("KB-102", "KB-101"):
        assert NORTH[ident]["title"] in sent and NORTH[ident]["text"] in sent
    assert NORTH["KB-100"]["text"] not in sent and NORTH["KB-100"]["title"] not in sent
    assert a["body"] in sent
    assert s["status"] == "completed"
    assert s["sources"] == [source(NORTH["KB-102"]), source(NORTH["KB-101"])]
    assert c.suggestion(s["id"])["sources"] == s["sources"]


def test_other_services_get_the_articles_too(c, hub):
    c.connect(SECOND, "knowledge")
    (a,) = c.tickets(1)
    s = c.suggest(a["id"], provider=SECOND, article_ids=["KB-100"])
    (call,) = reply_calls(hub, SECOND)
    sent = provider_text(call)
    assert NORTH["KB-100"]["text"] in sent and NORTH["KB-101"]["text"] not in sent
    assert s["sources"] == [source(NORTH["KB-100"])]


def test_no_selection_means_no_sources(c, hub):
    c.connect("pollen", "knowledge")
    (a,) = c.tickets(1)
    assert c.ticket(a["id"])["draft"] == {"text": "", "sources": []}
    s = c.suggest(a["id"], provider="pollen")
    assert s["sources"] == []
    sent = provider_text(reply_calls(hub, "pollen")[0])
    assert all(article["text"] not in sent for article in ARTICLES["north"])


def test_unknown_articles_are_refused(c, hub):
    c.connect("pollen", "knowledge")
    (a,) = c.tickets(1)
    for ids in (["KB-999"], ["KB-100", "KB-200"]):
        expect_error(c.ask(a["id"], provider="pollen", article_ids=ids), 422, "unknown_article")
    assert c.ok("GET", f"/api/tickets/{a['id']}/suggestions") == {"suggestions": []}
    assert reply_calls(hub, "pollen") == []


def test_ticket_page_links_the_sources(c):
    c.connect("pollen", "knowledge")
    (a,) = c.tickets(1)
    s = c.suggest(a["id"], provider="pollen", article_ids=["KB-100", "KB-102"])
    page = c.page(f"/tickets/{a['id']}")
    assert shows(page, s["text"]) and NORTH["KB-100"]["url"] in page
    assert shows(page, NORTH["KB-102"]["title"])


def test_sources_stay_with_the_accepted_draft(app, c):
    c.connect("pollen", "knowledge")
    (a,) = c.tickets(1)
    s = c.suggest(a["id"], provider="pollen", article_ids=["KB-101"])
    draft = c.ok("POST", f"/api/suggestions/{s['id']}/accept")["draft"]
    assert draft == {"text": s["text"], "sources": [source(NORTH["KB-101"])]}
    edited = c.ok("PUT", f"/api/tickets/{a['id']}/draft", json={"text": "edited by hand"})
    assert edited["draft"] == {"text": "edited by hand", "sources": [source(NORTH["KB-101"])]}
    assert NORTH["KB-101"]["url"] in c.page(f"/tickets/{a['id']}")
    app.restart()
    assert app.c.ticket(a["id"])["draft"]["sources"] == [source(NORTH["KB-101"])]
    assert app.c.suggestion(s["id"])["sources"] == [source(NORTH["KB-101"])]
