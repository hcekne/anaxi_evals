# Request 11 — Updated source documents

When a source document changes, bring in the new version and make that the one people normally open. Keep the old versions and their reviews. The new version needs its own review, and I'd like search to use the latest version.

## What I need

- Every change to a document's title or text keeps the previous content as an older version:
  a source bringing a new revision (ParcelBox, BoxLoop) and an edit (`PATCH`) both add a
  version. `version` numbers count up from 1 per document. Replaying an unchanged revision
  adds nothing.
- `GET /api/documents/{document_id}` (and every list, the document page, search) shows the
  latest version.
- `GET /api/documents/{document_id}/versions` →
  `{"versions": [{"version": 1, "title": "...", "text": "...", "source_revision": 3, "created_at": "2026-03-01T09:00:00Z"}, ...]}`,
  oldest first, latest included. `created_at` is the CaseFlow clock time the version was saved.
  `GET /api/documents/{document_id}/versions/{version}` → one of them; unknown → `404 not_found`.
- Reviews stay attached to the version they were made on. A new version starts unreviewed
  (`review_status` is `null`) and can be decided on with its own `version` number; deciding on an
  older version is still `409 stale_version`.
- Search only looks at each document's latest title and text.
- Approval messages already decided on keep the `revision` they were decided on.
- The document page links to its older versions; `GET /documents/{document_id}/versions/{version}`
  shows one.
