# Request 3 — Long-running work

Some imports take ages. Let me leave the page while they run and come back to see progress. If the app restarts halfway through, it should carry on without importing the same documents again. I also want a cancel button. It can finish the request already in progress, then stop; keep the documents it already imported.

## What I need

- Jobs keep running whatever the browser does; their status is always available from
  `GET /api/jobs/{job_id}` and the case page.
- **Restarts.** A job that was `queued`, `running` or `waiting` when the app stopped carries on
  by itself after the app starts again. It continues after the last page whose documents it had
  completely saved: it never requests a saved page again and never creates a duplicate document.
  A page that was in flight but not saved when the app stopped is requested again. A waiting job
  keeps its `retry_at`. The app may be stopped at any moment.
- **Cancel.** `POST /api/jobs/{job_id}/cancel` → `202` with the job.
  - If no request to the source is in flight (for example `queued` or `waiting`), the job becomes
    `cancelled` immediately.
  - If a request is in flight, the job becomes `cancelling`: that request is allowed to finish,
    the documents from its response are saved and counted, and then the job becomes `cancelled`.
    No further requests are made.
  - A job that is already `completed`, `failed` or `cancelled` → `409 conflict`.
  - A `cancelling` job interrupted by a restart becomes `cancelled` without further requests.
  - Documents a cancelled job already saved stay.
- **Progress.** `imported` and `unchanged` only ever count saved documents, so while a job runs
  the counts never exceed what the case already shows; `completed` is reported only after
  everything is saved.
- A running import never blocks the rest of the app: while a source is slow to answer, every
  other page and endpoint keeps responding.
- New statuses: `cancelling`, `cancelled`. A connection's unfinished jobs are the ones in
  `queued`, `running`, `waiting` or `cancelling`.
