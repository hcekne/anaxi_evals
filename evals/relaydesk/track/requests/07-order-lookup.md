# Request 7 — Look up an order

Most messages are about orders. Let the person enter an order number, fetch its status and total from this service, and choose to include that in the reply request. Show the total in dollars. Never fetch an order unless they ask.

## What I need

### Order service (attached)

- Address: `{EXTERNAL}/orders`. Credential: a bearer token per team; a token only sees its own
  team's orders. Test tokens: north `orders-north-token`, south `orders-south-token`.
- `GET /orders/{id}` with `Authorization: Bearer <token>` →
  `200 {"id": "A-1001", "status": "shipped", "total_cents": 4599}`. All orders are in US
  dollars; `total_cents` is the total in cents.
- `404` unknown order (or another team's), `401` bad token.

Test orders for north include `A-1001`, `A-1002` and `A-1003`; south has `B-2001`.

```sh
curl "$RELAYDESK_EXTERNAL_URL/orders/orders/A-1001" -H "Authorization: Bearer orders-north-token"
```

### RelayDesk

- `PUT /api/connections/orders` with `{"token": "..."}`.
- `POST /api/tickets/{id}/orders` with `{"order_id": "<non-empty string>"}` fetches the order
  now and saves it on the ticket → `201 {"order_id": "A-1001", "status": "shipped", "total_cents": 4599, "total": "$45.99"}`.
  - `total` is dollars: `$`, the whole dollars with commas between thousands, `.` and two-digit
    cents, for example `$1,200.00` and `$0.05`.
  - Unknown order → `404 order_not_found` (nothing saved); not connected →
    `409 not_configured`; any other failure of the service → `502 upstream_error`.
  - Looking the same order up again on that ticket fetches it again and replaces the saved
    entry in place.
- `GET /api/tickets/{id}` gains `"orders": [...]`: the orders looked up on that ticket, in the
  order first looked up, same shape as above.
- `POST /api/tickets/{id}/suggestions` accepts `"order_ids": ["A-1001", ...]` (optional,
  distinct strings, default none). Each must already be looked up on this ticket, otherwise
  `422 unknown_order` and nothing is recorded or sent. For each chosen order the order id, status
  and formatted total (`$45.99`) appear verbatim in what is sent to the provider. Orders not
  chosen are not sent.
- The order service is called only when someone looks an order up — never when asking for a
  suggestion or opening a page.
- The ticket page has an order-number box and shows the looked-up orders with their totals and a
  way to choose them for the suggestion.
