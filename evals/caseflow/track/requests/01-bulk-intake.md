# Request 1 — Bulk intake

Pasting these one by one is slow. Let me upload a CSV of documents using the sample file. If a few rows are wrong, tell me which ones and still keep the good ones. Uploading the same thing twice shouldn't give me duplicates.

## What I need

### The sample file

```csv
external_id,title,text
INV-001,Invoice 1,"Payment of 1,200 EUR received"
INV-002,Brief,"Line one
Line two"
INV-003,Fødselsattest,Født i Tromsø
```

The format: UTF-8 text (a leading byte-order mark is ignored), standard CSV quoting (fields may
be wrapped in double quotes; inside quotes, commas and line breaks are part of the value and `""`
is a literal quote). The first row is exactly `external_id,title,text`. Values are used exactly
as given (no trimming).

### Upload

`POST /api/cases/{case_id}/csv` with the file's bytes as the raw request body (any content type).

- A body that is not UTF-8, or whose header row is not exactly `external_id,title,text` →
  `422 invalid_csv` and nothing is imported. Unknown case → `404 not_found`.
- Otherwise `200`:

```json
{"created":   [{"row": 1, "external_id": "INV-001", "document_id": "..."}],
 "unchanged": [{"row": 3, "external_id": "INV-003", "document_id": "..."}],
 "errors":    [{"row": 2, "external_id": "INV-002", "code": "title_required", "message": "..."}]}
```

  Row 1 is the first record after the header (a quoted value spanning several lines is still one
  row). Each list is in row order. Every row lands in exactly one list.
- Each row is checked on its own; the good rows are saved even when other rows fail. The first
  rule that applies decides a row's outcome:
  1. not exactly three fields → `wrong_field_count` (`external_id` is the first field, or `null`
     if the row is empty);
  2. empty or whitespace-only `external_id` → `external_id_required` (`external_id`: the value given);
  3. empty or whitespace-only `title` → `title_required`;
  4. a document with that `external_id` already exists in this case (from an earlier upload or an
     earlier row of this file): identical title and text → `unchanged` (nothing is written, the
     existing `document_id` is reported); different title or text → error `conflicting_duplicate`
     and the existing document stays as it was;
  5. otherwise a new document is `created`.
- External ids are unique within one case: the same id in another case is a different document.

### Documents

Every document now also has `source` and `external_id`: uploaded rows are
`"source": "csv", "external_id": "INV-001"`; pasted documents are
`"source": "manual", "external_id": null`. Uploaded documents appear in the case and open like
pasted ones. The case page offers the upload.
