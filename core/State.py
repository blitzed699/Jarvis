"""
core/state.py

The World State Layer — structured belief state that persists across turns.
This is the 'working memory' of JARVIS's cognitive architecture.
Without this, JARVIS is planning blind.
"""

import os
import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum


class ActionStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CORRECTED = "corrected"


@dataclass
class ActionRecord:
    """A single action with expected vs actual outcome."""
    id: str
    action_type: str          # "tool" | "agent" | "llm" | "plan_step"
    action_name: str
    description: str
    expected_result: Dict[str, Any] = field(default_factory=dict)
    actual_result: Dict[str, Any] = field(default_factory=dict)
    status: ActionStatus = ActionStatus.PENDING
    confidence: float = 1.0   # 0.0 → 1.0
    discrepancies: List[str] = field(default_factory=list)
    corrections_applied: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    latency_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class PlanState:
    """Mutable state of an active multi-step plan."""
    goal: str
    current_step_index: int = 0
    total_steps: int = 0
    step_statuses: Dict[int, str] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def is_complete(self) -> bool:
        return all(s == "done" for s in self.step_statuses.values())

    def current_step_id(self) -> Optional[int]:
        for i in range(1, self.total_steps + 1):
            if self.step_statuses.get(i) in ("pending", "running"):
                return i
        return None

    def completion_pct(self) -> float:
        if not self.total_steps:
            return 0.0
        done = sum(1 for s in self.step_statuses.values() if s == "done")
        return done / self.total_steps


@dataclass
class EnvironmentState:
    """Snapshot of the environment JARVIS is operating in."""
    cwd: str = field(default_factory=os.getcwd)
    files_created_this_session: List[str] = field(default_factory=list)
    files_modified_this_session: List[str] = field(default_factory=list)
    processes_started: List[Dict[str, Any]] = field(default_factory=list)
    last_command_output: str = ""
    last_command_exit_code: int = 0
    available_tools: List[str] = field(default_factory=list)
    available_agents: List[str] = field(default_factory=list)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "cwd": self.cwd,
            "files_created": self.files_created_this_session[-10:],
            "files_modified": self.files_modified_this_session[-10:],
            "processes": self.processes_started[-5:],
            "last_output": self.last_command_output[:500],
            "last_exit_code": self.last_command_exit_code,
        }

    def track_file_creation(self, path: str) -> None:
        if path not in self.files_created_this_session:
            self.files_created_this_session.append(path)

    def track_file_modification(self, path: str) -> None:
        if path not in self.files_modified_this_session:
            self.files_modified_this_session.append(path)


@dataclass
class UserContext:
    """What JARVIS believes about the user right now."""
    name: Optional[str] = None
    active_project: Optional[str] = None
    active_goal: Optional[str] = None
    recent_rejections: List[str] = field(default_factory=list)
    preferences: Dict[str, Any] = field(default_factory=dict)
    mood_indicators: Dict[str, float] = field(default_factory=dict)
    last_feedback_rating: Optional[int] = None
    trust_level: float = 0.5   # Increases as JARVIS succeeds, drops on failure

    def add_rejection(self, approach: str) -> None:
        self.recent_rejections.append(approach)
        self.recent_rejections = self.recent_rejections[-5:]
        self.trust_level = max(0.0, self.trust_level - 0.1)

    def add_success(self) -> None:
        self.trust_level = min(1.0, self.trust_level + 0.05)


