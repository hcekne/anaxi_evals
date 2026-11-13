# Request 10 — Second shop

I am opening a second shop in the same app. Give it its own products, orders, stock, carrier settings, and staff login. Staff from one shop must not see or change the other shop's information.

## What I need

**Shops and staff (public fixture).**

| shop id | name | staff login | password |
| --- | --- | --- | --- |
| `main` | DispatchLedger | `morgan` | `morgan-test-pass` |
| `harbour` | DispatchLedger Harbour | `rowan` | `rowan-test-pass` |

Everything that exists today belongs to `main` and must be kept. `harbour` starts empty: no
products, orders, stock, warehouse preference (default `north`) or carrier credentials.
Harbour's test credentials: ParcelFox token `pf-harbour-token`; QuickCrate key
`qc-harbour-key` with callback secret `qc-harbour-secret`.

**Login.** `POST /api/login` with `{"username": "rowan", "password": "rowan-test-pass"}` →
`200 {"token": "<opaque>", "shop_id": "harbour"}`; wrong username or password →
`401 invalid_credentials`. Staff send `Authorization: Bearer <token>`. Tokens stay valid at
least until the web app restarts. `GET /api/shop` → `{"id": "harbour", "name": "DispatchLedger Harbour"}`.

**Public (customer) endpoints** need no login and pick the shop with the query parameter
`?shop=<shop id>` (absent → `main`; unknown → `404 not_found`): `GET /api/products`,
`GET /api/products/{id}`, `POST /api/quote`, `POST /api/orders`, the shop page `/`, and
`/track/{order id}` (an order link works on its own). Product ids are per shop: both shops may
have a `tea`.

**Every other `/api/...` endpoint is for staff**: without a valid token → `401 unauthorized`.
Staff act only on their own shop: another shop's orders, products, shipments, emails or
returns → `404 not_found`; lists, reports and CSV exports contain only their own shop;
products they add, stock feeds they deliver, warehouse preference and carrier credentials
apply to their own shop only (return references are unique per shop). Staff pages (`/orders`,
`/orders/{id}`, `/reports`) need a login too: accept the same `Authorization` header, plus a
login form at `/login` for browsers; without a login they show no shop data.

**Carriers per shop.** Each shop's labels use that shop's own carrier credentials, never the
other shop's; a shop without credentials for a carrier gets `409 not_configured`. QuickCrate
callbacks for a shop's jobs are signed with that shop's callback secret. The worker serves both
shops.
