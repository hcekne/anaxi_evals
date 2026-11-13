# Request 12 — Update a busy worker

Add a pause button for each warehouse so it can finish the parcel it is working on and leave the rest waiting. I need to update the warehouse program while orders are queued. When I start it again, carry on safely with those orders.

## What I need

- `GET /api/warehouses` →
  `{"warehouses": [{"id": "north", "paused": false, "waiting": 2, "working": 0}, {"id": "south", ...}]}`
  — `waiting` and `working` count this shop's shipments packed at that warehouse in that status.
- `POST /api/warehouses/{id}/pause` and `POST /api/warehouses/{id}/resume` → `200` with that
  warehouse's entry (pausing a paused warehouse or resuming a running one is fine). Unknown
  warehouse → `404 not_found`. Pausing is per shop: it never affects the other shop.
- While a warehouse is paused, the worker starts no new label attempts for that shop's
  shipments packed there: they stay `waiting` (and do not count as due for `--until-idle`).
  Label requests are still accepted and queued. An attempt already in progress finishes
  normally, and what follows from it still happens (its shipped email, QuickCrate completion).
  Emails, other warehouses and the other shop carry on. After resume, waiting shipments are
  worked on again as usual.
- The `/warehouses` staff page shows each warehouse's state and counts with a pause/resume
  button.

**Stopping and updating the worker.**

- On SIGTERM or SIGINT the running worker starts nothing new, finishes the attempt in progress
  and records its result, then exits with status 0 (within 15 seconds).
- If the worker is killed without warning, possibly after the carrier accepted a label but
  before the result was recorded, the earlier rule applies (taken up again after 60 seconds of
  clock) and the label must still not be duplicated.
- A worker built from newer code must carry on with work that older code queued: waiting
  shipments and emails keep their meaning, completed shipments stay completed.
