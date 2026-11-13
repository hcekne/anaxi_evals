# Request 4 — A second document format

Can I upload ordinary text PDFs too? Put their text in the same place as pasted documents. If it's a scan you can't read, or a broken file, tell me instead of showing an empty document as if it worked.

## What I need

`POST /api/cases/{case_id}/pdfs` with

```json
{"files": [{"name": "lease.pdf", "content_base64": "JVBERi0xLjQK..."}]}
```

→ `200 {"results": [...]}`, one result per file in the order given:

```json
{"name": "lease.pdf", "status": "imported", "document_id": "...", "message": null}
{"name": "scan.pdf", "status": "unsupported", "document_id": null, "message": "No readable text: this looks like a scanned image."}
{"name": "broken.pdf", "status": "corrupt", "document_id": null, "message": "..."}
```

- `files` must be a non-empty list of at most 20 objects, each with a non-empty string `name` and
  a string `content_base64`; otherwise `422 invalid_request` and nothing is imported. Unknown
  case → `404 not_found`.
- Each file is handled on its own: a bad file never stops the others. `message` is `null` for
  an imported file and a short human-readable explanation otherwise.
- An imported PDF becomes a document in the case like a pasted one: `title` is the file name
  without a trailing `.pdf` (any capitalisation), `text` is the extracted text (below),
  `"source": "pdf"`, `external_id`, `connection_id` and `source_revision` are `null`.
  Uploading a file again creates another document.
- `unsupported`: the file is a well-formed PDF but has no extractable text (for example a scan,
  whose pages only draw images, or text that is empty after normalisation), or it is encrypted
  (its trailer has `/Encrypt`). No document is created.
- `corrupt`: the content is not valid base64, or the file is not a readable PDF by the rules
  below (missing header or `%%EOF`, missing or broken catalog, page tree or content stream,
  undecodable compressed stream). No document is created.
- The case page offers the upload and shows these outcomes.

### Which PDFs and what text

Our PDFs come from one office tool, so you only need this much of the format:

- The file starts with `%PDF-1.` and contains `%%EOF`.
- Objects are written as `<num> <gen> obj ... endobj`; references are `<num> <gen> R`.
  **Do not rely on the cross-reference table**: its offsets are sometimes wrong and it may be
  missing. Find objects by their `obj` headers. Objects can appear in any order in the file.
- The catalog is the object whose dictionary has `/Type /Catalog`; its `/Pages` refers to the
  root of the page tree. A page tree node (`/Type /Pages`) lists its children in `/Kids`; a
  child is either another node or a page (`/Type /Page`). **Page order is the order of
  `/Kids`, depth first**, not the order of objects in the file.
- A page's `/Contents` is a reference to one stream or an array of references (their data is
  concatenated in order). A stream is `<< ... >>` followed by `stream`, a line break (`\n` or
  `\r\n`), `/Length` bytes of data and `endstream`. A content stream has no filter or
  `/Filter /FlateDecode` (zlib); any other filter on a content stream makes the file
  `unsupported`.
- Text appears between `BT` and `ET` through these operators:
  - `(string) Tj` shows a string;
  - `[(str) -250 (ing)] TJ` shows the array's strings joined together (the numbers are spacing:
    ignore them);
  - `(string) '` moves to a new line, then shows the string.
- Strings are literal `( ... )` (escapes `\n \r \t \b \f \( \) \\`, octal `\ddd` with 1 to 3
  digits, a backslash before a line break is a continuation and produces nothing; unescaped
  balanced parentheses are part of the string) or hexadecimal `<48656C6C6F>` (whitespace inside
  is ignored; an odd final digit is followed by an implied `0`). Each byte is one character
  with that code point (Latin-1): `\370` is `ø`.
- Every other operator and operand is ignored, except that `Td`, `TD`, `T*`, `'`, `BT` and the
  start of every page begin a new line.
- **The text** is all lines in order, each stripped of leading and trailing whitespace, empty
  lines dropped, joined with `\n`. Inner whitespace stays as it is.

### Sample pack

`lease.pdf` (two pages, uncompressed) must give exactly:

```text
Lease agreement
Tenant: Ana Lima
Rent: 1 200 EUR (monthly)
Signed in Tromsø, café
```

