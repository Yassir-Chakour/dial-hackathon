# Phase Eight Implementation Plan: Frontend Integration

This document translates Phase Eight of GOALS.md into an implementation plan.

Phase Eight connects the stable Phase Seven API to the supplied frontend. The goal is a reviewable France update workflow in which a buyer can inspect the old and new versions, understand what changed, inspect evidence, correct an ambiguous record, and approve or reject the exact current recommendation version.

The frontend must present backend facts and states faithfully. It must not calculate authoritative totals, decide approval eligibility, or hide uncertainty.

## 1. Phase-eight outcome

The frontend should be able to:

- start or inspect a France source update;
- show workflow processing status;
- compare previous and incoming/current versions;
- show preserved, added, replaced and removed records;
- show source file, version, sheet and row evidence;
- show the event/version timeline;
- show stale approval status and the reason;
- present review exceptions and ambiguous records;
- submit a validated correction;
- show recalculation progress and the new recommendation version;
- approve or reject only when the backend says the action is allowed;
- show clear synthetic-data and simulated-workflow labels;
- handle loading, errors, conflicts and stale data safely.

The frontend should support a convincing demo without pretending that authentication, persistence, model access or external procurement actions are already production capabilities.

## 2. Scope and boundaries

### Included

- typed API client for /api/v1;
- France update workflow screen;
- source/version and workflow status views;
- change-set comparison;
- evidence and lineage drawer;
- review queue and exception views;
- correction form;
- recommendation version and stale-state display;
- approve/reject controls;
- polling for asynchronous processing;
- frontend tests and accessibility checks.

### Deferred

- full product redesign;
- real identity provider UI;
- external procurement actions;
- websocket infrastructure;
- offline editing;
- multi-market workflow UI;
- replacing all existing synthetic dashboard data;
- client-side business calculations.

Use the existing frontend component system and navigation patterns. The new workflow should be a focused extension, not a parallel application.

## 3. Recommended frontend structure

Add a feature area consistent with the current app:

```text
frontend/src/
├── app/
│   └── dashboard/
│       └── france-update/
│           └── page.tsx
├── api/
│   ├── client.ts
│   ├── types.ts
│   ├── sources.ts
│   ├── workflows.ts
│   ├── recommendations.ts
│   ├── evidence.ts
│   └── reviews.ts
├── sections/
│   └── france-update/
│       ├── view.tsx
│       ├── update-header.tsx
│       ├── version-compare.tsx
│       ├── change-set-table.tsx
│       ├── evidence-drawer.tsx
│       ├── workflow-timeline.tsx
│       ├── review-queue.tsx
│       ├── correction-form.tsx
│       ├── recommendation-card.tsx
│       └── approval-panel.tsx
├── hooks/
│   ├── use-france-update.ts
│   ├── use-workflow-status.ts
│   └── use-recommendation.ts
└── lib/
    ├── api-errors.ts
    ├── formatters.ts
    └── feature-flags.ts
```

Follow existing naming, routing, theme and UI component conventions. Keep API data types separate from display view models.

## 4. API client and typed contracts

Create one configured client for the backend base URL. It should:

- use the /api/v1 prefix;
- set a request timeout;
- attach request correlation metadata where supported;
- send idempotency keys for writes;
- send If-Match/version headers for corrections and approvals;
- parse the common error envelope;
- expose typed responses;
- never expose provider tokens or server settings to browser code.

Keep the client response types aligned with backend OpenAPI schemas. Do not duplicate backend calculation logic in TypeScript.

Recommended client operations:

- createSource/updateSource;
- getSource/getSourceVersions;
- processSourceVersion;
- getWorkflowRun/resumeWorkflow;
- listRecommendations/getRecommendation;
- getRecommendationChanges/getHistory;
- getEvidence/getLineage;
- createCorrection;
- approveRecommendation/rejectRecommendation;
- createReplay/getReplay;
- listExceptions/listReviewQueue/resolveReview.

Use a single error adapter that maps status/code to user-facing actions:

- conflict → refresh and compare current version;
- validation failed → show affected field/issue;
- processing → continue polling;
- unauthorized → request sign-in or show unavailable state;
- internal error → show request ID and safe retry action.

Do not display raw backend error messages when they could reveal internal data.

## 5. France update workflow

Design the primary screen around the decision journey:

```text
1. Update received
2. Processing/status
3. Scope and source evidence
4. What changed
5. What was preserved
6. Reconciliation result
7. Exceptions/review items
8. Recommendation draft
9. Correction/recalculation
10. Approve or reject current version
```

The screen should always show:

- synthetic-data notice;
- market and update mode;
- current workflow state;
- source/version identifiers in a human-readable form;
- last updated timestamp;
- stale indicator;
- whether values are measured, calculated, assumed or unavailable.

