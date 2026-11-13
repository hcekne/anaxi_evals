# Request 12 — Export for another team

Let me download a case as JSON, including document IDs, latest text, old versions, and review history. Use the example format so the other team's importer can read it. Viewers can download too, but only what they are allowed to see.

## What I need

`GET /api/cases/{case_id}/export` → `200` with `Content-Type: application/json` and
`Content-Disposition: attachment; filename="case-<case_id>.json"`. The body is exactly this
format (our importer is strict: no other keys, no missing keys):

```json
{
  "format": "caseflow-case/1",
  "case": {"id": "...", "name": "...", "workspace_id": "..."},
  "documents": [
    {
      "id": "...",
      "title": "Lease agreement",
      "text": "latest text",
      "version": 2,
      "source": "parcelbox",
      "external_id": "PB-17",
      "responsible": "ana",
      "versions": [
        {"version": 1, "title": "...", "text": "...", "source_revision": 3, "created_at": "2026-03-01T09:00:00Z"},
        {"version": 2, "title": "...", "text": "...", "source_revision": 4, "created_at": "2026-03-02T09:00:00Z"}
      ],
      "reviews": [
        {"id": "...", "version": 1, "decision": "approved", "comment": "", "user": "ana", "decided_at": "2026-03-01T10:00:00Z"}
      ]
    }
  ]
}
```

- `title`, `text` and `version` are the latest version's. Values are exactly what the API shows
  for the same objects (same ids, timestamps and text).
- Documents oldest first; `versions` oldest first, latest included; `reviews` in decision order
  (all versions).
- An empty case exports `"documents": []`. Any text (quotes, backslashes, line breaks, Unicode)
  must come out as valid JSON that parses back to exactly the original.
- Every member, viewers included, can download a case of their workspace; others get
  `404 not_found`. Only that case's documents are included.
- The case page has a download link to `/api/cases/{case_id}/export`.
