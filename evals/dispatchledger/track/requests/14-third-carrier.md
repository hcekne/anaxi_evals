# Request 14 — Third carrier

Add ParcelPine using the attached instructions. I want the same choice of carriers, labels, tracking, and helpful error messages. Everything we already do with the other companies should keep working.

## What I need

### ParcelPine test service (attached instructions)

Test tokens: `pp-test-token` (shop `main`) and `pp-harbour-token` (shop `harbour`).

`POST {EXTERNAL}/parcelpine/shipments` with header `Authorization: Token <token>` and

```json
{"client_reference": "<your unique reference, up to 64 characters>",
 "weight_kg": "1.250",
 "recipient": {"name": "Ada Lovelace", "street": "12 Analytical Row", "city": "London",
               "postal_code": "N1 9GU", "country_code": "GB"}}
```

- `weight_kg` is the weight in kilograms as a decimal string with exactly three decimals:
  1250 g → `"1.250"`, 5 g → `"0.005"`, 30000 g → `"30.000"`.
- `201 {"reference": "PP-...", "document": {"format": "text", "content": "..."}, "tracking": "PP..."}`
  — a new shipment (one physical parcel).
- `200` with the same body — that `client_reference` was used before: the original shipment;
  nothing new is created. Look one up with
  `GET {EXTERNAL}/parcelpine/shipments?client_reference=<ref>` → `200` (the shipment) or
  `404 {"code": "not_found"}`.
- Errors are `{"code": "...", "message": "..."}`:
  - `422 destination_unsupported` — ParcelPine does not deliver to that country (it serves only
    GB, IE, FR, DE, NL and BE). Not worth retrying.
  - `422 invalid_request` — malformed body (including a badly formatted `weight_kg`).
  - `429 rate_limited` with header `Retry-After: <seconds>` — slow down: do not try again for
    that many seconds.
  - `401 unauthorized`; `503 unavailable` (nothing created). Connections can drop after a
    shipment was created.

### The shop

- `PUT /api/carriers/parcelpine/credentials` with `{"token": "pp-test-token"}` → `204`;
  carrier `{"id": "parcelpine", "name": "ParcelPine"}` in `GET /api/carriers`, selectable with
  `"carrier": "parcelpine"` everywhere carriers are chosen, credentials per shop.
- The worker sends `recipient` = name, line1 → `street`, city, postcode → `postal_code`,
  country → `country_code`; `weight_kg` from `weight_g` exactly as above. When done:
  `tracking_code` = `tracking`, `label_text` = `document.content`, `label_id` = `reference`.
- `destination_unsupported` → `needs_attention` at once (no retry) with `last_error.code` =
  `destination_unsupported` and a message naming the country.
- `429` is a transient failure, but the next attempt is not before `Retry-After` seconds
  (clock) from the reply: `next_attempt_at` = reply time + `Retry-After`, instead of the 1/2/4
  second delays. It still counts towards the four attempts.
- Everything else as for the other carriers: statuses, retries, never two parcels for one
  shipment, emails (naming `ParcelPine`), split shipments, pause, per-shop credentials. The
  other carriers keep working unchanged.
- Every `needs_attention` shipment has a `last_error.message` a person can act on.
