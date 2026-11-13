# Request 15 — A genuinely shared change

Some editors should only see documents they are responsible for. Add a restricted-editor option, using the responsibility we already assign. For those editors, hide everything else everywhere: lists, search, copied links, history, totals, downloads, and messages. If someone loses access, don't send a message that's still waiting.

## What I need

- A new workspace role, `restricted_editor`, set like any other role
  (`PUT /api/workspaces/{workspace_id}/members/{user}` with `{"role": "restricted_editor"}`).
- A restricted editor can do what an editor can (create cases, add and edit documents, decide
  reviews, start imports, cancel jobs), **but only sees documents whose `responsible` is
  them**, as it is right now. Documents they add themselves, or that an import they started
  first brought in, start out as theirs, so they see those.
- Every other document is invisible to them everywhere, exactly as if it did not exist:
  - the documents list of `GET /api/cases/{case_id}` and the case page;
  - search results;
  - `GET`/`PATCH` of the document, its versions, its reviews (reading or deciding), its notices,
    its responsible person, and its pages — all `404 not_found`;
  - report totals: they only count approval decisions on documents the restricted editor can
    see right now;
  - the JSON download: only the documents they can see;
  - approval messages: they are only ever sent a message for a document they can see (below).
- Cases, connections, jobs, members and the workspace itself stay visible to them.
- When an owner reassigns a document, it disappears from the previous restricted editor's view
  and appears in the new one's, immediately and everywhere.
- **Pending messages.** Right before every attempt to send an approval message, check that the
  recipient can still see the document (still a member of the workspace and, if a restricted
  editor, still the document's responsible person). If not, the message is never sent: its
  notice becomes `"status": "cancelled"`. This also applies to messages that were waiting when
  the app restarted.
- Owners, editors and viewers see what they saw before.
