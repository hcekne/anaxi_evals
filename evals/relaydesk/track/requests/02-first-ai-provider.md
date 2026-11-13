# Request 2 — First AI provider

Can it suggest a reply using Pollen? I've attached their connection details. Put a button next to the draft. I want to review the suggestion before using it, and keep anything I already typed unless I choose to replace it.

## What I need

### Pollen connection details (attached)

- Address: `{EXTERNAL}/pollen`, where `{EXTERNAL}` is `RELAYDESK_EXTERNAL_URL`.
- Credential: a bearer token. Test token: `pollen-demo-token`.
- `POST /draft` with headers `Authorization: Bearer <token>` and
  `Content-Type: application/json`, body
  `{"messages": [{"role": "system" | "user" | "assistant", "content": "<text>"}, ...]}`
  (at least one message).
  - `200 {"text": "<suggested reply>", "request_id": "pol-17"}`
  - `400` malformed body, `401 {"error": "invalid_token"}` bad token. Other statuses (for
    example `500`) happen when Pollen has trouble.

```sh
curl -X POST "$RELAYDESK_EXTERNAL_URL/pollen/draft" -H "Authorization: Bearer pollen-demo-token" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Customer asks: where is my order?"}]}'
```

### Connections

- `PUT /api/connections/pollen` with `{"token": "<non-empty string>"}` →
  `200 {"service": "pollen", "configured": true}`. Empty or missing token →
  `422 invalid_request`; an unknown service name → `404 not_found`.
- `GET /api/connections` → `{"connections": [{"service": "pollen", "configured": true|false}, ...]}`
  with one entry per service RelayDesk can connect to, sorted by `service`.
- The token is never returned by any endpoint or page.

### Suggestions

`POST /api/tickets/{id}/suggestions` with `{"provider": "pollen"}` asks Pollen for a reply and
answers `201` with the suggestion:

```json
{"id": "<suggestion id>", "ticket_id": "T-1001", "provider": "pollen",
 "status": "completed", "text": "<Pollen's text>", "error": null, "accepted": false}
```

- The Pollen request has at least one `user` message, and the ticket's subject and body appear
  verbatim in the content of its `user` message(s). Nothing from other tickets is sent.
- Pollen answers `401` → the suggestion is `"status": "failed"`, `"text": ""` and
  `"error": {"code": "provider_auth_failed", "message": "..."}`. Any other failure (another
  status, an unusable body, no connection) → `failed` with code `provider_error`. A failed
  suggestion is still recorded and returned with `201`.
- Missing or unknown `provider` → `422 invalid_request`; Pollen not connected →
  `409 not_configured` (nothing is recorded); unknown ticket → `404 not_found`.
- Asking never changes the draft.
- `GET /api/suggestions/{id}` → the suggestion (`404 not_found` if unknown).
  `GET /api/tickets/{id}/suggestions` → `{"suggestions": [...]}`, oldest first.
- `POST /api/suggestions/{id}/accept` → replaces the ticket's draft text with the suggestion's
  text, marks the suggestion `"accepted": true` and answers `200` with the ticket as
  `GET /api/tickets/{id}` returns it. Only a `completed` suggestion can be accepted, otherwise
  `409 conflict` (nothing changes). Accepting the same suggestion again changes nothing and
  answers `200`.
- Suggestions are kept like everything else.

### Pages

The ticket page has a "Suggest a reply" button next to the draft and shows the ticket's
suggestions (their text) with a way to accept each one.
