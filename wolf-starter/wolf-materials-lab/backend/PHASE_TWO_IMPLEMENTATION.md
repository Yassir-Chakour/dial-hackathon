# Phase Two Implementation Plan: Data and Persistence Foundation

This document translates Phase Two of `GOALS.md` into an implementation plan.

Phase Two should add durable local persistence without implementing the France ingestion engine, recommendation algorithm, LangGraph workflow, authentication, or frontend integration. The goal is to create a trustworthy storage layer that can preserve source evidence, versions, workflow state and future approval decisions.

## 1. Phase-two outcome

At the end of this phase, the backend should be able to:

- initialize a local SQLite database safely;
- create and migrate a documented schema;
- store source-file metadata and content hashes;
- store immutable source versions and raw normalized records;
- store processing events and idempotency keys;
- store recommendations, evidence links, corrections and approvals;
- preserve lineage between every derived object and its source version;
- enforce basic state transitions and optimistic concurrency;
- execute multi-record changes transactionally;
- avoid duplicate data when the same event is replayed;
- expose repository/service functions that later API and agent phases can reuse;
- test persistence behavior using isolated temporary databases.

The database is a local foundation. It is not yet a production multi-tenant database or a complete business workflow.

## 2. Recommended technology choices

Use mature, typed components with a clear upgrade path:

- SQLAlchemy 2.x for database models and repositories;
- Alembic for versioned schema migrations;
- SQLite for local development and the hackathon demo;
- `aiosqlite` if the FastAPI application uses async database access;
- Pydantic models for API/domain boundaries, separate from ORM models;
- `hashlib.sha256` for deterministic file and payload hashes;
- UTC-aware timestamps stored consistently in the database.

Do not couple application schemas directly to SQLAlchemy models. ORM models represent storage; Pydantic models represent validated inputs and outputs. This separation prevents a database migration from silently changing the public API.

Add dependencies through Poetry and commit the resulting `poetry.lock`. Pin compatible major versions and run migrations in CI against a clean database.

## 3. Recommended project structure

Extend the Phase One structure as follows:

```text
backend/
├── app/
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py              # Declarative base and model registration
│   │   ├── session.py           # Engine, session factory and transaction helpers
│   │   ├── migrations/          # Alembic configuration/scripts
│   │   └── models/
│   │       ├── source.py
│   │       ├── record.py
│   │       ├── event.py
│   │       ├── recommendation.py
│   │       └── review.py
│   ├── repositories/
│   │   ├── sources.py
│   │   ├── records.py
│   │   ├── events.py
│   │   ├── recommendations.py
│   │   └── reviews.py
│   ├── services/
│   │   ├── source_service.py
│   │   ├── lineage_service.py
│   │   └── workflow_service.py
│   └── schemas/
│       ├── source.py
│       ├── record.py
│       ├── recommendation.py
│       └── review.py
├── alembic.ini
├── migrations/
├── tests/
│   ├── db/
│   ├── repositories/
│   └── services/
└── data/                       # Local-only database, gitignored
```

Repositories should perform persistence operations. Services should coordinate repositories and enforce business invariants. Routes and future agent nodes should call services, not issue SQL directly.

## 4. Database configuration

Add typed settings such as:

| Setting | Purpose | Development default |
| --- | --- | --- |
| `DATABASE_URL` | SQLAlchemy connection URL | `sqlite:///./data/wolf-materials.db` |
| `DATABASE_ECHO` | SQL debugging | `false` |
| `DATABASE_BUSY_TIMEOUT_MS` | SQLite lock wait | `5000` |
| `DATABASE_AUTO_CREATE` | Whether local startup may create schema | `false` |
| `SOURCE_STORAGE_MODE` | `database` or future `object_storage` | `database` |
| `SOURCE_MAX_BYTES` | Maximum stored source size | explicit bounded value |

Rules:

