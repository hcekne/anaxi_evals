# Request — ArchiveTap with withdrawals

Add ArchiveTap as another source. It also tells us when documents are withdrawn. Hide those from normal views but retain their history for owners.

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
{"records": [{"record_key": "AT-9", "heading": "Deed", "content": "The deed ...", "edition": 4},
             {"record_key": "AT-3", "edition": 7, "withdrawn": true}],
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

### Records and withdrawals

The feed is an ordered list of events; apply them in order (page by page, record by record).
The same `record_key` can appear several times in one import.

- A normal record (no `withdrawn`, or `"withdrawn": false`) carries `heading`, `content` and
  `edition`. It becomes a document of the connection's case: `title` = `heading`, `text` =
  `content`, `"source": "archivetap"`, `external_id` = `record_key`, `source_revision` =
  `edition`. One document per connection and `record_key`; a new edition adds a version; the
  same edition again is unchanged.
- A withdrawal (`"withdrawn": true`, with `record_key` and `edition` only) withdraws that
  document. A withdrawal of an unknown or already-withdrawn key changes nothing.
- A normal record for a withdrawn document makes it reappear: it is no longer withdrawn, and a
  different edition also adds a version as usual.
- Job counts: a withdrawal or reappearance that changed something counts in `imported`; an event
  that changes nothing counts in `unchanged`.

### What withdrawn means

- Every document now has `"withdrawn": true` or `false` (always `false` for other sources).
- A withdrawn document is hidden from normal views for everyone: the case's documents list and
  page, search, and the JSON download.
- Workspace **owners** can still find it: `GET /api/cases/{case_id}?include_withdrawn=true`
  lists every document of the case, withdrawn ones included, each item as
  `{"id": "...", "title": "...", "withdrawn": true | false}`. For anyone else the parameter is
  ignored (they get the normal list).
- Owners can still open it and its history: `GET /api/documents/{id}` (showing
  `"withdrawn": true`), its versions, reviews, notices and its pages. For everyone else it is
  `404 not_found` everywhere, as if it did not exist, including deciding on it or editing it.
- Report totals do not change when a document is withdrawn: earlier approval decisions still
  count.
- Approval messages: a withdrawn document counts as not visible to a recipient who is not an
  owner, so a pending message to them is cancelled (as for any recipient who loses access).
- Nothing is ever deleted: a document that reappears has its earlier versions and reviews.
