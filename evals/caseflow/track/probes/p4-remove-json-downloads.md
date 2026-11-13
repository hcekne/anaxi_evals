# Request — Remove JSON downloads

Remove JSON downloads. Keep the rest, including reporting and the documents already here.

## What I need

- `GET /api/cases/{case_id}/export` no longer exists: it answers `404` for everyone, and no
  page links to a JSON download any more.
- Everything else stays exactly as it is: cases, documents and their versions, reviews and
  approval messages, search, imports, the monthly approval report and every page.
