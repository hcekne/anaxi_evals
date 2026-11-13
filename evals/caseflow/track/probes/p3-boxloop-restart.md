# Request — BoxLoop after a restart

BoxLoop imports nothing after a restart. Please fix it.

## What I need

What we found out from BoxLoop: their service restarts every night, and when it does it forgets
every export it has handed out. After that, `GET {EXTERNAL}/boxloop/exports/{id}` for an export
created before their restart answers `404`, and so does a `download_url` created before it.
This hits us most when our own app has been restarted in the middle of an import too, because
the job then picks up an export id from before.

- A `404` from the export status check or from the download means the export is gone, not that
  the import failed: request a fresh export (`POST {EXTERNAL}/boxloop/exports`) and carry on with
  that one, with the usual checks (right after creating it, then every 5 seconds on the CaseFlow
  clock). The job stays `running` (stage `preparing` while the new export is pending) and must
  not fail because of it.
- This also works when CaseFlow itself was restarted while the job waited.
- Nothing is duplicated: entries that were already saved are unchanged, as before.
- Every other BoxLoop answer keeps its existing meaning (`failed` → `export_failed`, `401` →
  `credentials_rejected`, anything else → `upstream_error`).