1. Production must not rely on automatic table creation. Run reviewed migrations.
2. Development may use a local SQLite file under a gitignored `data/` directory.
3. Tests must use a temporary database and never the developer’s database.
4. Enable SQLite foreign keys for every connection.
5. Set a busy timeout and use transactions consistently.
6. Do not log `DATABASE_URL`, file paths containing sensitive names, or SQL parameter values.
7. Keep the storage interface database-agnostic so PostgreSQL can replace SQLite later.

SQLite is sufficient for the local workflow, but its concurrency limits should be documented. Do not present SQLite as the production deployment choice.

## 5. Persistence model

Use immutable source and version records, with explicit current/superseded state. Recommended entities are below.

### 5.1 `source_files`

Represents one received file or source payload.

Suggested fields:

- `id` — internal UUID or opaque identifier;
- `tenant_id` — nullable in the hackathon, reserved for future isolation;
- `original_filename` — sanitized display name, never used as a filesystem path;
- `media_type` and `size_bytes`;
- `sha256` — hash of the exact original bytes;
- `content` — encrypted or local-only bytes for the demo, if stored in SQLite;
- `received_at` — UTC timestamp;
- `source_system` and safe metadata;
- `retention_status` and `deleted_at` for future lifecycle handling.

The hash must be calculated from the original bytes before parsing. Two identical byte streams should resolve to the same content identity.

### 5.2 `source_versions`

Represents a logical delivery/version derived from a source file.

Suggested fields:

- `id`;
- `source_file_id`;
- `market`;
- `version_label` or source-provided version;
- `parent_version_id` when the delivery supersedes or updates another version;
- `update_mode` such as `initial`, `replacement`, `addition`, `correction`;
- `scope_key` for the affected supplier/market subset;
- `status`: `received`, `processing`, `accepted`, `superseded`, `rejected`, `needs_review`;
- `created_at`, `accepted_at` and `superseded_at`;
- `metadata_json` containing bounded, validated metadata only.

Do not overwrite a previous version. Version history is evidence and must remain inspectable.

### 5.3 `source_records`

Stores one extracted/normalized record while retaining its raw evidence.

Suggested fields:

- `id`;
- `source_version_id`;
- `record_key` — deterministic key within the source scope;
- `source_row_number`;
- `source_sheet` or source section;
- `raw_values_json` — original row values with duplicate-header context;
- normalized supplier/product/date/quantity/unit/currency/value fields;
- `record_kind`: `line`, `header_total`, `credit`, `cancellation`, `unknown`;
- `validation_status`: `valid`, `ambiguous`, `invalid`;
- `validation_errors_json`;
- `created_at`.

Phase Two should store the shape and lineage, not decide France-specific normalization rules. Those rules belong in Phase Three.

### 5.4 `workflow_events`

Represents an intake or processing event.

Suggested fields:

- `id`;
- `event_key` — caller-supplied idempotency key, unique within a tenant/scope;
- `event_type`;
- `source_file_id` and `source_version_id` where applicable;
- `payload_hash`;
- `status`: `received`, `processing`, `completed`, `failed`, `needs_review`;
- `attempt_count`;
- `error_code` and safe error summary;
- `created_at`, `started_at`, `completed_at`.

The unique constraint on the idempotency key must be enforced by the database, not only by application code.

### 5.5 `recommendations`

Stores versioned derived decisions, even before Phase Three calculates them.

Suggested fields:

- `id`;
- `source_version_id` or a future decision-input snapshot ID;
- `recommendation_key`;
- `status`: `draft`, `needs_review`, `approved`, `rejected`, `stale`;
- `facts_json` containing deterministic computed facts;
- `explanation_json` containing structured explanation facts, not unverified model prose;
- `calculation_hash` to identify the exact inputs/calculation;
- `created_at` and `superseded_at`.

Never update an approved recommendation in place. Create a new version and mark the old one stale or superseded.

### 5.6 `evidence_links`

Connects a derived object to exact source evidence.

