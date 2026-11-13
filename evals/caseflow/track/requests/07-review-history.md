# Request 7 — Review history

Editors need to mark documents approved or needing changes and leave a comment. Keep who did it and when, and the version they reviewed. If they change their mind, keep the earlier decision in the history too. Viewers should just be able to read that history.

## What I need

### Decisions

`POST /api/documents/{document_id}/reviews` with
`{"decision": "approved", "comment": "Looks complete", "version": 1}` →

```json
{"id": "...", "document_id": "...", "version": 1, "decision": "approved",
 "comment": "Looks complete", "user": "ana", "decided_at": "2026-03-01T09:00:00Z"}
```

- `decision` is `approved` or `changes_requested`; anything else → `422 invalid_request`.
- `comment` is an optional string (default `""`).
- `version` is required: the document version the reviewer looked at. If it is not the
  document's current version → `409 stale_version`.
- `user` is the `X-User` who decided; `decided_at` is the CaseFlow clock time.
- Editors and owners can decide; viewers → `403 forbidden`.

### History

`GET /api/documents/{document_id}/reviews` → `{"reviews": [...]}`: every decision ever made on the
document, oldest first (decisions at the same clock time stay in the order they were made). A
decision is never changed or removed; changing your mind is a new decision. Every member,
viewers included, can read it.

Documents gain `"review_status"`: the latest decision on the document's current version
(`"approved"` or `"changes_requested"`), or `null` if that version has none.

The document page shows the history (who, when, version, decision, comment) and, for editors and
owners, a form to decide.
