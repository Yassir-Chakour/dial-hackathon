# Phase Five Implementation Plan: Agent Workflow

This document translates Phase Five of `GOALS.md` into an implementation plan.

Phase Five adds an orchestration layer around the deterministic ingestion and reconciliation services from Phases Two through Four. The agent should coordinate work, propose explanations and route exceptions, while code remains responsible for parsing, arithmetic, lineage, permissions and state changes.

## 1. Phase-five outcome

At the end of this phase, the backend should be able to:

- accept an update event and create a traceable workflow run;
- inspect source structure and determine which deterministic path is applicable;
- classify update mode without allowing model guesses to mutate data;
- call typed extraction, normalization, reconciliation and impact-analysis tools;
- produce a recommendation draft only from validated backend facts;
- collect evidence and structured exceptions;
- pause at a human-review boundary before approval or external action;
- resume safely after review;
- replay a workflow idempotently;
- record node status, inputs, outputs, failures and version references;
- enforce timeouts, budgets and retry policies;
- keep model prompts, outputs and source data within approved privacy boundaries.

The workflow must be auditable: a reviewer should be able to see what happened, which tools ran, which source version was used and why the workflow stopped.

## 2. Scope and boundaries

### Included

- LangGraph state definition;
- workflow graph and node boundaries;
- typed tool contracts;
- update intake and structure inspection;
- update-scope classification;
- deterministic service calls;
- recommendation draft generation from validated facts;
- evidence and exception collection;
- human-review pause/resume;
- workflow persistence and idempotency;
- tracing, safe logs and tests.

### Deferred

- real authentication and reviewer identity;
- final approval enforcement from Phase Six;
- frontend API endpoints from Phase Seven;
- external purchasing or messaging;
- background worker deployment;
- multi-market workflow specialization;
- autonomous tool selection with unrestricted model control;
- production model hosting and evaluation.

Phase Five may create a review request and a draft recommendation. It must not turn that draft into an approved purchase or contract action.

## 3. Recommended project structure

Extend the backend with:

```text
backend/
├── app/
│   ├── workflows/
│   │   ├── __init__.py
│   │   ├── state.py               # Typed graph state
│   │   ├── graph.py               # Graph construction
│   │   ├── nodes/
│   │   │   ├── intake.py
│   │   │   ├── inspect.py
│   │   │   ├── scope.py
│   │   │   ├── extract.py
│   │   │   ├── reconcile.py
│   │   │   ├── impact.py
│   │   │   ├── recommend.py
│   │   │   ├── evidence.py
│   │   │   └── review.py
│   │   ├── tools/
│   │   │   ├── contracts.py
│   │   │   ├── ingestion_tools.py
│   │   │   ├── reconciliation_tools.py
│   │   │   └── evidence_tools.py
│   │   ├── policies.py             # Budgets, allowed transitions, capabilities
│   │   └── checkpoints.py          # Run/checkpoint persistence adapter
│   ├── services/workflow_service.py
│   └── schemas/workflow.py
└── tests/workflows/
    ├── test_state.py
    ├── test_graph_routes.py
    ├── test_tools.py
    ├── test_review_pause.py
    ├── test_replay.py
    └── test_failures.py
```

Keep graph nodes thin. A node should validate state, call one bounded service/tool and return a typed state update. Business rules belong in domain services, not hidden inside prompts or graph callbacks.

## 4. Typed workflow state

Define a versioned state object. It should contain references and validated facts, not arbitrary conversation history:

```python
class WorkflowState(TypedDict):
    run_id: str
    event_id: str
    market: str
    source_file_id: str
    source_version_id: str | None
    previous_version_id: str | None
    parser_version: str | None
    workflow_version: str
    stage: WorkflowStage
    status: WorkflowStatus
    scope: UpdateScope | None
    ingestion_result_id: str | None
    reconciliation_result_id: str | None
    impact_summary: ImpactSummary | None
    recommendation_draft: RecommendationDraft | None
    evidence_refs: list[EvidenceRef]
    issues: list[WorkflowIssue]
    review_request: ReviewRequest | None
    budgets: WorkflowBudgets
    idempotency_key: str
```

Rules:

