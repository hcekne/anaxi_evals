# Request — KiteCourier

Add this fourth carrier; its tracking reference arrives separately from the label.

## What I need

### KiteCourier test service (attached instructions)

Test keys: `kc-test-key` (shop `main`) and `kc-harbour-key` (shop `harbour`).

`POST {EXTERNAL}/kitecourier/consignments` with header `X-Kite-Key: <key>` and

```json
{"request_id": "<your unique reference, up to 100 characters>", "mass_g": 1200,
 "deliver_to": {"name": "Ada Lovelace", "line1": "12 Analytical Row", "city": "London",
                "postcode": "N1 9GU", "country": "GB"}}
```

- `201 {"consignment_id": "kc_...", "label": {"format": "text", "content": "..."}}` — a new
  consignment (one physical parcel). The label is ready at once, but **there is no tracking
  reference yet**.
- `200` with the same body — that `request_id` was used before: the original consignment.
  Look one up with `GET {EXTERNAL}/kitecourier/consignments?request_id=<id>` → `200` (same body)
  or `404 {"error": "not_found"}`.
- `GET {EXTERNAL}/kitecourier/consignments/{consignment_id}/tracking` →
  `200 {"consignment_id": "...", "status": "awaiting_tracking", "tracking_number": null}` until
  KiteCourier assigns one (minutes to hours later), then
  `200 {"consignment_id": "...", "status": "assigned", "tracking_number": "KC..."}`.
- `401 {"error": "unauthorized"}`, `422 {"error": "invalid_request"}`, `503` (nothing created);
  connections can drop after a consignment was created.

### The shop

- `PUT /api/carriers/kitecourier/credentials` with `{"api_key": "kc-test-key"}` → `204`, per
  shop; carrier `{"id": "kitecourier", "name": "KiteCourier"}` in `GET /api/carriers`, selectable
  with `"carrier": "kitecourier"` wherever carriers are chosen. Not configured →
  `409 not_configured`.
- The worker sends `mass_g` = `weight_g` and `deliver_to` = the address as given, with one
  `request_id` per shipment. Retry rules and "never two parcels" are as for the other carriers.
- New shipment status **`awaiting_tracking`** (shown as "awaiting tracking"): the label exists
  (`label_text` = `label.content`, `label_id` = `consignment_id`) but `tracking_code` is still
  `null`. It counts as not shipped yet. Once KiteCourier reports a tracking number the shipment
  becomes `done` with `tracking_code` = `tracking_number`; that must have happened after the
  clock has moved on by 60 seconds and one `--until-idle` worker run has finished, and
  `--until-idle` must not wait for tracking numbers.
- The shipped email for such a shipment is sent only once its tracking number is known, and
  includes it (and names `KiteCourier`).
- ParcelFox, QuickCrate and ParcelPine keep working unchanged.
