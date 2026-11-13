"""Request 13: two font files served byte-exact and a per-shop font choice on the shop page;
the rest of the shop behaves as before."""

import base64

import httpx

from conftest import expect_error, shipment_of

FONTS = {
    "ledger-serif": ("Ledger Serif", "d09GMtNrSU5qieGENp7zf+Edomkzzu/g6bED/s1YfKGp/exn02tJTmqJ4YQ2nvN/4R2iaTPO7+DpsQP+zVh8oan97GfTa0lOaonhhDae83/hHaJpM87v4OmxA/7NWHyhqf3sZ0xlZGdlciBTZXJpZg=="),
    "dispatch-sans": ("Dispatch Sans", "d09GMoPW62ePcKodw6LNwNiLaJfcP03wVHVHpSDF0ZMYcvQ9g9brZ49wqh3Dos3A2Itol9w/TfBUdUelIMXRkxhy9D2D1utnj3CqHcOizcDYi2iX3D9N8FR1R6UgxdGTGHL0PURpc3BhdGNoIFNhbnM="),
}


def choose(app, font, staff="main"):
    response = app.put("/api/appearance", staff=staff, json={"font": font})
    assert response.status_code == 200 and response.json() == {"font": font}, response.text


def shop_page(app, shop=None):
    params = {"shop": shop} if shop else None
    return httpx.get(f"{app.public_url}/", params=params).text


def test_font_files_are_served_exactly(app):
    for slug, (_, data) in FONTS.items():
        response = httpx.get(f"{app.public_url}/static/fonts/{slug}.woff2")
        assert response.status_code == 200
        assert response.headers["content-type"].split(";")[0] == "font/woff2"
        assert response.content == base64.b64decode(data)


def test_default_is_system(app):
    assert httpx.get(f"{app.public_url}/api/appearance").json() == {"font": "system"}
    page = shop_page(app)
    assert "ledger-serif.woff2" not in page and "dispatch-sans.woff2" not in page


def test_choice_changes_shop_page(app):
    try:
        for slug, (family, _) in FONTS.items():
            choose(app, slug)
            assert httpx.get(f"{app.public_url}/api/appearance").json() == {"font": slug}
            page = shop_page(app)
            assert "@font-face" in page and f"/static/fonts/{slug}.woff2" in page and family in page
            other = next(s for s in FONTS if s != slug)
            assert f"{other}.woff2" not in page
            assert "Breakfast Tea" in page
    finally:
        choose(app, "system")
    page = shop_page(app)
    assert "ledger-serif.woff2" not in page and "dispatch-sans.woff2" not in page


def test_choice_is_per_shop_and_validated(app):
    choose(app, "dispatch-sans", staff="harbour")
    try:
        assert "dispatch-sans.woff2" in shop_page(app, "harbour")
        assert "dispatch-sans.woff2" not in shop_page(app)
        assert httpx.get(f"{app.public_url}/api/appearance", params={"shop": "harbour"}).json() == {
            "font": "dispatch-sans"}  # fmt: skip
        expect_error(app.put("/api/appearance", json={"font": "comic-sans"}), 422, "unknown_font")
        expect_error(app.put("/api/appearance", json={}), 422, "unknown_font")
        assert httpx.put(f"{app.public_url}/api/appearance", json={"font": "system"}).status_code == 401
    finally:
        choose(app, "system", staff="harbour")


def test_choice_survives_restart(fresh_app):
    choose(fresh_app, "ledger-serif")
    fresh_app.restart()
    assert "ledger-serif.woff2" in shop_page(fresh_app)


def test_shop_still_works_with_a_font(app, hub):
    choose(app, "ledger-serif")
    try:
        order = app.order()
        shipped = app.ship(order["id"])
        assert shipment_of(shipped)["status"] == "done"
        track = httpx.get(f"{app.public_url}/track/{order['id']}")
        assert shipment_of(shipped)["tracking_code"] in track.text
    finally:
        choose(app, "system")
