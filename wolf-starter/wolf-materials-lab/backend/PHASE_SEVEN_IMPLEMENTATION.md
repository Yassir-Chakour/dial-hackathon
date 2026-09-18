# Phase Seven Implementation Plan: API Layer

This document translates Phase Seven of GOALS.md into an implementation plan.

Phase Seven exposes ingestion, reconciliation, workflow and approval capabilities through a stable HTTP API for the frontend. The API should be a thin boundary over typed services. It must not duplicate business logic, trust client status fields or expose raw database behavior.

## 1. Phase-seven outcome

The backend should be able to:

- expose versioned source-import endpoints;
- return current and historical recommendations;
- return evidence and lineage with safe references;
- accept validated reviewer corrections;
- approve or reject the exact current recommendation version;
- replay an event safely and report its result;
- expose exceptions and review-queue items;
- return stable typed JSON contracts;
- enforce request validation, idempotency and concurrency;
- return consistent errors and request IDs;
- paginate and filter without leaking data across scopes;
- generate OpenAPI documentation from runtime schemas.

The API should make existing backend capabilities usable by the frontend without moving calculations or approval rules into browser code.

## 2. Scope and boundaries

### Included

- /api/v1 route structure;
- source import and status endpoints;
- version/recommendation/evidence endpoints;
- correction and approval/rejection endpoints;
- replay and review-queue endpoints;
- request/response Pydantic schemas;
- pagination, filtering and sorting rules;
- authorization placeholders and resource-scope checks;
- idempotency and optimistic-concurrency headers;
- safe error mapping;
- API tests and contract checks.

### Deferred

- frontend implementation;
- production identity provider integration;
- external procurement-system actions;
- public API exposure;
- real-time push notifications;
- gateway/rate-limit deployment;
- breaking API changes.

## 3. API principles

1. Routes identify resources; services implement behavior.
2. Every write is validated and scoped.
3. Every state-changing request is idempotent where practical.
4. Every approval references exact IDs and hashes.
5. Every response uses typed schemas.
6. Every error uses the Phase One envelope.
7. No endpoint returns secrets, raw database errors or unrestricted source content.
8. Historical versions are read-only.
9. Responses provide facts and evidence references; the frontend formats explanations.
10. Public contracts use opaque IDs and explicit versioning.

## 4. Route structure

Use an explicit prefix:

```text
/api/v1
├── /health/live
├── /health/ready
├── /sources
├── /source-versions
├── /workflow-runs
├── /recommendations
├── /evidence
├── /corrections
├── /approvals
├── /replays
├── /exceptions
└── /review-queue
```

Keep route modules separate under app/api: sources, versions, workflows, recommendations, evidence, corrections, approvals, replays, exceptions and review_queue.

## 5. Source import endpoints

POST /api/v1/sources accepts a source file or supported raw fixture representation.

Request fields:

- multipart bytes or an explicitly typed fixture payload;
- declared market;
- representation/media type;
- idempotency key;
- optional source-system metadata;
- client filename as display metadata only.

Response fields:

- opaque source ID;
- content hash;
- size and media type;
- received timestamp;
- ingestion status;
- workflow run ID if processing starts;
- synthetic-data marker where applicable.

Enforce size and row/field limits, sanitize filenames, reject path-like upload instructions and never return file bytes. Require idempotency for non-trivial processing.

GET /api/v1/sources/{source_id} returns safe metadata and processing status. It must not return bytes by default.

GET /api/v1/sources/{source_id}/versions returns paginated versions with status, update mode and lineage.

POST /api/v1/source-versions/{version_id}/process starts or resumes processing. Require idempotency key, expected source hash and workflow version. Reject changed hashes and superseded versions.

## 6. Workflow endpoints

GET /api/v1/workflow-runs/{run_id} returns run status/stage, source/version/reconciliation IDs, safe issues, review request ID, timestamps, retry count, result hashes and allowed next actions.

POST /api/v1/workflow-runs/{run_id}/resume resumes only from a persisted checkpoint and validated reviewer action. Require idempotency key and expected checkpoint version.

POST /api/v1/workflow-runs/{run_id}/cancel allows cancellation only before completion/approval. Cancellation is auditable and never deletes source evidence.

Do not return raw graph state, prompts, model responses or stack traces.

## 7. Recommendation endpoints

GET /api/v1/recommendations supports bounded filters for market, status, source/reconciliation version, recommendation key, stale/affected state, time range and review-required status. Use cursor pagination and return summaries by default.

GET /api/v1/recommendations/{recommendation_id} returns status/version, deterministic facts, calculation categories, assumptions, uncertainties, input/source IDs, hashes, issues and allowed reviewer actions.

GET /api/v1/recommendations/{recommendation_id}/changes returns added, replaced, preserved and removed records, reason codes, old/new references, totals, reconciliation status, evidence IDs and issues. Support compact mode.

