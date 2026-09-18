# Phase Four Implementation Plan: Versioning and Reconciliation

This document translates Phase Four of `GOALS.md` into an implementation plan.

Phase Four connects the Phase Two persistence layer with the Phase Three ingestion engine. It determines how an accepted incoming France version changes the current dataset. The central rule is that a replacement must replace only its declared scope; it must not be appended as a second copy or delete unrelated records.

## 1. Phase-four outcome

At the end of this phase, the backend should be able to:

- load the previous accepted France version;
- validate the incoming version and its declared update scope;
- apply a supplier-subset replacement without double counting;
- preserve unrelated France suppliers and records;
- calculate previous, incoming and current totals deterministically;
- distinguish additions, replacements, removals, preserved records and corrections;
- reconcile totals against fixture expectations and arithmetic invariants;
- produce a structured, evidence-linked change set;
- mark superseded records and versions without deleting history;
- make the operation idempotent and replay-safe;
- expose clear exceptions when scope or evidence is incomplete.

Phase Four should produce a trustworthy current dataset and change explanation. Recommendation generation and human approval remain later phases.

## 2. Scope and invariants

### Included

- previous/current version selection;
- update-scope validation;
- France replacement application;
- record identity and matching;
- current-record materialization;
- change-set generation;
- arithmetic reconciliation;
- supersession lineage;
- event idempotency;
- reconciliation exceptions;
- tests for duplicate and adversarial updates.

### Deferred

- recommendation scoring or optimization;
- LangGraph orchestration;
- model-generated explanations;
- approval and stale-approval workflow;
- frontend screens;
- real procurement system writes;
- multi-market generalization beyond an extensible interface.

### Core invariants

1. A source version is immutable.
2. A replay produces the same current records and result hash.
3. A replacement changes only the declared scope.
4. Unrelated records remain unchanged and traceable.
5. Every changed current record links to incoming or prior evidence.
6. No header total is counted as a line amount.
7. Credits and cancellations retain their signed meaning.
8. A failed reconciliation never becomes the current accepted dataset.
9. Historical versions and records are never hard-deleted as part of reconciliation.

## 3. Recommended project structure

Extend the backend with:

```text
backend/
├── app/
│   ├── reconciliation/
│   │   ├── __init__.py
│   │   ├── contracts.py          # Scope, snapshots and change-set models
│   │   ├── scope.py              # Scope validation and matching
│   │   ├── identity.py           # Stable record identity/matching
│   │   ├── apply.py              # Pure replacement/addition application
│   │   ├── totals.py             # Decimal arithmetic and reconciliation
│   │   ├── changes.py            # Structured change-set generation
│   │   ├── lineage.py            # Superseded/current relationships
│   │   └── pipeline.py           # Transactional orchestration
│   ├── services/reconciliation_service.py
│   ├── repositories/reconciliation.py
│   └── schemas/reconciliation.py
└── tests/reconciliation/
    ├── test_scope.py
    ├── test_identity.py
    ├── test_apply.py
    ├── test_totals.py
    ├── test_changes.py
    ├── test_lineage.py
    └── test_replay.py
```

Keep the record-set transformation pure. The service layer should load persisted inputs, call pure functions, validate the result and commit the new current state in one transaction.

## 4. Version selection

Never reconcile against an arbitrary latest row or an unaccepted version.

Define a current-version query using:

- market;
- logical source scope;
- accepted status;
- effective version/date;
- explicit supersession state.

The service should reject:

- missing prior version when the update requires one;
- multiple current versions for the same scope;
- incoming versions already superseded;
- incoming versions with a different source hash but reused event key;
- records from a different market or incompatible parser/rules version unless an explicit migration exists.

For the first France workflow, make the selected inputs visible in the reconciliation result:

```json
{
  "market": "FR",
  "previous_version_id": "fr-v1",
  "incoming_version_id": "fr-v2",
  "update_mode": "replacement",
  "scope": {
    "supplier_ids": ["supplier-key"],
    "market": "FR"
  }
}
```

## 5. Scope validation

The incoming scope is a safety boundary. Validate it before touching current records.

Checks should include:

- market matches the prior/current dataset;
- update mode is supported;
- replacement supplier scope is non-empty;
- every scope identifier has evidence in the incoming source;
- scope does not accidentally expand to the entire market;
- incoming records belong to the declared scope unless explicitly classified as metadata;
- no record outside the scope is removed or replaced;
- source version and scope evidence are accepted and review-complete.

If scope is missing, ambiguous or contradictory, return a reconciliation exception and leave the current version unchanged.

Do not infer full-market replacement from the absence of a supplier. Full replacement must be explicit and separately authorized.

## 6. Record identity and matching

Reconciliation requires a stable business identity, not database row IDs.

Define a canonical identity strategy for France records, for example:

```text
market + supplier + product + document/line identity
```

