"""Workflow graph execution engine with state transitions, budgets, and step checkpointing."""

from typing import Any, Callable
from sqlalchemy.orm import Session
from langgraph.graph import END, START, StateGraph

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
    """Executes the workflow as a LangGraph state machine.

    The node implementations remain deterministic and database-backed; LangGraph
    provides the explicit state graph, routing, and a stable extension point for
    future model/tool nodes.
    """

    def __init__(self, checkpoints: CheckpointAdapter | None = None) -> None:
        self.checkpoints = checkpoints or CheckpointAdapter()

    def run(self, session: Session, state: WorkflowState) -> WorkflowState:
        graph = StateGraph(WorkflowState)

        for node_name, node_func in NODE_SEQUENCE:
            def execute_node(
                current_state: WorkflowState,
                *,
                _node_name: str = node_name,
                _node_func: NodeCallable = node_func,
            ) -> dict[str, Any]:
                if current_state["status"] in {"paused", "completed", "failed", "needs_review"}:
                    return {}
                try:
                    updates = _node_func(session, current_state)
                except Exception as exc:
                    updates = {
                        "status": "failed",
                        "stage": "failed",
                        "issues": [
                            *current_state.get("issues", []),
                            WorkflowIssue(
                                code="node_execution_exception",
                                message=f"Node {_node_name} encountered an unhandled exception: {exc}",
                                severity="error",
                                node=_node_name,
                            ),
                        ],
                    }

                checkpoint_state: WorkflowState = dict(current_state)  # type: ignore[assignment]
                checkpoint_state.update(updates)  # type: ignore[typeddict-item]
                budgets = checkpoint_state["budgets"]
                self.checkpoints.save_checkpoint(
                    session,
                    run_id=str(checkpoint_state["run_id"]),
                    step_index=budgets.current_steps,
                    node_name=_node_name,
                    stage=str(checkpoint_state["stage"]),
                    status=str(checkpoint_state["status"]),
                    state=checkpoint_state,
                )
                return updates

            graph.add_node(node_name, execute_node)

        graph.add_edge(START, NODE_SEQUENCE[0][0])
        for index, (node_name, _) in enumerate(NODE_SEQUENCE):
            next_node = NODE_SEQUENCE[index + 1][0] if index + 1 < len(NODE_SEQUENCE) else END

            def route(current_state: WorkflowState, *, _next: str = next_node) -> str:
                if current_state["status"] in {"paused", "completed", "failed", "needs_review"}:
                    return END
                return _next

            if next_node == END:
                graph.add_edge(node_name, END)
            else:
                graph.add_conditional_edges(node_name, route, {_next_label(next_node): next_node, END: END})

        compiled = graph.compile()
        result = compiled.invoke(dict(state))
        return dict(result)  # type: ignore[return-value]

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


def _next_label(node_name: str) -> str:
    """Keep conditional-edge labels distinct from LangGraph's END sentinel."""
    return node_name