Suggested fields:

- `id`;
- `recommendation_id` or another derived-object reference;
- `source_record_id`;
- `source_file_id`;
- `relation`: `supports`, `contradicts`, `changed_by`, `preserved_from`;
- `created_at`.

Use foreign keys and unique constraints to prevent duplicate evidence links.

### 5.7 `corrections` and `approvals`

Corrections should preserve the original value and identify the reviewer/action. Approvals must reference an exact recommendation ID and calculation/input hash.

Approval fields should include:

- `recommendation_id`;
- `decision`: `approved` or `rejected`;
- `reviewer_id` placeholder for the future authenticated identity;
- `reason` with a bounded length;
- `created_at`;
- `superseded_by` or `stale_at` where applicable.

Do not treat a free-text approval note as authorization. The exact version and validation state are the authorization boundary.

## 6. Constraints and indexes

Add database constraints for invariants that must hold even if a bug bypasses the service layer:

- unique `(tenant_id, sha256)` where applicable;
- unique `(tenant_id, event_key)`;
- foreign keys on every lineage relationship;
- non-negative file size and bounded text fields;
- valid status values enforced through application enums and database checks where supported;
- unique recommendation key per input version;
- unique evidence link per derived record/source record/relation;
- one active current version per logical source scope;
- indexes on `source_version_id`, `record_key`, `event_key`, `status`, `created_at` and approval lookups.

Use deterministic keys for records and scopes. Avoid relying on row order or auto-increment IDs to identify business records.

## 7. Transactions and state transitions

Create one transaction boundary around each operation that changes related tables.

For example, accepting a source version should atomically:

1. create or find the source file by hash;
2. create the source version;
3. create the workflow event;
4. write extracted records when available;
5. update the event status;
6. commit all changes together.

If any step fails, roll back the entire operation and preserve a safe failure status where possible.

Define explicit state-transition functions instead of assigning strings throughout the code:

```text
received -> processing -> completed
received -> needs_review
processing -> failed
completed -> superseded
approved -> stale
```

Reject invalid transitions with a stable domain error. A recommendation cannot become approved if it is stale, incomplete or linked to an unaccepted input version.

## 8. Idempotency and replay safety

Implement idempotency now because later phases explicitly require duplicate event replay.

- Require or derive a stable `event_key` for each processing event.
- Store the exact input `payload_hash`.
- Add a database unique constraint on the event key.
- When the same key and payload hash are replayed, return the original result without inserting new rows.
- When the same key arrives with a different payload hash, return a conflict and create no partial state.
- Make source-file storage content-addressed by SHA-256 where possible.
- Test concurrent duplicate submissions, not only sequential retries.

Do not use timestamps, random IDs or filenames as the only deduplication key.

## 9. Security and privacy

Persistence introduces sensitive-data risk even with synthetic fixtures.

### Security controls

- Use parameterized SQL through SQLAlchemy; never concatenate SQL from user input.
- Treat filenames, metadata, JSON fields and future source rows as untrusted input.
- Sanitize filenames for display and never use them to construct a storage path.
- Enforce maximum source size before storing bytes.
- Keep database files and backups outside the repository and add `data/`, local databases and exports to `.gitignore`.
- Restrict database file permissions to the service user.
- Do not expose raw database IDs when opaque public IDs are more appropriate.
- Do not make raw source-content endpoints public by default.
- Keep migrations reviewed and forward-only; never silently drop data in a normal migration.
- Redact SQL parameters and source values from logs.

### Privacy controls

- Store only the original source bytes and metadata required for evidence and replay.
- Define a retention policy field now, even if deletion is implemented later.
- Keep synthetic-data markers on source files and records so demo data cannot be mistaken for real procurement data.
- Avoid storing user identity until authentication exists; use a clearly documented placeholder rather than an invented identity.
- Do not send stored source content to a model or external service in Phase Two.
- Provide a future deletion path that removes or tombstones source content while preserving the minimum audit record required by policy.
- Encrypt production databases/backups and source storage when real data is introduced; SQLite local demo encryption is not assumed.