Do not make the reviewer navigate through unrelated dashboard screens to understand one update.

## 6. Version comparison view

Show previous, incoming and current states clearly.

Required sections:

- previous accepted version;
- incoming version and declared scope;
- current materialization;
- total/count summaries returned by the backend;
- change categories: added, replaced, preserved, removed from current;
- warnings and blocking issues;
- result/reconciliation status.

Every summary must be labelled as backend-reported. The frontend may format numbers but must not recompute authoritative totals.

For large change sets:

- show paginated rows;
- allow filters by change type, supplier, product and reason;
- keep filters bounded and URL-safe;
- show a compact summary first;
- lazy-load evidence and details.

## 7. Change-set table

Each row should display:

- change type;
- product/material;
- supplier;
- previous value;
- incoming/current value;
- unit/currency;
- reason code;
- validation status;
- evidence count;
- review status.

Use explicit visual states:

- added;
- replaced;
- preserved;
- removed from current;
- needs review;
- conflict;
- stale.

Do not use colour alone. Provide text, icons with labels and accessible status descriptions.

A row click opens evidence and lineage, not a free-form explanation generated solely by the frontend.

## 8. Evidence and lineage drawer

The evidence view should make source traceability understandable:

- source file name as safe display text;
- source hash or short fingerprint;
- source version;
- sheet/section;
- row number;
- column/field references;
- raw value only when the backend authorizes it;
- normalized value;
- transformation warning;
- related correction;
- supersession relationship.

Show the evidence relation: supports, changed by, preserved from or contradicts.

For missing or restricted evidence, show the reason and review action. Never show a blank field that could be mistaken for “no issue.”

Do not construct download paths from filenames or row numbers. Use backend-provided opaque evidence IDs and URLs.

## 9. Workflow timeline

Render workflow events in chronological order:

- source received;
- inspection completed;
- scope classified;
- ingestion completed;
- reconciliation completed;
- impact analysis;
- review requested;
- correction submitted;
- recalculation;
- approval/rejection;
- stale/revoked events.

Each event should include:

- human-readable label;
- timestamp;
- status;
- source/version/recommendation reference;
- safe reason;
- link to details where available.

Use polling for asynchronous processing with:

- bounded interval and maximum duration;
- paused/failed/complete states;
- retry/backoff;
- a visible “last checked” time;
- a stop condition when the user leaves the page.

Do not poll indefinitely or treat a timeout as success.

## 10. Review queue and exceptions

Create a review panel that separates:

- blocking exceptions;
- warnings;
- ambiguous records;
- scope decisions;
- reconciliation mismatches;
- stale recommendation notices.

Each item should show:

- severity;
- reason code;
- affected resource;
- source row/evidence count;
- current status;
- allowed actions;
- whether the item blocks approval.

A review item should never offer an action the backend would reject. Use the backend’s allowed-actions field to enable controls.

## 11. Correction form

The correction UI must be field-specific and evidence-first.

Display:

- original raw value;
- normalized value;
- field label;
- validation reason;
- acceptable format/unit;
- evidence references;
- correction impact warning.

On submit:

1. re-fetch or verify the current recommendation/input hash;
2. send an idempotency key;
3. send expected hash/version;
4. show a pending/recalculation state;
5. refresh the recommendation and change set;
6. invalidate stale local data;
7. show the new version/hash and any remaining issues.

The form must not allow editing the original source file or arbitrary JSON. Only backend-allowed fields may be corrected.

If the correction changes scope, identity, unit or currency, explain that reconciliation and approval may be required again.

## 12. Recommendation and approval panel

Show a versioned recommendation card containing:

- recommendation status;
- current version;
- input/result hashes in a compact inspectable form;
- deterministic facts;
- recurring savings/rebates/cost avoidance as separate categories;
- assumptions;
- uncertainties;
- affected items;
- evidence completeness;
- required review actions;
- stale reason if stale.

Approval controls:

- render only when backend says approval is allowed;
- show exact version being approved;
- require reviewer confirmation and bounded reason if configured;
- submit expected hashes and idempotency key;
- disable while request is pending;
- handle 409 conflicts by refreshing the current recommendation;
- show approval timestamp and audit reference on success.

Rejection should require a reason and preserve the recommendation history.

Never enable an Approve button merely because a local status says complete.

## 13. State management

Use a server-state library or a small, disciplined data-fetching layer consistent with the existing project.

Recommended principles:

- server data is the source of truth;
- cache keys include resource ID and version;
- invalidate recommendation/evidence/workflow queries after writes;
- do not cache raw source content longer than necessary;
- cancel requests when a component unmounts;
- handle stale-while-revalidate explicitly;
- keep form state separate from server state;
- preserve the user’s unsent correction locally only where safe.

Suggested query keys:

