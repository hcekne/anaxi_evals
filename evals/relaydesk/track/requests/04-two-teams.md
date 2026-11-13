# Request 4 — Two separate teams

Two support teams will use this. Give each team its own tickets, drafts, saved provider choice and connection details. A person from one team mustn't be able to see the other team's stuff, even by copying a ticket link.

## What I need

### Teams and sign-in

The teams come from a JSON file whose path is in the environment variable
`RELAYDESK_TEAMS_FILE`, read when the app starts. Attached test file:

```json
{"teams": [
  {"id": "north", "name": "North Desk", "users": [
    {"username": "nora", "password": "north-pass-1"},
    {"username": "nils", "password": "north-pass-2"}]},
  {"id": "south", "name": "South Desk", "users": [
    {"username": "sara", "password": "south-pass-1"}]}
]}
```

- `POST /api/login` with `{"username", "password"}` → `200 {"username": "nora", "team": "north"}`
  and a session cookie the browser sends back from then on. Wrong username or password →
  `401 invalid_credentials`.
- `GET /api/me` → `{"username", "team"}`. `POST /api/logout` → `200` and the session no longer
  works.
- Every `/api/` endpoint except `/api/health` and `/api/login` now needs a signed-in session;
  without one → `401 unauthenticated`. Pages without a session send the person to a sign-in page
  at `/login` instead of showing any data. A sign-in may end when the app restarts.

### Separation

- Each team has its own tickets, drafts, statuses, suggestions, saved provider choice and
  connections. People in the same team share them.
- Ticket ids are unique within a team only: both teams may import a ticket with the same id,
  and each team sees only its own.
- Anything belonging to another team answers exactly as if it did not exist (`404 not_found`),
  through the API and through pages such as `/tickets/{id}`.
- Calls to Pollen and Comet use the connection details of the signed-in person's team.
- Tickets that existed before this change belong to the first team in the file.

### Test credentials for the two teams (attached)

| Service | north | south |
| --- | --- | --- |
| Pollen token | `pollen-north-token` | `pollen-south-token` |
| Comet key | `comet-north-key` | `comet-south-key` |

The demo credentials from earlier requests keep working too.
