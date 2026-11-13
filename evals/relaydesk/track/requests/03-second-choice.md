# Request 3 — A second choice

Add Comet as another option, using these instructions. Let me choose either one when asking for a suggestion, and remember my usual choice. Everything else should work the same.

## What I need

### Comet instructions (attached)

- Address: `{EXTERNAL}/comet`. Credential: an API key. Test key: `comet-demo-key`.
- `POST /compose` with headers `X-Api-Key: <key>` and `Content-Type: application/json`, body
  `{"conversation": [{"speaker": "customer" | "agent" | "system", "text": "<text>"}, ...]}`
  (at least one entry).
  - `200 {"completion": {"body": "<suggested reply>"}, "id": "cmt-4"}`
  - `400` malformed body, `401` bad key; other statuses happen when Comet has trouble.
- Comet has no other endpoints.

```sh
curl -X POST "$RELAYDESK_EXTERNAL_URL/comet/compose" -H "X-Api-Key: comet-demo-key" \
  -H "Content-Type: application/json" \
  -d '{"conversation": [{"speaker": "customer", "text": "Where is my order?"}]}'
```

### RelayDesk

- `PUT /api/connections/comet` with `{"token": "<the API key>"}`, same rules as Pollen.
- `GET /api/providers` → `{"providers": [{"id": "comet", "name": "Comet"}, {"id": "pollen", "name": "Pollen"}]}`:
  the services available for new suggestions, sorted by `id`.
- `POST /api/tickets/{id}/suggestions` accepts `"provider": "comet"` as well. `provider` is now
  optional: when it is left out, the saved usual choice is used.
- The usual choice: `GET /api/preferences` → `{"provider": "pollen"}` (Pollen until someone
  changes it); `PUT /api/preferences` with `{"provider": "comet"}` → `200` with the same shape.
  An unknown provider → `422 invalid_request`. Naming a provider when asking for a suggestion does
  not change the saved choice. The choice is kept like everything else.
- The Comet request has at least one entry with `"speaker": "customer"` whose text contains the
  ticket's subject and body verbatim. The suggestion's `text` is `completion.body`.
- Errors map exactly as for Pollen (`401` → `provider_auth_failed`, any other failure →
  `provider_error`), and everything else about suggestions, drafts and accepting works the same
  for either service.
- The ticket page lets the person pick the service when asking and shows which service made each
  suggestion.
