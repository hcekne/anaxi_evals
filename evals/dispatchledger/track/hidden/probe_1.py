"""Probe 1: a large-print theme released with the website only; old clients unaffected."""

import httpx

from conftest import expect_error

CSS = '/* DispatchLedger large-print theme v1 */\n:root { --lp-scale: 1.5; }\nhtml { font-size: 150%; }\nbody { line-height: 1.6; color: #000; background: #fff; }\nbutton, input, select { font-size: 1.25rem; min-height: 3rem; padding: 0.5rem 1rem; }\na { text-decoration: underline; }\ntable td, table th { padding: 0.75rem 1rem; }\n'
LINK = "/static/themes/large-print.css"


def theme(app, value, staff="main"):
    response = app.put("/api/appearance/theme", staff=staff, json={"theme": value})
    assert response.status_code == 200 and response.json() == {"theme": value}, response.text


def page(app, path="/", shop=None):
    return httpx.get(f"{app.public_url}{path}", params={"shop": shop} if shop else None).text


def test_stylesheet_served_exactly(app):
    response = httpx.get(f"{app.public_url}{LINK}")
    assert response.status_code == 200
    assert response.headers["content-type"].split(";")[0] == "text/css"
    assert response.content == CSS.encode()


def test_default_and_choice(app):
    assert httpx.get(f"{app.public_url}/api/appearance/theme").json() == {"theme": "standard"}
    order = app.order()
    before_shop, before_track = page(app), page(app, f"/track/{order['id']}")
    assert LINK not in before_shop and LINK not in before_track
    theme(app, "large-print")
    try:
        assert httpx.get(f"{app.public_url}/api/appearance/theme").json() == {"theme": "large-print"}
        assert LINK in page(app) and LINK in page(app, f"/track/{order['id']}")
        assert "Breakfast Tea" in page(app)
    finally:
        theme(app, "standard")
    assert LINK not in page(app) and LINK not in page(app, f"/track/{order['id']}")


def test_validation_and_per_shop(app):
    expect_error(app.put("/api/appearance/theme", json={"theme": "huge"}), 422, "unknown_theme")
    expect_error(app.put("/api/appearance/theme", json={}), 422, "unknown_theme")
    assert httpx.put(f"{app.public_url}/api/appearance/theme", json={"theme": "standard"}).status_code == 401
    theme(app, "large-print", staff="harbour")
    try:
        assert LINK in page(app, shop="harbour") and LINK not in page(app)
        assert httpx.get(f"{app.public_url}/api/appearance/theme", params={"shop": "harbour"}).json() == {
            "theme": "large-print"}
    finally:
        theme(app, "standard", staff="harbour")


def test_old_font_clients_unchanged(app):
    response = app.put("/api/appearance", json={"font": "dispatch-sans"})
    assert response.status_code == 200 and response.json() == {"font": "dispatch-sans"}
    theme(app, "large-print")
    try:
        assert httpx.get(f"{app.public_url}/api/appearance").json() == {"font": "dispatch-sans"}
        shop = page(app)
        assert LINK in shop and "dispatch-sans.woff2" in shop
    finally:
        theme(app, "standard")
        app.put("/api/appearance", json={"font": "system"})


def test_choice_survives_restart(fresh_app):
    theme(fresh_app, "large-print")
    fresh_app.restart()
    assert LINK in page(fresh_app)
