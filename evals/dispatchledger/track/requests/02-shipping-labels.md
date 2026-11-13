# Request 2 — Shipping labels

We are using ParcelFox for deliveries. Let me put in an address and package weight, then get a label for an order. Show its tracking number. Their little test service and instructions are attached.

## What I need

### ParcelFox test service (attached instructions)

Base URL `{EXTERNAL}/parcelfox`. Test token: `pf-test-token`.

`POST {EXTERNAL}/parcelfox/labels` with header `Authorization: Bearer <token>` and

```json
{"order_ref": "o-123", "shipment_ref": "s-456",
 "address": {"name": "Ada Lovelace", "line1": "12 Analytical Row", "city": "London",
             "postcode": "N1 9GU", "country": "GB"},
 "weight_g": 1200, "idempotency_key": "any string up to 100 characters"}
```

- `201 {"label_id": "pfl_...", "tracking_code": "PF...", "label_text": "..."}` — a new label:
  ParcelFox will collect one physical parcel for it.
- `200` with the same body — that `idempotency_key` was already used with this token: you get
  the original label back and nothing new is created. One key means one physical parcel.
- `401 {"error": "unauthorized"}` — bad token. `422 {"error": "invalid_request", "detail": "..."}`
  — bad body. `503 {"error": "unavailable"}` — temporarily unavailable, nothing was created.
- The connection can also drop **after** a label was created, so you get no answer. Find out
  what happened with `GET {EXTERNAL}/parcelfox/labels/by-key/{idempotency_key}` (same header) →
  `200` with the label, or `404 {"error": "not_found"}` when there is none; or repeat the POST
  with the same key.

```sh
curl -s -X POST "$EXTERNAL/parcelfox/labels" -H 'Authorization: Bearer pf-test-token' \
  -H 'Content-Type: application/json' \
  -d '{"order_ref":"o-1","shipment_ref":"s-1","address":{"name":"Ada Lovelace","line1":"12 Analytical Row","city":"London","postcode":"N1 9GU","country":"GB"},"weight_g":1200,"idempotency_key":"s-1"}'
```

### The shop

- `PUT /api/carriers/parcelfox/credentials` with `{"token": "pf-test-token"}` → `204`
  (non-empty string, otherwise `422 invalid_request`). Never shown again.
  `GET /api/carriers` → `{"carriers": [{"id": "parcelfox", "name": "ParcelFox", "configured": true}]}`.
- **Shipments.** Every order now has `"shipments"`: at checkout the shop creates one shipment
  holding all its items:
  `{"id": "<generated>", "status": "not_requested", "carrier": null, "items": [{"product_id": "tea", "quantity": 2}], "address": null, "weight_g": null, "tracking_code": null, "label_id": null, "label_text": null}`.
- `POST /api/orders/{id}/label` with
  `{"address": {"name", "line1", "city", "postcode", "country"}, "weight_g": 1200}` gets the
  order's label from ParcelFox → `201` with the order, its shipment now `"status": "done"`,
  `"carrier": "parcelfox"`, the address and weight given, and ParcelFox's `tracking_code`,
  `label_id` and `label_text`.
  - The address is sent to ParcelFox unchanged, `weight_g` as given, `order_ref` = the order id,
    `shipment_ref` = the shipment id.
  - Validation, with a message that says what is wrong: `name`, `line1` and `city` are
    non-empty strings of at most 100 characters, `postcode` a non-empty string of at most 12,
    `country` two upper-case letters → otherwise `422 invalid_address`. `weight_g` is an
    integer from 1 to 30000 → otherwise `422 invalid_weight`. Unknown order → `404 not_found`.
  - ParcelFox not configured → `409 not_configured`.
  - The shipment already has its label → `200` with the order unchanged; no new parcel. Two
    clicks at the same moment must also end up with exactly one ParcelFox parcel.
  - ParcelFox unavailable, no answer or a dropped connection → `502 carrier_unavailable`, the
    shipment stays `not_requested`; ParcelFox refusing the request (4xx) →
    `502 carrier_rejected`. Asking again later must never produce a second parcel if the
    first one was in fact created.
- The order page (`/orders/{id}`) shows the label's tracking number.
