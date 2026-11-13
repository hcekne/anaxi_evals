# Request 9 — Returns

Let me record that someone returned some items, put the accepted returns back in stock, and show the remaining order value in the report. It is just a record for now, no bank connection. Clicking twice must not record two returns.

## What I need

- `POST /api/orders/{id}/returns` with
  `{"reference": "RET-1042", "items": [{"product_id": "tea", "quantity": 1}]}` records an
  accepted return → `201`:
  `{"reference": "RET-1042", "order_id": "...", "created_at": "...", "items": [{"product_id": "tea", "name": "Breakfast Tea", "quantity": 1, "unit_price": 450, "value": 450}], "value": 450}`.
  - `reference` matches `[A-Za-z0-9-]{1,40}` (else `422 invalid_request`) and is **unique**:
    sending the same reference again for the same order and the same items → `200` with the
    original return and nothing else happens (also when both arrive at the same moment); the
    same reference with a different order or items → `409 duplicate_reference`.
  - `items` as in checkout (`422 invalid_quantity`, `422 invalid_request` for an empty list or a
    product twice).
  - **Data pack rule:** a line cannot exceed the delivered quantity minus earlier returns of that
    product on that order → `422 return_exceeds_delivered` (nothing recorded). Delivered means
    in a shipment whose status is `done`; a product not delivered at all has 0.
  - Values use the order's own unit prices.
- Returned units go back on the shelf of the warehouse that shipped them (when one product was
  shipped from several shipments, fill the earliest shipment first): they are added to that
  warehouse's snapshot figure, so they are available to sell again.
- Orders gain `"returns"` (oldest first), `"returned_value"` and `"remaining_value"`
  (= `total` − `returned_value`).
- **Report.** Each day entry gains `"original_value"` (= `value`), `"returned_value"` and
  `"remaining_value"`. Returns count on the day the **order** was accepted. The CSV header
  becomes `date,orders,items,original_value,returned_value,remaining_value` (values in pounds
  with two decimals).
- Order pages show returns and the remaining value. It is only a record: nothing is refunded.