class WorldState:
    """
    Structured belief state that persists across turns.
    Replaces the ad-hoc context building in jarvis.py with a rigorous model.
    """

    def __init__(self):
        self.user = UserContext()
        self.environment = EnvironmentState()
        self.action_history: List[ActionRecord] = []
        self.active_plan: Optional[PlanState] = None
        self.open_questions: List[str] = []
        self.uncertainties: List[str] = []
        self.session_id: str = self._generate_session_id()
        self._state_version: int = 0

    def _generate_session_id(self) -> str:
        return f"state_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hashlib.md5(os.urandom(8)).hexdigest()[:6]}"

    # ------------------------------------------------------------------
    # Mutation methods (all increment version for change-tracking)
    # ------------------------------------------------------------------
    def record_action(self, action: ActionRecord) -> ActionRecord:
        self.action_history.append(action)
        self._state_version += 1
        if len(self.action_history) > 50:
            self.action_history = self.action_history[-50:]
        return action

    def update_action(self, action_id: str, **kwargs) -> Optional[ActionRecord]:
        for action in self.action_history:
            if action.id == action_id:
                for key, value in kwargs.items():
                    if hasattr(action, key):
                        setattr(action, key, value)
                self._state_version += 1
                return action
        return None

    def set_plan(self, goal: str, total_steps: int) -> PlanState:
        self.active_plan = PlanState(
            goal=goal,
            total_steps=total_steps,
            step_statuses={i: "pending" for i in range(1, total_steps + 1)}
        )
        self._state_version += 1
        return self.active_plan

    def update_plan_step(self, step_id: int, status: str) -> None:
        if self.active_plan and step_id in self.active_plan.step_statuses:
            self.active_plan.step_statuses[step_id] = status
            if status == "done":
                self.user.add_success()
            self._state_version += 1

    def add_open_question(self, question: str) -> None:
        if question not in self.open_questions:
            self.open_questions.append(question)
            self._state_version += 1

    def resolve_question(self, question: str, answer: str = "") -> None:
        if question in self.open_questions:
            self.open_questions.remove(question)
            self._state_version += 1

    def add_uncertainty(self, uncertainty: str) -> None:
        if uncertainty not in self.uncertainties:
            self.uncertainties.append(uncertainty)
            self._state_version += 1

    def resolve_uncertainty(self, uncertainty: str) -> None:
        if uncertainty in self.uncertainties:
            self.uncertainties.remove(uncertainty)
            self._state_version += 1

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------
    def get_last_action(self, action_type: Optional[str] = None) -> Optional[ActionRecord]:
        if not self.action_history:
            return None
        if action_type:
            for action in reversed(self.action_history):
                if action.action_type == action_type:
                    return action
            return None
        return self.action_history[-1]

    def get_recent_failures(self, n: int = 5) -> List[ActionRecord]:
        failures = [a for a in self.action_history if a.status == ActionStatus.FAILED]
        return failures[-n:]

    def get_recent_corrections(self, n: int = 5) -> List[ActionRecord]:
        corrected = [a for a in self.action_history if a.status == ActionStatus.CORRECTED]
        return corrected[-n:]

    def get_action_by_id(self, action_id: str) -> Optional[ActionRecord]:
        for a in self.action_history:
            if a.id == action_id:
                return a
        return None

    def get_recurring_discrepancy_pattern(self) -> Optional[str]:
        """Detect if the same failure keeps happening (for procedural memory)."""
        if len(self.action_history) < 3:
            return None
        recent = self.action_history[-10:]
        all_disc = []
        for a in recent:
            all_disc.extend(a.discrepancies)
        from collections import Counter
        counts = Counter(all_disc)
        most_common = counts.most_common(1)
        if most_common and most_common[0][1] >= 3:
            return most_common[0][0]
        return None

    # ------------------------------------------------------------------
    # Prompt formatting — this replaces the ad-hoc context in jarvis.py
    # ------------------------------------------------------------------
    def get_state_summary(self, verbose: bool = False) -> str:
        lines = [f"## World State (v{self._state_version})"]

        # User context
        u = self.user
        lines.append("### User Context")
        if u.name:
            lines.append(f"- Name: {u.name}")
        if u.active_project:
            lines.append(f"- Active project: {u.active_project}")
        if u.active_goal:
            lines.append(f"- Active goal: {u.active_goal}")
        if u.recent_rejections:
            lines.append(f"- Recent rejections: {u.recent_rejections[-1]}")
        lines.append(f"- Trust level: {u.trust_level:.0%}")

        # Active plan
        if self.active_plan:
            p = self.active_plan
            lines.append(f"\n### Active Plan: {p.goal}")
            lines.append(f"- Progress: {p.completion_pct():.0%} ({p.total_steps} steps)")
            current = p.current_step_id()
            if current:
                lines.append(f"- Current step: #{current}")
            failed_steps = [i for i, s in p.step_statuses.items() if s == "failed"]
            if failed_steps:
                lines.append(f"- Failed steps: {failed_steps}")

        # Open questions / uncertainties
        if self.open_questions:
            lines.append("\n### ⚠ Open Questions")
            for q in self.open_questions:
                lines.append(f"- {q}")
        if self.uncertainties:
            lines.append("\n### ⚠ Uncertainties")
            for u_text in self.uncertainties:
                lines.append(f"- {u_text}")

        # Recent action history (last 3)
        recent = self.action_history[-3:]
        if recent:
            lines.append("\n### Recent Actions")
            for a in recent:
                icon = "✓" if a.status == ActionStatus.DONE else "✗" if a.status == ActionStatus.FAILED else "↻" if a.status == ActionStatus.CORRECTED else "⋯"
                lines.append(f"- {icon} [{a.action_type}:{a.action_name}] {a.description[:60]}...")
                if a.discrepancies:
                    lines.append(f"    ⚠ {a.discrepancies[0][:80]}")
                if a.corrections_applied:
                    lines.append(f"    ↻ corrected: {a.corrections_applied[-1][:60]}")

        # Environment snapshot
        env = self.environment.snapshot()
        if env["files_created"]:
            lines.append("\n### Files This Session")
            for f in env["files_created"][-5:]:
                lines.append(f"- {f}")

        if verbose:
            lines.append(f"\n### Environment")
            lines.append(f"- CWD: {env['cwd']}")
            lines.append(f"- Last exit code: {env['last_exit_code']}")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "version": self._state_version,
            "user": {
                "name": self.user.name,
                "active_project": self.user.active_project,
                "active_goal": self.user.active_goal,
                "recent_rejections": self.user.recent_rejections,
                "preferences": self.user.preferences,
                "trust_level": self.user.trust_level,
                "last_feedback": self.user.last_feedback_rating,
            },
            "environment": self.environment.snapshot(),
            "active_plan": {
                "goal": self.active_plan.goal,
                "current_step": self.active_plan.current_step_id(),
                "step_statuses": self.active_plan.step_statuses,
                "completion_pct": self.active_plan.completion_pct(),
            } if self.active_plan else None,
            "action_history": [a.to_dict() for a in self.action_history[-20:]],
            "open_questions": self.open_questions,
            "uncertainties": self.uncertainties,
        }

    def save_checkpoint(self, path: str = "memory/state_checkpoint.json") -> None:
        """Save state to disk for crash recovery."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)

    @classmethod
    def load_checkpoint(cls, path: str = "memory/state_checkpoint.json") -> Optional["WorldState"]:
        """Restore state from disk."""
        if not os.path.exists(path):
            return None
        # Full deserialization is complex; this is a scaffold.
        # In production you would hydrate the full object graph.
        with open(path, "r") as f:
            data = json.load(f)
        ws = cls()
        ws.session_id = data.get("session_id", ws.session_id)
        return ws
