"""Top-level workflow orchestration service managing runs, checkpoints, and replay idempotency."""

from typing import Any
from sqlalchemy.orm import Session

from app.db.models import WorkflowRun
from app.persistence import EventRepository
from app.schemas.workflow import ResumeWorkflowRequest, StartWorkflowRequest, WorkflowRunResponse
from app.workflows.checkpoints import CheckpointAdapter
from app.workflows.graph import WorkflowGraphRunner
from app.workflows.policies import compute_workflow_fingerprint
from app.workflows.state import (
    WORKFLOW_VERSION,
    WorkflowBudgets,
    WorkflowState,
)


class WorkflowService:
    """Coordinates agent workflow runs with transactional checkpoints and event idempotency."""

    def __init__(
        self,
        checkpoints: CheckpointAdapter | None = None,
        events: EventRepository | None = None,
        runner: WorkflowGraphRunner | None = None,
    ) -> None:
        self.checkpoints = checkpoints or CheckpointAdapter()
        self.events = events or EventRepository()
        self.runner = runner or WorkflowGraphRunner(self.checkpoints)

    def start_workflow(
        self,
        session: Session,
        request: StartWorkflowRequest,
    ) -> WorkflowRunResponse:
        """Start a new workflow run or idempotently replay an existing completed/paused run."""
        from app.db.models import SourceFile

        source_file = session.get(SourceFile, request.source_file_id)
        if source_file is None:
            return WorkflowRunResponse(
                run_id="failed-init",
                event_id="none",
                market=request.market,
                stage="failed",
                status="failed",
                workflow_version=WORKFLOW_VERSION,
                issues=[
                    {
                        "code": "source_file_not_found",
                        "message": f"Source file {request.source_file_id} does not exist.",
                        "severity": "error",
                        "node": "intake",
                    }
                ],
            )

        fingerprint = compute_workflow_fingerprint(
            request.event_key, request.market, request.source_file_id, WORKFLOW_VERSION
        )

        event_result = self.events.create_or_get_event(
            session,
            event_key=request.event_key,
            payload_hash=fingerprint,
            event_type="workflow.orchestrate",
            tenant_id=request.tenant_id,
            source_file_id=request.source_file_id,
        )

        run, replayed = self.checkpoints.create_or_get_run(
            session,
            event_id=event_result.event.id,
            market=request.market,
            input_fingerprint=fingerprint,
            source_file_id=request.source_file_id,
            tenant_id=request.tenant_id,
        )

        if replayed or event_result.replayed:
            latest_chk = self.checkpoints.get_latest_checkpoint(session, run.id)
            chk_state: dict[str, Any] = latest_chk.state_json if latest_chk else {}
            return self._build_response(run, chk_state, replayed=True)

        initial_state: WorkflowState = {
            "run_id": run.id,
            "event_id": event_result.event.id,
            "tenant_id": request.tenant_id,
            "market": request.market,
            "source_file_id": request.source_file_id,
            "source_version_id": None,
            "previous_version_id": request.previous_version_id,
            "parser_version": "france-fixture-ingestion-pipeline",
            "workflow_version": WORKFLOW_VERSION,
            "stage": "received",
            "status": "running",
            "scope": None,
            "ingestion_result_id": None,
            "reconciliation_result_id": None,
            "impact_summary": None,
            "recommendation_draft": None,
            "evidence_refs": [],
            "issues": [],
            "review_request": None,
            "budgets": WorkflowBudgets(),
            "idempotency_key": request.event_key,
            "history": [],
        }

        final_state = self.runner.run(session, initial_state)
        session.flush()

        # Update run model
        run.stage = final_state["stage"]
        run.status = final_state["status"]
        if final_state.get("source_version_id"):
            run.source_version_id = final_state.get("source_version_id")
        if final_state.get("previous_version_id"):
            run.previous_version_id = final_state.get("previous_version_id")

        return self._build_response(run, final_state, replayed=False)

    def resume_workflow(
        self,
        session: Session,
        request: ResumeWorkflowRequest,
    ) -> WorkflowRunResponse:
        """Resume a paused workflow run after human review or correction."""
        run = session.get(WorkflowRun, request.run_id)
        if run is None:
            raise ValueError(f"Workflow run {request.run_id} not found.")

        latest_chk = self.checkpoints.get_latest_checkpoint(session, run.id)
        if latest_chk is None:
            raise ValueError(f"No checkpoint available to resume run {request.run_id}.")

        state = self._hydrate_state(run, latest_chk.state_json)
        final_state = self.runner.resume(
            session,
            state,
            action=request.action,
            correction_payload=request.correction_payload,
        )
        session.flush()

        run.stage = final_state["stage"]
        run.status = final_state["status"]

        return self._build_response(run, final_state, replayed=False)

    def _build_response(
        self,
        run: WorkflowRun,
        state: dict[str, Any] | WorkflowState,
        replayed: bool,
    ) -> WorkflowRunResponse:
        rec_draft = state.get("recommendation_draft")
        rec_draft_dict: dict[str, Any] | None = None
        if isinstance(rec_draft, dict):
            rec_draft_dict = rec_draft
        elif hasattr(rec_draft, "__dict__"):
            rec_draft_dict = dict(rec_draft.__dict__)

        review_req = state.get("review_request")
        review_req_dict: dict[str, Any] | None = None
        if isinstance(review_req, dict):
            review_req_dict = review_req
        elif hasattr(review_req, "__dict__"):
            review_req_dict = dict(review_req.__dict__)

        raw_issues = state.get("issues", [])
        issues_data: list[dict[str, Any]] = [
            iss.__dict__ if hasattr(iss, "__dict__") else dict(iss)  # type: ignore[arg-type]
            for iss in raw_issues
        ]

        return WorkflowRunResponse(
            run_id=run.id,
            event_id=run.event_id,
            market=run.market,
            stage=run.stage,
            status=run.status,
            workflow_version=run.workflow_version,
            source_version_id=run.source_version_id,
            reconciliation_result_id=state.get("reconciliation_result_id"),
            recommendation_draft=rec_draft_dict,
            review_request=review_req_dict,
            issues=issues_data,
            replayed=replayed,
        )

    def _hydrate_state(self, run: WorkflowRun, state_json: dict[str, Any]) -> WorkflowState:
        # Reconstruct typed WorkflowState safely from checkpoint JSON
        budgets_data = state_json.get("budgets", {})
        budgets = WorkflowBudgets(
            step_limit=budgets_data.get("step_limit", 20),
            current_steps=budgets_data.get("current_steps", 0),
            max_tool_calls=budgets_data.get("max_tool_calls", 10),
            current_tool_calls=budgets_data.get("current_tool_calls", 0),
            max_model_calls=budgets_data.get("max_model_calls", 5),
            current_model_calls=budgets_data.get("current_model_calls", 0),
            max_duration_seconds=budgets_data.get("max_duration_seconds", 60.0),
        )

        stage_val = state_json.get("stage", run.stage)
        status_val = state_json.get("status", run.status)

        return {
            "run_id": run.id,
            "event_id": run.event_id,
            "tenant_id": run.tenant_id,
            "market": run.market,
            "source_file_id": run.source_file_id or "",
            "source_version_id": run.source_version_id,
            "previous_version_id": run.previous_version_id,
            "parser_version": state_json.get("parser_version"),
            "workflow_version": run.workflow_version,
            "stage": stage_val,
            "status": status_val,
            "scope": None,
            "ingestion_result_id": state_json.get("ingestion_result_id"),
            "reconciliation_result_id": state_json.get("reconciliation_result_id"),
            "impact_summary": None,
            "recommendation_draft": None,
            "evidence_refs": state_json.get("evidence_refs", []),
            "issues": [],
            "review_request": None,
            "budgets": budgets,
            "idempotency_key": state_json.get("idempotency_key", run.id),
            "history": state_json.get("history", []),
        }