## 10. Reusable repository and service interfaces

Define protocols or narrow interfaces around storage so tests can replace the database and future PostgreSQL migration does not change business code.

Recommended operations:

- `find_source_by_hash(sha256)`;
- `create_source_file(...)`;
- `create_source_version(...)`;
- `get_current_version(scope)`;
- `create_or_get_event(event_key, payload_hash)`;
- `replace_event_status(event_id, status, error_code=None)`;
- `insert_source_records(version_id, records)`;
- `get_records_for_version(version_id)`;
- `create_recommendation(...)`;
- `link_evidence(...)`;
- `record_correction(...)`;
- `create_approval(...)`;
- `mark_recommendations_stale(input_version_id)`.

Reusable service functions should enforce invariants such as idempotency and valid transitions. Repositories should remain focused on persistence and not contain recommendation or procurement rules.

## 11. Migration strategy

Create an initial migration containing the complete Phase Two foundation schema. Do not create tables implicitly at application import time.

Required migration checks:

- fresh database upgrade succeeds;
- upgrade from the previous migration succeeds;
- downgrade behavior is documented and safe for local development;
- foreign keys and indexes are present;
- migration is deterministic and works in CI;
- schema metadata does not depend on application startup side effects.

Before adding later business logic, create a migration for any schema change. Never edit an already-applied migration to repair a deployed database.

## 12. Testing strategy

Use temporary databases and factories that create isolated test data.

Required tests:

- schema migration creates all expected tables and indexes;
- foreign keys reject orphaned records;
- source bytes produce a stable SHA-256 hash;
- identical source files are detected as duplicates;
- different bytes never share a source identity;
- source versions preserve parent/superseded lineage;
- raw row numbers and original values are stored unchanged;
- event keys are idempotent;
- same event key with different payload hash returns conflict;
- transaction failure rolls back related inserts;
- invalid status transitions are rejected;
- evidence links cannot reference missing source records;
- approved recommendations cannot be modified in place;
- stale recommendations cannot receive a new approval;
- sensitive fields are absent from logs and API responses;
- repository tests work without relying on global application state.

Add a small persistence test fixture representing France v1 and a placeholder incoming version, but do not implement France replacement calculations yet. The fixture should verify lineage and replay behavior only.

## 13. Implementation order

1. Add SQLAlchemy, Alembic and SQLite dependencies through Poetry.
2. Add database settings and a gitignored local `data/` directory.
3. Create the engine/session factory with foreign keys and safe transaction helpers.
4. Define the source, version, record, event, recommendation, evidence, correction and approval models.
5. Add constraints and indexes for identity, lineage and idempotency.
6. Generate the initial Alembic migration and verify it on a clean database.
7. Implement repositories with narrow, typed methods.
8. Implement source/version/event services with transactions and state transitions.
9. Add isolated repository and migration tests.
10. Run the Phase One quality gate plus migration and persistence checks.
11. Document local database initialization, reset procedure and data-retention assumptions.

## 14. Explicitly out of scope for Phase Two

Do not implement these yet:

- parsing CSV/XLSX files;
- France-specific replacement-supplier rules;
- currency/unit normalization;
- invoice-header or cancellation arithmetic;
- automatic recommendation generation;
- LangGraph nodes or model provider calls;
- reviewer login or real identity management;
- production PostgreSQL rollout;
- object storage deployment;
- external procurement actions.

Phase Two should store the information those capabilities will need, but it should not pretend to calculate or approve them yet.

## Definition of done

Phase Two is complete when a clean checkout can migrate a local SQLite database, persist a source file and immutable version lineage, store records/events/derived-object placeholders, safely replay an idempotent event, reject conflicting duplicates and invalid state transitions, and pass the complete test and quality gate without leaking source data or secrets.
