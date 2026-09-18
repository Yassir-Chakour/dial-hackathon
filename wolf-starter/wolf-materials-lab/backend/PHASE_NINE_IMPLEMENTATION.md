# Phase Nine Implementation Plan: Verification and Adversarial Cases

This document translates Phase Nine of GOALS.md into an implementation plan.

Phase Nine proves that the backend and frontend work together correctly under normal, corrected and hostile inputs. The goal is evidence-backed correctness, not only a green happy-path demo. Every important result must be reproducible, explainable and safe when data is incomplete or contradictory.

## 1. Phase-nine outcome

At the end of this phase, the project should be able to demonstrate:

- France v1 to v2 replacement behavior end to end;
- duplicate event replay without double counting;
- repeated invoice totals excluded from line arithmetic;
- credits and cancellations handled with their original sign;
- unrelated suppliers preserved;
- missing references routed to review;
- ambiguous records abstained from rather than guessed;
- stale approval rejection;
- corrected recommendation approval;
- evidence references for every changed result;
- safe behavior under malformed, oversized and adversarial inputs;
- reproducible test results from a clean checkout;
- known limitations and residual risks documented.

## 2. Scope and boundaries

### Included

- unit, integration, contract and end-to-end tests;
- deterministic fixture and golden-result management;
- adversarial input suite;
- security/privacy regression tests;
- workflow and approval state-machine tests;
- replay/concurrency testing;
- evidence completeness checks;
- test reports and quality gates.

### Deferred

- production load testing at final scale;
- third-party penetration testing;
- real customer-data testing;
- production disaster recovery;
- multi-market acceptance testing;
- model quality benchmarking beyond the workflow’s safety boundary.

Use synthetic fixtures only. Never add real customer, supplier or credential data to test cases.

## 3. Verification principles

1. Test row-level facts, not only totals.
2. Test both accepted and rejected outcomes.
3. Treat expected fixture results as test data, not unquestionable truth.
4. Assert provenance, version and hashes on every derived result.
5. Test replay and concurrency explicitly.
6. Verify that failures leave prior accepted state unchanged.
7. Verify that the model cannot bypass deterministic rules.
8. Make every test failure actionable with source row, record ID and reason code.
9. Keep tests deterministic and isolated.
10. Run security/privacy tests in CI, not only before demos.

## 4. Test layers

### Unit tests

Pure functions:

- CSV/raw-matrix readers;
- header detection;
- row classification;
- decimal/date/unit normalization;
- record identity;
- scope validation;
- replacement application;
- totals;
- change-set generation;
- decision calculation;
- approval policy;
- API error mapping.

Unit tests should use tiny focused inputs and assert exact outputs/reason codes.

### Integration tests

Use a temporary SQLite database and real migrations to test:

- source/version/event persistence;
- ingestion persistence;
- reconciliation transaction boundaries;
- lineage and supersession;
- recommendation versions;
- corrections;
- stale propagation;
- approvals and audit events;
- idempotency and conflict behavior.

Do not use the developer’s local database.

### Contract tests

Validate:

- API responses against OpenAPI schemas;
- HTTP status/error mapping;
- pagination and ETag behavior;
- required idempotency headers;
- stable enum/status values;
- frontend mock responses against backend contracts.

### End-to-end tests

Run the actual API and frontend against an isolated test database:

1. load France v1;
2. inspect the initial state;
3. submit France v2 replacement;
4. show changed and preserved records;
5. inspect evidence;
6. resolve an ambiguity;
7. recalculate;
8. approve the current recommendation;
9. replay v2;
10. prove the result and totals remain unchanged.

## 5. Golden fixture set

Create a versioned fixture directory:

```text
backend/tests/acceptance/fixtures/france/
├── v1/
├── v2-replacement/
├── expected/
│   ├── records.json
│   ├── change-set.json
│   ├── totals.json
│   └── evidence.json
└── adversarial/
```

Golden outputs should include:

