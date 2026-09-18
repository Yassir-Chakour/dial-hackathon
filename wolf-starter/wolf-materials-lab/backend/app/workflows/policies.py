"""Workflow policies, transition guards, budget enforcement, and authority bounds."""

import hashlib
import re
from typing import Any

from app.workflows.state import WorkflowBudgets, WorkflowStage


class WorkflowPolicyError(Exception):
    """Base error for workflow policy violations."""


class BudgetExceededError(WorkflowPolicyError):
    """Raised when execution limits (steps, tool calls, model calls) are exceeded."""


class InvalidTransitionError(WorkflowPolicyError):
    """Raised when an illegal stage transition is attempted."""


ALLOWED_TRANSITIONS: dict[WorkflowStage, set[WorkflowStage]] = {
    "received": {"inspected", "failed", "needs_review"},
    "inspected": {"scoped", "failed", "needs_review"},
    "scoped": {"ingested", "failed", "needs_review", "awaiting_review"},
    "ingested": {"reconciled", "failed", "needs_review", "awaiting_review"},
    "reconciled": {"impacted", "failed", "needs_review", "awaiting_review"},
    "impacted": {"drafted", "failed", "needs_review"},
    "drafted": {"awaiting_review", "completed", "failed", "needs_review"},
    "awaiting_review": {"reconciled", "scoped", "completed", "failed", "needs_review"},
    "needs_review": {"scoped", "reconciled", "completed", "failed"},
    "completed": set(),
    "failed": set(),
}


def validate_transition(current: WorkflowStage, target: WorkflowStage) -> None:
    """Ensure stage transitions follow the state-machine rules."""
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise InvalidTransitionError(f"Illegal workflow transition: {current} -> {target}.")


def enforce_budget(budgets: WorkflowBudgets, operation: str = "step") -> WorkflowBudgets:
    """Track resource consumption and enforce safety boundaries."""
    new_steps = budgets.current_steps + (1 if operation == "step" else 0)
    new_tools = budgets.current_tool_calls + (1 if operation == "tool" else 0)
    new_models = budgets.current_model_calls + (1 if operation == "model" else 0)

    if new_steps > budgets.step_limit:
        raise BudgetExceededError(f"Step limit exceeded: {new_steps} > {budgets.step_limit}")
    if new_tools > budgets.max_tool_calls:
        raise BudgetExceededError(f"Tool call limit exceeded: {new_tools} > {budgets.max_tool_calls}")
    if new_models > budgets.max_model_calls:
        raise BudgetExceededError(f"Model call limit exceeded: {new_models} > {budgets.max_model_calls}")

    return WorkflowBudgets(
        step_limit=budgets.step_limit,
        current_steps=new_steps,
        max_tool_calls=budgets.max_tool_calls,
        current_tool_calls=new_tools,
        max_model_calls=budgets.max_model_calls,
        current_model_calls=new_models,
        max_duration_seconds=budgets.max_duration_seconds,
    )


def compute_workflow_fingerprint(
    event_key: str,
    market: str,
    source_file_id: str,
    workflow_version: str,
) -> str:
    """Compute a deterministic hash representing the workflow run input identity."""
    raw = f"{event_key}:{market}:{source_file_id}:{workflow_version}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def redact_workflow_state(state: dict[str, Any]) -> dict[str, Any]:
    """Sanitize state for checkpoint persistence, removing sensitive/unbounded payloads."""
    redacted: dict[str, Any] = {}
    for key, val in state.items():
        if key in {"content", "raw_bytes", "password", "token", "secret"}:
            redacted[key] = "[REDACTED]"
        elif isinstance(val, (str, int, float, bool)) or val is None:
            redacted[key] = val
        elif isinstance(val, (list, tuple)):
            # Cap list length to prevent checkpoint explosion
            redacted[key] = [_sanitize_val(item) for item in list(val)[:50]]
        elif isinstance(val, dict):
            redacted[key] = {k: _sanitize_val(v) for k, v in val.items() if k not in {"password", "secret"}}
        elif hasattr(val, "__dict__"):
            redacted[key] = {k: _sanitize_val(v) for k, v in val.__dict__.items() if not k.startswith("_")}
        else:
            redacted[key] = str(val)
    return redacted


def _sanitize_val(val: Any) -> Any:
    if isinstance(val, (str, int, float, bool)) or val is None:
        return val
    if isinstance(val, (list, tuple)):
        return [_sanitize_val(i) for i in list(val)[:20]]
    if isinstance(val, dict):
        return {k: _sanitize_val(v) for k, v in val.items() if k not in {"password", "secret"}}
    if hasattr(val, "__dict__"):
        return {k: _sanitize_val(v) for k, v in val.__dict__.items() if not k.startswith("_")}
    return str(val)


def defend_prompt_injection(raw_text: str) -> str:
    """Neutralize instruction overrides within source data cells or descriptions."""
    sanitized = raw_text
    patterns = [
        r"(?i)ignore\s+(all\s+)?(previous|prior)\s+instructions",
        r"(?i)system\s*:",
        r"(?i)admin\s*:",
        r"(?i)sudo\s+",
        r"(?i)you\s+are\s+now\s+in\s+",
    ]
    for pattern in patterns:
        sanitized = re.sub(pattern, "[FILTERED_INSTRUCTION]", sanitized)
    return sanitized
