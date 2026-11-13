# Request — Kuwaiti dinar

We also need the attached three-decimal currency. Keep old orders, exports, and waiting shipments working.

## What I need

**The attached currency (public data pack).**

| code | minor unit digits | shown as |
| --- | --- | --- |
| `KWD` | 3 | `KWD 12.500` |

- Shops can choose `KWD` with `PUT /api/shop` like the other three currencies. Amounts in the
  API stay integers in the minor unit (fils: 12500 means 12.500 dinars).
- Shown amounts (pages, emails, the customer page) are `KWD`, a space, then the amount with
  exactly three decimals: 5 → `KWD 0.005`, 1234567 → `KWD 1234.567`.
- CSV values have three decimals without the code (`12.500`); KWD rows sort with the other
  currencies by code.
- Nothing about GBP, EUR and JPY changes. Orders, returns, reports and queued emails of orders
  placed before the shop switched keep their own currency.
