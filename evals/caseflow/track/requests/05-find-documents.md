# Request 5 — Find documents

Add search inside a case. Search titles and document text, ignoring capitals, and show a short matching snippet. I should be able to click a result and open the right document.

## What I need

`GET /api/cases/{case_id}/search?q=<text>` →

```json
{"query": "lease",
 "results": [{"document_id": "...", "title": "Lease agreement",
              "snippet": "...the lease ends in May...", "url": "/documents/..."}]}
```

- `q` is required; surrounding whitespace is ignored; empty after that → `422 invalid_request`.
  Unknown case → `404 not_found`.
- A document matches when the query is contained in its title or its text, **ignoring
  capitals** the way Python's `str.casefold()` does (so `STRASSE` finds `Straße` and `ÉCOLE` finds
  `école`). Plain substring matching: no stemming, no splitting into words.
- Only documents of that case. Results are ordered oldest document first.
- `snippet` is a continuous piece of the document's text, at most 120 characters, copied exactly
  from the text. If the text matches, the snippet contains the first match in the text; if only
  the title matches, the snippet is the start of the text (up to 120 characters).
- `url` is the path of the document page (`/documents/{document_id}`); opening it shows that
  document. Searching never changes any document.
- The case page has a search box; `GET /cases/{case_id}/search?q=<text>` shows the results as
  links to their documents.

Sample examples (title — text):

| Document | Query | Matches |
| --- | --- | --- |
| `Lease` — `The LEASE ends in May.` | `lease` | yes (title and text) |
| `Straßenplan` — `Map of Oslo` | `STRASSE` | yes (title only) |
| `Note` — `Die Straße ist gesperrt.` | `strasse` | yes |
| `Brev` — `Møte på ÉCOLE i Tromsø` | `école` | yes |
| `Brev` — `Møte på ÉCOLE i Tromsø` | `TROMSØ` | yes |
| `Brev` — `Møte på ÉCOLE i Tromsø` | `tromso` | no |
