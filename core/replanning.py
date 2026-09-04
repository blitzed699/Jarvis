"""
core/replanning.py

Replanning Engine — Tier 2 Intelligence Amplification.
When a plan step fails, JARVIS does not give up.
It analyzes the failure, selects a recovery strategy, and regenerates the plan.

Failure taxonomy:
  - tool_error      → retry with corrected params
  - agent_error     → retry with more context or different agent
  - dependency      → wait or reorder steps
  - permission      → escalate to user or use sudo
  - timeout         → break into smaller chunks
  - hallucination   → re-verify and force re-execution
  - unknown         → ask user or abort

Recovery strategies:
  - retry           → same step, same approach
  - retry_with_fix  → same step, corrected approach
  - skip            → mark optional, continue
  - substitute      → swap agent/tool
  - replan_from     → regenerate remaining steps
  - abort           → stop, report failure
"""

import json
import time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class FailureCategory(Enum):
    TOOL_ERROR = "tool_error"
    AGENT_ERROR = "agent_error"
    DEPENDENCY_MISSING = "dependency"
    PERMISSION_DENIED = "permission"
    TIMEOUT = "timeout"
    HALLUCINATION = "hallucination"
    VALIDATION_FAILED = "validation"
    UNKNOWN = "unknown"


class RecoveryStrategy(Enum):
    RETRY = "retry"
    RETRY_WITH_FIX = "retry_with_fix"
    SKIP = "skip"
    SUBSTITUTE_AGENT = "substitute"
    REPLAN_FROM = "replan_from"
    ABORT = "abort"


@dataclass
class FailureAnalysis:
    category: FailureCategory
    confidence: float
    root_cause: str
    is_transient: bool
    can_retry: bool
    suggested_fix: str
    affected_steps: List[int]


@dataclass
class RecoveryPlan:
    strategy: RecoveryStrategy
    reason: str
    new_steps: List[Dict[str, Any]]
    skip_original_ids: List[int]
    inject_before: Optional[int] = None


