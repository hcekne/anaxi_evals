# Request 11 — Stop unwanted work

Add a stop button for an unfinished suggestion, including ones in a batch. Once I stop it, a late answer mustn't appear in my draft. For Harbor, tell their service to cancel too. Stopping one ticket mustn't stop the others.

## What I need

- `POST /api/suggestions/{id}/cancel` → `200` with the suggestion, now `"status": "cancelled"`.
  Only a `queued` or `running` suggestion can be stopped; a `completed`, `failed` or `cancelled`
  one → `409 conflict` and it stays exactly as it was. Unknown (or another team's) →
  `404 not_found`.
- Once cancelled, a suggestion never changes again: its status stays `cancelled` and its `text`
  stays what it was at that moment, whatever arrives later. It cannot be accepted
  (`409 conflict`) and never touches the draft.
- A `queued` suggestion that is cancelled is never sent to its provider.
- A Harbor suggestion whose job was already submitted: send `DELETE {EXTERNAL}/harbor/jobs/{job_id}`
  once, and stop polling that job.
- A streaming suggestion stops reading the stream (closing the connection is fine).
- Stopping one item of a batch leaves the other items running. A batch is `completed` once each
  item is `completed`, `failed` or `cancelled`.
- A cancelled suggestion stays cancelled after a restart and is not resumed.
- The ticket page and batch progress show a stop button for each unfinished suggestion.
