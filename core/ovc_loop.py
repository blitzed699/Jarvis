"""
core/ovc_loop.py

The Observe → Verify → Correct Loop.
This is the heart of JARVIS v0.4 cognitive architecture.

After every action:
  1. OBSERVE  — check what actually happened
  2. VERIFY   — compare against expectation
  3. CORRECT  — if mismatch, generate and apply fix
  4. RE-VERIFY — confirm the fix worked

Without this loop, JARVIS is just an LLM with tools.
With this loop, JARVIS becomes a reliable autonomous system.
"""

import time
import hashlib
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field

from .state import WorldState, ActionRecord, ActionStatus
from .observer import Observer, ObservationResult
from .verifier import Verifier, VerificationResult


@dataclass
class OVCCycleResult:
    """Complete result of an OVC cycle."""
    action_record: ActionRecord
    observation: ObservationResult
    verification: VerificationResult
    corrected: bool
    final_success: bool
    iterations: int
    corrections_history: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_record.id,
            "action": self.action_record.description,
            "verified": self.verification.verified,
            "confidence": self.verification.confidence,
            "severity": self.verification.severity,
            "corrected": self.corrected,
            "final_success": self.final_success,
            "iterations": self.iterations,
            "discrepancies": self.observation.discrepancies,
            "recommendation": self.verification.recommendation,
        }


