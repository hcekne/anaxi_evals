# Request — Carrier cut-off pauses

Handle this newly supplied warehouse pause reason and update the warehouse program without interrupting shop orders.

## What I need

**The new pause reason (supplied by the warehouse team).** Pauses now have a reason:

| reason | meaning |
| --- | --- |
| `manual` | what pausing has always meant: paused until someone presses resume. |
| `carrier_cutoff` | the carriers' collection has gone for the day: paused **until** a given time, then the warehouse carries on by itself, without anyone pressing resume. |

- `POST /api/warehouses/{id}/pause` accepts an optional JSON body
  `{"reason": "carrier_cutoff", "until": "2026-03-02T17:00:00Z"}`. Without a body (as today) the
  reason is `manual`. `carrier_cutoff` needs an `until` later than the current time (clock);
  `manual` takes no `until`. Any other reason, a `manual` pause with an `until`, or a
  missing/invalid/past `until` for `carrier_cutoff` → `422 invalid_request`.
- Warehouse entries (`GET /api/warehouses` and the pause/resume answers) gain `"reason"` and
  `"until"`: `null` both when running, `"manual"`/`null` for a manual pause, and
  `"carrier_cutoff"` with the time for a cut-off. Once the clock reaches `until`, the warehouse
  counts as running again (`paused: false`, reason and until `null`) and the worker starts its
  waiting labels as usual — the first `--until-idle` run at or after that time does them. Resume
  ends either kind of pause at once.
- Everything else about pausing is unchanged (per shop, the attempt in progress finishes,
  emails continue, `--until-idle` does not wait for a paused warehouse). Work queued before the
  update keeps its meaning, and an old-style pause made before the update stays a manual pause.
- Shop orders must keep being taken while the worker is updated.
