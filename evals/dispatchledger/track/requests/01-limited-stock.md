# Request 1 — Limited stock

We only have a few of each item. Show what is left and stop people buying more than we have, even if two people order the last item at almost the same time.

## What I need

- Every product has `stock`: the number of units still available to buy. Products in
  `GET /api/products` and `GET /api/products/{id}` include it, and the shop page shows it.
- Sample stock when sample data is loaded: `tea` 10, `mug` 5, `apron` 3.
- `POST /api/products` accepts an optional `stock` (integer ≥ 0, default 0).
- `PUT /api/products/{id}/stock` with `{"stock": 7}` sets the units available → `200` with the
  product (integer ≥ 0, otherwise `422 invalid_request`; unknown product → `404 not_found`).
- Checkout takes the ordered quantities out of stock. If any line asks for more than is
  available → `409 out_of_stock`, and nothing changes: no order, no stock taken for any line.
  This must hold when many checkouts arrive at the same moment: never sell more units than
  there were, and every successful checkout gets its units.
- Quotes neither check nor take stock.

**Checkout submission key** (public data pack): checkout accepts an optional
`"submission_key"` (a non-empty string of at most 100 characters). The browser sends one per
press of the order button, so a repeated submission identifies the **same** order:

- The first successful checkout with a key → `201` with the new order.
- Any later checkout with the same key → `200` with that original order (even if the repeated
  body differs); no new order and no further stock is taken. This also holds when the repeats
  arrive at the same moment as the first.
- A checkout that failed (for example `409 out_of_stock`) does not use up its key.
