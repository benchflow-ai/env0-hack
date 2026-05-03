# mock-gdoc: Development TODO

Focused backlog for turning `mock-gdoc` from a task-specific mock into a more complete and stable Google Docs environment.

---

## P0: Stability and Contract Alignment

- [ ] Fix the API test hang so `tests/test_api.py` completes reliably
  - Inspect FastAPI app startup, middleware, session lifecycle, and test fixtures
  - Confirm `health`, document CRUD, and admin endpoints all return promptly
- [ ] Stop silently swallowing unsupported `batchUpdate` requests
  - Return a clear mock limitation error for unsupported request types
  - Add tests for unsupported request handling
- [ ] Align product/docs copy with actual capability
  - Update `README.md`
  - Update environment UI copy that currently claims support for comments and revisions
- [ ] Document the current supported API surface
  - Public document endpoints
  - Supported `batchUpdate` request types
  - Known intentional limitations
- [ ] Add regression tests for core edge cases
  - Empty document operations
  - Invalid indices and ranges
  - Unsupported request payloads
  - Not-found and cross-user access cases

## P1: Fill the Most Visible Feature Gaps

- [x] Implement comments API using the existing `Comment` model and schemas (5dd80a2)
  - List comments for a document
  - Create a comment
  - Get a single comment
  - Update comment content
  - Resolve or unresolve a comment
  - Delete a comment
  - Threaded replies (create and delete)
- [ ] Implement revisions API on top of existing `DocumentRevision` records
  - List revisions for a document
  - Get a specific revision
  - Decide whether revision content is metadata-only or includes snapshot payloads
- [ ] Upgrade search beyond title-only matching
  - Support body-text search in addition to title search
  - Preserve simple query semantics for example tasks
- [ ] Add pagination semantics
  - Introduce `pageToken` and `nextPageToken`
  - Keep `pageSize`
- [ ] Extend the dev UI to expose comments and revisions
  - Dashboard visibility
  - API explorer examples
  - DB viewer navigation

## P2: Improve Google Docs Fidelity

- [ ] Expand `batchUpdate` coverage
  - `updateTextStyle`
  - `updateParagraphStyle`
  - `createParagraphBullets`
  - `deleteParagraphBullets`
- [ ] Add structured content support beyond plain paragraph text
  - Preserve richer paragraph and text runs
  - Stop collapsing everything back into a plain-text body rebuild
- [ ] Decide on and implement a minimal table editing story
  - Either support a narrow table subset
  - Or explicitly mark tables as unsupported in API/docs
- [ ] Add stronger index and range validation
  - Out-of-bounds indices
  - Empty or inverted ranges
  - Multi-step batch interactions
- [ ] Add fidelity-focused unit tests
  - Style updates do not flatten the body
  - Structural edits preserve existing content correctly

## P3: Collaboration and Multi-User Semantics

- [ ] Make `num_users` actually seed multiple users
- [ ] Stop assigning all documents to the primary user during seed
- [x] Add basic ownership and sharing semantics (220019c)
  - Owner-only documents
  - Shared readable documents
  - Shared editable documents
  - Four roles: owner, writer, commenter, reader
- [ ] Enforce access rules consistently across documents, comments, and revisions
- [ ] Add tests for cross-user behavior
  - Read allowed vs denied
  - Comment allowed vs denied
  - Edit allowed vs denied

## P4: Tasks and Evaluation Coverage

- [ ] Add new GDoc example tasks beyond search and summary flows
  - Comment on a document instead of editing it
  - Search by body content, not just title
  - Inspect revision history before changing a document
  - Preserve source docs while producing a derived artifact
- [ ] Add at least one safety-style task
  - Penalize modifying or deleting the source document
  - Penalize writing to the wrong document
- [ ] Add evaluator coverage for newly exposed APIs
  - Comments
  - Revisions
  - Pagination
  - Full-text search

## Completion Criteria

- [ ] `tests/test_api.py` passes reliably
- [ ] `tests/test_web_routes.py`, `tests/test_tasks.py`, and `tests/test_seed.py` remain green
- [ ] README, UI copy, and exposed API behavior describe the same capability set
- [ ] At least two new GDoc example tasks cover functionality beyond title search and document creation
- [ ] Agents can complete the main gdoc tasks using only the exposed API and skill docs
