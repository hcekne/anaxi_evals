# Request 13 — Retire an integration

We're stopping ParcelBox. Remove its connection option and stop its unfinished imports. Keep everything it already brought in, including the history and exports. BoxLoop and normal uploads should carry on as before.

## What I need

- A new ParcelBox connection is no longer possible: `"source": "parcelbox"` →
  `422 unsupported_source`, and the pages no longer offer it.
- Existing ParcelBox connections stay listed, with `"status": "retired"`. Starting an import on one
  → `409 source_retired`; changing its credentials → `409 source_retired`.
- ParcelBox jobs that were unfinished (`queued`, `running`, `waiting`, `cancelling`) become
  `cancelled` and never contact ParcelBox again, including after any restart.
- Everything ParcelBox already brought in stays as it is and keeps working: its documents (with
  their `source`, `external_id`, `source_revision` and `connection_id`), versions, reviews,
  responsibility, approval messages, search, the JSON download, reports, and its finished jobs.
- BoxLoop, CSV, PDF and pasted documents carry on exactly as before.
- This has to work on the data we already have: when the new version starts on a data directory
  written by the current version (with ParcelBox connections, finished and unfinished ParcelBox
  jobs and imported documents in it), everything above holds.
