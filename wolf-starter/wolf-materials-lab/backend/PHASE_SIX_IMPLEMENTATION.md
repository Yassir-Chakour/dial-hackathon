# Phase Six Implementation Plan: Procurement Decision and Approval

This document translates Phase Six of `GOALS.md` into an implementation plan.

Phase Six turns a reconciled change set and workflow output into a versioned procurement decision that a human can inspect, correct and approve. Approval must belong to the exact current recommendation version and its validated inputs. A narrative that looks correct is not an approval.

## 1. Phase-six outcome

At the end of this phase, the backend should be able to:

- create versioned recommendations from validated reconciliation facts;
- identify recommendations affected by a source update;
- mark prior approvals stale when their inputs change;
- expose changed records, reasons and evidence references;
- accept reviewer corrections as new immutable facts;
- recalculate affected recommendations after corrections;
- reject stale, incomplete or unsupported approvals;
- approve only the exact current recommendation version;
- preserve reviewer, timestamp, input/version hashes and correction history;
- keep purchasing, contract and notification actions as drafts or mocks.

The system should make it impossible to approve a recommendation whose evidence or calculation inputs are no longer current.

## 2. Scope and boundaries

### Included

- recommendation input snapshots;
- deterministic benefit and decision calculations;
- recommendation versioning;
- impact and staleness propagation;
- correction workflow;
- review queue and decision states;
- approval/rejection service;
- audit records;
- exact-version and optimistic-concurrency checks;
- security/privacy tests.

### Deferred

- production identity provider and full role administration;
- external procurement-system writes;
- contract signing or notifications;
- frontend endpoints from Phase Seven;
- background queue deployment;
- multi-market award rules;
- production PostgreSQL/object storage;
- autonomous approval by a model.

Phase Six can create a draft external action, but it must not send, purchase, award or modify a contract.

## 3. Recommended project structure

Extend the backend with:

```text
backend/
├── app/
│   ├── decisions/
│   │   ├── __init__.py
│   │   ├── contracts.py          # Decision, benefit and approval schemas
│   │   ├── calculator.py         # Pure deterministic calculations
│   │   ├── builder.py            # Recommendation construction
│   │   ├── impact.py             # Dependency and staleness propagation
│   │   ├── corrections.py        # Reviewer correction validation
│   │   ├── approval_policy.py    # Approval preconditions
│   │   ├── audit.py              # Audit-event construction
│   │   └── service.py            # Transactional orchestration
│   ├── repositories/
│   │   ├── decisions.py
│   │   ├── corrections.py
│   │   └── approvals.py
│   └── schemas/decisions.py
└── tests/decisions/
    ├── test_calculator.py
    ├── test_versioning.py
    ├── test_impact.py
    ├── test_corrections.py
    ├── test_approval_policy.py
    ├── test_rejection.py
    └── test_concurrency.py
```

Keep calculations and approval policy pure where possible. The service layer should load immutable inputs, call pure functions and commit changes transactionally.

## 4. Decision model

A recommendation should be a versioned projection of validated facts, not a mutable note.

Recommended entities:

### `decision_input_snapshots`

Captures the exact inputs used for a recommendation:

- reconciliation/current version ID;
- source version IDs;
- change-set ID;
- correction IDs;
- assumption IDs and values;
- calculation/rules version;
- canonical input hash;
- created timestamp.

Once used by a recommendation, a snapshot is immutable.

### `recommendations`

Suggested fields:

- opaque recommendation ID;
- stable recommendation key;
- decision input snapshot ID;
- status: `draft`, `needs_review`, `approved`, `rejected`, `stale`, `superseded`;
- deterministic facts;
- calculation outputs;
- evidence completeness status;
- blocking issue IDs;
- created/superseded timestamps;
- result hash;
- parent recommendation ID when recalculated.

### `recommendation_items`

Stores the records or award lines contributing to the decision:

- recommendation ID;
- product/material key;
- supplier/market;
- quantity/unit/currency;
- validated price or signed value;
- decision outcome;
- source/reconciliation evidence;
- reason codes;
- input record IDs.

### `approvals`

Stores an explicit reviewer decision:

- recommendation ID and result hash;
- input snapshot ID and hash;
- reviewer identity reference;
- decision;
- reason;
- created timestamp;
- policy version;
- request/correlation ID;
- stale/revoked timestamp if later invalidated.

Never update approved recommendation facts in place.

## 5. Deterministic decision calculation

The calculation layer must receive typed, validated facts only. It should:

- operate on `Decimal` values;
- preserve currency and unit context;
- distinguish recurring savings, rebates and cost avoidance;
- reject unsupported comparisons;
- record assumptions separately from measured source values;
- return a calculation result plus reason codes and warnings;
- produce a stable result hash.

Example calculation categories:

```text
recurring_saving
one_time_rebate
cost_avoidance
price_change
not_comparable
insufficient_evidence
```

