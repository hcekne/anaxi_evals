# Request 6 — Daily report

Give me a daily report of accepted orders, items sold, and order value. Let me download it as CSV. Use UTC dates, and do not count something twice just because it was retried.

## What I need

- `GET /api/reports/daily?from=2026-03-01&to=2026-03-07` → `{"days": [{"date": "2026-03-02", "orders": 3, "items": 7, "value": 4150}, ...]}`.
  `from` and `to` are UTC dates, both included; missing, malformed or `from` after `to` →
  `422 invalid_request`. One entry per date in the range with at least one accepted order,
  oldest first.
  - `orders`: orders accepted (placed) that UTC day — `created_at` decides the day.
  - `items`: total quantity of their lines. `value`: sum of their totals, in pence.
- An accepted order is an order checkout created. Rejected checkouts never count; a repeated
  submission of the same order counts once; label, shipment and email states (and their
  retries) do not matter.
- `GET /api/reports/daily.csv?from=...&to=...` → `text/csv`, header row
  `date,orders,items,value`, then the same rows, `value` in pounds with two decimals
  (`41.50`).
- `GET /reports` — a page showing the report with a link to download the CSV.
