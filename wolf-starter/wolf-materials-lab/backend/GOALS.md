# Wolf Materials Lab Backend Goals

## Product goal

Build a procurement decision agent that can receive a new supplier source file, understand what changed, recalculate the affected purchasing decision, preserve evidence and version lineage, and require a human to approve the new result before it becomes current.

The first complete implementation focuses on the France replacement-supplier scenario. The architecture must remain extensible to the other supplied market update scenarios.

## Core capabilities

- Receive CSV and spreadsheet source files through an API.
- Preserve the original file, source version, file hash and source metadata.
- Extract rows without losing source row numbers or duplicate-header context.
- Normalize dates, currencies, units, suppliers, products and signed values.
- Distinguish line values, invoice totals, credits, cancellations and headers.
- Apply the correct update scope instead of adding every version together.
- Preserve unaffected records when a supplier subset is replaced.
- Detect duplicate events and make replay idempotent.e
- Compare the previous and incoming versions.
- Calculate the updated purchasing recommendation deterministically.
- Link every important result to source-file and source-row evidence.
- Explain why a recommendation changed using validated backend facts.
- Mark approvals based on previous versions as stale.
- Allow a reviewer to correct an ambiguous record.
- Require approval of the exact current version.
- Reject approval when evidence or required validation is incomplete.
- Expose review state, exceptions and lineage to the frontend.
- Keep external purchasing or contract actions as drafts or mocks.

## Development phases

### Phase 1: Backend foundation

- Establish the FastAPI application.
- Define configuration and environment handling.
- Define Pydantic request and response schemas.
- Establish the Poetry project and reproducible dependency lockfile.
- Add health and readiness endpoints.
- Define consistent error responses and logging boundaries.

### Phase 2: Data and persistence foundation

- Configure SQLite for local development.
- Define database models and repositories.
- Store source files, versions and hashes.
- Store normalized source records.
- Store workflow events and processing status.
- Store recommendations, evidence links, corrections and approvals.

### Phase 3: France ingestion engine

- Read the supplied France source fixture.
- Support the raw row and CSV representations.
- Preserve source row references and original values.
- Detect the France replacement-supplier update mode.
- Normalize products, suppliers, quantities, units, dates and prices.
- Handle negative cancellation values.
- Ignore repeated invoice header totals when calculating line totals.
- Validate required fields and route ambiguous records to review.

### Phase 4: Versioning and reconciliation

- Load the previous France version.
- Apply the incoming supplier-subset replacement correctly.
- Preserve unrelated France suppliers and records.
- Calculate previous, incoming and current totals.
- Reconcile totals against expected fixture outcomes.
- Produce a structured change set.
- Track superseded and accepted records.
- Make processing idempotent using event keys and file hashes.

### Phase 5: Agent workflow

- Define the LangGraph state model.
- Add update intake and structure inspection nodes.
- Add update-scope classification.
- Add deterministic extraction and normalization tools.
- Add reconciliation and impact-analysis tools.
- Add recommendation generation from validated facts.
- Add evidence collection and exception reporting.
- Add a human-review pause before approval.
- Ensure the model proposes explanations while code verifies calculations.

### Phase 6: Procurement decision and approval

- Create versioned recommendations.
- Identify recommendations affected by a source update.
- Mark previous approvals as stale.
- Expose the changed records and reasons.
- Support reviewer corrections.
- Recalculate after a correction.
- Approve only the current recommendation version.
- Reject stale or incomplete approvals.
- Preserve reviewer, timestamp, version and correction history.

### Phase 7: API layer

- Add source import endpoints.
- Add current and historical recommendation endpoints.
- Add evidence and lineage endpoints.
- Add correction endpoints.
- Add approval and rejection endpoints.
- Add event replay endpoints.
- Add exception and review-queue endpoints.
- Return stable typed JSON contracts for the frontend.

### Phase 8: Frontend integration

- Add a France update workflow screen.
- Show the current recommendation and previous version.
- Show what changed and what was preserved.
- Show the evidence source file and row references.
- Show the event and version timeline.
- Show stale approval status.
- Add reviewer correction controls.
- Add approve and reject actions.
- Show explicit synthetic-data and simulated-workflow labels.

### Phase 9: Verification and adversarial cases

- Test full France v1 to v2 replacement behavior.
- Test duplicate event replay.
- Test repeated invoice totals.
- Test cancellation handling.
- Test unrelated supplier preservation.
- Test missing product or supplier references.
- Test ambiguous records and human review.
- Test stale approval rejection.
- Test corrected recommendation approval.
- Test evidence references for every changed result.

### Phase 10: Extensibility and production readiness

- Generalize update modes for Italy, Hungary and Kosovo.
- Support real uploaded XLSX files.
- Move from SQLite to PostgreSQL when required.
- Add durable LangGraph checkpoints.
- Add authentication and reviewer identity.
- Add object storage for source files.
- Add background processing and retries.
- Add audit logging and observability.
- Add tenant and permission boundaries.
- Add controlled integrations with real procurement systems.

## Definition of success

The backend succeeds when a reviewer can see that a France source update changed a purchasing decision, understand exactly why it changed, inspect the supporting source rows, correct an ambiguous record, approve the new version, and replay the same update without changing the result or double-counting the data.