Do not call a lower future price a saving without a defined baseline and comparable unit. Do not calculate a benefit from a rejected or ambiguous source record. A calculation with missing evidence becomes `needs_review`, not zero.

The model may draft a natural-language explanation after calculations, but it cannot modify the calculation output.

## 6. Recommendation construction

Build recommendations only after:

1. source version is accepted;
2. reconciliation is accepted;
3. all blocking record issues are resolved or explicitly excluded;
4. input scope is known;
5. calculation rules/version are recorded;
6. evidence references are available.

The builder should produce:

- decision summary;
- affected products/records;
- proposed supplier or action;
- deterministic financial/operational facts;
- assumptions;
- uncertainties and exceptions;
- evidence references;
- required reviewer actions;
- calculation/input/result hashes.

A recommendation must state what it does not know. Do not replace uncertainty with confident prose.

## 7. Impact and staleness propagation

When a new reconciled version is accepted:

1. find recommendations whose input snapshot references the affected source/version/record;
2. compare changed record keys and evidence links;
3. mark affected drafts as needing recalculation;
4. mark affected approved recommendations `stale`;
5. preserve historical approval and its prior result hash;
6. create a new recommendation version when recalculation is requested;
7. leave unaffected recommendations current when their evidence and inputs are unchanged;
8. store the reason and exact change set that caused staleness.

Staleness is not deletion or automatic rejection of historical work. It means the old approval no longer authorizes the changed facts.

Use structured reason codes:

```text
source_version_changed
input_record_replaced
evidence_superseded
reviewer_correction
calculation_rules_changed
assumption_changed
```

Do not mark every recommendation stale after every event. Propagation must be dependency-based and testable.

## 8. Reviewer corrections

A correction changes the interpreted record, not the original source.

A correction should contain:

- correction ID;
- target source record/recommendation item;
- original value;
- corrected value;
- field and validation type;
- reviewer identity reference;
- reason;
- evidence or comment;
- created timestamp;
- correction version/hash.

Rules:

- raw source remains immutable;
- corrections are append-only;
- corrected values must pass the same schema and domain validation;
- corrections cannot change market or source ownership without a separate workflow;
- a correction invalidates dependent calculation/input hashes;
- affected recommendations are recalculated as new versions;
- prior drafts/approvals are never silently rewritten.

If a correction changes scope, identity, currency or unit semantics, require a stronger review state and prevent direct approval until reconciliation is rerun.

## 9. Approval policy

Implement approval as a pure precondition check plus a transactional commit.

Approval is allowed only when all are true:

- recommendation status is current and approvable;
- recommendation result hash matches the stored current result;
- input snapshot is still current;
- source/reconciliation version is accepted;
- no blocking issues remain;
- all required evidence links exist;
- required corrections have been applied and validated;
- reviewer has the required capability;
- the approval request is not stale;
- no newer recommendation exists for the same decision key;
- optimistic-concurrency version matches.

Approval must reject with stable codes such as:

```text
recommendation_not_found
recommendation_stale
input_snapshot_changed
source_version_not_accepted
blocking_issues_present
evidence_incomplete
reviewer_not_authorized
newer_version_exists
approval_conflict
```

Do not rely on a client-provided `status=approved` field. The server recomputes policy preconditions from persisted state.

## 10. Rejection and withdrawal

A reviewer may reject a recommendation with a bounded reason and optional issue references.

A rejection should:

- preserve the recommendation and evidence;
- store reviewer, time, policy version and reason;
- prevent it from being approved without a new version or explicit reopen policy;
- keep any external action in draft state;
- expose the failure reason to later review APIs.

If an already approved recommendation becomes stale, do not rewrite its historical decision. Create a staleness event and require a new recommendation/approval for current action.

If an approval must be withdrawn for an operational reason, create a separate revocation event with authorization and reason. Do not delete the original approval.

## 11. Transaction and concurrency rules

Approval and staleness propagation must be transactional.

Approval transaction:

1. lock or compare-and-swap the recommendation version;
2. reload current source/input/recommendation hashes;
3. run approval policy;
4. insert approval audit record;
5. update recommendation status;
6. create a draft/mock action record if required;
7. commit atomically.

If any precondition changes, roll back and return `approval_conflict`.

Staleness transaction:

1. accept the new current/reconciled version;
2. find dependent recommendations;
3. mark affected recommendations stale;
4. create structured staleness/audit events;
5. commit with the new version.

Never approve and publish a recommendation through separate unguarded transactions.

## 12. Security and privacy

### Security controls

