# Request 5 — Another carrier

Add QuickCrate too and let me pick the delivery company. They say their label can take a while to be ready. Show that properly, and keep ParcelFox working.

## What I need

### QuickCrate test service (attached instructions)

Test key: `qc-test-key`; its callback secret: `qc-callback-secret`.

`POST {EXTERNAL}/quickcrate/jobs` with header `X-QuickCrate-Key: <key>` and

```json
{"client_ref": "<your unique reference, up to 100 characters>",
 "callback_url": "<optional absolute http(s) URL>",
 "parcel": {"reference": "<free text, e.g. the order id>", "weight_grams": 1200,
            "recipient": {"name": "Ada Lovelace", "address_lines": ["12 Analytical Row"],
                          "city": "London", "postcode": "N1 9GU", "country": "GB"}}}
```

- `202 {"job_id": "qcj_...", "status": "pending"}` — a new label job (one physical parcel).
- `200 {"job_id": ..., "status": ...}` — that `client_ref` was used before: the existing job.
- `401`, `422` and `503` (nothing created) as for the other services; the connection can drop
  after a job was created (repeat with the same `client_ref`).
- `GET {EXTERNAL}/quickcrate/jobs/{job_id}` (same header) →
  `200 {"job_id", "client_ref", "status": "pending" | "ready" | "failed", "label": null | {"tracking": "QC...", "text": "..."}, "failure": null | "<reason>"}`.
  A label can take seconds or hours to become `ready`; a `failed` job never will.

**Completion callbacks.** If you give `callback_url`, QuickCrate also POSTs to it every time the
job's status changes:
`{"callback_id": "cb_...", "job_id": "...", "client_ref": "...", "status": "...", "sequence": 2, "label": ..., "failure": ...}`
with header `X-QuickCrate-Signature: sha256=<hex>`, the HMAC-SHA256 of the raw body bytes keyed
with the callback secret. Example: secret `qc-callback-secret`, body
`{"callback_id":"cb_1","job_id":"qcj_1","status":"ready"}` →
`sha256=adb1e8480c1326f20cff864b1cd16c6d68816509357d9883f86e74bf5dc62478`.
The same callback can arrive more than once (same `callback_id`), and callbacks can arrive out
of order: `sequence` grows with every status change of a job, so a callback with a lower
`sequence` than one already seen is stale. A non-2xx reply makes QuickCrate retry that callback
after 10, 60 and 300 seconds. Polling alone is also fine.

### The shop

- `PUT /api/carriers/quickcrate/credentials` with
  `{"api_key": "qc-test-key", "callback_secret": "qc-callback-secret"}` → `204`.
  `GET /api/carriers` lists both: `{"id": "quickcrate", "name": "QuickCrate", "configured": ...}`.
- `POST /api/orders/{id}/label` accepts `"carrier": "parcelfox" | "quickcrate"` (default
  `parcelfox`): unknown → `422 unknown_carrier`; that carrier not configured →
  `409 not_configured`. The shipment records its `carrier`.
- The worker sends QuickCrate `recipient` = name, `[line1]`, city, postcode, country;
  `weight_grams` = `weight_g`. Retry rules and "never twice" are the same as for ParcelFox
  (one `client_ref` per shipment).
- New shipment status **`preparing`** (shown as "preparing"): QuickCrate has the job but the
  label is not ready. When it becomes `ready` → `done` with `tracking_code` = `label.tracking`,
  `label_text` = `label.text`, `label_id` = the job id (and the shipped email goes out).
  `failed` → `needs_attention` with `last_error.code` = `label_failed`.
- Once QuickCrate reports a job `ready`, the shipment must be `done` after the clock has moved
  on by 30 seconds and one `--until-idle` worker run has finished (or sooner, from a valid
  callback). `--until-idle` must not wait for pending jobs.
- If you accept callbacks: a missing or wrong signature → `401 invalid_signature` and nothing
  changes; duplicate and stale callbacks are answered `2xx` and change nothing. A finished
  shipment never goes back.
- ParcelFox keeps working exactly as before.
