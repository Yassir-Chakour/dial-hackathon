# Phase Ten Implementation Plan: Extensibility and Production Readiness

This document translates Phase Ten of GOALS.md into an implementation plan.

Phase Ten moves the validated hackathon workflow toward a production-capable platform. It should preserve the correctness and review boundaries established in Phases One through Nine while expanding markets, storage, identity, operations and integrations.

Production readiness is not the same as deploying the demo. It requires explicit threat modeling, data governance, operational ownership, recovery procedures, measurable service limits and a controlled migration path.

## 1. Phase-ten outcome

At the end of this phase, the platform should be able to:

- support Italy, Hungary and Kosovo through configurable update rules;
- ingest real XLSX files safely in addition to CSV/raw fixtures;
- run on PostgreSQL with reviewed migrations;
- use object storage for source files and controlled evidence access;
- resume workflows from durable checkpoints;
- authenticate users and enforce reviewer/approver roles;
- isolate tenants and resource scopes;
- process large imports through background jobs with retries and dead-letter handling;
- emit structured audit logs, metrics and traces;
- support retention, deletion and incident response procedures;
- integrate with real procurement systems only through reviewed, reversible and authorized adapters;
- preserve the same evidence, versioning, idempotency and approval invariants.

The system should fail closed when identity, evidence, scope, validation or external dependencies are uncertain.

## 2. Preconditions

Before Phase Ten starts, confirm that Phases One through Nine are complete:

- versioned API contracts exist;
- ingestion and reconciliation are deterministic;
- source/version lineage is covered by tests;
- recommendation/approval policy is server-side;
- adversarial and replay tests pass;
- evidence completeness checks exist;
- no real secrets or customer data are stored in the repository;
- all production assumptions are documented.

Do not begin production scaling by bypassing unresolved correctness or provenance failures.

## 3. Target architecture

A production deployment should separate:

- API service for authenticated read/write requests;
- background worker service for ingestion, reconciliation and workflow runs;
- PostgreSQL for transactional metadata and state;
- object storage for source files and restricted evidence artifacts;
- durable workflow/checkpoint store;
- queue/broker for background jobs;
- secrets manager;
- observability platform;
- controlled integration adapters.

Conceptually:

```text
Browser/client
    -> API gateway/WAF
    -> authenticated API service
        -> PostgreSQL
        -> object storage
        -> workflow/checkpoint store
        -> job queue -> worker service
                         -> model/provider adapters
                         -> procurement adapters
    -> audit/metrics/traces
```

Keep the API, worker and adapters behind the same domain services and policy checks. Do not let workers bypass approval policy because they run outside the HTTP process.

## 4. Multi-market extensibility

Replace France-specific branching with a market capability interface:

```python
class MarketRules(Protocol):
    market_code: str
    rules_version: str

    def inspect_structure(self, rows: list[SourceRow]) -> StructureResult: ...
    def detect_scope(self, inspection: StructureResult) -> UpdateScope: ...
    def normalize_record(self, row: SourceRow) -> CanonicalSourceRecord: ...
    def validate_update(self, version: SourceVersion) -> list[Issue]: ...
```

Each market package should define:

- supported representations;
- header/section mappings;
- locale/date/decimal rules;
- supplier/product aliases;
- update modes and scope semantics;
- validation rules;
- fixture and golden acceptance cases;
- rules version and migration notes.

Common reader, evidence, hashing, persistence, reconciliation and approval functions remain shared. Do not duplicate the entire ingestion pipeline per country.

A market is not production-ready until it has:

- representative fixtures;
- wrong-scope and duplicate-event tests;
- currency/unit rules;
- evidence references;
- documented unsupported layouts;
- operational owner and change process.

## 5. XLSX ingestion

Add XLSX support behind a bounded file-processing service.

Security requirements:

- enforce maximum file size, workbook count, sheet count, row/column count and decompressed size;
- reject or safely ignore macros, external links, embedded objects and unsupported formulas;
- process workbooks in a sandboxed worker with no unnecessary network access;
- never execute formulas or VBA;
- detect zip bombs and malformed archives;
- preserve sheet names, row/column positions, merged/header context and raw values;
- record library/parser version and workbook metadata;
- make all extracted data traceable to workbook/sheet/row/column evidence.

Treat formula results cautiously. Prefer stored values only when the source policy allows them; otherwise mark the field unsupported or requiring review.

Keep XLSX parsing separate from normalization. The output must use the same SourceRow contract as CSV/raw input.

## 6. PostgreSQL migration

Move transactional data from SQLite to PostgreSQL using reviewed migrations.

Plan:

1. define PostgreSQL-compatible types and constraints;
2. run migrations on a clean database;
3. export/import only through a versioned migration tool;
4. verify counts, hashes, foreign keys and lineage;
5. run dual-read or shadow validation if the risk justifies it;
6. switch writes during a controlled maintenance window;
7. retain rollback and restore procedures;
8. verify idempotency and approval behavior after migration.

PostgreSQL requirements:

