# Request 4 — Customer updates

Email customers when their order is accepted and when it ships. Use MailPost. If sending fails, try again later without holding up shipping, and please do not send duplicate emails.

## What I need

### MailPost test service (attached instructions)

Test key: `mp-test-key`. The shop reads its key from the environment variable
`DISPATCHLEDGER_MAILPOST_KEY` (our tooling sets it for the web app and the worker).

`POST {EXTERNAL}/mailpost/messages` with header `X-MailPost-Key: <key>` and
`{"to": "ada@example.test", "subject": "...", "body": "...", "dedup_key": "<string up to 100 characters>"}`

- `201 {"message_id": "mp_..."}` — accepted; the message will be delivered.
- `200 {"message_id": "<original>"}` — that `dedup_key` was accepted before; it is **not**
  delivered again.
- `401 {"error": "unauthorized"}`, `422 {"error": "invalid_request"}`, and
  `503 {"error": "unavailable"}` (not accepted; nothing will be delivered).
- The connection can drop after a message was accepted. Look it up with
  `GET {EXTERNAL}/mailpost/messages?dedup_key=<key>` (same header) →
  `200 {"messages": [{"message_id", "to", "subject", "body", "dedup_key"}]}` (empty list when
  nothing was accepted with that key), or send it again with the same `dedup_key`.

### The emails

- **accepted**: queued when an order is placed. Subject `Order <order id> accepted`. The body
  has one line per item `<quantity> x <product name> <line total>`, e.g. `2 x Breakfast Tea £9.00`,
  a line `Total: <order total>`, and the order's tracking link `<DISPATCHLEDGER_PUBLIC_URL>/track/<order id>`.
- **shipped**: queued when a shipment's label is done. Subject `Order <order id> has shipped`.
  The body names the carrier (`ParcelFox`), the tracking code, one line per item of the
  shipment `<quantity> x <product name>`, and the tracking link.
- Amounts are formatted as on the pages (`£9.00`). Emails go to the order's customer email.
- Emails are sent by the worker, never while answering a web request, and with the same
  retry rules as labels: a transient failure (no answer, 5xx, 429) is retried at most three
  times after 1, 2 and 4 seconds (clock); a fourth failure → `needs_attention`. Other 4xx →
  `needs_attention` at once.
- Email and label work are independent: a MailPost outage must not delay or stop labels, and
  emails do not wait for label work.
- Never send one email twice: every attempt for the same email uses the same `dedup_key`.

**Visible and retryable.** Orders now include `"emails"`, in the order they were queued:
`[{"id": "<generated>", "kind": "accepted" | "shipped", "shipment_id": null | "<shipment id>", "status": "waiting" | "working" | "sent" | "needs_attention", "attempts": 0, "next_attempt_at": null, "last_error": null}]`.
`POST /api/emails/{id}/retry` queues a `needs_attention` email again (`202` with the email,
status `waiting`, attempts back to 0); for a `sent` email → `409 conflict`; `waiting` or
`working` → `200` unchanged; unknown → `404 not_found`. The order page shows email states.

**Customer page.** `GET /track/{order id}` is a page for the customer showing the order's items,
total and each shipment's status and tracking code; unknown order → `404`.
