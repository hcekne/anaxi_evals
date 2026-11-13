# Request 8 — Split deliveries

Some orders need items from both warehouses. Allow that now, with a separate label for each parcel. Tell the customer which items are in each delivery. Do not say the whole order has shipped until all its parcels have.

## What I need

- **Allocation.** As before, a single warehouse supplies the whole order when the preferred or
  else the other warehouse can. When neither can alone but both together can, split it: each
  line takes as many units as the preferred warehouse has available, and the rest from the
  other warehouse. Otherwise `409 out_of_stock`, nothing reserved.
- One shipment per warehouse used (preferred warehouse first), each listing only its own
  `items` and `warehouse`. Each shipment gets its own label, carrier, tracking code, retries and
  status exactly like a single shipment, with its own carrier idempotency key.
- `POST /api/orders/{id}/shipments/{shipment_id}/label` — same body, rules and answers as the
  order-level endpoint, for that shipment (unknown shipment → `404 not_found`). The order-level
  `POST /api/orders/{id}/label` keeps working for orders with exactly one shipment; for an order
  with several → `409 multiple_shipments`. Different shipments of one order may use different
  carriers.
- Orders gain `"delivery_status"`: `not_shipped` (no shipment `done`), `partially_shipped`
  (some), `shipped` (all of them). Pages show it.
- **Customer emails.** One shipped email per shipment, sent when that shipment is `done`,
  listing only that shipment's items (`<quantity> x <product name>`), its carrier and tracking
  code. Its subject is `Order <order id> has shipped` only if every shipment of the order was
  `done` when this one completed; otherwise `Part of order <order id> has shipped`, and the body
  must not say the whole order has shipped. The customer page lists every delivery with its
  items, status and tracking code.
- Orders stored before this change (one shipment) still load, ship and report as before.
