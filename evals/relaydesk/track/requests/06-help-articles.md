# Request 6 — Answers from our help articles

Let people search our help articles and include the ones they select when asking for a reply. Show links to those articles beside the suggestion so the person can check them, and keep the links when they accept it. Use this article service.

## What I need

### Article service (attached)

- Address: `{EXTERNAL}/knowledge`. Credential: a bearer token per team; a token can only read
  its own team's articles. Test tokens: north `kb-north-token`, south `kb-south-token`.
- `GET /articles?q=<text>&team=<team id>` with `Authorization: Bearer <token>` →
  `200 {"articles": [{"id": "KB-100", "title": "...", "text": "...", "url": "https://..."}, ...]}`.
  Matches `q` in the title or text, ignoring case; an empty `q` returns all of the team's
  articles. `url` is optional and missing for some articles.
- `GET /articles/{id}?team=<team id>` → `200` with one article; `404` unknown article (or
  another team's).
- `401` bad token; `403` when `team` is not the token's team.

```sh
curl "$RELAYDESK_EXTERNAL_URL/knowledge/articles?q=refund&team=north" \
  -H "Authorization: Bearer kb-north-token"
```

### RelayDesk

- `PUT /api/connections/knowledge` with `{"token": "..."}` (per team, like the others).
- `GET /api/articles?q=<text>` → `{"articles": [{"id", "title", "text", "url"}, ...]}` from the
  service for the signed-in person's team, in the service's order, `url` `null` when missing.
  `GET /api/articles/{id}` → one article, `404 not_found` when the service does not know it.
  Not connected → `409 not_configured`.
- `POST /api/tickets/{id}/suggestions` accepts `"article_ids": ["KB-100", ...]` (optional,
  distinct strings, default none). RelayDesk reads each selected article from the service and
  includes its title and text verbatim in what it sends to the provider (Pollen: in a message's
  content; Comet: in a conversation entry's text). Articles that were not selected are not sent.
  An id the service does not know for this team → `422 unknown_article` and nothing is recorded
  or sent to the provider. Articles selected but the article service not connected →
  `409 not_configured`.
- Every suggestion gains `"sources": [{"id", "title", "url"}, ...]`: the selected articles in
  the order given (`url` `null` when missing), `[]` when none were selected.
- The ticket's draft gains `sources` too: `"draft": {"text": "...", "sources": [...]}`,
  `[]` until a suggestion is accepted. Accepting copies the suggestion's sources into the draft
  along with its text; editing the draft text keeps them. They are kept like everything else.
- The ticket page has an article search with a way to select articles, and shows the source
  links beside each suggestion and beside the draft.