- foreign keys and check constraints enabled;
- transaction isolation appropriate to approval/reconciliation concurrency;
- connection pooling and timeouts;
- encrypted connections;
- least-privilege database roles;
- tested backups and point-in-time recovery;
- indexes reviewed with query plans;
- tenant/resource filters included in query paths.

Do not rely on application-only constraints that the database can enforce.

## 7. Object storage and source retention

Move large source bytes and evidence artifacts to private object storage.

Store in PostgreSQL:

- object key;
- content hash;
- media type/size;
- encryption/key reference;
- retention/deletion state;
- source/version lineage;
- access audit metadata.

Object storage rules:

- private buckets/containers by default;
- server-side encryption and managed key rotation;
- no public URLs;
- short-lived, scoped download URLs only when required;
- object key generated by the server from opaque IDs, never from user filenames;
- malware/content scan before processing;
- immutable/versioned storage where audit policy requires it;
- deletion workflow that checks retention/legal hold;
- access logs and alerts for unusual downloads.

Do not duplicate raw source content in logs, database JSON, checkpoints or model prompts.

## 8. Durable workflows and background processing

Move long-running ingestion/reconciliation/agent runs to a durable worker system.

Job requirements:

- stable job/event/workflow ID;
- idempotency key and input fingerprint;
- retry policy by failure class;
- timeout and cancellation handling;
- dead-letter queue for repeated failures;
- checkpoint after safe node boundaries;
- progress/status events;
- operator replay tool;
- no retry of irreversible external actions without explicit idempotency.

Separate transient failures from data failures:

- network timeout may retry;
- malformed source should become a review/failure;
- authorization failure should not retry blindly;
- stale approval must not retry into approval;
- external action timeout requires provider-specific reconciliation.

Use a worker identity with least privilege. Worker jobs must re-check tenant, scope and approval state at execution time.

## 9. Authentication, authorization and tenant boundaries

Introduce an identity provider and server-side authorization.

Model:

- user/service identity;
- tenant or organization;
- role/capability;
- resource scope;
- reviewer/approver relationship;
- audit actor.

Suggested capabilities:

```text
source:view
source:import
review:resolve
recommendation:view
recommendation:correct
recommendation:approve
recommendation:reject
integration:execute
administration:manage
```

Rules:

- deny by default;
- authenticate every protected request;
- authorize at the service/repository boundary;
- filter every query by tenant and permitted market/resource scope;
- never trust tenant IDs from request bodies;
- prevent self-approval where policy requires separation of duties;
- require re-authentication or step-up authorization for high-impact approval/integration actions;
- record actor, role and authorization decision in audit events;
- use service identities for workers and integrations, not shared human tokens.

Test cross-tenant and cross-market access as a release blocker.

## 10. Secrets and configuration

Use a managed secrets system for:

- database credentials;
- object-storage credentials;
- model/provider tokens;
- identity-provider secrets;
- signing keys;
- integration credentials.

Requirements:

- no secrets in source control, images, logs, browser bundles or workflow state;
- rotation without code deployment where practical;
- separate credentials by environment and service;
- short-lived credentials for workers/integrations;
- startup validation for required production configuration;
- alerts for expired or near-expiry credentials;
- documented break-glass procedure with audit.

Configuration should be immutable per deployment and observable only through safe capability/status fields.

## 11. Audit logging and observability

Create append-only audit events for:

- source access/import/deletion;
- version acceptance/supersession;
- corrections;
- workflow pauses/resumes/cancellations;
- reconciliation results;
- recommendation creation/recalculation;
- approval/rejection/revocation;
- permission failures;
- object downloads;
- integration requests/responses;
- administrative changes.

Each event includes actor/service, tenant, target IDs, status transition, hashes, policy/rules version, request/run ID and timestamp. Avoid raw source content, credentials and full prompts.

Operational observability should include:

- request rate, latency and error rate;
- ingestion throughput and failure categories;
- queue depth and oldest job age;
- workflow duration/retry/timeout rates;
- review queue age and blocking count;
- reconciliation mismatch rate;
- approval conflict/stale rate;
- object-storage download anomalies;
- integration success/failure and latency;
- database health, locks and connection pool saturation.

Use trace correlation across API, worker, database, model and integration calls. Redact spans by default.

Define alerts with owners, severity and runbooks. A metric without an operator action is not operational readiness.

## 12. Data governance and privacy

Before real data:

- define data classification for source files, supplier data, prices, reviewer identity and audit records;
- document purpose, retention and deletion;
- define tenant isolation and support access;
- establish regional storage/processing requirements;
- define provider/model data-retention policies;
- execute a privacy/security review;
- document data-subject or contractual deletion handling where applicable;
- define incident notification and breach response;
- verify backups follow the same protection and retention policy.

Apply data minimization:

- store only needed source fields;
- send only necessary excerpts to models;
- avoid personal data in decision evidence unless required;
- redact logs/telemetry;
- segregate production data from development;
- prohibit production data in test fixtures without approved anonymization.

## 13. Controlled external integrations

Create an adapter boundary for procurement systems:

