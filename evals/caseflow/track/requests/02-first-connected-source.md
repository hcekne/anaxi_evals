# Request 2 — First connected source

Our documents are also in ParcelBox. Let me connect it to a case and import everything, including documents beyond the first page. Sometimes it asks us to wait; show what's happening and continue when it lets us.

## What I need

### The clock

Everything time-based in CaseFlow uses one clock that I can control, so that waits can be
tested without real waiting:

- `GET /api/clock` → `{"now": "2026-01-31T23:59:59Z", "frozen": false}`.
- `PUT /api/clock` with `{"now": "2026-03-01T09:00:00Z"}` sets the clock to that time and freezes
  it there (it does not move until set again) → `200` with the same shape (`"frozen": true`).
  A badly formed time → `422 invalid_request`. Setting it backwards is allowed.
- `DELETE /api/clock` → `200`, back to real time (`"frozen": false`).
- The setting survives restarts.

### Connections

- `POST /api/cases/{case_id}/connections` with
  `{"source": "parcelbox", "credentials": {"token": "pb-123"}}` →
  `201 {"id": "...", "case_id": "...", "source": "parcelbox", "status": "active"}`.
  Unknown `source` → `422 unsupported_source`. Missing or empty token → `422 invalid_request`.
- `GET /api/cases/{case_id}/connections` → `{"connections": [...]}`, oldest first.
  `GET /api/connections/{connection_id}` → one connection.
- `PUT /api/connections/{connection_id}/credentials` with the source's credentials
  (`{"token": "..."}`) → `200` with the connection, `status` back to `"active"`.
- Credentials are never returned or shown.

### Imports

- `POST /api/connections/{connection_id}/imports` → `202` with a new import job. It runs in the
  background; the response does not wait for it.
  - The connection already has an unfinished job → `409 import_in_progress`.
  - The connection's `status` is `"unauthorized"` → `409 credentials_rejected`, without
    contacting ParcelBox.
- `GET /api/jobs/{job_id}` and `GET /api/cases/{case_id}/jobs` (`{"jobs": [...]}`, oldest first):

```json
{"id": "...", "case_id": "...", "connection_id": "...", "source": "parcelbox",
 "status": "running", "imported": 4, "unchanged": 0, "retry_at": null, "error": null}
```

  - `status`: `queued`, `running`, `waiting` (told to wait; `retry_at` says until when),
    `completed` or `failed` (`error` is then `{"code": "...", "message": "..."}`).
  - `imported` counts documents this job created or changed, `unchanged` the ones it found
    already up to date. Both only count documents that have been saved.
  - `completed` only once every document is saved.
- The case page shows the case's connections and jobs with their status.

### ParcelBox

`GET {EXTERNAL}/parcelbox/documents` with header `Authorization: Bearer <token>` returns the
first page; follow with `GET {EXTERNAL}/parcelbox/documents?cursor=<next_cursor>` (URL-encoded)
until `next_cursor` is `null`.

```json
{"items": [{"id": "PB-17", "title": "Lease", "text": "The tenant ...", "revision": 3}],
 "next_cursor": "c2ZhZGY..."}
```

- Cursors are opaque strings: pass them back exactly. A page may have no items. `revision` is an
  integer.
- `429` means wait: its `Retry-After` header is a whole number of seconds. The job goes
  `waiting` with `retry_at` = the clock time of the 429 plus that many seconds, and then repeats
  the same request (same cursor) once the clock has reached `retry_at`, within 2 seconds of
  that. While waiting it makes no requests.
- `401` means the token is wrong, and stays wrong until the credentials change: the job fails
  with `credentials_rejected` and the connection's `status` becomes `"unauthorized"` until
  new credentials are saved.
- Any other non-200 response, unreadable body or connection error: the job fails with
  `upstream_error`.
- ParcelBox can be slow: allow it at least 30 seconds per request.

### Imported documents

Each ParcelBox item becomes a document in the connection's case: `title`, `text`,
`"source": "parcelbox"`, `"external_id": "PB-17"`. Documents now also carry `connection_id` and
`source_revision` (both `null` for pasted and uploaded documents).

- One document per connection and item id. An item whose id and revision are already saved is
  unchanged: nothing is written.
- The same id with a different revision updates that document in place (same document id) with
  the new title, text and revision.
