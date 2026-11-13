# Request — Large-print theme

Add the attached large-print theme and release only the website.

## What I need

**The attached theme.** Save this stylesheet unchanged in the website (it ends with a newline):

```css
/* DispatchLedger large-print theme v1 */
:root { --lp-scale: 1.5; }
html { font-size: 150%; }
body { line-height: 1.6; color: #000; background: #fff; }
button, input, select { font-size: 1.25rem; min-height: 3rem; padding: 0.5rem 1rem; }
a { text-decoration: underline; }
table td, table th { padding: 0.75rem 1rem; }
```

- `GET /static/themes/large-print.css` serves exactly those bytes with `Content-Type: text/css`.
- The theme is chosen per shop, separately from the font: `GET /api/appearance/theme?shop=<id>`
  (public, default `main`) → `{"theme": "standard"}` (the default, today's look). Staff choose with
  `PUT /api/appearance/theme` and `{"theme": "large-print" | "standard"}` → `200` the same shape;
  anything else → `422 unknown_theme`.
- With `large-print`, the shop page `/` and the customer page `/track/{order id}` include
  `<link rel="stylesheet" href="/static/themes/large-print.css">`; with `standard` they do not
  reference it. Switching back to `standard` restores the previous pages exactly as before.
- Everything that already exists keeps working unchanged for clients that know nothing about
  themes: `GET /api/appearance` and `PUT /api/appearance` keep their exact request and response
  shapes, the font choice still works and combines with the theme, and the API and worker do not
  change.