- use explicit enums for stages and statuses;
- use immutable IDs for persisted objects;
- store facts as typed models;
- do not store secrets or raw source payloads in checkpoints;
- keep free-text model output separate from validated facts;
- include schema/workflow version so old runs can be resumed safely;
- use bounded lists and text lengths to prevent state growth.

Possible stages:

```text
received
inspected
scoped
ingested
reconciled
impacted
drafted
awaiting_review
completed
failed
needs_review
```

## 5. Graph topology

Use a mostly linear graph with explicit exception branches:

```text
intake
  -> inspect_structure
  -> classify_scope
  -> ingest_records
  -> reconcile_versions
  -> analyze_impact
  -> collect_evidence
  -> draft_recommendation
  -> human_review
       |-- correction/retry -> revalidate -> reconcile_versions
       |-- reject ----------> completed/rejected
       |-- approve ---------> hand off to Phase Six
       |-- missing evidence -> needs_review
```

The graph should never route directly from model output to an external action. Every branch must pass through typed validation and policy checks.

Conditional edges should depend on structured state fields, not string matching on model text. For example:

- `scope.confidence == "high"`;
- `reconciliation.status == "accepted"`;
- `issues.has_blocking_errors is false`;
- `review_request.required is true`.

## 6. Node responsibilities

### Intake node

- validate event ID, source version reference and idempotency key;
- load the source/version metadata;
- reject missing or conflicting identifiers;
- create or resume a workflow run;
- establish budgets and workflow version;
- never accept raw filesystem paths or arbitrary tool URLs.

### Structure inspection node

- call the Phase Three reader/header services;
- report representation, row count, sections, candidate headers and parser warnings;
- persist an inspection result;
- stop for review when structure is ambiguous or limits are exceeded.

### Scope classification node

- use deterministic France rules first;
- allow a model to propose a scope only when rules cannot classify it, if such fallback is explicitly enabled;
- require scope evidence and confidence;
- compare the proposed scope to allowed market/update modes;
- never apply scope based only on unverified prose.

The model may suggest `replacement`, `addition` or `correction`; a deterministic validator must accept or reject it.

### Ingestion node

- call the Phase Three ingestion service;
- persist canonical records, validation statuses and review items;
- return only IDs and typed summaries in workflow state;
- route invalid or ambiguous records to review;
- do not duplicate parsing logic inside the node.

### Reconciliation node

- call the Phase Four reconciliation service;
- validate previous/incoming versions and scope;
- produce a change set and result hash;
- stop on mismatch, conflict or incomplete evidence;
- never ask the model to calculate totals.

### Impact-analysis node

- identify changed records and downstream recommendations affected by them;
- use persisted evidence and deterministic dependency queries;
- mark affected findings as requiring review;
- return structured impact facts and evidence references.

### Evidence node

- collect source file/version/row references;
- verify that every important change and fact has a source link;
- detect stale or missing evidence;
- avoid copying full source rows into prompts or logs unnecessarily.

### Recommendation-draft node

- receive only validated facts, change sets, approved assumptions and evidence references;
- produce a typed draft containing facts, uncertainties, suggested next action and citations;
- keep model-generated explanation separate from deterministic calculations;
- refuse to invent missing values or claim approval.

### Human-review node

- create a persisted review request;
- pause before approval or any external action;
- resume only from a stored checkpoint and a typed reviewer decision;
- re-run validation/reconciliation after a correction;
- never let a reviewer decision silently change the source version.

## 7. Tool contracts

Every tool should have a narrow input/output schema and an explicit capability policy.

Example:

```python
class ReconcileInput(BaseModel):
    previous_version_id: str
    incoming_version_id: str
    scope: UpdateScope
    event_id: str

class ReconcileOutput(BaseModel):
    reconciliation_id: str
    status: Literal["accepted", "needs_review", "rejected"]
    current_version_id: str | None
    change_set_id: str | None
    result_hash: str
    issue_ids: list[str]
```

Tool requirements:

- validate inputs with Pydantic;
- use allowlisted service functions;
- return typed outputs only;
- include source/version/result IDs;
- be deterministic where possible;
- be idempotent by event and input hash;
- enforce timeouts and record duration;
- never expose database sessions, filesystem paths or secrets to model tools;
- return safe errors with stable codes.

