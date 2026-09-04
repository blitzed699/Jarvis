"""
core/ovc_loop.py

Observe → Verify → Correct Loop (v0.4.1)
- Corrections are now actually applied via apply_correction_fn callback
- Critic is properly integrated as a pre-verification gate
- Evidence is collected and returned
- Successful corrections are tracked
"""

import time
import hashlib
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field

from .state import WorldState, ActionRecord, ActionStatus
from .observer import Observer, ObservationResult
from .verifier import Verifier, VerificationResult


@dataclass
class Evidence:
    """Structured evidence that a claim is true."""
    evidence_type: str  # filesystem, execution, test, critic, network
    claim: str
    data: Dict[str, Any]
    confidence: float
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))


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
    critic_verdict: Optional[str] = None  # PASS, NEEDS_FIX, REJECT, or None
    evidence: List[Evidence] = field(default_factory=list)

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
            "critic_verdict": self.critic_verdict,
            "evidence_count": len(self.evidence),
        }


class OVCLoop:
    """
    Observe → Verify → Correct Loop

    Usage:
        ovc = OVCLoop(llm, world_state, observer, verifier, critic_fn=optional_critic)
        result = ovc.execute(
            action_type="tool",
            action_name="write_file",
            description="Create hello.py",
            execute_fn=lambda: tool.run(...),
            expected={"path": "/tmp/hello.py", "exists": True},
            apply_correction_fn=my_correction_handler,  # ← NEW: actually applies fixes
            run_critic=True  # ← NEW: enable critic gate
        )
    """

    MAX_ITERATIONS = 3

    def __init__(self, llm_client, world_state: WorldState,
                 observer: Observer, verifier: Verifier,
                 critic_fn: Optional[Callable] = None):
        self.llm = llm_client
        self.state = world_state
        self.observer = observer
        self.verifier = verifier
        self.critic_fn = critic_fn
        self._correction_stats = {"total": 0, "successful": 0}

    def execute(self, action_type: str, action_name: str, description: str,
                execute_fn: Callable[[], Dict[str, Any]],
                expected: Dict[str, Any],
                observe_fn: Optional[Callable] = None,
                apply_correction_fn: Optional[Callable[[str, Dict[str, Any]], bool]] = None,
                max_iterations: int = MAX_ITERATIONS,
                project_id: Optional[str] = None,
                run_critic: bool = False) -> OVCCycleResult:
        """
        Execute an action within the OVC loop.

        Args:
            apply_correction_fn: callback(correction_str, last_result) -> bool
                Should modify the execution context and return True if applied.
            run_critic: if True and critic_fn is set, run critic before verification.
        """
        action_id = f"act_{int(time.time() * 1000)}_{hashlib.md5(description.encode()).hexdigest()[:4]}"
        corrections_history = []
        evidence_list = []

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
        critic_verdict = None

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
                    corrections_history=corrections_history,
                    evidence=evidence_list
                )

            # ==========================================================
            # CRITIC GATE (optional, for agent outputs)
            # ==========================================================
            if run_critic and self.critic_fn and action_type == "agent":
                try:
                    critic_output = self.critic_fn(description, str(current_result.get("result", "")))
                    critic_verdict = critic_output.get("verdict", "PASS")
                    if critic_verdict == "REJECT":
                        # Critic rejects → hard fail, no retry
                        obs = self._default_observe(action_type, action_name, description, current_result, expected)
                        ver = VerificationResult(
                            action_id=action_id,
                            verified=False,
                            confidence=0.0,
                            discrepancies=[f"CRITIC REJECT: {critic_output.get('review', '')}"],
                            severity="critical",
                            recommendation="HALT — critic rejected output. Replan required.",
                            auto_correctable=False
                        )
                        record.status = ActionStatus.FAILED
                        self.state.update_action(action_id, status=ActionStatus.FAILED)
                        return OVCCycleResult(
                            action_record=record,
                            observation=obs,
                            verification=ver,
                            corrected=False,
                            final_success=False,
                            iterations=iteration,
                            corrections_history=corrections_history,
                            critic_verdict="REJECT",
                            evidence=evidence_list
                        )
                    elif critic_verdict == "NEEDS_FIX":
                        # Force a discrepancy so verification fails
                        current_result["_critic_issues"] = critic_output.get("review", "")
                except Exception:
                    critic_verdict = None

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

            # Collect evidence from observation
            evidence_list.extend(self._extract_evidence(observation, action_name))

            # ==========================================================
            # VERIFY
            # ==========================================================
            # If critic said NEEDS_FIX, inject it as a critical discrepancy
            discrepancies = list(observation.discrepancies)
            if current_result and "_critic_issues" in current_result:
                discrepancies.insert(0, f"CRITIC NEEDS_FIX: {current_result['_critic_issues']}")

            verification = self.verifier.verify(
                expected, observation.actual,
                discrepancies, action_type, action_name
            )
            verification.action_id = action_id
            last_verification = verification

            # Update record with observation results
            record.actual_result = observation.actual
            record.discrepancies = discrepancies

            # ==========================================================
            # DECIDE: success or correct?
            # ==========================================================
            if verification.verified and critic_verdict != "NEEDS_FIX":
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
                    corrections_history=corrections_history,
                    critic_verdict=critic_verdict,
                    evidence=evidence_list
                )

            # ==========================================================
            # CORRECT (if we have retries left)
            # ==========================================================
            if iteration >= max_iterations:
                break

            # Check if verifier thinks this is auto-correctable
            if not verification.auto_correctable and critic_verdict != "NEEDS_FIX":
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

                # ======================================================
                # ACTUALLY APPLY THE CORRECTION
                # ======================================================
                if apply_correction_fn:
                    applied = apply_correction_fn(correction, current_result)
                    if applied:
                        self._correction_stats["successful"] += 1
                        continue  # Retry with corrected execution
                    else:
                        # Correction couldn't be applied → stop wasting retries
                        break
                else:
                    # No correction handler provided → we can only record and retry blindly
                    # This is a known limitation for some action types
                    continue
            else:
                break

        # ==============================================================
        # FAILED after max iterations or non-correctable
        # ==============================================================
        record.status = ActionStatus.FAILED
        self.state.update_action(action_id, status=ActionStatus.FAILED)
        self.state.user.add_rejection(description)

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
            corrections_history=corrections_history,
            critic_verdict=critic_verdict,
            evidence=evidence_list
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
                paths = expected.get("file_paths", [])
                file_obs = self.observer.observe_file_system(paths) if paths else None
                output_obs = self.observer.observe_agent_output(
                    description, output,
                    expected_elements=expected.get("expected_elements", [])
                )
                all_disc = []
                if file_obs and not file_obs.match:
                    all_disc.extend(file_obs.discrepancies)
                if not output_obs.match:
                    all_disc.extend(output_obs.discrepancies)
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

        return ObservationResult(
            observation_type="generic",
            target=description,
            expected=expected,
            actual=result,
            match=result.get("success", False),
            discrepancies=[] if result.get("success") else [result.get("result", "Unknown failure")]
        )

    # ------------------------------------------------------------------
    # Evidence extraction
    # ------------------------------------------------------------------
    def _extract_evidence(self, observation: ObservationResult, action_name: str) -> List[Evidence]:
        """Convert observation results into structured evidence."""
        evidence = []
        now = time.strftime("%Y-%m-%dT%H:%M:%S")

        if observation.observation_type == "file_system":
            for path, info in observation.actual.items():
                evidence.append(Evidence(
                    evidence_type="filesystem",
                    claim=f"File {path} exists and is valid",
                    data=info,
                    confidence=1.0 if info.get("exists") else 0.0,
                    timestamp=now
                ))

        elif observation.observation_type == "command":
            evidence.append(Evidence(
                evidence_type="execution",
                claim=f"Command exited with code {observation.actual.get('exit_code')}",
                data=observation.actual,
                confidence=1.0 if observation.actual.get('exit_code') == 0 else 0.0,
                timestamp=now
            ))

        elif observation.observation_type == "python_execution":
            evidence.append(Evidence(
                evidence_type="execution",
                claim="Python code executed",
                data=observation.actual,
                confidence=0.0 if observation.actual.get('stderr') else 1.0,
                timestamp=now
            ))

        elif observation.observation_type == "agent_output":
            evidence.append(Evidence(
                evidence_type="critic",
                claim="Agent output reviewed for hallucinations",
                data={
                    "claimed_actions": observation.metadata.get("claimed_actions", []),
                    "requires_verification": observation.metadata.get("requires_verification", False)
                },
                confidence=0.0 if observation.metadata.get("requires_verification") else 1.0,
                timestamp=now
            ))

        return evidence

    # ------------------------------------------------------------------
    # Correction generation
    # ------------------------------------------------------------------
    def _generate_correction(self, action_type: str, action_name: str,
                             description: str, result: Dict[str, Any],
                             observation: ObservationResult,
                             verification: VerificationResult) -> Optional[str]:
        """Generate a correction strategy. Uses LLM if available, else heuristics."""

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
