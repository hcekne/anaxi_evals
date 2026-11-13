# Request 15 — A change that really crosses boundaries

Our shops now sell in dollars, euros and yen. The order service has changed as described here. Show the right currency and amount wherever an order appears, including the information sent for a reply. Old saved orders were all dollars and must still display correctly. Keep jobs already waiting in the queue working during the update.

## What I need

### Order service, version 2 (attached)

- `GET {EXTERNAL}/orders/v2/orders/{id}` with the same bearer tokens →
  `200 {"id": "E-3001", "status": "shipped", "money": {"minor_units": 1234, "currency": "EUR"}}`.
- `currency` is `USD`, `EUR` or `JPY`. USD and EUR have two decimals (`minor_units` are cents);
  JPY has none (`minor_units` are whole yen).
- `404` unknown order (or another team's), `401` bad token.
- The old `GET {EXTERNAL}/orders/orders/{id}` is retired and now answers `410`.

Test orders for north include `A-1001` (USD), `E-3001` and `E-3002` (EUR), `J-4001` and
`J-4002` (JPY); south has `B-2001` (USD) and `E-5001` (EUR).

### RelayDesk

- An order, wherever the API returns it (lookup answer and the ticket's `orders`), is now
  `{"order_id": "E-3001", "status": "shipped", "money": {"minor_units": 1234, "currency": "EUR"}, "total": "€12.34"}`.
  `total_cents` is no longer part of it.
- `total` is the symbol (`$` USD, `€` EUR, `¥` JPY) followed by the amount with commas between
  thousands: two decimals for USD and EUR, none for JPY. Examples: `$1,200.00`, `€2,500.75`,
  `¥1,500`, `¥1,234,567`. Never convert between currencies.
- Wherever an order appears — API, ticket page and what is sent to a reply service — the amount
  and currency agree with this `total`.
- Orders saved before this update have no currency; they are US dollars. They appear exactly
  like new USD orders (`"money": {"minor_units": <their cents>, "currency": "USD"}`, `"$45.99"`)
  everywhere, including in replies still waiting to be sent.
- An order whose currency is not one of the three → `502 upstream_error`.
- Updating means stopping the running version and starting this one on the same data
  directory. Suggestions still queued or running at that moment carry on in the new version and
  send the chosen orders' information in the new form.