class ReplanningEngine:
    """
    Analyzes plan failures and generates recovery strategies.
    """

    # Keywords that map discrepancies to failure categories
    CATEGORY_PATTERNS = {
        FailureCategory.PERMISSION_DENIED: [
            "permission denied", "access denied", "unauthorized",
            "forbidden", "not permitted", "sudo", "root required"
        ],
        FailureCategory.TIMEOUT: [
            "timed out", "timeout", "took too long", "deadline exceeded",
            "connection timed out", "read timeout"
        ],
        FailureCategory.TOOL_ERROR: [
            "command not found", "no such file", "does not exist",
            "not found", "missing", "module not found", "import error"
        ],
        FailureCategory.HALLUCINATION: [
            "hallucination", "claimed to create", "does not exist",
            "file not found", "agent claimed", "not actually created"
        ],
        FailureCategory.VALIDATION_FAILED: [
            "mismatch", "incorrect", "wrong", "unexpected", "invalid",
            "failed validation", "assertion failed"
        ],
        FailureCategory.DEPENDENCY_MISSING: [
            "dependency", "depends on", "not met", "prerequisite",
            "requires", "missing dependency"
        ],
    }

    def __init__(self, llm_client, planner, world_state, ovc_loop=None):
        self.llm = llm_client
        self.planner = planner
        self.world_state = world_state
        self.ovc = ovc_loop
        self.replan_history: List[Dict] = []

    def analyze_failure(self, failed_step, result: Dict[str, Any],
                        discrepancies: List[str]) -> FailureAnalysis:
        """
        Categorize a failure from step result + discrepancies.
        """
        result_str = json.dumps(result, default=str).lower()
        disc_str = " ".join(d.lower() for d in discrepancies)
        combined = result_str + " " + disc_str

        # Score each category
        scores = {}
        for cat, patterns in self.CATEGORY_PATTERNS.items():
            score = sum(1 for p in patterns if p in combined)
            if score > 0:
                scores[cat] = score

        if scores:
            best_cat = max(scores, key=scores.get)
            confidence = min(0.5 + scores[best_cat] * 0.15, 0.95)
        else:
            best_cat = FailureCategory.UNKNOWN
            confidence = 0.3

        # Determine transience and retryability
        transient = best_cat in (
            FailureCategory.TIMEOUT,
            FailureCategory.TOOL_ERROR,
            FailureCategory.HALLUCINATION
        )
        can_retry = best_cat not in (
            FailureCategory.PERMISSION_DENIED,
            FailureCategory.UNKNOWN
        )

        # Generate root cause and fix suggestion
        root_cause = self._infer_root_cause(best_cat, discrepancies)
        fix = self._suggest_fix(best_cat, discrepancies, failed_step)

        return FailureAnalysis(
            category=best_cat,
            confidence=confidence,
            root_cause=root_cause,
            is_transient=transient,
            can_retry=can_retry,
            suggested_fix=fix,
            affected_steps=[failed_step.id] if hasattr(failed_step, 'id') else []
        )

    def _infer_root_cause(self, category: FailureCategory,
                          discrepancies: List[str]) -> str:
        mapping = {
            FailureCategory.TOOL_ERROR: "Tool execution failed — path, command, or dependency issue.",
            FailureCategory.AGENT_ERROR: "Agent produced invalid or incomplete output.",
            FailureCategory.PERMISSION_DENIED: "Insufficient permissions for the requested operation.",
            FailureCategory.TIMEOUT: "Operation exceeded time limit.",
            FailureCategory.HALLUCINATION: "Agent claimed success but evidence is missing.",
            FailureCategory.VALIDATION_FAILED: "Output did not match expected structure or values.",
            FailureCategory.DEPENDENCY_MISSING: "Required prerequisite step was not completed.",
            FailureCategory.UNKNOWN: "Failure cause could not be determined.",
        }
        base = mapping.get(category, "Unknown failure.")
        if discrepancies:
            base += f" Discrepancy: {discrepancies[0][:120]}"
        return base

    def _suggest_fix(self, category: FailureCategory,
                     discrepancies: List[str], failed_step) -> str:
        fixes = {
            FailureCategory.TOOL_ERROR: "Verify paths and commands exist before execution.",
            FailureCategory.AGENT_ERROR: "Provide additional context and retry with clearer instructions.",
            FailureCategory.PERMISSION_DENIED: "Request elevated permissions or change target path.",
            FailureCategory.TIMEOUT: "Increase timeout or break task into smaller subtasks.",
            FailureCategory.HALLUCINATION: "Force re-execution with explicit verification checkpoints.",
            FailureCategory.VALIDATION_FAILED: "Adjust parameters to match expected output format.",
            FailureCategory.DEPENDENCY_MISSING: "Ensure prerequisite steps complete successfully first.",
            FailureCategory.UNKNOWN: "Gather more diagnostic information before retrying.",
        }
        return fixes.get(category, "Investigate and retry.")

    def select_recovery_strategy(self, analysis: FailureAnalysis,
                                  attempt_count: int = 1) -> RecoveryStrategy:
        """
        Choose a recovery strategy based on failure analysis and attempt history.
        """
        if attempt_count >= 3:
            if analysis.category == FailureCategory.HALLUCINATION:
                return RecoveryStrategy.ABORT
            return RecoveryStrategy.REPLAN_FROM

        if analysis.category == FailureCategory.PERMISSION_DENIED:
            return RecoveryStrategy.ABORT

        if analysis.category == FailureCategory.DEPENDENCY_MISSING:
            return RecoveryStrategy.REPLAN_FROM

        if analysis.is_transient and analysis.can_retry:
            if attempt_count == 1:
                return RecoveryStrategy.RETRY
            return RecoveryStrategy.RETRY_WITH_FIX

        if analysis.category == FailureCategory.AGENT_ERROR:
            return RecoveryStrategy.SUBSTITUTE_AGENT

        if analysis.category == FailureCategory.VALIDATION_FAILED:
            return RecoveryStrategy.RETRY_WITH_FIX

        return RecoveryStrategy.RETRY_WITH_FIX

    def generate_recovery_plan(self, original_goal: str, failed_step,
                                analysis: FailureAnalysis,
                                completed_steps: List,
                                remaining_steps: List) -> RecoveryPlan:
        """
        Generate a concrete recovery plan with new/modified steps.
        """
        strategy = self.select_recovery_strategy(analysis)

        if strategy == RecoveryStrategy.RETRY:
            return RecoveryPlan(
                strategy=strategy,
                reason=f"Transient {analysis.category.value}. Retrying step {failed_step.id}.",
                new_steps=[],
                skip_original_ids=[],
                inject_before=None
            )

        if strategy == RecoveryStrategy.SKIP:
            return RecoveryPlan(
                strategy=strategy,
                reason=f"Step {failed_step.id} appears optional. Skipping.",
                new_steps=[],
                skip_original_ids=[failed_step.id],
                inject_before=None
            )

        if strategy == RecoveryStrategy.ABORT:
            return RecoveryPlan(
                strategy=strategy,
                reason=f"Critical failure ({analysis.category.value}). Aborting plan.",
                new_steps=[],
                skip_original_ids=[],
                inject_before=None
            )

        # For replan_from and retry_with_fix, ask LLM for new steps
        if strategy in (RecoveryStrategy.REPLAN_FROM, RecoveryStrategy.RETRY_WITH_FIX):
            new_steps = self._llm_replan(
                original_goal, failed_step, analysis,
                completed_steps, remaining_steps, strategy
            )
            return RecoveryPlan(
                strategy=strategy,
                reason=f"Regenerating plan from step {failed_step.id} due to {analysis.category.value}.",
                new_steps=new_steps,
                skip_original_ids=[s.id for s in remaining_steps],
                inject_before=failed_step.id
            )

        if strategy == RecoveryStrategy.SUBSTITUTE_AGENT:
            alt_agent = self._pick_alternative_agent(failed_step)
            new_step = {
                "id": failed_step.id,
                "description": f"[RETRY with {alt_agent}] {failed_step.description}",
                "agent": alt_agent,
                "depends_on": failed_step.depends_on if hasattr(failed_step, 'depends_on') else []
            }
            return RecoveryPlan(
                strategy=strategy,
                reason=f"Swapping agent to {alt_agent} for step {failed_step.id}.",
                new_steps=[new_step],
                skip_original_ids=[failed_step.id],
                inject_before=failed_step.id
            )

        return RecoveryPlan(
            strategy=RecoveryStrategy.ABORT,
            reason="No viable recovery strategy found.",
            new_steps=[],
            skip_original_ids=[],
            inject_before=None
        )

    def _llm_replan(self, original_goal: str, failed_step, analysis: FailureAnalysis,
                    completed_steps: List, remaining_steps: List,
                    strategy: RecoveryStrategy) -> List[Dict[str, Any]]:
        """Use LLM to generate recovery steps."""
        if not self.llm:
            return []

        completed_desc = "\n".join(
            f"- Step {s.id}: {s.description} (done)"
            for s in completed_steps
        )
        remaining_desc = "\n".join(
            f"- Step {s.id}: {s.description} (pending)"
            for s in remaining_steps
        )

        prompt = f"""You are JARVIS's replanning system. A plan step failed and needs recovery.

Original goal: {original_goal}

Completed steps:
{completed_desc}

Failed step: {failed_step.id} — {failed_step.description}
Failure category: {analysis.category.value}
Root cause: {analysis.root_cause}
Suggested fix: {analysis.suggested_fix}

Remaining steps before failure:
{remaining_desc}

Generate a JSON array of steps to recover and complete the goal.
Each step: {{"id": int, "description": str, "agent": str, "depends_on": [int]}}
Use agents from: coding_agent, research_agent, business_agent, creative_agent, tool, llm.
If the fix is simple, return just 1-2 steps. If complex, return a full replan.

Return ONLY raw JSON array. No markdown."""

        try:
            raw = self.llm.generate(prompt, max_tokens=1500, temperature=0.3)
            # Extract JSON array
            import re
            raw = re.sub(r'```(?:json)?\s*', '', raw)
            raw = raw.replace('```', '')
            start = raw.find('[')
            end = raw.rfind(']')
            if start != -1 and end != -1:
                steps = json.loads(raw[start:end+1])
                if isinstance(steps, list):
                    return steps
        except Exception:
            pass

        # Fallback: single retry step
        return [{
            "id": failed_step.id,
            "description": f"[RECOVERED] {failed_step.description} — Fix: {analysis.suggested_fix}",
            "agent": getattr(failed_step, 'agent', 'llm'),
            "depends_on": getattr(failed_step, 'depends_on', [])
        }]

    def _pick_alternative_agent(self, failed_step) -> str:
        """Pick an alternative agent when substitution is needed."""
        current = getattr(failed_step, 'agent', 'llm')
        alternatives = {
            'coding_agent': 'llm',
            'research_agent': 'llm',
            'business_agent': 'llm',
            'creative_agent': 'llm',
            'llm': 'coding_agent',
            'tool': 'llm',
        }
        return alternatives.get(current, 'llm')

    def execute_recovery(self, original_goal: str, failed_step, result: Dict[str, Any],
                         discrepancies: List[str],
                         completed_steps: List, remaining_steps: List,
                         attempt_count: int = 1) -> Tuple[RecoveryPlan, FailureAnalysis]:
        """
        Full recovery pipeline: analyze → select strategy → generate plan.
        Returns (recovery_plan, failure_analysis).
        """
        analysis = self.analyze_failure(failed_step, result, discrepancies)
        plan = self.generate_recovery_plan(
            original_goal, failed_step, analysis,
            completed_steps, remaining_steps
        )

        self.replan_history.append({
            "timestamp": time.time(),
            "goal": original_goal,
            "failed_step": getattr(failed_step, 'id', '?'),
            "analysis": {
                "category": analysis.category.value,
                "confidence": analysis.confidence,
                "root_cause": analysis.root_cause,
            },
            "strategy": plan.strategy.value,
            "reason": plan.reason,
        })

        return plan, analysis

    def get_history(self) -> List[Dict]:
        return self.replan_history

    def get_stats(self) -> Dict[str, Any]:
        if not self.replan_history:
            return {"total_replans": 0}
        cats = {}
        strats = {}
        for h in self.replan_history:
            cats[h["analysis"]["category"]] = cats.get(h["analysis"]["category"], 0) + 1
            strats[h["strategy"]] = strats.get(h["strategy"], 0) + 1
        return {
            "total_replans": len(self.replan_history),
            "failure_categories": cats,
            "strategies_used": strats,
        }
