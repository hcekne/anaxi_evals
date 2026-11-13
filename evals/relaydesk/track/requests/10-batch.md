# Request 10 — Work through a batch

Let me select up to ten tickets and ask for suggestions in the background. I should be able to leave the page and come back. If the app restarts halfway through, the finished suggestions should still be there and unfinished tickets should carry on.

## What I need

- `POST /api/batches` with `{"ticket_ids": ["T-1", ...], "provider": "pollen"}` → `201`:

  ```json
  {"id": "<batch id>", "provider": "pollen", "status": "running",
   "items": [{"ticket_id": "T-1", "suggestion_id": "<id>", "status": "queued"}]}
  ```

  - 1 to 10 distinct ticket ids of the team; otherwise `422 invalid_request`. An unknown ticket
    → `404 not_found`. `provider` is optional (the saved choice when left out). Provider not
    connected → `409 not_configured`. On any error nothing is created.
  - Every item is an ordinary suggestion for its ticket (no articles, no orders): it appears in
    `GET /api/suggestions/{id}` and in the ticket's suggestion list, and is accepted the usual
    way. Items keep the order of `ticket_ids`.
- Suggestions have a new status `queued`: recorded but not yet sent to the provider. How many
  items run at the same time is up to you.
- `GET /api/batches/{id}` → the batch with each item's current status (the same as its
  suggestion's). The batch is `running` until every item has finished (`completed` or
  `failed`), then `completed`. `GET /api/batches` → `{"batches": [...]}`, oldest first. Batches
  belong to the team like everything else (another team's → `404 not_found`).
- The work happens in the app, not in the page: closing the page changes nothing.
- **Restarts.** Every suggestion that has not finished — in a batch or not — carries on by
  itself after the app starts again, even when the app was killed abruptly. Finished suggestions
  stay exactly as they were. A ticket never gets a second suggestion for the same batch item.
  Sending a Pollen or Comet request again after a restart is fine; a Harbor job that was already
  submitted must be resumed by polling its job id, never submitted again.
- The inbox page lets the person select tickets and start a batch, and shows batch progress.
