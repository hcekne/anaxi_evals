"""Probe 2: a purely visual change to the inbox header; everything else must stay as it was."""

import re

from step_14 import with_stylesheets


def test_header_uses_the_accent_colour_and_spacing(c):
    text = with_stylesheets(c, c.page("/")).lower()
    assert "#0b7a75" in text
    assert re.search(r"padding[^;{}]*24px", text)


def test_inbox_still_lists_tickets(c):
    (a,) = c.tickets(1)
    page = c.page("/")
    assert a["id"] in page and a["customer_email"] in page
