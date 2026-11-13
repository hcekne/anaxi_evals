# Request 13 — Website appearance only

The shop page looks a bit plain. Add the two attached fonts and a choice between them. I want to put just this website change live while the shop server and warehouse program keep running exactly as they are.

## What I need

**The attached fonts.** Save these two files (base64 below) unchanged in the website:

- Ledger Serif → `ledger-serif.woff2`:
  `d09GMtNrSU5qieGENp7zf+Edomkzzu/g6bED/s1YfKGp/exn02tJTmqJ4YQ2nvN/4R2iaTPO7+DpsQP+zVh8oan97GfTa0lOaonhhDae83/hHaJpM87v4OmxA/7NWHyhqf3sZ0xlZGdlciBTZXJpZg==`
- Dispatch Sans → `dispatch-sans.woff2`:
  `d09GMoPW62ePcKodw6LNwNiLaJfcP03wVHVHpSDF0ZMYcvQ9g9brZ49wqh3Dos3A2Itol9w/TfBUdUelIMXRkxhy9D2D1utnj3CqHcOizcDYi2iX3D9N8FR1R6UgxdGTGHL0PURpc3BhdGNoIFNhbnM=`

**What the site does.**

- `GET /static/fonts/ledger-serif.woff2` and `GET /static/fonts/dispatch-sans.woff2` serve
  exactly those bytes with `Content-Type: font/woff2`.
- The font choice is per shop: `GET /api/appearance?shop=<id>` (public, default `main`) →
  `{"font": "system"}`, where `"system"` (the default) is today's look. Staff choose with
  `PUT /api/appearance` and `{"font": "ledger-serif" | "dispatch-sans" | "system"}` → `200`
  the same shape; anything else → `422 unknown_font`.
- The shop page `/` for a shop whose font is chosen includes an `@font-face` rule loading that
  font's URL above (font family `Ledger Serif` or `Dispatch Sans`) and uses it for the page
  text. With `system` the page references neither font file.
- Nothing else about the shop, its API or the worker changes.