class OVCLoop:
    """
    Observe → Verify → Correct Loop

    Usage:
        ovc = OVCLoop(llm, world_state, observer, verifier)
        result = ovc.execute(
            action_type="tool",
            action_name="write_file",
            description="Create hello.py",
            execute_fn=lambda: tool.run(path="/tmp/hello.py", content="print(1)"),
            expected={"path": "/tmp/hello.py", "exists": True}
        )
        if not result.final_success:
            print("Failed after corrections:", result.verification.recommendation)
    """

    MAX_ITERATIONS = 3

    def __init__(self, llm_client, world_state: WorldState,
                 observer: Observer, verifier: Verifier):
        self.llm = llm_client
        self.state = world_state
        self.observer = observer
        self.verifier = verifier
        self._correction_stats = {"total": 0, "successful": 0}

    def execute(self, action_type: str, action_name: str, description: str,
                execute_fn: Callable[[], Dict[str, Any]],
                expected: Dict[str, Any],
                observe_fn: Optional[Callable] = None,
                max_iterations: int = MAX_ITERATIONS,
                project_id: Optional[str] = None) -> OVCCycleResult:
        """
        Execute an action within the OVC loop.

        Args:
            action_type: "tool" | "agent" | "llm" | "plan_step"
            action_name: specific tool/agent name
            description: human-readable what this action should do
            execute_fn: zero-arg callable that performs the action
            expected: dict describing expected outcome (for observation)
            observe_fn: optional custom observation function
            max_iterations: max correction attempts (default 3)
            project_id: optional project scope

        Returns:
            OVCCycleResult with full cycle history
        """
        action_id = f"act_{int(time.time() * 1000)}_{hashlib.md5(description.encode()).hexdigest()[:4]}"
        corrections_history = []

        # Record action start
        record = ActionRecord(
            id=action_id,
            action_type=action_type,
            action_name=action_name,
            description=description,
            expected_result=expected,
            status=ActionStatus.RUNNING
        )
        self.state.record_action(record)
        if project_id:
            self.state.user.active_project = project_id

        iteration = 0
        corrected = False
        current_result = None
        last_observation = None
        last_verification = None

        while iteration < max_iterations:
            iteration += 1

            # ==========================================================
            # EXECUTE
            # ==========================================================
            try:
                start = time.time()
                current_result = execute_fn()
                latency = int((time.time() - start) * 1000)
                record.latency_ms = latency
            except Exception as e:
                record.status = ActionStatus.FAILED
                record.actual_result = {"error": str(e)}
                self.state.update_action(action_id, status=ActionStatus.FAILED)

                obs = ObservationResult(
                    observation_type="execution",
                    target=description,
                    expected=expected,
                    actual={"error": str(e)},
                    match=False,
                    discrepancies=[f"Execution failed: {str(e)}"]
                )
                ver = self.verifier.verify(expected, {}, obs.discrepancies, action_type, action_name)
                ver.action_id = action_id

                return OVCCycleResult(
                    action_record=record,
                    observation=obs,
                    verification=ver,
                    corrected=False,
                    final_success=False,
                    iterations=iteration,
                    corrections_history=corrections_history
                )

            # ==========================================================
            # OBSERVE
            # ==========================================================
            if observe_fn:
                observation = observe_fn(current_result)
            else:
                observation = self._default_observe(
                    action_type, action_name, description,
                    current_result, expected
                )
            last_observation = observation

            # ==========================================================
            # VERIFY
            # ==========================================================
            verification = self.verifier.verify(
                expected, observation.actual,
                observation.discrepancies, action_type, action_name
            )
            verification.action_id = action_id

            # Update record with observation results
            record.actual_result = observation.actual
            record.discrepancies = observation.discrepancies

            # ==========================================================
            # DECIDE: success or correct?
            # ==========================================================
            if verification.verified:
                record.status = ActionStatus.DONE if not corrected else ActionStatus.CORRECTED
                record.confidence = verification.confidence
                self.state.update_action(
                    action_id,
                    status=record.status,
                    actual_result=observation.actual,
                    confidence=verification.confidence
                )

                return OVCCycleResult(
                    action_record=record,
                    observation=observation,
                    verification=verification,
                    corrected=corrected,
                    final_success=True,
                    iterations=iteration,
                    corrections_history=corrections_history
                )

            # ==========================================================
            # CORRECT (if we have retries left)
            # ==========================================================
            if iteration >= max_iterations:
                break

            # Check if verifier thinks this is auto-correctable
            if not verification.auto_correctable:
                # Not auto-correctable — fail fast
                break

            correction = self._generate_correction(
                action_type, action_name, description,
                current_result, observation, verification
            )

            if correction:
                corrections_history.append(correction)
                record.corrections_applied.append(correction)
                corrected = True
                self.state.update_action(
                    action_id,
                    corrections_applied=record.corrections_applied
                )
                self._correction_stats["total"] += 1
                # The execute_fn for next iteration should incorporate the correction.
                # In practice, the caller provides an execute_fn that can be retried,
                # or the correction is applied externally and execute_fn is called again.
                continue
            else:
                break

        # ==============================================================
        # FAILED after max iterations or non-correctable
        # ==============================================================
        record.status = ActionStatus.FAILED
        self.state.update_action(action_id, status=ActionStatus.FAILED)
        self.state.user.add_rejection(description)

        # Use last known verification, or build a default one
        if last_verification:
            final_ver = last_verification
        else:
            final_ver = VerificationResult(
                action_id=action_id,
                verified=False,
                confidence=0.0,
                discrepancies=record.discrepancies or ["Failed after corrections"],
                severity="critical",
                recommendation="Manual review required"
            )

        return OVCCycleResult(
            action_record=record,
            observation=last_observation if last_observation else ObservationResult(
                observation_type="unknown", target=description,
                expected=expected, actual=current_result or {},
                match=False, discrepancies=["No observation available"]
            ),
            verification=final_ver,
            corrected=corrected,
            final_success=False,
            iterations=iteration,
            corrections_history=corrections_history
        )

    # ------------------------------------------------------------------
    # Default observation routing
    # ------------------------------------------------------------------
    def _default_observe(self, action_type: str, action_name: str,
                         description: str, result: Dict[str, Any],
                         expected: Dict[str, Any]) -> ObservationResult:
        """Route to the right observation method based on action type."""

        if action_type == "tool":
            if action_name in ("write_file", "file_read"):
                path = expected.get("path") or result.get("file_path") or result.get("path")
                if path:
                    return self.observer.observe_file_system([path])
            elif action_name == "shell":
                command = expected.get("command", "")
                return self.observer.observe_command(command)
            elif action_name == "run_python":
                code = expected.get("code", "")
                return self.observer.observe_python_execution(code)
            elif action_name == "file_list":
                path = expected.get("path", ".")
                return self.observer.observe_file_system([path])

        elif action_type == "agent":
            output = result.get("result", "")
            if action_name == "coding_agent":
                # Coding agent: check files AND check for hallucination
                paths = expected.get("file_paths", [])
                file_obs = self.observer.observe_file_system(paths) if paths else None
                output_obs = self.observer.observe_agent_output(
                    description, output,
                    expected_elements=expected.get("expected_elements", [])
                )
                # Merge observations
                all_disc = []
                if file_obs and not file_obs.match:
                    all_disc.extend(file_obs.discrepancies)
                if not output_obs.match:
                    all_disc.extend(output_obs.discrepancies)
                # If agent claimed to create files but they don't exist, that's CRITICAL
                if output_obs.metadata.get("requires_verification") and paths:
                    if file_obs and not file_obs.match:
                        all_disc.insert(0, "AGENT HALLUCINATION: claimed to create files that do not exist")

                return ObservationResult(
                    observation_type="coding_agent",
                    target=description,
                    expected=expected,
                    actual={
                        "files": file_obs.actual if file_obs else {},
                        "output": output_obs.actual if output_obs else {}
                    },
                    match=len(all_disc) == 0,
                    discrepancies=all_disc,
                    metadata={"hallucination_risk": output_obs.metadata.get("hallucination_risk", "LOW")}
                )
            else:
                return self.observer.observe_agent_output(
                    description, output,
                    expected_elements=expected.get("expected_elements", [])
                )

        elif action_type == "plan_step":
            return ObservationResult(
                observation_type="plan_step",
                target=description,
                expected=expected,
                actual=result,
                match=result.get("success", False),
                discrepancies=[] if result.get("success") else [result.get("result", "Step failed")]
            )

        # Fallback
        return ObservationResult(
            observation_type="generic",
            target=description,
            expected=expected,
            actual=result,
            match=result.get("success", False),
            discrepancies=[] if result.get("success") else [result.get("result", "Unknown failure")]
        )

    # ------------------------------------------------------------------
    # Correction generation
    # ------------------------------------------------------------------
    def _generate_correction(self, action_type: str, action_name: str,
                             description: str, result: Dict[str, Any],
                             observation: ObservationResult,
                             verification: VerificationResult) -> Optional[str]:
        """Generate a correction strategy. Uses LLM if available, else heuristics."""

        # First: use verifier's hint if available
        if verification.correction_hint:
            return verification.correction_hint

        if not self.llm:
            return None

        prompt = f"""You are JARVIS's self-correction system. An action failed and needs to be fixed.

Action type: {action_type}
Action name: {action_name}
Description: {description}

Expected outcome: {observation.expected}
Actual outcome: {observation.actual}
Discrepancies:
{chr(10).join(f"- {d}" for d in observation.discrepancies)}
Severity: {verification.severity}

Current raw result: {result}

Provide ONE specific, concrete correction strategy. Be extremely specific.
Good examples:
- "Retry write_file with absolute path /home/user/project/main.py"
- "Add shebang #!/usr/bin/env python3 to the generated script"
- "Change command from 'python' to 'python3'"
- "Create parent directory with os.makedirs() before writing file"
- "Add timeout=60 to the shell command"
- "Install missing package: pip install requests"

Bad examples (too vague):
- "Fix the error"
- "Try again"
- "Check the code"

Correction strategy (one sentence, specific and actionable):"""

        try:
            correction = self.llm.generate(prompt, max_tokens=150).strip()
            # Validate: must be specific enough
            if len(correction) > 10 and not correction.lower().startswith(("fix", "try", "check")):
                return correction
        except Exception:
            pass

        return None

    def get_stats(self) -> Dict[str, Any]:
        """Return correction statistics."""
        total = self._correction_stats["total"]
        successful = self._correction_stats["successful"]
        rate = (successful / total * 100) if total > 0 else 0.0
        return {
            "corrections_attempted": total,
            "corrections_successful": successful,
            "success_rate": f"{rate:.1f}%"
        }
