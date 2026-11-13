# Request 9 — Historical reporting

Show me how many approvals happened each month, with a date filter and workspace totals. Count each approval decision, including a later re-approval, using UTC when it happened. Later edits mustn't change old totals. Include the start date and stop just before the end date, and explain that beside the filter.

## What I need

`GET /api/reports/approvals?from=2026-01-01&to=2026-04-01&workspace_id=...` →

```json
{"from": "2026-01-01", "to": "2026-04-01",
 "workspaces": [{"workspace_id": "...", "name": "Team A", "total": 3,
                 "months": [{"month": "2026-01", "approvals": 2},
                            {"month": "2026-03", "approvals": 1}]}],
 "total": 3}
```

- Counts **approval decisions** (`"decision": "approved"`), not documents: two approvals of one
  document count twice. `changes_requested` decisions are not counted.
- A decision is counted in the UTC month of its `decided_at`.
- `from` and `to` are optional dates `YYYY-MM-DD`. A decision counts when
  `decided_at` ≥ `from` 00:00:00Z and `decided_at` < `to` 00:00:00Z: the start date is included, the
  report stops just before the end date. A missing bound means no limit; they are echoed back
  (`null` when missing). A badly formed date, or `from` after `to` → `422 invalid_request`.
- `workspaces`: every workspace the user belongs to (oldest first), or only `workspace_id` when
  given (not a member or unknown → `404 not_found`). Workspaces without approvals are listed with
  `"total": 0, "months": []`. `months` lists only months with approvals, oldest first.
  The top-level `total` adds up the listed workspaces.
- Totals depend only on the decisions: editing documents later, adding versions or reassigning
  never changes an old total.
- Every member (viewers included) can read the report for their workspaces.
- The page `GET /reports?from=YYYY-MM-DD&to=YYYY-MM-DD` (both optional, as above) shows the
  same report (each month label such as `2026-02` with its count) with the date filter and,
  beside the filter, the sentence "The start date is included; the report stops just before the end date."
