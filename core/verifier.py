"""
core/verifier.py

The Verification Engine — JARVIS's quality control.
v0.4.1: Critic NEEDS_FIX is now blocking. Only severity="none" = verified.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field


@dataclass
class VerificationResult:
    """Result of verifying an action against its expected outcome."""
    action_id: str
    verified: bool
    confidence: float
    discrepancies: List[str]
    severity: str
    recommendation: str
    auto_correctable: bool = False
    correction_hint: str = ""
    evidence: List[Dict[str, Any]] = field(default_factory=list)

    def is_blocking(self) -> bool:
        """Should this discrepancy block progress?"""
        return self.severity in ("major", "critical") and not self.verified

    def is_trustworthy(self) -> bool:
        """Can JARVIS claim this action succeeded?"""
        return self.verified and self.confidence >= 0.8 and self.severity == "none"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "verified": self.verified,
            "confidence": self.confidence,
            "severity": self.severity,
            "recommendation": self.recommendation,
            "discrepancies": self.discrepancies,
            "evidence_count": len(self.evidence),
        }


class Verifier:
    """
    Verification engine: the gatekeeper of truth.
    Never trusts claims — only verified outcomes.
    """

    def __init__(self, llm_client=None):
        self.llm = llm_client

    def verify(self, expected: Dict[str, Any], actual: Dict[str, Any],
               discrepancies: List[str], action_type: str,
               action_name: str = "") -> VerificationResult:
        """
        Verify whether an action achieved its goal.

        CRITICAL RULE: If critic injected a NEEDS_FIX discrepancy, severity is ALWAYS critical.
        Only severity="none" with zero discrepancies = verified.
        """
        # Check for critic-injected discrepancies first
        has_critic_issue = any(d.startswith("CRITIC") for d in discrepancies)

        if not discrepancies:
            return VerificationResult(
                action_id="",
                verified=True,
                confidence=1.0,
                discrepancies=[],
                severity="none",
                recommendation="Continue",
                auto_correctable=False
            )

        severity = self._assess_severity(discrepancies, action_type, action_name)
        confidence = self._calculate_confidence(discrepancies, severity)
        recommendation = self._generate_recommendation(
            severity, discrepancies, action_type, action_name
        )
        auto_correctable, hint = self._assess_auto_correctable(
            discrepancies, action_type, action_name
        )

        # v0.4.1: Critic issues are ALWAYS blocking
        if has_critic_issue:
            severity = "critical"
            confidence = 0.0
            auto_correctable = True
            hint = "Address critic feedback and regenerate output"
            recommendation = "HALT — critic identified issues. Fix and re-criticize before claiming success."

        # v0.4.1: Only "none" = verified. "minor" is no longer auto-pass.
        verified = severity == "none" and not has_critic_issue

        return VerificationResult(
            action_id="",
            verified=verified,
            confidence=confidence,
            discrepancies=discrepancies,
            severity=severity,
            recommendation=recommendation,
            auto_correctable=auto_correctable,
            correction_hint=hint
        )

    def verify_plan_completion(self, plan_state, world_state) -> VerificationResult:
        """Verify whether a completed plan actually achieved its goal."""
        if not plan_state:
            return VerificationResult(
                action_id="plan",
                verified=False,
                confidence=0.0,
                discrepancies=["No active plan"],
                severity="critical",
                recommendation="Create a plan before claiming completion"
            )

        done_count = sum(1 for s in plan_state.step_statuses.values() if s == "done")
        total = len(plan_state.step_statuses)

        if done_count < total:
            return VerificationResult(
                action_id="plan",
                verified=False,
                confidence=0.0,
                discrepancies=[f"Plan incomplete: {done_count}/{total} steps done"],
                severity="critical",
                recommendation="Complete remaining steps before claiming success"
            )

        recent_failures = world_state.get_recent_failures(n=5)
        if recent_failures:
            return VerificationResult(
                action_id="plan",
                verified=False,
                confidence=0.2,
                discrepancies=[
                    f"Recent failure: {a.description} ({a.discrepancies[0] if a.discrepancies else 'unknown'})"
                    for a in recent_failures
                ],
                severity="critical",
                recommendation="Review and fix failures before claiming completion"
            )

        recent_with_issues = [
            a for a in world_state.action_history[-10:]
            if a.discrepancies and a.status.value != "corrected"
        ]
        if recent_with_issues:
            return VerificationResult(
                action_id="plan",
                verified=False,
                confidence=0.5,
                discrepancies=[
                    f"Uncorrected issue in {a.action_name}: {a.discrepancies[0]}"
                    for a in recent_with_issues
                ],
                severity="critical",
                recommendation="Address uncorrected issues before claiming completion"
            )

        return VerificationResult(
            action_id="plan",
            verified=True,
            confidence=0.95,
            discrepancies=[],
            severity="none",
            recommendation="Plan completed and verified. You may report success."
        )

    def _assess_severity(self, discrepancies: List[str], action_type: str,
                         action_name: str) -> str:
        """Categorize severity. Critic issues are handled upstream."""
        critical_patterns = [
            "does not exist", "execution failed", "timed out",
            "permission denied", "cannot read", "cannot write",
            "connection refused", "no such file", "not found",
            "segmentation fault", "killed", "abort", "hallucination"
        ]
        major_patterns = [
            "not found", "mismatch", "missing", "error", "failed",
            "incorrect", "unexpected", "empty", "wrong"
        ]

        for d in discrepancies:
            if d.startswith("CRITIC"):
                continue  # Handled upstream
            d_lower = d.lower()
            if any(p in d_lower for p in critical_patterns):
                return "critical"
            if any(p in d_lower for p in major_patterns):
                return "major"

        return "minor"

    def _calculate_confidence(self, discrepancies: List[str], severity: str) -> float:
        """Calculate confidence score based on discrepancies."""
        base = {"none": 1.0, "minor": 0.6, "major": 0.25, "critical": 0.05}.get(severity, 0.5)
        penalty = min(len(discrepancies) * 0.08, 0.25)
        return max(0.0, base - penalty)

    def _generate_recommendation(self, severity: str, discrepancies: List[str],
                                 action_type: str, action_name: str) -> str:
        if severity == "none":
            return "Continue"

        if severity == "minor":
            return "Continue with caution — log discrepancies for review"

        if severity == "major":
            if action_type == "agent" and action_name == "coding_agent":
                return "Fix code and re-test before claiming completion"
            elif action_type == "tool" and action_name in ("shell", "run_python"):
                return "Retry with corrected parameters or environment"
            elif action_type == "plan_step":
                return "Re-execute this step with corrections"
            else:
                return "Re-execute with corrections"

        # critical
        if action_type == "agent" and action_name == "coding_agent":
            return "HALT — code is broken or critic rejected. Debug, fix, and re-criticize before proceeding."
        elif action_type == "tool":
            return "HALT — tool failed critically. Check environment, permissions, and inputs."
        else:
            return "HALT — critical failure. Replan from last known good state."

    def _assess_auto_correctable(self, discrepancies: List[str],
                                 action_type: str, action_name: str) -> tuple:
        correctable_patterns = {
            "does not exist": (True, "Check path spelling and ensure parent directories exist"),
            "permission denied": (True, "Check file permissions or use sudo if appropriate"),
            "no such file": (True, "Create missing directories before writing file"),
            "timed out": (True, "Increase timeout or break task into smaller chunks"),
            "not found": (True, "Verify the resource exists and the path is correct"),
            "empty": (True, "Regenerate content — previous write may have failed silently"),
            "missing import": (True, "Add the required import statement"),
            "module not found": (True, "Install missing dependency or check module name"),
        }

        for disc in discrepancies:
            disc_lower = disc.lower()
            for pattern, (correctable, hint) in correctable_patterns.items():
                if pattern in disc_lower:
                    return correctable, hint

        return False, "Manual intervention or replanning may be required"
