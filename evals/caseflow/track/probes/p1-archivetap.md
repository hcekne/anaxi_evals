# Request — ArchiveTap

Add ArchiveTap as another document source.

## What I need

### Connecting

`POST /api/cases/{case_id}/connections` with
`{"source": "archivetap", "credentials": {"account": "acme", "secret": "s3cr3t"}}` → `201`
connection with `"source": "archivetap"`. Both fields are required non-empty strings, otherwise
`422 invalid_request`. `PUT /api/connections/{id}/credentials` takes the same
`{"account": "...", "secret": "..."}`. The secret is never returned or shown.

ArchiveTap behaves like ParcelBox did, under its own names: everything the earlier requests
asked of imports applies (background jobs and their statuses and counts, waiting on `429`,
`401` making the connection `"unauthorized"`, carrying on after a restart from the page after
the last saved one, cancelling, one unfinished job per connection, revisions becoming new
versions, responsibility, roles, search, the JSON download, reports and messages).
ParcelBox stays retired.

### ArchiveTap

`GET {EXTERNAL}/archivetap/records` with headers `X-Archive-Account: <account>` and
`X-Archive-Secret: <secret>` returns the first page; follow with
`GET {EXTERNAL}/archivetap/records?page=<next_page>` (URL-encoded) until `next_page` is `null`.

```json
{"records": [{"record_key": "AT-9", "heading": "Deed", "content": "The deed ...", "edition": 4}],
 "next_page": "q1w2e3..."}
```

- `next_page` values are opaque: pass them back exactly. A page may have no records. `edition`
  is an integer.
- `429` with an integer `Retry-After` header: wait on the CaseFlow clock exactly as for ParcelBox
  (`waiting`, `retry_at`, then repeat the same request within 2 seconds of the clock reaching it).
- `401`: the job fails with `credentials_rejected` and the connection becomes `"unauthorized"`
  until its credentials change; starting an import meanwhile → `409 credentials_rejected`.
- Any other non-200 answer, unreadable body or connection error: the job fails with
  `upstream_error`. Allow at least 30 seconds per request.

### Documents

Each record becomes a document of the connection's case: `title` = `heading`, `text` =
`content`, `"source": "archivetap"`, `external_id` = `record_key`, `source_revision` =
`edition`. One document per connection and `record_key`; an unchanged key and edition is a
no-op; a new edition adds a version.