Use the strongest available source identifiers in order:

1. stable source line/document ID;
2. supplier + product + transaction/document reference;
3. a documented fallback key containing source context and row identity.

The fallback must be deterministic and must not silently merge two ambiguous records. If two incoming records resolve to the same key with conflicting values, create a conflict exception.

Do not match records solely on description text, amount or row position. Those fields can support review, but they are not sufficient identity by themselves.

Store match metadata:

- identity strategy/version;
- matched prior record ID, if any;
- match confidence;
- fields used;
- conflict reasons;
- source evidence references.

## 7. Applying a supplier-subset replacement

Represent the operation as a pure set transformation:

```text
current = unaffected(previous, scope) ∪ incoming(scope)
```

For a France replacement:

1. load all accepted previous records;
2. partition them into in-scope and out-of-scope records;
3. validate that every incoming record belongs to the scope;
4. discard in-scope records only from the new current materialization;
5. retain all out-of-scope records unchanged;
6. add accepted incoming records;
7. preserve lineage from superseded prior records to incoming records;
8. reject the entire operation if validation or reconciliation fails.

Do not delete prior rows from history. “Removed from current” means superseded, not destroyed.

If the incoming version contains only a subset of the supplier’s records, the scope contract must say whether it is a full supplier replacement or a narrower subset. Do not guess.

## 8. Change-set contract

Create a typed change set that is consumable by later APIs and review screens:

```python
class ChangeSet(BaseModel):
    previous_version_id: str
    incoming_version_id: str
    current_version_id: str | None
    scope: UpdateScope
    added: list[RecordChange]
    replaced: list[RecordChange]
    removed_from_current: list[RecordChange]
    preserved: list[RecordChange]
    conflicts: list[ReconciliationIssue]
    warnings: list[ReconciliationIssue]
    result_hash: str
    status: Literal["accepted", "needs_review", "rejected"]
```

Each `RecordChange` should include:

- stable record key;
- prior and incoming record IDs where applicable;
- change type;
- old/new signed value and quantity where relevant;
- reason code;
- source/version/row evidence;
- whether the change affects a later recommendation.

Use machine-readable reason codes such as:

```text
in_scope_replacement
new_record
prior_record_superseded
preserved_outside_scope
identity_conflict
missing_scope_evidence
arithmetic_mismatch
```

Keep human-readable explanations as derived views of these facts, not as the source of truth.

## 9. Totals and reconciliation

Use `Decimal` throughout. Never use binary floating point for monetary reconciliation.

Compute separate totals for:

- previous accepted version;
- incoming version;
- in-scope previous records;
- in-scope incoming records;
- preserved out-of-scope records;
- resulting current materialization;
- credits and cancellations;
- excluded invoice/header totals.

Do not sum every version together. The expected relationship for a replacement is conceptually:

```text
current_total = preserved_previous_total + accepted_incoming_scope_total
```

Apply signed credits/cancellations according to their record classification. A repeated invoice total is evidence, not a line value.

Reconciliation should report:

- exact calculated values;
- currency/unit basis;
- record counts by kind;
- excluded totals and reasons;
- expected fixture value, when supplied;
- difference;
- tolerance policy, if any;
- pass/fail status;
- evidence references.

Do not hide a mismatch with rounding. Currency precision and tolerance must be explicit and documented.

## 10. Materialization and lineage

Create a new current version or snapshot for each accepted reconciliation. It should reference:

- previous version;
- incoming version;
- reconciliation/change-set ID;
- parser/rules version;
- reconciliation algorithm version;
- result hash;
- creation timestamp.

For each current record, preserve one of these lineage relationships:

- `introduced_by_incoming`;
- `preserved_from_previous`;
- `replaced_previous_record`;
- `derived_from_correction`.

The current materialization is a view of accepted history. It must be possible to explain where every current record came from.

A superseded previous record remains queryable with its original source evidence and status. Never update its source values in place.

## 11. Idempotency and concurrency

Use the Phase Two event key and payload hash.

For a replay with the same event key and payload hash:

- return the original reconciliation result;
- do not create another current version;
- do not duplicate change-set or lineage rows;
- do not increment totals.

For the same event key with a different payload hash:

- return a conflict;
- do not partially apply the event;
- record a safe exception if policy requires it.

Protect current-version selection and commit against concurrent updates. For SQLite, use a transaction and an explicit application lock or compare-and-swap version check. A reconciliation must fail rather than overwrite a newer current version.

Use an input fingerprint containing previous-version ID, incoming-version ID, scope, algorithm version and canonical records. It should be part of the result hash and uniqueness strategy.

## 12. Failure handling

Treat reconciliation as an all-or-nothing operation.

Failure cases include:

- missing previous version;
- ambiguous or expanded scope;
- duplicate identities;
- unsupported cross-market record;
- currency/unit mismatch;
- arithmetic mismatch;
- missing evidence;
- concurrent current-version change;
- duplicate event conflict.

