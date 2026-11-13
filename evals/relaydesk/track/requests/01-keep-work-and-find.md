# Request 1 — Keep work and find tickets

Please keep the tickets and my drafts when I close and reopen it. Add a search box for the subject or customer's email, and let me mark a ticket closed and show it again later.

## What I need

- Everything RelayDesk holds (tickets, drafts, statuses and everything later requests add)
  survives the app being stopped and started again. Keep it under `RELAYDESK_DATA_DIR`.
- `GET /api/tickets?q=<text>&status=<open|closed|all>`:
  - `q` keeps tickets whose subject or customer email contains the text, ignoring upper/lower
    case. A missing or empty `q` keeps every ticket.
  - `status` defaults to `open`: closed tickets leave the inbox list. `closed` lists only closed
    tickets, `all` lists both. Any other value → `422 invalid_request`.
  - The order stays the import order.
- `POST /api/tickets/{id}/close` → `200` with the ticket (`"status": "closed"`);
  `POST /api/tickets/{id}/reopen` → `200` with the ticket (`"status": "open"`). Both are harmless
  to repeat. Unknown id → `404 not_found`. A closed ticket keeps its draft and can still be opened
  with `GET /api/tickets/{id}` and its page.
- The inbox page has a search box and a way to see closed tickets and reopen them.