```python
class ProcurementAdapter(Protocol):
    def validate_draft(self, action: DraftAction) -> ValidationResult: ...
    def submit(self, action: ApprovedAction, idempotency_key: str) -> SubmissionResult: ...
    def get_status(self, external_id: str) -> ExternalStatus: ...
    def cancel_or_compensate(self, external_id: str) -> ActionResult: ...
```

Rules:

- integrations receive only approved, current, evidence-backed actions;
- approval must be checked again at submission time;
- every call uses an idempotency key;
- no direct integration calls from model nodes;
- dry-run and sandbox environments by default;
- outbound allowlists and timeouts;
- provider response is treated as untrusted;
- external IDs/statuses are stored;
- uncertain submission is reconciled before retry;
- compensation/cancellation workflow is explicit;
- integration failures create review tasks, not silent retries.

Start with mock adapters and contract tests. Enable real adapters only after security, authorization, audit and recovery review.

## 14. Reliability, backup and disaster recovery

Define service objectives:

- availability target;
- maximum acceptable data loss;
- recovery time target;
- maximum queue delay;
- import/reconciliation completion target.

Implement and test:

- automated PostgreSQL backups;
- point-in-time recovery;
- object-storage versioning/replication as required;
- encrypted backup storage;
- restore into an isolated environment;
- migration rollback/forward recovery;
- queue replay and dead-letter recovery;
- workflow checkpoint recovery;
- incident runbooks;
- periodic recovery drills.

A backup is not verified until a restore has been tested and evidence recorded.

## 15. Dependency and supply-chain security

- pin and scan dependencies;
- generate software bill of materials;
- scan container/base images;
- verify package provenance where possible;
- patch critical vulnerabilities under a defined SLA;
- run static analysis and secret scanning;
- review XLSX/CSV parsing libraries;
- restrict runtime filesystem/network permissions;
- sign release artifacts;
- separate build and runtime credentials.

Do not install unreviewed model tools or plugins in production workflows.

## 16. Performance and scaling

Measure rather than assume:

- maximum supported file size/row count;
- records per second for each market;
- reconciliation duration;
- queue throughput and retry rate;
- database query latency;
- evidence lookup latency;
- frontend polling load;
- model cost/latency if enabled.

Scale independently:

- API replicas for requests;
- workers for ingestion/reconciliation;
- model adapter capacity;
- database read replicas only after consistency requirements are understood;
- object storage for artifacts.

Keep deterministic calculations independent of model throughput. The system must degrade safely if a model provider is unavailable.

## 17. Migration and rollout strategy

Use staged environments:

1. local development;
2. isolated test;
3. staging with synthetic production-like volume;
4. limited pilot;
5. controlled production rollout.

For every release:

- run migrations before dependent code;
- execute smoke and acceptance tests;
- verify health/readiness;
- verify queue workers and checkpoint resume;
- verify audit/event ingestion;
- monitor errors and rollback signals;
- retain release/version identifiers.

Use feature flags for:

- market rule activation;
- XLSX support;
- model provider use;
- external integrations;
- new approval policies.

A feature flag must not weaken security or allow approval bypass.

## 18. Testing and production gates

Required pre-production tests:

- all Phase Nine acceptance/adversarial tests;
- PostgreSQL migration and rollback/restore tests;
- object-storage access/expiry/deletion tests;
- authentication/authorization and cross-tenant tests;
- worker retry/dead-letter/checkpoint tests;
- secret rotation tests;
- integration idempotency and uncertain-response tests;
- dependency and container scans;
- backup restore drill;
- load and resource-limit tests;
- accessibility and API contract regression tests.

Block release on:

- cross-tenant data access;
- approval bypass;
- missing evidence for accepted decisions;
- replay double counting;
- unencrypted or public source storage;
- secret leakage;
- unbounded uploads/jobs;
- untested restore path.

## 19. Implementation order

1. Define production threat model, data classification and service objectives.
2. Generalize market rules and add acceptance fixtures for each market.
3. Add safe XLSX parsing and parser security tests.
4. Migrate schema and repositories to PostgreSQL.
5. Add private object storage and source retention workflows.
6. Add durable queue/checkpoint workers.
7. Add identity, roles, tenant/resource authorization and separation of duties.
8. Add managed secrets and configuration rotation.
9. Add audit/metrics/traces, alerts and runbooks.
10. Add mock and then reviewed procurement adapters.
11. Validate backup/restore, migrations, failure recovery and load.
12. Roll out by environment using feature flags and a rollback plan.

## 20. Explicitly out of scope for Phase Ten

Do not treat these as automatically solved:

- legal/privacy compliance without review;
- guaranteed model correctness;
- unrestricted autonomous procurement;
- untested production integrations;
- indefinite source retention;
- public access to source evidence;
- scaling by adding infrastructure without measurements;
- bypassing review to reduce operational friction.

## Definition of done

Phase Ten is complete when the system can safely support multiple markets, XLSX input, PostgreSQL/object storage, durable background workflows, authenticated tenant-scoped review and approval, operational audit/observability, tested backup/recovery and controlled external integrations. The original guarantees remain intact: deterministic calculations, complete evidence, immutable history, idempotent replay, exact-version approval and fail-closed behavior.