On failure:

- preserve the source and incoming version;
- store a structured reconciliation issue;
- mark the event `needs_review` or `failed`;
- leave the prior current version active;
- do not create a partially accepted current dataset;
- avoid logging raw rows or sensitive commercial values.

## 13. Security and privacy

### Security

- Treat scope metadata and record keys as untrusted input.
- Use parameterized repository methods and database constraints.
- Never use user-supplied scope values to construct SQL or filesystem paths.
- Enforce maximum change-set and record counts to prevent resource exhaustion.
- Use optimistic concurrency so a stale worker cannot overwrite a newer version.
- Do not let model output choose replacement scope or bypass reconciliation checks.
- Expose only opaque public IDs through future APIs.
- Keep administrative migration and repair operations separate from normal ingestion.
- Log event ID, version IDs, result status and safe reason codes—not raw supplier prices or source rows.

### Privacy

- Reuse stored source evidence instead of copying raw rows into every change-set record.
- Store only the old/new fields needed for audit and review.
- Keep supplier names and commercial values out of routine logs.
- Do not send previous/current records to external model providers.
- Preserve synthetic-data labels on fixture-derived materializations.
- Define retention of superseded versions before real data is introduced.
- Support future tenant filtering on every version, record, event and recommendation query.

## 14. Reusable functions and interfaces

Keep these transformations pure and reusable:

- `select_current_version(scope)`;
- `validate_update_scope(previous, incoming, scope)`;
- `build_record_identity(record, strategy)`;
- `match_records(previous_records, incoming_records)`;
- `apply_replacement(previous_records, incoming_records, scope)`;
- `build_change_set(previous, incoming, current)`;
- `calculate_signed_totals(records)`;
- `reconcile_totals(snapshot)`;
- `build_lineage_edges(change_set)`;
- `compute_reconciliation_hash(inputs)`;
- `assert_valid_transition(state, event)`.

Service boundaries should look like:

```text
ReconciliationService.reconcile(event_id)
  -> load inputs
  -> validate scope
  -> match records
  -> apply pure transformation
  -> reconcile totals
  -> persist change set and lineage transactionally
  -> return result
```

The service must not contain duplicated CSV parsing or normalization logic.

## 15. Testing strategy

Use the supplied France v1/incoming/expected fixtures and focused adversarial cases.

### Version and scope tests

- correct previous accepted version is selected;
- missing or multiple current versions fail safely;
- France replacement scope is accepted;
- missing scope is reviewable, not defaulted;
- a different market is rejected;
- an out-of-scope incoming record fails the operation;
- unrelated suppliers remain unchanged.

### Matching and application tests

- exact identity produces replacement;
- new incoming record is added;
- prior in-scope record is superseded;
- out-of-scope record is preserved with lineage;
- conflicting identity produces a review issue;
- no hard delete occurs;
- current materialization contains no duplicate business identity.

### Arithmetic tests

- repeated invoice totals are excluded;
- negative credits/cancellations remain signed;
- previous/incoming/current totals reconcile;
- currency mismatch is rejected;
- expected fixture totals are compared exactly or with a documented tolerance;
- totals do not double after replay.

### Replay and concurrency tests

- same event/payload returns original result;
- same key/different payload conflicts;
- a failed transaction leaves the previous current version active;
- stale worker cannot overwrite a newer current version;
- two duplicate submissions result in one accepted materialization.

### Provenance tests

- every added/replaced/preserved record has source evidence;
- each superseded record remains queryable;
- change-set result hash is stable;
- only the intended scope is marked changed.

## 16. Implementation order

1. Define scope, snapshot, change-set and reconciliation issue schemas.
2. Implement version selection and current-scope queries.
3. Implement deterministic record identity and matching.
4. Implement the pure supplier-subset replacement transformation.
5. Implement signed totals and excluded-total accounting.
6. Implement change-set and lineage generation.
7. Add transactional reconciliation service and repository methods.
8. Add idempotency, result hashes and concurrency checks.
9. Add failure-state handling and structured exceptions.
10. Run the France fixtures and compare against expected outcomes.
11. Add adversarial and replay/concurrency tests.
12. Document the exact replacement semantics and known limitations.

## 17. Explicitly out of scope for Phase Four

Do not implement:

- recommendation ranking or optimization;
- model-written explanations;
- LangGraph workflows;
- human approvals or stale-approval rejection;
- frontend review screens;
- OCR or new document formats;
- other market update modes;
- external procurement actions;
- production database migration.

## Definition of done

Phase Four is complete when a France replacement event creates one correct current materialization, replaces only its declared supplier scope, preserves unrelated records, retains complete supersession lineage, reconciles signed totals without counting repeated headers, creates a reviewable change set, rejects ambiguous or conflicting updates, and produces no change when replayed with the same event and payload.