- accepted source/version IDs replaced with stable test IDs;
- normalized records;
- record kinds;
- previous/incoming/current totals;
- change categories;
- preserved/superseded relationships;
- evidence references;
- review issues;
- result hashes where deterministic.

Do not compare timestamps or random database IDs. Normalize those fields before comparison.

When a golden result changes, require a review note explaining why the expected behavior changed.

## 6. France acceptance scenarios

### Scenario A: initial version

Verify:

- source hash and version are stored;
- rows preserve one-based source references;
- duplicate headers remain evidence;
- valid line records are accepted;
- invoice totals are classified and excluded;
- warnings/issues are visible;
- an initial current snapshot can be created.

### Scenario B: supplier-subset replacement

Verify:

- the previous current version is selected;
- only the declared supplier scope changes;
- unrelated suppliers are byte/value equivalent in the new current view;
- prior in-scope records are superseded, not deleted;
- incoming records have evidence;
- change set includes added/replaced/preserved categories;
- current totals match the expected fixture.

### Scenario C: duplicate replay

Submit the same event:

- sequentially;
- with the same idempotency key;
- with a different request ID;
- concurrently where practical.

Verify one result, one current materialization, no duplicate records, no changed totals and a stable result hash.

### Scenario D: repeated invoice total

Verify the repeated header total:

- remains stored as source evidence;
- is classified as invoice_total;
- is excluded from line aggregation;
- has an explainable reason code;
- cannot create a false saving or recommendation.

### Scenario E: credit/cancellation

Verify:

- negative value remains negative;
- credit/cancellation record is retained;
- affected document/line reference is linked when available;
- arithmetic uses signed semantics;
- missing relationship routes to review;
- the source row is visible in evidence.

### Scenario F: ambiguous correction

Verify:

- ambiguous record blocks approval;
- reviewer can submit an allowed correction;
- original raw source remains unchanged;
- correction is append-only;
- affected recommendation is recalculated;
- old draft/approval becomes stale;
- new recommendation requires exact current-version approval.

## 7. Adversarial input suite

Add focused cases for:

- duplicate event;
- same event key with different payload;
- wrong replacement scope;
- replacement that unexpectedly contains another supplier;
- currency mismatch;
- box-versus-piece confusion;
- unsupported product equivalence;
- cancellation without a matching prior line;
- missing source/version;
- changed source evidence after approval;
- duplicate business identity;
- conflicting values for the same identity;
- repeated headers in the middle of a file;
- repeated invoice totals in every line;
- malformed decimal/date;
- ambiguous date;
- missing unit/currency;
- empty or oversized file;
- huge row/column count;
- CSV formula-like cell;
- embedded instruction in a source row;
- invalid UTF-8;
- path traversal-looking filename;
- arbitrary URL supplied as source;
- unauthorized evidence access;
- stale workflow checkpoint;
- stale recommendation approval;
- concurrent corrections;
- model output containing a fake approval command.

A failure should become an explicit exception, rejection or review item. It must never produce a fabricated accepted decision.

## 8. Invariant and property tests

Use property-based tests where useful.

Invariants:

- parsing the same bytes twice yields the same canonical result hash;
- replaying an accepted event does not alter current records;
- current materialization contains no duplicate business identity;
- no out-of-scope record changes during a subset replacement;
- source rows and raw values remain immutable;
- a repeated invoice total never contributes to line totals;
- a negative cancellation never becomes positive through normalization;
- an approved recommendation is immutable;
- any input/evidence change makes dependent approval stale;
- every changed result has at least one evidence reference;
- failed reconciliation leaves the prior current version active;
- unsupported/ambiguous values never become silently valid;
- no model proposal changes deterministic facts.

Use a canonical JSON representation for equality comparisons. Exclude timestamps and generated IDs from pure-function hashes.

## 9. Security and privacy verification

### Input security

- file and row limits are enforced;
- malformed encodings fail safely;
- formulas/macros/links are not executed;
- filenames cannot create storage paths;
- no arbitrary URLs or commands are accepted;
- SQL injection-like values remain data;
- large or deeply nested payloads are rejected.

