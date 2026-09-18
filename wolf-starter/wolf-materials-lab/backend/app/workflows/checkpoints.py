from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import WorkflowCheckpoint, WorkflowRun
from app.workflows.policies import redact_workflow_state
from app.workflows.state import WORKFLOW_VERSION, WorkflowState


class CheckpointAdapter:
    """Manages transactional persistence for workflow state snapshots."""

    def create_or_get_run(
        self,
        session: Session,
        *,
        event_id: str,
        market: str,
        input_fingerprint: str,
        source_file_id: str | None = None,
        tenant_id: str | None = None,
    ) -> tuple[WorkflowRun, bool]:
        existing = session.scalar(select(WorkflowRun).where(WorkflowRun.event_id == event_id))
        if existing:
            return existing, True

        run = WorkflowRun(
            event_id=event_id,
            tenant_id=tenant_id,
            market=market,
            status="running",
            stage="received",
            workflow_version=WORKFLOW_VERSION,
            input_fingerprint=input_fingerprint,
            source_file_id=source_file_id,
        )
        session.add(run)
        session.flush()
        return run, False

    def save_checkpoint(
        self,
        session: Session,
        *,
        run_id: str,
        step_index: int,
        node_name: str,
        stage: str,
        status: str,
        state: WorkflowState,
    ) -> WorkflowCheckpoint:
        from sqlalchemy import func

        last_step = session.scalar(
            select(func.max(WorkflowCheckpoint.step_index)).where(WorkflowCheckpoint.run_id == run_id)
        )
        actual_step = (last_step or 0) + 1

        redacted = redact_workflow_state(dict(state))
        checkpoint = WorkflowCheckpoint(
            run_id=run_id,
            step_index=actual_step,
            node_name=node_name,
            stage=stage,
            status=status,
            state_json=redacted,
        )
        session.add(checkpoint)

        run = session.get(WorkflowRun, run_id)
        if run:
            run.stage = stage
            run.status = status
            if state.get("source_version_id"):
                run.source_version_id = state.get("source_version_id")
            if state.get("previous_version_id"):
                run.previous_version_id = state.get("previous_version_id")

        session.flush()
        return checkpoint

    def get_latest_checkpoint(self, session: Session, run_id: str) -> WorkflowCheckpoint | None:
        return session.scalar(
            select(WorkflowCheckpoint)
            .where(WorkflowCheckpoint.run_id == run_id)
            .order_by(WorkflowCheckpoint.step_index.desc())
        )
