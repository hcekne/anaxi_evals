# Request 8 — Handle outages

Sometimes these AI services are busy. Please retry temporary failures twice, respect their ‘try again in this many seconds’ message, and tell me clearly when it still hasn't worked. A bad connection key shouldn't keep retrying. Stick with the service I chose and keep my work safe.

## What I need

### What Pollen and Comet send when they have trouble (attached)

- `429` with a `Retry-After` header holding a whole number of seconds: busy, try again after
  that many seconds.
- `503`: temporarily unavailable. It may carry `Retry-After` too.
- `401`: bad credential. Trying again will not help.

### Retry rules

These apply to every request that asks a reply service for a reply (for Pollen's stream, to
the status of the stream request):

- At most **three attempts**: the first plus two retries.
- Only `429` and `503` are retried. Before a retry wait `Retry-After` seconds when the response
  has that header, otherwise 1 second.
- `401` is never retried → `failed` with `provider_auth_failed`. Any other unexpected status is
  not retried → `failed` with `provider_error`. A Pollen stream that was cut off after it started
  is not retried (`stream_interrupted`).
- When the third attempt also gets `429` or `503` → `failed` with code `provider_unavailable`
  and a message saying the service is still busy after 3 attempts.
- The suggestion stays `running` while waiting. Never switch to another service; drafts and
  earlier suggestions are never touched.

### Clock

`RELAYDESK_TIME_SCALE` (a positive number, default `1`) is how many real seconds one second of
waiting lasts. Every wait a request describes in seconds lasts that many seconds times the scale.
Our tests run with `RELAYDESK_TIME_SCALE=0.05` and check that the waits happen.