The model should not receive a generic “execute Python” or unrestricted database tool.

## 8. Model authority policy

Use the model for interpretation and communication, not authority:

### Model may

- summarize validated facts;
- propose a scope when configured as a fallback;
- identify a likely review reason;
- draft an explanation citing supplied evidence;
- suggest which deterministic tool should run next from an allowlist.

### Model may not

- write directly to the database;
- select arbitrary files or URLs;
- change source/version status;
- bypass schema validation;
- change totals, currency, units or identity;
- approve a recommendation;
- send a purchase, contract or external message;
- treat an invoice instruction as a system instruction;
- claim evidence that was not supplied.

All tool calls and model proposals must be checked by the workflow policy layer.

## 9. Human-review pause and resume

Persist a review request with:

- run ID and checkpoint ID;
- exact source/incoming/current version IDs;
- blocking issue IDs;
- affected record IDs;
- evidence references;
- allowed reviewer actions;
- expiration or stale-check metadata;
- workflow and policy version.

Allowed actions should be explicit:

```text
correct_record
accept_scope
reject_scope
request_more_evidence
reject_update
continue_to_approval_phase
```

When a correction is submitted:

1. validate the correction against the record schema;
2. store it as a new correction, never overwrite raw source data;
3. create a new calculation/reconciliation input hash;
4. re-run affected deterministic steps;
5. invalidate the prior draft if facts changed;
6. create a new review checkpoint.

A paused workflow must not resume against a newer source/version without detecting the change and requiring revalidation.

## 10. Idempotency, retries and budgets

Use the Phase Two event key plus a workflow-run key:

```text
workflow_run_key = event_id + workflow_version + input_fingerprint
```

For replay:

- return the existing completed result for the same key and fingerprint;
- resume an incomplete run from its latest safe checkpoint;
- reject the same key with a different input fingerprint;
- do not repeat irreversible actions.

Classify steps:

- safe retry: read-only inspection, deterministic parsing, evidence lookup;
- retry with idempotency: persistence and reconciliation;
- no automatic retry: human decisions and future external actions.

Budgets should include:

- maximum graph steps;
- maximum model calls;
- maximum tool calls per type;
- maximum source rows/bytes;
- maximum wall-clock duration;
- maximum prompt and response tokens;
- maximum checkpoint/state size.

When a budget is exceeded, create a structured exception and pause/fail safely. Do not loop until a model produces an answer.

## 11. State and checkpoint persistence

Store checkpoint metadata and typed state references through the Phase Two persistence boundary. Avoid storing complete raw files or sensitive source rows in every checkpoint.

Persist:

- run ID and event ID;
- workflow version and schema version;
- node/stage;
- status;
- input/result hashes;
- source/version/reconciliation IDs;
- issue and review IDs;
- retry count and timestamps;
- safe error code;
- checkpoint payload only after redaction and size validation.

Checkpoint writes should be transactional with state transitions. A node is not complete until its output and status are persisted.

## 12. Security and privacy

### Security controls

- Use an allowlist for nodes, tools, model endpoints and model names.
- Keep provider tokens server-side and redact them from traces.
- Apply network timeouts and response-size limits to model calls.
- Do not permit user-supplied URLs or arbitrary tool arguments.
- Treat source documents and model outputs as untrusted content.
- Defend against prompt injection: source text must be passed as data, never as higher-priority instructions.
- Revalidate authorization at resume time, not only when the workflow starts.
- Prevent confused-deputy behavior by binding every tool call to the current run, tenant and permitted source scope.
- Protect checkpoints and review data as sensitive operational records.
- Do not expose internal graph state or stack traces through API responses.
- Record policy denials and unsafe tool attempts as security events without logging payload contents.

### Privacy controls

- Send the smallest necessary validated excerpt to a model.
- Prefer IDs, summaries and evidence references over full source rows.
- Do not send raw source files to a model by default.
- Do not include supplier pricing, personal data or credentials in traces.
- Define provider retention and training policies before enabling external models.
- Keep synthetic-data labels visible in drafts and review records.
- Provide a deletion/redaction strategy for workflow runs before real data is accepted.
- Enforce tenant filtering in every checkpoint, evidence and review query.

