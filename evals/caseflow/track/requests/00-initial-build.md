# Request 0 — Initial build

Make me a little browser app called CaseFlow for keeping case documents together. I want to create a case, give it a name, paste in some documents, and open them again later. Ask me for a title if I leave it blank. Please keep everything when I close and restart it.

This is the first version; more requests will follow, so build it to last.

## What I need

### Cases

- `POST /api/cases` with `{"name": "Smith v. Jones"}` → `201 {"id": "...", "name": "Smith v. Jones"}`.
  A missing name, or one that is empty or only whitespace → `422 name_required` (a message
  that tells me to give the case a name). A name that is not a string → `422 invalid_request`.
- `GET /api/cases` → `{"cases": [{"id": "...", "name": "..."}, ...]}`, oldest first.
- `GET /api/cases/{case_id}` → `{"id": "...", "name": "...", "documents": [{"id": "...", "title": "..."}, ...]}`
  with the case's documents oldest first. Unknown case → `404 not_found`.

### Documents

- `POST /api/cases/{case_id}/documents` with `{"title": "Witness statement", "text": "..."}` →
  `201` with the document:
  `{"id": "...", "case_id": "...", "title": "Witness statement", "text": "..."}`.
  - A missing title, or one that is empty or only whitespace → `422 title_required` (a message
    asking for a title). Nothing is saved.
  - `text` is required and must be a string; it may be empty. Wrong types → `422 invalid_request`.
  - Unknown case → `404 not_found`.
- `GET /api/documents/{document_id}` → the document. Unknown → `404 not_found`.
- Titles and text are kept exactly as given (any Unicode, line breaks and surrounding spaces
  included).
- A document's id never changes.

### Pages

The browser pages are HTML served by the app:

- `GET /` lists the cases, each linking to its case page, with a form to create a case.
- `GET /cases/{case_id}` shows the case name and its documents' titles, each linking to the
  document page, with a form to paste in a new document.
- `GET /documents/{document_id}` shows the document's title and its full text.

Unknown cases or documents → `404`. Text shown on pages is HTML-escaped. A form submission that
leaves the title blank must show the validation message rather than saving.

### Keeping things

Everything survives a restart of the app: keep it under `CASEFLOW_DATA_DIR` (SQLite is fine).
After a restart the same ids return the same cases and documents.
