# Request 7 — Two warehouses

We now have two warehouses. Use the attached stock feed, and let me choose which warehouse to try first. If it cannot supply an order, use the other one. Old stock messages should not put stock back by mistake.

## What I need

The warehouses are `north` and `south`.

### The stock feed (attached instructions)

The warehouses' stock system delivers snapshot messages to the shop:

`POST /api/warehouse-feed` with
`{"snapshots": [{"warehouse": "north", "sku": "tea", "available": 12, "revision": 41}, ...]}`

- `sku` is the product id; `available` (integer ≥ 0) is the number of units physically on that
  warehouse's shelves; `revision` (integer ≥ 0) grows with every new snapshot of that warehouse
  and SKU.
- Messages can arrive late, twice, or out of order. A snapshot is **applied** only if its
  revision is greater than the last applied revision for that warehouse and SKU; otherwise it
  is **ignored**.
- → `200 {"applied": <count>, "ignored": <count>}`. An unknown warehouse →
  `422 unknown_warehouse`, an unknown SKU → `422 unknown_product`, anything else malformed →
  `422 invalid_request`; a rejected message applies nothing.

**Data pack rule.** Feeds describe physical stock **before** this shop's unfulfilled
reservations: units of orders that have not shipped yet are still on the shelf and still in the
snapshot. So, per warehouse and product:
available to sell = snapshot units − units reserved by orders allocated to that warehouse whose
shipment is not `done` yet (never below 0). A newer snapshot must never erase reservations.
When a shipment becomes `done` its units have left: they are taken off that warehouse's
snapshot figure and the reservation ends (until a newer snapshot replaces the figure).

### The shop

- Stock now comes only from the feed: `PUT /api/products/{id}/stock` and the `stock` field of
  `POST /api/products` are no longer used (a new product has no stock until a snapshot
  arrives). On upgrade and when sample data is first loaded, the stock that existed becomes
  `north`'s snapshot at revision 0.
- Products show `"stock"` (available to sell in both warehouses together) and
  `"warehouses": {"north": 3, "south": 0}` (available per warehouse).
- `GET /api/warehouse-preference` → `{"preferred": "north"}` (the default);
  `PUT /api/warehouse-preference` with `{"preferred": "south"}` → `200` the same shape; unknown
  → `422 unknown_warehouse`.
- **Checkout allocation.** The whole order is taken from the preferred warehouse if it can
  supply every line; otherwise from the other warehouse if it can supply every line; otherwise
  `409 out_of_stock` and nothing is reserved. All the earlier checkout guarantees (no
  overselling under simultaneous checkouts, submission keys) still hold.
- Shipments gain `"warehouse"`: where their items are packed.
