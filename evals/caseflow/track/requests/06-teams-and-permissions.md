# Request 6 — Teams and permissions

Two teams will use this. Give each team its own workspace. Owners can manage members and connections, editors can add and change documents, and viewers can only read. Nobody should be able to see another team's material, even with a copied link.

## What I need

### Who is asking

CaseFlow runs on our own machines with fixed local sessions: every API request and page names its
user in the `X-User` header (a user id matching `[a-z][a-z0-9_-]{0,31}`). There are no passwords.

- Missing or malformed `X-User` → `401 unauthenticated`, on every `/api/` endpoint and page except
  `GET /api/health` and the `/api/clock` endpoints.
- Pages use the same header (you may also accept a cookie for real browsers, but the header
  must work).

### Workspaces and members

- `POST /api/workspaces` with `{"name": "Team A"}` → `201 {"id": "...", "name": "Team A", "role": "owner"}`.
  Any user can create one and becomes its owner. Blank name → `422 name_required`.
- `GET /api/workspaces` → `{"workspaces": [{"id", "name", "role"}, ...]}`: the workspaces the user
  belongs to, oldest first, with the user's role.
- `GET /api/workspaces/{workspace_id}/members` → `{"members": [{"user": "ana", "role": "owner"}, ...]}`
  sorted by user.
- `PUT /api/workspaces/{workspace_id}/members/{user}` with `{"role": "editor"}` → `200 {"user", "role"}`:
  adds the user or changes their role. Roles are `owner`, `editor` and `viewer`; anything else →
  `422 invalid_request`.
- `DELETE /api/workspaces/{workspace_id}/members/{user}` → `204`. Not a member → `404 not_found`.
- Removing or demoting the last owner → `409 last_owner`.

### Cases belong to a workspace

- `POST /api/cases` now requires `workspace_id`: `{"name": "...", "workspace_id": "..."}`.
  Case JSON (create, list, detail) gains `"workspace_id"`.
- `GET /api/cases` lists the cases of every workspace the user belongs to, oldest first;
  `?workspace_id=...` limits it to one workspace.
- Everything inside a case (its documents, connections, jobs, search, pages, uploads, imports)
  belongs to the case's workspace.
- Data that existed before this change goes into a workspace with id `default` owned by user
  `admin`.

### Editing documents

`PATCH /api/documents/{document_id}` with `{"title": "..."}`, `{"text": "..."}` or both → `200`
with the document. Blank title → `422 title_required`. Documents now carry `"version"`: `1` when
created, increased by one every time the title or text actually changes (an edit, or a source
bringing a changed revision). An edit that changes nothing changes nothing.

### Roles

| Operation | viewer | editor | owner |
| --- | --- | --- | --- |
| Read anything in the workspace: cases, documents, search, connections (never credentials), jobs, members, pages | yes | yes | yes |
| Create cases; add documents (paste, CSV, PDF); edit documents; start imports; cancel jobs | no | yes | yes |
| Create connections, change their credentials; manage members | no | no | yes |

- A member whose role does not allow the operation → `403 forbidden`.
- **Someone who is not a member of the workspace gets `404 not_found`** for anything that
  belongs to it, by any route: cases, documents, connections, jobs, search, members, pages, and
  any request body or URL that refers to it (for example creating a case in it). A copied link
  or a changed id is never enough to see or change another team's material.