GET /api/v1/recommendations/{recommendation_id}/history returns immutable versions, corrections, stale events and approvals in chronological order. Every history entry identifies exact input/result hashes and is read-only.

## 8. Evidence and lineage endpoints

GET /api/v1/evidence/{evidence_id} returns source file/version IDs, row/sheet/column references, evidence relation, source hash, validation status and timestamp. Raw rows are not returned by default.

GET /api/v1/recommendations/{recommendation_id}/evidence returns evidence grouped by recommendation item or change.

GET /api/v1/records/{record_id}/lineage returns upstream source version, source row, corrections, supersession and downstream recommendation references.

If demo raw-row viewing is needed, expose a separate protected endpoint with strict authorization, field redaction and bounded output. Never treat a row reference as a filesystem path.

## 9. Correction endpoints

POST /api/v1/recommendations/{recommendation_id}/corrections accepts a typed correction:

```json
{
  "target_record_id": "opaque-id",
  "field": "unit_price",
  "original_value": "12.50",
  "corrected_value": "12.05",
  "reason": "Reviewer confirmed source cell",
  "evidence_ids": ["opaque-evidence-id"]
}
```

Require expected recommendation/input hash, idempotency key, bounded reason, valid evidence, an allowed field and reviewer capability.

Return correction ID/status, new input hash, affected workflow/recommendation IDs, required next action and recalculation status.

Corrections are append-only. The endpoint must not update original source records in place.

GET /api/v1/corrections/{correction_id} returns correction history and validation outcome without unrelated source data.

## 10. Approval, rejection and revocation endpoints

POST /api/v1/recommendations/{recommendation_id}/approve requires expected result hash, expected input hash, idempotency key, optional If-Match version and a bounded reason. Reviewer identity comes from authenticated context, not the request body.

The server re-runs approval preconditions at commit time. It rejects stale, incomplete, superseded or changed recommendations.

Return approval ID, final status, approved hashes, timestamp, audit event ID and mock-action ID if applicable.

POST /api/v1/recommendations/{recommendation_id}/reject requires a bounded reason and exact expected hashes. Preserve recommendation, evidence and history.

POST /api/v1/approvals/{approval_id}/revoke is separate from rejection and requires authorization, reason and expected current status. Never delete an original approval.

External actions remain drafts or mocks. There must be no route that silently sends a purchase or contract change.

## 11. Replay, exception and review endpoints

POST /api/v1/replays accepts original event ID, source/version ID, payload/input hash, idempotency key and replay mode: dry_run or apply_if_safe. Default to dry_run.

Return original/replay result hashes, identical-result status, record/change counts, conflict status and reused/created workflow or reconciliation IDs.

GET /api/v1/replays/{replay_id} returns replay status and comparison. Identical input must not create a new current version.

GET /api/v1/exceptions supports bounded filters for status, severity, source/version, market, workflow and reason code. Return safe message, target IDs, row reference, status, timestamps and allowed actions.

GET /api/v1/review-queue returns review ID, blocking reason, target, evidence count, current status, allowed actions and stale indicator.

POST /api/v1/review-queue/{review_id}/resolve requires typed action, expected version/checkpoint token and idempotency key. Route corrections, scope decisions and rejection through dedicated services.

## 12. Common response contracts

Define shared schemas:

```python
class PageInfo(BaseModel):
    next_cursor: str | None
    limit: int

class ApiError(BaseModel):
    code: str
    message: str
    request_id: str
    details: list[ErrorDetail]

class ResourceMeta(BaseModel):
    id: str
    created_at: datetime
    version: int
    etag: str
```

Use consistent data/meta envelopes where appropriate:

```json
{
  "data": {},
  "meta": {
    "request_id": "req-opaque",
    "version": 1
  }
}
```

Do not mix success and error shapes unpredictably. Document nullable fields and enums in OpenAPI.

## 13. Pagination and consistency

- Use cursor pagination for list endpoints.
- Cap maximum page size.
- Allow only an explicit list of sort fields.
- Use stable ordering by timestamp plus opaque ID.
- Treat cursors as opaque and integrity-protected.
- Apply resource/tenant filtering before pagination.
- Return a consistent snapshot or version token for detail pages.
- Use ETag and If-Match for mutable resources.
- Return 409 Conflict for stale versions.
- Return 202 Accepted for bounded asynchronous processing.
- Avoid revealing an unauthorized resource's existence.

## 14. Security and privacy

### Security