### Authorization and state security

- unauthorized users cannot see protected source/evidence;
- reviewers cannot perform administrative actions;
- client status cannot bypass approval;
- stale hashes are rejected;
- cross-market/tenant IDs are rejected;
- approval race conditions produce one accepted result;
- external actions remain mock-only.

### Privacy

- logs omit raw source rows, supplier prices, prompts and tokens;
- errors omit stack traces and database details;
- API defaults return metadata/evidence references instead of raw files;
- localStorage/URL state does not contain sensitive source content;
- fixture responses are labelled synthetic;
- audit events retain safe IDs and reason codes without confidential payloads.

## 10. Evidence completeness checks

Create a verification command that scans accepted results and checks:

- every current record has source version and row evidence;
- every changed recommendation item has evidence;
- every approval has input/result hashes;
- every correction has original and corrected values;
- every superseded record has a reason and lineage edge;
- every issue has severity, code and target;
- every total has currency/unit context;
- every excluded invoice total has an exclusion reason.

The command should fail CI if any accepted result lacks required provenance.

## 11. Test reports and quality gates

Produce machine-readable reports for:

- unit/integration coverage;
- acceptance scenario results;
- adversarial case results;
- API contract validation;
- evidence completeness;
- security/dependency scan;
- type/lint status.

Recommended CI gate:

```bash
poetry check
poetry run ruff check .
poetry run mypy app
poetry run pytest -q
poetry run pytest tests/acceptance -q
poetry run python -m app.verification.evidence_check
```

Set a meaningful coverage threshold for core ingestion, reconciliation, decision and approval modules. Do not allow a high aggregate percentage to hide untested security/state-critical paths.

## 12. Failure triage

Every failed test should report:

- scenario/test name;
- event/source/version IDs;
- record key and source row when applicable;
- expected/actual status;
- expected/actual hash or total;
- reason code;
- whether database state was rolled back;
- suggested review owner/action.

Do not print raw source contents or secrets in CI logs.

Classify failures:

- correctness;
- provenance;
- state/approval;
- security/privacy;
- performance/resource;
- test-fixture error.

Correctness, provenance, security and approval failures block the release/demo.

## 13. Performance and reliability checks

Phase Nine is not full production load testing, but verify reasonable limits:

- ingestion completes within a defined fixture budget;
- replay is no more expensive than the original operation where cached;
- pagination prevents oversized responses;
- large change sets do not block API health endpoints;
- model/tool timeouts terminate safely;
- retry limits prevent loops;
- database transactions do not leave locks after failure;
- frontend polling stops at completion/failure/timeout.

Record measurements with the test environment and fixture version. Do not claim production performance from local synthetic tests.

## 14. Implementation order

1. Freeze and document the France acceptance fixtures.
2. Add golden normalized records, change sets, totals and evidence.
3. Add unit and database integration tests.
4. Add full end-to-end France workflow test.
5. Add duplicate/replay/concurrency tests.
6. Add adversarial input fixtures and expected outcomes.
7. Add property/invariant tests.
8. Add evidence completeness and security/privacy checks.
9. Add CI reports and quality gates.
10. Run the final demo path from a clean checkout.
11. Record known limitations, unsupported formats and residual risks.

## 15. Explicitly out of scope for Phase Nine

Do not implement:

- new business features;
- production scale claims;
- real customer-data validation;
- unreviewed changes to golden outcomes;
- bypasses added only to make tests pass;
- automatic suppression of failing security/provenance tests;
- new market rules;
- real external actions.

## Definition of done

Phase Nine is complete when the full France scenario, correction path and replay path pass from a clean checkout; all listed adversarial cases produce safe, explainable outcomes; accepted decisions have complete evidence and lineage; stale/unauthorized approvals are rejected; no source data or secrets leak through logs/API/UI; and CI reports reproducible quality results with documented limitations.

