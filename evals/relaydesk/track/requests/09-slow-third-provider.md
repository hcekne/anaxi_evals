# Request 9 — A slow third provider

We want Harbor too. It gives you a job number and you have to come back for the answer; their notes are attached. Show that it's working while we wait. It doesn't do the word-by-word display, and that's fine.

## What I need

### Harbor notes (attached)

- Address: `{EXTERNAL}/harbor`. Credential: bearer token per team. Test tokens: north
  `harbor-north-token`, south `harbor-south-token`.
- `POST /jobs` with `Authorization: Bearer <token>` and JSON body `{"prompt": "<text>"}` →
  `202 {"job_id": "hj-12"}`.
- `GET /jobs/{job_id}` → `200 {"state": "pending"}`, `200 {"state": "complete", "answer": "<reply>"}`
  or `200 {"state": "cancelled"}`.
- `DELETE /jobs/{job_id}` → `200 {"state": "cancelled"}`: cancels a pending job.
- `404` unknown job, `401` bad token, `429`/`503` when busy (as Pollen and Comet).
- Poll a job **at most once per second**, the first time no earlier than one second after
  submitting it. A job id stands for one submission: submit once, then keep polling that id.
- No streaming.

```sh
curl -X POST "$RELAYDESK_EXTERNAL_URL/harbor/jobs" -H "Authorization: Bearer harbor-north-token" \
  -H "Content-Type: application/json" -d '{"prompt": "Customer asks: where is my order?"}'
```

### RelayDesk

- Provider id `harbor`, name `Harbor`, `"streaming": false` in `GET /api/providers`; it can be
  the saved choice. `PUT /api/connections/harbor` with `{"token": "..."}`.
- The `prompt` contains everything a reply request includes for the other services: the
  ticket's subject and body, selected articles' title and text, chosen orders' id, status and
  total — and nothing that was not selected.
- The suggestion is `running` with `text` `""` while Harbor works, then `completed` with
  `text` = `answer`. A job Harbor reports as `cancelled` without RelayDesk asking → `failed`
  with `provider_error`.
- Submitting follows the retry rules of request 8. Seconds here follow `RELAYDESK_TIME_SCALE`.
- The ticket page shows a working message while Harbor works.
