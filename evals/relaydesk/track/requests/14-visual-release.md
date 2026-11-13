# Request 14 — A small visual release

Give the inbox a font menu with these two supplied fonts. Remember my choice in this browser. Nothing about tickets or replies should change. I'd like to put this visual update live while the reply jobs already running carry on.

## What I need

### The two supplied fonts (attached)

The files are small WOFF2 font files, base64-encoded below. Decode them and ship them
byte-for-byte.

`fjord-sans.woff2` — family name **Fjord Sans**:

```text
d09GMgABAAAAAADUa2zTJyHBJBdyNHo+RQ6NezrXunmyZlz5Ir3ILy94bTZJKOpjR9PQHNxYV3ZaS2bgzxxFx338ySznP0rAmIebpObzMAtz9/UVp4w/mv5Gqwko/f4MvfWDKVP6rCVPP/JbKaixPVei8MUI93hM7hj/BQ0laGlGPsMzuLO9WxYkDkf4hU0I18A3FbgvrvjrAVf8vQfxqEGJb9UGE7n4s2u1XbYq2JnEzseKcZS98RSHWwWnjN9sZ92XVWvWSmTOzh/whg6/XrHu5hg=
```

`larch-serif.woff2` — family name **Larch Serif**:

```text
d09GMgABAAAAAADUjLGCiVQx0B7RZVJAQTpr1E5yGOWE8fF8boGy6zZnTHUt6P8G9tb3rVA7d0MscQF6bm7n8EhwMQZ2dAYURDCmQPlMbYUXyNmhMAE+iv31Jk0v/qCvRjaS8LrON+7VAqOEJYsQplH8EwPr/5j0v2oHHo6uo46J7P4o5UAKKmGq9CqztAPt5SLduHyxauy7TLYD5y5mwhZzzUBQp0hSqUWxP1BE76MrN+nspiHRamGS3Z7OYXfgwHT6Elo/OrN7qQzxRIa0P0nEL4Y=
```

### Fonts in the inbox

- `GET /static/fonts/fjord-sans.woff2` and `GET /static/fonts/larch-serif.woff2` → `200`,
  `Content-Type: font/woff2`, exactly the supplied bytes. These two URLs work without signing in.
- The inbox page (`GET /`) declares both families with `@font-face` rules pointing at those
  URLs (in the page itself or in a stylesheet it links), offers a font menu with both, and uses
  the chosen font for the inbox.
- The choice is remembered in the browser, not for the team: picking a font stores it in a
  cookie named `relaydesk_font` with the value `fjord-sans` or `larch-serif`, and the inbox
  page is rendered with the font from that cookie. The inbox page's `<body>` element carries
  `data-font="<value>"` naming the font in use; without the cookie, or with any other value,
  it is `fjord-sans`.

### Releasing it

Nothing else changes: every API answer, stored record and background job behaves as before.
Putting this live means stopping the running version and starting the new one on the same data
directory; replies that were still being worked on when the old version stopped finish in the
new version (as request 10 already requires), and Harbor jobs are not submitted again.