- source by source ID;
- versions by source ID;
- workflow by run ID;
- recommendation by ID/version;
- changes by recommendation ID/result hash;
- evidence by evidence ID;
- review queue by filters.

## 14. Loading, empty and failure states

Every screen needs explicit states:

- loading;
- empty;
- processing;
- needs review;
- stale;
- rejected;
- unauthorized;
- unavailable;
- conflict;
- complete.

Examples:

- no evidence is not the same as evidence still loading;
- no recommendation is not the same as recommendation rejected;
- stale approval is not the same as no approval;
- synthetic demo mode is not the same as live backend mode.

Show safe recovery actions such as refresh, retry processing, open review item or return to previous version. Include request IDs for support when an operation fails.

## 15. Security and privacy

### Security

- Keep backend tokens and model credentials out of frontend code, bundles and browser storage.
- Do not trust hidden UI controls as authorization; the backend remains authoritative.
- Escape source labels and reviewer comments before rendering.
- Do not render raw HTML or markdown from source files without sanitization.
- Avoid putting sensitive source values in URLs, query strings or analytics events.
- Clear sensitive local state on sign-out or tenant change.
- Do not cache restricted evidence in shared browser storage.
- Protect correction and approval forms against duplicate submission.
- Use CSRF protection if browser cookies are used.
- Show only backend-authorized actions.
- Maintain accessible focus and error states so users do not miss blocking review requirements.

### Privacy

- Show only the evidence fields needed for the current review.
- Redact restricted values according to backend response policy.
- Do not send source rows, supplier prices or reviewer comments to third-party analytics.
- Mark all supplied fixtures as synthetic.
- Do not persist raw source data in localStorage or URL state.
- Clear demo data when switching environments.
- Make download/export actions explicit and protected.

## 16. Accessibility and usability

The workflow is a review tool, so accessibility is a correctness requirement.

- Use semantic headings and table headers;
- provide keyboard access to row details and drawers;
- use text labels in addition to icons and colour;
- announce asynchronous status changes;
- associate validation errors with fields;
- preserve focus when dialogs open/close;
- support zoom and responsive layouts;
- provide readable currency, date and unit formatting;
- show exact values on demand, not only rounded summaries;
- keep source-row references copyable.

Test keyboard-only review, correction and approval flows.

## 17. Testing strategy

### API/client tests

- request/response schemas match OpenAPI;
- request IDs and common errors are mapped;
- idempotency keys are sent on writes;
- ETag/If-Match headers are sent;
- 409 conflicts trigger refresh;
- unauthorized/forbidden states do not show controls.

### Component tests

- previous/incoming/current versions render distinctly;
- change types and statuses are accessible without colour;
- evidence drawer shows row/sheet/column references;
- stale approvals show reason and block approval;
- correction form validates fields and refreshes after success;
- approval requires backend permission and exact hashes;
- review queue displays blocking vs warning items.

### End-to-end demo tests

- start with France v1;
- process the replacement update;
- show changed and preserved records;
- open evidence for a changed row;
- display a review exception;
- correct one record;
- show recalculated recommendation version;
- approve the current version;
- replay the event and show no double count;
- attempt stale approval and show a safe conflict.

### Security/privacy tests

- source labels are escaped;
- raw HTML is not rendered;
- sensitive values are absent from URLs/localStorage/analytics;
- duplicate clicks do not duplicate writes;
- restricted evidence is not shown;
- logout clears sensitive client state.

## 18. Implementation order

1. Add API base URL/configuration and typed client types.
2. Implement source/version/workflow data hooks.
3. Add the France update route and workflow header/status.
4. Add version comparison and change-set views.
5. Add evidence/lineage drawer and timeline.
6. Add review queue, exceptions and correction form.
7. Add recommendation version and approval/rejection panel.
8. Add polling, cache invalidation, conflicts and failure states.
9. Add synthetic/simulated labels and accessibility polish.
10. Add component, API-mock and end-to-end tests.
11. Verify the complete France demo path against the backend.
12. Document the local frontend/backend start commands and demo limitations.

## 19. Explicitly out of scope for Phase Eight

Do not implement:

- backend business logic in the browser;
- client-side approval authorization;
- real external purchase or contract execution;
- unrestricted raw-source downloads;
- multi-market workflows;
- production authentication UX;
- websocket infrastructure;
- replacement of all existing synthetic dashboard data.

## Definition of done

Phase Eight is complete when a reviewer can use the frontend to follow a France source update, inspect previous/incoming/current versions, understand changed and preserved records, open evidence and lineage, resolve an ambiguous record, see a new recommendation version, approve/reject the exact current version, and safely replay the event without double counting. Loading, conflicts, stale states, errors, synthetic-data labels, accessibility and privacy boundaries are all covered by tests.

