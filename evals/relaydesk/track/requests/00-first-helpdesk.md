# Request 0 — Build the first helpdesk

Make me a little helpdesk website called RelayDesk. I want to upload this CSV of customer messages, see an inbox, open a message and write a reply draft. I don't need it to send emails. If a file cannot be read, tell me and keep the tickets already there. Please make it runnable on my laptop and include a way to check that it works.

## What I need

### The tickets file

The attached file is CSV as in RFC 4180: UTF-8 text (a leading byte-order mark is allowed),
comma-separated, fields may be quoted with `"` and quoted fields may contain commas, doubled
quotes and line breaks. Blank lines at the end are ignored.

- The first row is the header and is exactly `id,customer_email,subject,body`.
- Every other row is one ticket. All four fields are required and non-empty.
- `id` is 1–64 characters from letters, digits, `.`, `_` and `-`.

Attached `tickets.csv`:

```csv
id,customer_email,subject,body
T-1001,ola.nordmann@example.no,Where is my order?,"Hi, I ordered a kettle last week and still have no tracking number. Can you help?"
T-1002,jalal.haddad@example.com,Refund for broken lamp,"The lamp arrived cracked.
I would like a refund, please."
T-1003,søren.ærø@example.dk,Glemt passord,"Jeg får ikke logget inn — kan dere hjelpe meg å nullstille passordet?"
```

### Uploading

`POST /api/imports` with the file's raw bytes as the request body (any `Content-Type`):

- `200 {"imported": ["T-1001", "T-1002", "T-1003"], "skipped": []}`: new tickets are added in
  file order. A row whose `id` is already in RelayDesk leaves the existing ticket (and its draft)
  exactly as it was; its id is listed in `skipped` instead.
- A file that cannot be read → `422` with error code `invalid_csv` and a message saying what is
  wrong. Nothing from that file is added and every ticket already there stays as it was. A file
  cannot be read when it is not UTF-8, is empty, has a different header, has a row with a
  different number of fields, has an empty field or an invalid `id`, or repeats an `id`.

### Tickets and drafts

- `GET /api/tickets` → `{"tickets": [{"id", "customer_email", "subject", "status"}, ...]}` in the
  order the tickets were first imported. `status` is `"open"`.
- `GET /api/tickets/{id}` →
  `{"id", "customer_email", "subject", "body", "status", "draft": {"text": ""}}`, text exactly
  as imported. Unknown id → `404 not_found`.
- `PUT /api/tickets/{id}/draft` with `{"text": "<any string, may be empty>"}` → `200` with the
  ticket as `GET` returns it. Each ticket has its own draft. A missing or non-string `text` →
  `422 invalid_request`; unknown id → `404 not_found`.
- RelayDesk sends no email and contacts no outside service for any of this.

### Pages

- `GET /` — the inbox (HTML): every ticket's subject and customer email, each linking to its
  page, and a way to upload a file.
- `GET /tickets/{id}` — the ticket's page (HTML): subject, customer email, body and a draft
  editor holding the current draft text. Unknown id → `404`.

Our checks only look for the data in these pages (HTML-escaped as usual), not for any layout.
