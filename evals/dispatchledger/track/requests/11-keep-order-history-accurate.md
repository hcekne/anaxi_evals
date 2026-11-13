# Request 11 — Keep order history accurate

If I rename a product or change its price tomorrow, yesterday's orders, emails, returns, and reports should still show what the customer actually bought and paid. New orders should use the new details.

## What I need

- `PATCH /api/products/{id}` with `{"name": "...", "price": ...}` (either or both; same rules as
  when adding) → `200` with the product. The shop page, quotes and new orders use the new
  details at once.
- Everything about an existing order keeps what the customer actually bought and paid: its
  lines' names, unit prices and totals in the API and pages, emails sent later (for example the
  shipped email after a rename), return values, and reports.

**Historical records (public data pack).** Orders from the old till system are imported with
`POST /api/orders/import`:

```json
{"orders": [{"legacy_id": "TILL-0042", "created_at": "2026-01-15T10:30:00Z",
             "customer": {"name": "Grace Hopper", "email": "grace@example.test"},
             "items": [{"product_id": "tea", "name": "Breakfast Tea (Assam)",
                        "unit_price": 395, "quantity": 2}]}]}
```

→ `200 {"orders": [{"legacy_id": "TILL-0042", "order_id": "<id>"}]}` in the order given. Each
record holds the purchase-time product names and prices: the imported order shows exactly these
(`line_total` = `unit_price` × `quantity`, `total` = their sum), whatever the catalogue says now;
the product need not exist any more. `created_at` is kept. An import takes no stock and sends
no emails; the order has no shipments (`delivery_status` `not_shipped`) and carries
`"legacy_id"` (other orders: `null`). Importing a `legacy_id` that was already imported returns
the same `order_id` and changes nothing. Every field shown is required: `legacy_id` a non-empty string of at
most 100 characters, `created_at` in the time format above, customer as in checkout, a
non-empty list of items with a non-empty `name`, `unit_price` an integer ≥ 0 and `quantity` an
integer ≥ 1. Any invalid record → `422 invalid_request` and nothing is imported. Imported orders appear in lists, the report (on their `created_at`
date) and `/track/{id}`.
