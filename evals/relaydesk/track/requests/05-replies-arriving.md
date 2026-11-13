# Request 5 — Show replies arriving

Pollen can now show the reply as it arrives. Please do that so people aren't staring at a blank box. If I pick Comet, just show a working message until its reply is ready. Don't lose my original draft if something fails.

## What I need

### Pollen streaming (attached)

`POST {EXTERNAL}/pollen/draft/stream` takes the same headers and body as `/draft`. It answers
`200` with `Content-Type: text/event-stream` (server-sent events, each event is `event:` and
`data:` lines followed by a blank line):

```text
event: delta
data: {"text": "Hi Ola, "}

event: delta
data: {"text": "thanks for writing."}

event: done
data: {"request_id": "pol-9"}
```

- One or more `delta` events, then exactly one `done` event, which is always last. The reply is
  the concatenation of the `delta` texts in order.
- A stream that ends without `done` was cut off: the reply is incomplete and must not be used.
- `400`, `401` and trouble statuses come back as ordinary JSON responses, before any event.

Comet has no streaming; only `POST /compose` exists.

### RelayDesk

- Pollen suggestions now use `/draft/stream` instead of `/draft`.
- `POST /api/tickets/{id}/suggestions` answers right away without waiting for the reply:
  `202` with the suggestion in `"status": "running"` (`201` is also fine when it has already
  finished). Errors that need no outside call (`422`, `404`, `409 not_configured`) still answer
  at once and record nothing.
- While a suggestion is `running`, `GET /api/suggestions/{id}` shows its progress: for Pollen
  `text` is everything received so far; for Comet `text` stays `""` until the reply is there.
  Then the suggestion becomes `completed` with the whole text (each piece exactly once), or
  `failed`.
- A Pollen stream that is cut off → `failed` with code `stream_interrupted`. A suggestion that is
  not `completed` can never be accepted, and the draft is never changed by a failure.
- Each entry of `GET /api/providers` gains `"streaming": true | false` (Pollen `true`,
  Comet `false`). Comet is never sent a streaming request.
- The ticket page shows the text as it arrives for Pollen and a working message while waiting
  for Comet.
