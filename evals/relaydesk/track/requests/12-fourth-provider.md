# Request 12 — Fourth provider with different output

Please add Quartz using the attached notes. It sends the words and article references separately. Show both properly. It can't look up orders itself, so include only the order information the person has already fetched and chosen to use.

## What I need

### Quartz notes (attached)

- Address: `{EXTERNAL}/quartz`. Credential: bearer token per team. Test tokens: north
  `quartz-north-token`, south `quartz-south-token`.
- `POST /responses` with `Authorization: Bearer <token>` and JSON body
  `{"input": [{"type": "text", "text": "<text>"}, ...]}` (one or more items; `type` is always
  `"text"`). It answers `200` with `text/event-stream`:

```text
event: text_delta
data: {"text": "Hi Ola, "}

event: citation
data: {"article_id": "KB-100", "title": "Resetting your password", "url": "https://help.relaydesk.test/north/kb-100"}

event: text_delta
data: {"text": "here is how to reset it."}

event: completed
data: {"response_id": "qz-3"}
```

- Any number of `text_delta` and `citation` events, in any order, then exactly one `completed`
  event, always last. The reply text is the concatenation of the `text_delta` texts only;
  citations are never part of the text. A citation's `url` may be missing. A stream without
  `completed` was cut off.
- `400`, `401`, `429` (with `Retry-After`) and `503` come back as JSON before the stream, as
  for the other services.
- Quartz has no jobs, no polling and no order lookups of its own.

### RelayDesk

- Provider id `quartz`, name `Quartz`, `"streaming": true`; it can be the saved choice.
  `PUT /api/connections/quartz` with `{"token": "..."}`.
- The input items carry what other services get: the ticket's subject and body, selected
  articles' title and text, and the chosen orders that were already looked up (id, status,
  total). Asking Quartz never calls the order service.
- While running, `text` is the text received so far; when complete, `text` is all `text_delta`
  texts joined, with no citation content mixed in.
- Every suggestion gains `"citations": [{"article_id", "title", "url"}, ...]`: Quartz's
  citations in the order received (`url` `null` when missing); `[]` for the other services.
  They are kept with the suggestion.
- Cut-off streams, retries, cancelling and batches work as for the other services.
- The ticket page shows Quartz's citations as links, apart from the text.
