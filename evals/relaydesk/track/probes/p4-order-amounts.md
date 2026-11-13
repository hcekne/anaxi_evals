# Request — Order amounts, version 3

The order service now returns currency amounts this way; keep existing drafts and queued work usable.

## What I need

### Order service, version 3 (attached)

- `GET {EXTERNAL}/orders/v3/orders/{id}` with the same bearer tokens →
  `200 {"id": "E-3001", "status": "shipped", "total": {"amount": "12.34", "currency": "EUR"}}`.
- `amount` is a decimal string with exactly the currency's number of decimals: two for `USD`,
  `EUR` and the newly supported `GBP` (British pounds), none for `JPY` (for example `"1500"`).
- `404` unknown order (or another team's), `401` bad token.
- Version 2 (`/orders/v2/orders/{id}`) is retired and now answers `410`.

Test orders for north include `A-1001` (USD), `E-3001` (EUR), `J-4001` (JPY) and `G-6001`
(GBP).

### RelayDesk

- Orders keep the shape RelayDesk already returns:
  `{"order_id", "status", "money": {"minor_units", "currency"}, "total"}`, with `minor_units`
  in the currency's smallest unit (pence for GBP). GBP totals are written like dollars and
  euros with the symbol `£`, for example `£5.00`.
- Orders saved before this change — including the oldest dollar-only ones — still appear
  exactly as before, in the API, on pages and in what is sent to reply services.
- Drafts stay as they are, and suggestions that are queued or running when this version
  replaces the old one carry on and send the chosen orders' information correctly.