## 13. Observability

Record structured workflow events:

- run ID, event ID and request ID;
- workflow/node/version;
- start/end time and duration;
- status and safe error code;
- tool name and result ID;
- input/result hashes;
- retry count;
- model name and token/latency metrics when allowed;
- review pause/resume events.

Never record raw prompts, full model responses or raw source rows by default. If temporary debug capture is required, make it opt-in, access-controlled, time-limited and redacted.

Useful metrics:

- workflow success/failure rate;
- runs paused for review;
- scope-classification ambiguity rate;
- reconciliation rejection rate;
- average node/tool duration;
- retry and timeout counts;
- model proposal acceptance rate;
- evidence completeness rate.

## 14. Reusable policies and helpers

Create reusable functions/policies:

- `create_or_resume_workflow(event_id, input_fingerprint)`;
- `validate_workflow_transition(current, next)`;
- `enforce_budget(state, operation)`;
- `authorize_tool_call(state, tool_name, args)`;
- `redact_workflow_state(state)`;
- `build_evidence_context(ids)`;
- `validate_model_proposal(proposal)`;
- `route_on_structured_status(state)`;
- `persist_checkpoint(state)`;
- `resume_from_checkpoint(run_id)`;
- `compute_workflow_input_fingerprint(state)`;
- `build_safe_model_prompt(facts, evidence)`.

Keep these independent of the specific France rules so future markets can reuse the workflow shell.

## 15. Testing strategy

### State and graph tests

- valid state transitions follow the expected graph;
- invalid transitions fail safely;
- conditional routes use structured fields;
- every node returns schema-valid state;
- graph version is persisted;
- incomplete runs resume from a checkpoint.

### Tool tests

- invalid tool inputs are rejected;
- tools cannot access arbitrary URLs or files;
- deterministic tools return stable result hashes;
- duplicate tool calls are idempotent;
- tool failures return safe structured errors;
- model output cannot directly mutate persistence.

### Workflow tests

- France event runs through intake, inspection, ingestion and reconciliation;
- ambiguous scope pauses for review;
- repeated invoice totals do not affect reconciliation;
- reconciliation mismatch stops before drafting;
- evidence gaps create a review issue;
- recommendation draft cites only supplied facts;
- reviewer correction triggers revalidation;
- stale checkpoint detects changed input version;
- duplicate workflow event produces one result.

### Security/privacy tests

- tokens and raw source data are absent from logs;
- prompt-injection text in a source row cannot change node policy;
- model endpoint timeout fails safely;
- state and checkpoint size limits are enforced;
- tenant/source-scope mismatch is rejected;
- unsafe tool attempts are logged as safe security events.

## 16. Implementation order

1. Define workflow status/stage, issue, review and checkpoint schemas.
2. Add the typed `WorkflowState` and workflow version.
3. Create tool contracts and capability policies.
4. Implement intake and structure-inspection nodes.
5. Connect deterministic ingestion and reconciliation services.
6. Implement scope fallback and validation with explicit review routing.
7. Add impact analysis and evidence collection.
8. Add recommendation draft generation from validated facts only.
9. Add persisted human-review pause/resume.
10. Add idempotency, budgets, retries and checkpoint persistence.
11. Add structured workflow logs and safe metrics.
12. Test full France flow, replay, failure, injection and review cases.
13. Document which model/provider capabilities are optional and simulated.

## 17. Explicitly out of scope for Phase Five

Do not implement:

- final approval authorization;
- external purchasing, contract or notification actions;
- frontend review endpoints;
- authentication/identity provider integration;
- production worker queues;
- unrestricted autonomous agents;
- model training or benchmark claims;
- other markets' specialized rules;
- OCR or new source formats.

## Definition of done

Phase Five is complete when a France update can run through a typed, checkpointed workflow; deterministic tools perform ingestion, reconciliation and evidence work; the model can only propose bounded explanations or classifications; ambiguity and failures pause safely; a reviewer can resume the run; duplicate events are idempotent; and logs, checkpoints and model calls meet the defined security and privacy boundaries.

