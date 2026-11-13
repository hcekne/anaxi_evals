# Request 8 — Notify somebody

Give each document a person responsible: start with whoever added it or set up its import, and let a workspace owner change that. When a document is approved, send that person a message through NoticeSink. It sometimes goes offline, so try again later. Please don't send the same approval message twice, including after a restart. A separate later approval should get its own message.

## What I need

### Responsibility

- Documents gain `"responsible": "<user>"`. It starts as the user who added the document (paste,
  CSV row, PDF upload) or, for a document brought in by an import, the user who started the
  import job that first created it.
- `PUT /api/documents/{document_id}/responsible` with `{"user": "bo"}` → `200` with the document.
  Owners only (others → `403 forbidden`). The user must be a member of the workspace (any role),
  otherwise `422 not_a_member`.

### Approval messages

Every `approved` decision sends one message to the person responsible for the document **at the
moment of the decision**. Changing the responsible person later never changes the recipient of a
message already decided on. `changes_requested` decisions send nothing. Two separate approval
decisions (for example approve, request changes, approve again) are two messages.

- Sending happens in the background: the decision is saved and answered with `201` whether or not
  NoticeSink is reachable.
- The first attempt starts within 2 seconds of the decision. After a failed attempt, the next
  one starts once the CaseFlow clock has reached the failed attempt's time plus 60 seconds
  (within 2 seconds of that). Keep trying until it is accepted. Pending messages survive restarts.
- Every attempt for one decision uses the same `message_id` and the same body. A message is never
  sent again once NoticeSink has accepted it or reported it as a duplicate, restarts included.
- `GET /api/documents/{document_id}/notices` → `{"notices": [...]}` in decision order, readable by
  every member:

```json
{"message_id": "...", "review_id": "...", "recipient": "bo", "revision": 1,
 "status": "pending", "attempts": 2}
```

  `status` is `pending`, `sent` or `failed`; `attempts` counts the requests made so far.

### NoticeSink

`POST {EXTERNAL}/noticesink/messages` with a JSON body:

```json
{"message_id": "...", "workspace_id": "...", "document_id": "...", "revision": 1,
 "recipient": "bo", "text": "\"Lease agreement\" (version 1) was approved by ana."}
```

- `message_id`: chosen by CaseFlow, unique per approval decision, at most 100 characters from
  `[A-Za-z0-9._:-]`. `revision` is the document version that was approved. `recipient` is the
  responsible user. `text` is a short human-readable sentence that includes the document title.
- `202 {"status": "accepted"}`: accepted and delivered.
- `200 {"status": "duplicate"}`: that `message_id` was already accepted; nothing new is delivered.
  Counts as success.
- `503`: temporarily offline, nothing was accepted. Try again later.
- NoticeSink sometimes accepts a message and then loses the response (the connection closes
  without an answer, or the request times out). Treat that as a failed attempt and try again with
  the same `message_id`; NoticeSink's deduplication makes that safe.
- `400`: the body is malformed. Do not retry: the notice becomes `failed`.
- Any other response or connection error is a failed attempt to be retried.
