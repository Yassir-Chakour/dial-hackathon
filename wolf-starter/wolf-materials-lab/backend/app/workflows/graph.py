"""Workflow graph execution engine with state transitions, budgets, and step checkpointing."""

from typing import Any, Callable
from sqlalchemy.orm import Session

from app.workflows.checkpoints import CheckpointAdapter
from app.workflows.nodes.evidence import evidence_node
from app.workflows.nodes.extract import extract_node
from app.workflows.nodes.impact import impact_node
from app.workflows.nodes.inspect import inspect_node
from app.workflows.nodes.intake import intake_node
from app.workflows.nodes.reconcile import reconcile_node
from app.workflows.nodes.recommend import recommend_node
from app.workflows.nodes.review import review_node
from app.workflows.nodes.scope import scope_node
from app.workflows.state import WorkflowIssue, WorkflowState

NodeCallable = Callable[[Session, WorkflowState], dict[str, Any]]

NODE_SEQUENCE: list[tuple[str, NodeCallable]] = [
    ("intake", intake_node),
    ("inspect", inspect_node),
    ("scope", scope_node),
    ("extract", extract_node),
    ("reconcile", reconcile_node),
    ("impact", impact_node),
    ("evidence", evidence_node),
    ("recommend", recommend_node),
    ("review", review_node),
]


class WorkflowGraphRunner:
    """Executes workflow stages sequentially, respecting exception branches and budgets."""

    def __init__(self, checkpoints: CheckpointAdapter | None = None) -> None:
        self.checkpoints = checkpoints or CheckpointAdapter()

    def run(self, session: Session, state: WorkflowState) -> WorkflowState:
        current_state: WorkflowState = dict(state)  # type: ignore[assignment]

        for node_name, node_func in NODE_SEQUENCE:
            # If current stage or status dictates halt, stop executing
            if current_state["status"] in {"paused", "completed", "failed", "needs_review"}:
                break

            # Execute node
            try:
                updates = node_func(session, current_state)
                current_state.update(updates)  # type: ignore[typeddict-item]
            except Exception as exc:
                current_state["status"] = "failed"
                current_state["stage"] = "failed"
                issues = list(current_state.get("issues", []))
                issues.append(
                    WorkflowIssue(
                        code="node_execution_exception",
                        message=f"Node {node_name} encountered an unhandled exception: {exc}",
                        severity="error",
                        node=node_name,
                    )
                )
                current_state["issues"] = issues

            # Save checkpoint after every node execution
            budgets = current_state["budgets"]
            self.checkpoints.save_checkpoint(
                session,
                run_id=str(current_state["run_id"]),
                step_index=budgets.current_steps,
                node_name=node_name,
                stage=str(current_state["stage"]),
                status=str(current_state["status"]),
                state=current_state,
            )

        return current_state

    def resume(
        self,
        session: Session,
        state: WorkflowState,
        action: str,
        correction_payload: dict[str, Any] | None = None,
    ) -> WorkflowState:
        """Resume a paused workflow after a reviewer decision."""
        current_state: WorkflowState = dict(state)  # type: ignore[assignment]

        if current_state["status"] not in {"paused", "needs_review"}:
            raise ValueError(f"Cannot resume workflow in status {current_state['status']}.")

        if action in {"continue_to_approval_phase", "accept_scope"}:
            current_state["status"] = "completed"
            current_state["stage"] = "completed"
        elif action == "reject_update":
            current_state["status"] = "failed"
            current_state["stage"] = "failed"
        elif action == "correct_record":
            # Re-enter reconciliation and drafting stages
            current_state["status"] = "running"
            current_state["stage"] = "reconciled"
            # Re-run from reconcile node onwards
            reconcile_index = next(i for i, (name, _) in enumerate(NODE_SEQUENCE) if name == "reconcile")
            for node_name, node_func in NODE_SEQUENCE[reconcile_index:]:
                if current_state["status"] in {"paused", "completed", "failed", "needs_review"}:
                    break
                updates = node_func(session, current_state)
                current_state.update(updates)  # type: ignore[typeddict-item]
                budgets = current_state["budgets"]
                self.checkpoints.save_checkpoint(
                    session,
                    run_id=str(current_state["run_id"]),
                    step_index=budgets.current_steps,
                    node_name=node_name,
                    stage=str(current_state["stage"]),
                    status=str(current_state["status"]),
                    state=current_state,
                )
        else:
            raise ValueError(f"Unsupported resume action: {action}")

        budgets = current_state["budgets"]
        self.checkpoints.save_checkpoint(
            session,
            run_id=str(current_state["run_id"]),
            step_index=budgets.current_steps,
            node_name="resume",
            stage=str(current_state["stage"]),
            status=str(current_state["status"]),
            state=current_state,
        )

        return current_state