- Require authentication before real source, review or approval data; isolate local demo mode.
- Enforce authorization at the service boundary.
- Separate viewer, reviewer, approver and administrator capabilities.
- Never trust client-provided status, reviewer ID, market, tenant or approval result.
- Require idempotency keys for uploads, corrections, replay and approval writes.
- Apply request size, timeout, pagination and rate limits.
- Validate Content-Type and never execute uploaded content.
- Restrict CORS to configured frontend origins.
- Return generic internal errors with a request ID.
- Add secure deployment headers.
- Keep raw source and model outputs out of access logs.
- Add CSRF protection when browser cookie authentication is introduced.
- Protect interactive API docs in non-local deployments.

### Privacy

- Return metadata/evidence references by default, not full source content.
- Redact sensitive fields according to role.
- Never return secrets, provider tokens, database URLs or stack traces.
- Keep reviewer identity server-derived and minimal.
- Apply tenant and retention filters to every query.
- Do not include supplier pricing in normal logs.
- Mark fixture responses as synthetic.
- Define export/deletion behavior before real data access.

## 15. Error mapping

Map service errors to stable responses:

| Condition | HTTP | Code |
| --- | ---: | --- |
| malformed request | 400 | invalid_request |
| unauthenticated | 401 | authentication_required |
| unauthorized | 403 | not_authorized |
| missing resource | 404 | not_found |
| stale version/hash | 409 | conflict |
| duplicate key/different payload | 409 | idempotency_conflict |
| incomplete evidence/review | 422 | validation_failed |
| processing in progress | 202 | processing |
| dependency unavailable | 503 | dependency_unavailable |
| unexpected failure | 500 | internal_error |

All errors use the Phase One envelope and X-Request-ID.

## 16. OpenAPI and contract testing

Generate OpenAPI from runtime Pydantic models. Review schemas, statuses, enum values, authentication requirements, nullable fields, pagination and errors.

Contract tests should:

- validate representative responses against OpenAPI;
- verify every write has idempotency/concurrency behavior;
- verify stale approval returns the documented code;
- verify no route returns raw ORM objects;
- verify API version and deprecation headers;
- verify no response contains secrets or unrestricted source content.

Generate frontend clients only from reviewed API schemas.

## 17. Reusable API helpers

Create reusable functions:

- require_scope(resource, actor);
- parse_cursor(cursor);
- build_page(items, next_cursor);
- require_idempotency_key(request);
- check_if_match(request, current_etag);
- to_public_id(internal_id);
- map_service_error(error);
- safe_detail_response(resource, actor);
- redact_response_fields(data, actor);
- enqueue_or_resume_workflow(command);
- assert_write_allowed(resource, actor, action).

Routes should validate, authorize, call a service and serialize the result.

## 18. Testing strategy

### Route tests

- every endpoint returns documented status and schema;
- malformed bodies use the common error shape;
- unknown fields are rejected where configured;
- request IDs are generated/propagated safely;
- pagination caps and cursor validation work;
- unsupported filters/sorts are rejected.

### Workflow/source tests

- identical upload idempotency creates one source;
- changed payload with the same key conflicts;
- processing can be polled;
- replay dry-run does not mutate current data;
- duplicate replay reuses the original result.

### Recommendation/approval tests

- detail contains hashes and evidence references;
- change endpoint shows affected/preserved records;
- stale approval returns conflict;
- missing evidence returns validation failure;
- correction requires expected hash and creates a new version;
- rejection/revocation preserve audit history;
- client status cannot bypass approval policy.

### Security/privacy tests

- unauthorized resources do not leak existence;
- raw source bytes are not returned by default;
- logs/errors omit secrets and source values;
- scope filters apply to every route;
- upload size/content limits are enforced;
- external actions remain mock-only.

## 19. Implementation order

1. Define API resource schemas and common envelopes.
2. Create /api/v1 route modules and service dependencies.
3. Add source/version and workflow status endpoints.
4. Add recommendation, change-set and history endpoints.
5. Add evidence and lineage endpoints.
6. Add correction, review-queue and exception endpoints.
7. Add approval/rejection/revocation endpoints.
8. Add replay endpoints with dry-run default.
9. Add pagination, ETags, idempotency and authorization boundaries.
10. Generate/review OpenAPI and add contract tests.
11. Add security/privacy and failure-path tests.
12. Document local demo authentication limitations and production requirements.

## 20. Explicitly out of scope for Phase Seven

Do not implement:

- frontend screens;
- production authentication provider;
- real external procurement calls;
- public API keys or third-party client access;
- websocket notifications;
- production gateway/scaling infrastructure;
- breaking schema changes;
- new ingestion or reconciliation business rules.

## Definition of done

Phase Seven is complete when the frontend can use stable /api/v1 contracts to import and inspect sources, follow workflow status, view recommendations/change sets/evidence, submit corrections, resolve review items, replay events and approve/reject exact current versions. All writes are validated, scoped, idempotent and concurrency-safe; errors are consistent; raw source and secrets remain protected; and the API contract is covered by automated tests.

