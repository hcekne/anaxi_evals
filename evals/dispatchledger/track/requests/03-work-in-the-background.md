# Request 3 — Work in the background

Getting labels is slowing the page down. Queue them and let me run the shipping work on the warehouse computer while the shop keeps taking orders. Show waiting, working, done, or needs attention. If ParcelFox is temporarily down, try again; never send the same parcel twice.

## What I need

**The worker.** Add a `"worker"` entry to `run.json`: the argv that starts the shipping worker as
its own process, for example
`{"command": [...], "worker": [".venv/bin/python", "-m", "dispatchledger", "worker"]}`.
It runs from the repository root with the same environment variables as the web app (they share
`DISPATCHLEDGER_DATA_DIR`), and the web app does not need to be running for it to work. Our
tooling starts it two ways:

- **As is**: it keeps working until it gets SIGTERM or SIGINT, and picks up new work within one
  second (real time).
- **With `--until-idle` appended**: it does every job that is due now — including work that
  becomes due during the run — then exits with status 0 as soon as nothing is due. Jobs
  scheduled for a later time are not due yet; the run does not wait for them.

**Queued labels.** `POST /api/orders/{id}/label` keeps its body, validation and errors
(`422 invalid_address`, `422 invalid_weight`, `404 not_found`, `409 not_configured`), but no
longer talks to ParcelFox: it queues the work and answers `202` with the order, the shipment in
`"status": "waiting"` with the address and weight recorded. It must answer promptly even when
ParcelFox is hanging. If the shipment is already `waiting`, `working` or `done` → `200` with the
order and nothing new is queued. If it is `needs_attention` → it is queued again (`202`, status
`waiting`, `attempts` back to 0).

Shipments now also have `"attempts"` (label attempts since the label was last requested),
`"next_attempt_at"` (a time, or `null`) and `"last_error"` (`{"code": "...", "message": "..."}`
or `null`). Statuses:

| status | meaning | shown on pages as |
| --- | --- | --- |
| `not_requested` | no label asked for yet | not requested |
| `waiting` | queued, possibly until `next_attempt_at` | waiting |
| `working` | a worker is getting the label right now | working |
| `done` | label obtained; tracking code known | done |
| `needs_attention` | given up; `last_error` says why | needs attention |

**Retries (public data pack).** A *transient* failure is no answer (connection error, dropped
connection, timeout after 10 seconds) or an HTTP 5xx or 429 reply. After a transient failure the
shipment goes back to `waiting` and is retried at most three times, with virtual delays of
1, 2 and 4 seconds: `next_attempt_at` = the time of the failure + 1 s after the first failure,
+ 2 s after the second, + 4 s after the third. A job is due when the current time (the clock
file) is at or after `next_attempt_at`. A fourth failed attempt → `needs_attention` with
`last_error.code` = `carrier_unavailable`. Any other 4xx refusal → `needs_attention` at once
with `last_error.code` = `carrier_rejected`.

**Never twice.** Every attempt for one shipment, including after being queued again and after
crashes or restarts, uses the same ParcelFox idempotency key, so one shipment is never more than
one physical parcel. When an attempt's outcome is unknown (dropped connection), the next attempt
must end with the label ParcelFox actually created.

**Durability.** Queued work survives restarts of the web app and of the worker. If a worker
stops while a shipment is `working` (killed, crashed), a later worker takes that shipment up
again once 60 seconds (clock) have passed since the attempt started.