```text
JVBERi0xLjQKJeLjz9MKMSAwIG9iago8PCAvVHlwZSAvQ2F0YWxvZyAvUGFnZXMgMiAwIFIgPj4KZW5kb2JqCjIgMCBvYmoKPDwg
L1R5cGUgL1BhZ2VzIC9LaWRzIFs0IDAgUiA3IDAgUl0gL0NvdW50IDIgPj4KZW5kb2JqCjMgMCBvYmoKPDwgL1R5cGUgL0ZvbnQg
L1N1YnR5cGUgL1R5cGUxIC9CYXNlRm9udCAvSGVsdmV0aWNhID4+CmVuZG9iago0IDAgb2JqCjw8IC9UeXBlIC9QYWdlIC9QYXJl
bnQgMiAwIFIgL01lZGlhQm94IFswIDAgNjEyIDc5Ml0gL1Jlc291cmNlcyA8PCAvRm9udCA8PCAvRjEgMyAwIFIgPj4gPj4gL0Nv
bnRlbnRzIDUgMCBSID4+CmVuZG9iago1IDAgb2JqCjw8IC9MZW5ndGggMTIwID4+CnN0cmVhbQpCVAovRjEgMTIgVGYKNzIgNzIw
IFRkCihMZWFzZSBhZ3JlZW1lbnQpIFRqCjAgLTE2IFRkCihUZW5hbnQ6IEFuYSBMaW1hKSBUagowIC0xNiBUZAooUmVudDogMSAy
MDAgRVVSIFwobW9udGhseVwpKSBUagpFVAoKZW5kc3RyZWFtCmVuZG9iago3IDAgb2JqCjw8IC9UeXBlIC9QYWdlIC9QYXJlbnQg
MiAwIFIgL01lZGlhQm94IFswIDAgNjEyIDc5Ml0gL1Jlc291cmNlcyA8PCAvRm9udCA8PCAvRjEgMyAwIFIgPj4gPj4gL0NvbnRl
bnRzIDggMCBSID4+CmVuZG9iago4IDAgb2JqCjw8IC9MZW5ndGggNjAgPj4Kc3RyZWFtCkJUCi9GMSAxMiBUZgo3MiA3MjAgVGQK
KFNpZ25lZCBpbiBUcm9tc1wzNzAsIGNhZlwzNTEpIFRqCkVUCgplbmRzdHJlYW0KZW5kb2JqCnhyZWYKMCA5CjAwMDAwMDAwMDAg
NjU1MzUgZiAKMDAwMDAwMDAxNSAwMDAwMCBuIAowMDAwMDAwMDY0IDAwMDAwIG4gCjAwMDAwMDAxMjcgMDAwMDAgbiAKMDAwMDAw
MDE5NyAwMDAwMCBuIAowMDAwMDAwMzIzIDAwMDAwIG4gCjAwMDAwMDAwMDAgMDAwMDAgbiAKMDAwMDAwMDQ5NCAwMDAwMCBuIAow
MDAwMDAwNjIwIDAwMDAwIG4gCnRyYWlsZXIKPDwgL1NpemUgOSAvUm9vdCAxIDAgUiA+PgpzdGFydHhyZWYKNzMwCiUlRU9GCg==
```

`notes.pdf` (compressed, objects in reverse order, `TJ` arrays) must give exactly:

```text
Meeting notes
Budget  approved
Next review: 2026-06-01
```

```text
JVBERi0xLjQKJeLjz9MKOCAwIG9iago8PCAvTGVuZ3RoIDk4IC9GaWx0ZXIgL0ZsYXRlRGVjb2RlID4+CnN0cmVhbQp4nHMK4dJ3
M1QwNFIISeMyN1IwNzJQCEnhitZwKk1JTy1R0FTQNTI1UNCAMxILCoryy1JTNGMVQry4DBR0Dc0gGvxSKxDKi1LLMlPLreB8IwMj
M10DIDKE6HMN4QIA6gEcowplbmRzdHJlYW0KZW5kb2JqCjcgMCBvYmoKPDwgL1R5cGUgL1BhZ2UgL1BhcmVudCAyIDAgUiAvTWVk
aWFCb3ggWzAgMCA2MTIgNzkyXSAvUmVzb3VyY2VzIDw8IC9Gb250IDw8IC9GMSAzIDAgUiA+PiA+PiAvQ29udGVudHMgOCAwIFIg
Pj4KZW5kb2JqCjUgMCBvYmoKPDwgL0xlbmd0aCA2MyAvRmlsdGVyIC9GbGF0ZURlY29kZSA+PgpzdHJlYW0KeJxzCuHSdzNUMDRS
CEnjMjdSMDcyUAhJ4YrW8E1NLcnMS1fQVNA1MjVQ0MjLL0kt1oxVCPHicg3hAgBpmg2NCmVuZHN0cmVhbQplbmRvYmoKNCAwIG9i
ago8PCAvVHlwZSAvUGFnZSAvUGFyZW50IDIgMCBSIC9NZWRpYUJveCBbMCAwIDYxMiA3OTJdIC9SZXNvdXJjZXMgPDwgL0ZvbnQg
PDwgL0YxIDMgMCBSID4+ID4+IC9Db250ZW50cyA1IDAgUiA+PgplbmRvYmoKMyAwIG9iago8PCAvVHlwZSAvRm9udCAvU3VidHlw
ZSAvVHlwZTEgL0Jhc2VGb250IC9IZWx2ZXRpY2EgPj4KZW5kb2JqCjIgMCBvYmoKPDwgL1R5cGUgL1BhZ2VzIC9LaWRzIFs0IDAg
UiA3IDAgUl0gL0NvdW50IDIgPj4KZW5kb2JqCjEgMCBvYmoKPDwgL1R5cGUgL0NhdGFsb2cgL1BhZ2VzIDIgMCBSID4+CmVuZG9i
agp4cmVmCjAgOQowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDA3MDMgMDAwMDAgbiAKMDAwMDAwMDY0MCAwMDAwMCBuIAowMDAw
MDAwNTcwIDAwMDAwIG4gCjAwMDAwMDA0NDQgMDAwMDAgbiAKMDAwMDAwMDMxMCAwMDAwMCBuIAowMDAwMDAwMDAwIDAwMDAwIG4g
CjAwMDAwMDAxODQgMDAwMDAgbiAKMDAwMDAwMDAxNSAwMDAwMCBuIAp0cmFpbGVyCjw8IC9TaXplIDkgL1Jvb3QgMSAwIFIgPj4K
c3RhcnR4cmVmCjc1MgolJUVPRgo=
```

