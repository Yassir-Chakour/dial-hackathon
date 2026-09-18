# Phase Six reviewer and approval notes

Phase Six creates immutable decision input snapshots and recommendation versions. A reviewer approves only by sending the opaque recommendation ID, the current result hash, the current input hash, the expected optimistic-concurrency version, a bounded reason, and a request ID.

Approval is server-side policy. The stored recommendation must still be current, its source/reconciliation version must be accepted, evidence must be complete, blocking issues must be absent, the reviewer must have the `approve` capability, and no newer version may exist. Client-provided status fields are ignored. Any changed input or concurrent write returns a stable policy error and does not commit an approval.

Drafting, reviewing, and approving are separate capabilities in the domain contract. Reviewer identity is stored as an opaque reference. The current implementation does not provide production authentication or role administration, so callers must supply an authorization result to the policy service until Phase Seven/identity work integrates it.

Corrections are append-only and validated against the same domain rules as source facts. Corrections that change market, ownership, currency, or unit semantics require reconciliation and cannot directly authorize approval. Source rows are never edited.

External procurement, contract, and notification operations are mock-only. An approved decision can create a `procurement_draft` mock action with `external_send: false`; no network request, purchase, award, contract update, or notification is performed.

All decision, correction, staleness, approval, rejection, revocation, and mock-action events are auditable without copying raw supplier prices or source rows into routine audit data. Synthetic-data labels remain the responsibility of the source/draft caller and are not removed by decision processing.