- Use server-side approval policy; never trust frontend status fields.
- Bind approval to opaque recommendation ID, result hash and input snapshot hash.
- Recheck authorization and freshness at commit time.
- Use least privilege: drafting, reviewing and approving are separate capabilities even before full identity integration.
- Prevent self-approval in the future by storing creator/reviewer references now.
- Do not let model output or reviewer free text alter structured decision fields without validation.
- Enforce bounded reason/comment lengths and reject unsafe markup where rendered.
- Use parameterized repositories and database constraints.
- Do not expose raw source content in review list responses.
- Audit policy failures, stale attempts and rejected approval attempts without logging confidential values.
- Keep external actions disabled or mock-only in this phase.

### Privacy controls

- Store reviewer identity references only when required; do not invent personal data.
- Keep source evidence linked by ID rather than duplicated in approval records.
- Redact supplier pricing and source rows from routine logs.
- Restrict recommendation/evidence access by future tenant and reviewer scope.
- Define retention for approvals, corrections and audit records before real data is introduced.
- Preserve synthetic-data labels in drafts, decisions and demo responses.
- Do not send recommendation inputs or reviewer comments to external models unless explicitly approved and minimized.

## 13. Audit trail

Create append-only audit events for:

- recommendation created;
- recommendation recalculated;
- correction submitted/accepted/rejected;
- recommendation marked stale;
- approval attempted/accepted/rejected;
- recommendation rejected;
- approval revoked;
- mock external action created.

Each event should include:

- event ID/type;
- actor reference;
- target opaque ID;
- previous/current status;
- input/result hash;
- policy/calculation version;
- timestamp;
- request/run correlation ID;
- safe reason codes.

Audit events describe what happened. They do not replace immutable source versions or recommendation snapshots.

## 14. Reusable functions and services

Create reusable functions:

- `build_decision_input_snapshot(inputs)`;
- `calculate_decision_facts(snapshot)`;
- `build_recommendation(snapshot, calculation)`;
- `find_impacted_recommendations(change_set)`;
- `mark_recommendation_stale(recommendation, reason)`;
- `validate_correction(correction, target)`;
- `recalculate_after_correction(correction_id)`;
- `check_approval_preconditions(request, current_state)`;
- `commit_approval(request, checked_state)`;
- `record_audit_event(event)`;
- `create_mock_action(recommendation_id)`.

Keep calculation functions independent of HTTP, LangGraph and database sessions. The approval policy should be callable from APIs, workflow nodes and tests.

## 15. Testing strategy

### Calculation tests

- comparable baseline produces expected recurring saving;
- rebates and cost avoidance remain separate;
- currency/unit mismatch is rejected;
- missing evidence produces `needs_review`;
- rejected/ambiguous records cannot contribute;
- result hash is stable for the same snapshot;
- assumptions are separate from measured facts.

### Versioning and impact tests

- accepted recommendation references an immutable input snapshot;
- source update marks only affected recommendations stale;
- unrelated recommendation remains current;
- historical approved result remains inspectable;
- corrected record creates a new recommendation version;
- newer recommendation prevents approval of an older one.

### Correction tests

- raw source value remains unchanged;
- valid correction is stored append-only;
- invalid correction is rejected;
- identity/scope/unit correction triggers stronger review;
- correction changes input/result hash;
- dependent recommendation is recalculated.

### Approval tests

- exact current version can be approved;
- stale recommendation is rejected;
- changed input hash is rejected;
- missing evidence is rejected;
- blocking issue is rejected;
- unauthorized reviewer is rejected;
- concurrent approval produces one accepted result;
- client-provided status cannot bypass policy;
- approved recommendation cannot be edited in place.

### Security/privacy tests

- audit logs omit raw prices/source rows;
- model prose cannot change structured facts;
- reason/comment limits are enforced;
- tenant/scope mismatch is rejected;
- mock external action never sends a real request;
- approval attempt does not leak internal exception details.

## 16. Implementation order

1. Define decision input snapshot, recommendation, correction, approval and audit schemas.
2. Implement deterministic decision calculations and result hashing.
3. Implement recommendation construction from reconciliation facts.
4. Implement dependency-based impact/staleness propagation.
5. Implement append-only correction storage and validation.
6. Implement approval precondition policy.
7. Implement transactional approval/rejection/revocation services.
8. Add audit events and mock-action records.
9. Add optimistic-concurrency and idempotency protections.
10. Add unit, integration and adversarial tests.
11. Document reviewer capabilities, approval preconditions and demo limitations.
12. Run the full quality gate with a clean temporary database.

## 17. Explicitly out of scope for Phase Six

Do not implement:

- production authentication or identity administration;
- frontend API endpoints;
- external purchase/contract/message execution;
- automatic approval;
- model-based financial calculations;
- new ingestion formats;
- other markets' award rules;
- production deployment and operational scaling.

## Definition of done

Phase Six is complete when a reconciled France update produces an evidence-linked, versioned recommendation; affected previous approvals become stale without losing history; reviewers can submit validated corrections; approval succeeds only for the exact current recommendation/input/result hashes; stale or incomplete approvals are rejected; every decision is auditable; and all external actions remain drafts or mocks.

