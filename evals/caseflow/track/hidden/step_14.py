"""Request 14: local fonts and a keyboard-operable larger-text choice on the document screen.
Only the served bytes and the page markup are checked; rendering, persistence across browser
sessions and independent release are not exercised here."""

import hashlib
import re

from conftest import VIEWER, ok

FONTS = {
    "CaseSerif-Regular.woff2": (420, "23693d24feec1fcb6b8f2e5eec93134e1853745282f18e2b3d0739ba8ce77625"),
    "CaseSerif-Bold.woff2": (452, "03d056dd2ecbad3fd7d0bf96c8aadb87aa410d9a41965665d5470d70d0bf5b0e"),
}


def test_font_files_are_served_locally(app):
    for name, (size, digest) in FONTS.items():
        response = app.http.get(f"/assets/fonts/{name}")
        assert response.status_code == 200, name
        assert response.headers["content-type"].split(";")[0].strip() == "font/woff2"
        assert len(response.content) == size
        assert hashlib.sha256(response.content).hexdigest() == digest


def check_page(text: str) -> None:
    assert "@font-face" in text
    assert re.search(r"""font-family:\s*["']?CaseSerif""", text)
    for name in FONTS:
        assert f"/assets/fonts/{name}" in text, name
    assert "http://" not in text and "https://" not in text


def test_document_page_uses_the_fonts_and_offers_larger_text(app):
    case = app.case()
    doc = app.doc(case["id"], "Font check", "Readable text")
    page = app.get(f"/documents/{doc['id']}", user=VIEWER)
    assert page.status_code == 200 and "Readable text" in page.text
    check_page(page.text)
    button = re.search(r"<button[^>]*\bid=[\"']text-size-toggle[\"'][^>]*>", page.text)
    assert button, "no <button id=text-size-toggle>"
    assert re.search(r"aria-pressed=[\"'](true|false)[\"']", button.group(0))
    assert "localStorage" in page.text and "caseflow.textSize" in page.text


def test_older_version_pages_use_the_fonts(app):
    case = app.case()
    doc = app.doc(case["id"], "Versioned font", "one")
    ok(app.patch(f"/api/documents/{doc['id']}", json={"text": "two"}))
    page = app.get(f"/documents/{doc['id']}/versions/1")
    assert page.status_code == 200 and "one" in page.text
    check_page(page.text)


def test_the_api_is_unaffected(app):
    case = app.case()
    doc = app.doc(case["id"], "Still JSON", "x")
    assert app.document(doc["id"])["title"] == "Still JSON"