`scan.pdf` is a scanned page (an image, no text) and must be `unsupported`:

```text
JVBERi0xLjQKJeLjz9MKMSAwIG9iago8PCAvVHlwZSAvQ2F0YWxvZyAvUGFnZXMgMiAwIFIgPj4KZW5kb2JqCjIgMCBvYmoKPDwg
L1R5cGUgL1BhZ2VzIC9LaWRzIFs0IDAgUl0gL0NvdW50IDEgPj4KZW5kb2JqCjMgMCBvYmoKPDwgL1R5cGUgL0ZvbnQgL1N1YnR5
cGUgL1R5cGUxIC9CYXNlRm9udCAvSGVsdmV0aWNhID4+CmVuZG9iago0IDAgb2JqCjw8IC9UeXBlIC9QYWdlIC9QYXJlbnQgMiAw
IFIgL01lZGlhQm94IFswIDAgNjEyIDc5Ml0gL1Jlc291cmNlcyA8PCAvWE9iamVjdCA8PCAvSW0xIDcgMCBSID4+ID4+IC9Db250
ZW50cyA1IDAgUiA+PgplbmRvYmoKNSAwIG9iago8PCAvTGVuZ3RoIDMxID4+CnN0cmVhbQpxIDYxMiAwIDAgNzkyIDAgMCBjbSAv
SW0xIERvIFEKCmVuZHN0cmVhbQplbmRvYmoKNyAwIG9iago8PCAvVHlwZSAvWE9iamVjdCAvU3VidHlwZSAvSW1hZ2UgL1dpZHRo
IDggL0hlaWdodCA4IC9Db2xvclNwYWNlIC9EZXZpY2VHcmF5IC9CaXRzUGVyQ29tcG9uZW50IDggL0ZpbHRlciAvQVNDSUlIZXhE
ZWNvZGUgL0xlbmd0aCAxMjkgPj4Kc3RyZWFtCjAwMTAyMDMwNDA1MDYwNzA4MDkwYTBiMGMwZDBlMGYwMDAxMDIwMzA0MDUwNjA3
MDgwOTBhMGIwYzBkMGUwZjAwMDEwMjAzMDQwNTA2MDcwODA5MGEwYjBjMGQwZTBmMDAwMTAyMDMwNDA1MDYwNzA4MDkwYTBiMGMw
ZDBlMGYwPgplbmRzdHJlYW0KZW5kb2JqCnhyZWYKMCA4CjAwMDAwMDAwMDAgNjU1MzUgZiAKMDAwMDAwMDAxNSAwMDAwMCBuIAow
MDAwMDAwMDY0IDAwMDAwIG4gCjAwMDAwMDAxMjEgMDAwMDAgbiAKMDAwMDAwMDE5MSAwMDAwMCBuIAowMDAwMDAwMzIxIDAwMDAw
IG4gCjAwMDAwMDAwMDAgMDAwMDAgbiAKMDAwMDAwMDQwMiAwMDAwMCBuIAp0cmFpbGVyCjw8IC9TaXplIDggL1Jvb3QgMSAwIFIg
Pj4Kc3RhcnR4cmVmCjcwMAolJUVPRgo=
```

`broken.pdf` is `notes.pdf` cut off after 300 bytes and must be `corrupt`:

```text
JVBERi0xLjQKJeLjz9MKOCAwIG9iago8PCAvTGVuZ3RoIDk4IC9GaWx0ZXIgL0ZsYXRlRGVjb2RlID4+CnN0cmVhbQp4nHMK4dJ3
M1QwNFIISeMyN1IwNzJQCEnhitZwKk1JTy1R0FTQNTI1UNCAMxILCoryy1JTNGMVQry4DBR0Dc0gGvxSKxDKi1LLMlPLreB8IwMj
M10DIDKE6HMN4QIA6gEcowplbmRzdHJlYW0KZW5kb2JqCjcgMCBvYmoKPDwgL1R5cGUgL1BhZ2UgL1BhcmVudCAyIDAgUiAvTWVk
aWFCb3ggWzAgMCA2MTIgNzkyXSAvUmVzb3VyY2VzIDw8IC9Gb250IDw8IC9GMSAzIDAgUiA+PiA+PiAvQ29udGVudHMgOCAwIFIg
```
