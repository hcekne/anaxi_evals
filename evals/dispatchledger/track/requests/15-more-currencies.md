# Request 15 — More currencies

Let each shop sell in pounds, euros, or yen. Orders must remember their currency, and reports must keep currencies separate. No conversions. Yen has no pennies. Existing orders must still look right, including old links customers have.

## What I need

**Currencies (public data pack).**

| code | minor unit digits | shown as |
| --- | --- | --- |
| `GBP` | 2 | `£12.50` |
| `EUR` | 2 | `€12.50` |
| `JPY` | 0 | `¥1250` |

All amounts in the API stay integers in the **minor unit of their currency** (pence, cents,
yen). Shown amounts are the symbol, then the amount with exactly the currency's minor digits,
no thousands separator.

- Each shop has a currency: `GET /api/shop` → `{"id", "name", "currency": "GBP"}` (default
  `GBP`). Staff change it with `PUT /api/shop` and `{"currency": "JPY"}` → `200` the same shape;
  anything other than the three codes → `422 unsupported_currency`. Nothing is converted:
  product prices keep their numbers and are read in the shop's current currency.
- Products, quotes, orders and returns carry `"currency"`. A checkout takes the shop's currency
  at that moment and the order keeps it for ever, whatever the shop changes to later.
- **Data pack rule:** orders that existed before currencies (and every imported historical
  record) are `GBP`.
- Pages, emails (including ones still queued, or sent long after) and the customer page
  `/track/{id}` — including links customers already have — show each order's amounts in that
  order's currency.
- **Reports keep currencies apart.** Day entries become one per date **and currency** with at
  least one accepted order, sorted by date then currency code, each with `"currency"`; no
  amounts are ever added across currencies. The CSV header becomes
  `date,currency,orders,items,original_value,returned_value,remaining_value`; values are
  written with the currency's minor digits and no symbol (`12.50`, `1250`).
