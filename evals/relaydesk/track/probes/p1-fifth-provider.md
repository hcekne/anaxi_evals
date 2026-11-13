# Request — A fifth reply service

Add this fifth reply service; its instructions are attached.

## What I need

### Nimbus instructions (attached)

- Address: `{EXTERNAL}/nimbus`. Credential: an API key sent as the header `X-Nimbus-Key`.
  Test keys: north `nimbus-north-key`, south `nimbus-south-key`.
- `POST /v1/replies` with JSON `{"instructions": "<text>", "context": ["<text>", ...]}`
  (`context` may be empty) answers `200` with `text/event-stream`:

```text
event: start
data: {"reply_id": "nr-7"}

event: chunk
data: {"delta": "Hi Ola, "}

event: chunk
data: {"delta": "your refund is on its way."}

event: end
data: {"reply_id": "nr-7"}
```

  - Exactly one `start` event first, any number of `chunk` events, exactly one `end` event last.
    The reply is the concatenation of the `delta` texts. A stream without `end` was cut off.
- `POST /v1/replies/{reply_id}/cancel` → `200 {"reply_id": "nr-7", "cancelled": true}`: stops a
  reply that is still being written.
- `401` bad key; `429` (with `Retry-After`) and `503` when busy. These come as JSON before the
  stream.

### RelayDesk

- Provider id `nimbus`, name `Nimbus`, `"streaming": true`, connected with
  `PUT /api/connections/nimbus` and `{"token": "<the API key>"}`. It can be the saved choice and
  be used for batches.
- `context` carries what the other services get: the ticket's subject and body, the selected
  articles' title and text, and the chosen (already looked-up) orders' id, status and total.
  `instructions` is any text you like.
- Like the other streaming services: the text so far is visible while running; cut-off streams
  fail with `stream_interrupted`; the retry rules apply; `citations` is `[]`.
- Stopping a Nimbus suggestion whose stream has started also sends
  `POST {EXTERNAL}/nimbus/v1/replies/{reply_id}/cancel` once, with the reply id from its
  `start` event.
- The ticket page offers Nimbus and names it on its suggestions.
