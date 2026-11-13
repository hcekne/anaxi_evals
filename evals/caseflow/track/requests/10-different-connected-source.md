# Request 10 — A different connected source

Another team uses BoxLoop. Add that too. It makes us request an export and wait for a download, so please show progress while it's preparing. I'd like both connections to keep working in the same case.

## What I need

### Connecting

`POST /api/cases/{case_id}/connections` with
`{"source": "boxloop", "credentials": {"api_key": "bl-123"}}` → `201` connection with
`"source": "boxloop"`. Missing or empty `api_key` → `422 invalid_request`.
`PUT /api/connections/{id}/credentials` takes `{"api_key": "..."}` for a BoxLoop connection.
Starting an import, the job endpoints, cancel, restarts and the role rules work as for ParcelBox.
A case can have ParcelBox and BoxLoop connections side by side.

### BoxLoop

Every request carries the header `X-BoxLoop-Key: <api_key>`.

1. `POST {EXTERNAL}/boxloop/exports` with body `{}` →
   `201 {"id": "exp-41", "status": "pending"}` starts preparing a full export of the account.
2. `GET {EXTERNAL}/boxloop/exports/{id}` →
   - `200 {"id": "exp-41", "status": "pending"}`: still preparing;
   - `200 {"id": "exp-41", "status": "ready", "download_url": "<absolute URL>"}`;
   - `200 {"id": "exp-41", "status": "failed", "reason": "..."}`.
3. `GET <download_url>` → `200` with a UTF-8 JSON array:
   `[{"key": "case/lease.txt", "name": "Lease", "body": "...", "version": 7}]` (`version` is an
   integer). This is everything in the account; there is no paging and no "changes since".

Check the export's status right after creating it, then again each time 5 seconds have passed on
the CaseFlow clock since the previous check (within 2 seconds of that). While the export is
`pending` the job is `running` with `"stage": "preparing"`.

- `failed` → the job fails with `export_failed`.
- `401` from any of these → the job fails with `credentials_rejected` and the connection becomes
  `"unauthorized"`, exactly like ParcelBox.
- Any other unexpected response or connection error → the job fails with `upstream_error`.
- After a restart, a job that had already created its export carries on checking **that** export;
  it does not create another one. The same goes for one that was downloading or saving.
- Cancel works as for ParcelBox: while the job only waits for the next check, it is cancelled
  immediately and makes no more requests.

### Jobs

Jobs gain `"stage"`: `"preparing"` while a BoxLoop export is pending; otherwise `null` or a short
word of your choice describing what the job is doing.

### Documents

Each entry becomes a document: `title` = `name`, `text` = `body`, `"source": "boxloop"`,
`external_id` = `key`, `source_revision` = `version`, `connection_id` = the connection. Keys
are scoped to their connection: the same key in another connection, or the same id from
ParcelBox, is a different document. An entry whose key and version are already saved is
unchanged; a new version of a known key updates its document like a ParcelBox revision does.
