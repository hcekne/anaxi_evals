# Request 13 — Retire Comet

We're dropping Comet. Remove it from new work, but keep old suggestions readable with the name of the service that made them. If someone had Comet selected, ask them to choose another option. Don't silently send their message somewhere else.

## What I need

- Comet disappears from `GET /api/providers`. Asking for a Comet suggestion or a Comet batch,
  or saving Comet as the usual choice → `422 provider_retired`. RelayDesk never sends anything to
  Comet again.
- A team whose saved choice was Comet: `GET /api/preferences` →
  `{"provider": null, "needs_choice": true}`. Asking for a suggestion or batch without naming a
  provider → `409 choose_provider`, and nothing is recorded or sent to any service. Saving a new
  choice ends this. Otherwise `needs_choice` is `false`.
- Suggestions Comet made before stay readable as they were: `GET /api/suggestions/{id}` and the
  ticket's suggestion list still return them with `"provider": "comet"` and their text, and the
  ticket page shows them with the name "Comet". Drafts accepted from them stay as they are.
- The other services work without any Comet connection details.
