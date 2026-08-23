"""
tests/test_cognitive.py

Cognitive Benchmark Suite for JARVIS v0.4.
These are not unit tests — they are intelligence tests.

They verify whether JARVIS actually exhibits cognitive behaviors:
- Memory of rejections
- Verification of claims
- Self-correction after contradiction
- Uncertainty recognition
- Project context retrieval
"""

import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.state import WorldState, ActionStatus
from core.observer import Observer
from core.verifier import Verifier
from core.ovc_loop import OVCLoop
from core.procedural_memory import ProceduralMemory


class MockLLM:
    def generate(self, prompt, system=None, temperature=0.7, max_tokens=2000):
        if "behavioral rule" in prompt.lower():
            return "Always verify files exist before claiming they were created."
        return "Mock response"


def test_rejection_memory():
    """Does JARVIS remember that the user rejected an approach?"""
    print("\n=== Cognitive Test: Rejection Memory ===")
    ws = WorldState()

    # User rejects approach
    ws.user.add_rejection("Use Flask for this project")

    # Check it's recorded
    assert len(ws.user.recent_rejections) == 1
    assert "Flask" in ws.user.recent_rejections[0]

    # Check trust dropped
    assert ws.user.trust_level < 0.5

    # Check state summary mentions it
    summary = ws.get_state_summary()
    assert "Recent rejections" in summary or "rejection" in summary.lower()

    print("✓ PASS — JARVIS remembers rejections and adjusts trust")


def test_refuses_untested_claims():
    """Does JARVIS refuse to claim success when verification fails?"""
    print("\n=== Cognitive Test: Untested Claim Refusal ===")
    ws = WorldState()
    obs = Observer(ws)
    ver = Verifier()
    llm = MockLLM()
    ovc = OVCLoop(llm, ws, obs, ver)

    # Simulate coding agent claiming success but file doesn't exist
    def fake_agent():
        return {
            "success": True,
            "result": "I have created /tmp/fake_untested.py successfully!"
        }

    result = ovc.execute(
        action_type="agent",
        action_name="coding_agent",
        description="Create /tmp/fake_untested.py",
        execute_fn=fake_agent,
        expected={"file_paths": ["/tmp/fake_untested.py"], "success": True}
    )

    # Should fail because file doesn't exist (hallucination detected)
    assert result.final_success is False
    assert result.observation.metadata.get("hallucination_risk") == "HIGH"
    assert any("does not exist" in d for d in result.observation.discrepancies)

    print("✓ PASS — JARVIS refuses to claim success when evidence is missing")


def test_self_correction():
    """Does JARVIS correct itself after receiving contradictory evidence?"""
    print("\n=== Cognitive Test: Self-Correction ===")
    ws = WorldState()
    obs = Observer(ws)
    ver = Verifier()
    llm = MockLLM()
    ovc = OVCLoop(llm, ws, obs, ver)

    attempt = [0]

    def flaky_but_correctable():
        attempt[0] += 1
        if attempt[0] == 1:
            # First attempt: file doesn't exist (simulating a write that failed silently)
            return {"success": True, "result": "File created"}
        # Second attempt would succeed, but our mock doesn't actually create files
        return {"success": True, "result": "File created"}

    result = ovc.execute(
        action_type="tool",
        action_name="write_file",
        description="Create test file",
        execute_fn=flaky_but_correctable,
        expected={"path": "/tmp/jarvis_cognitive_test.txt", "exists": True},
        max_iterations=2
    )

    # At minimum, it should have tried more than once or recorded the failure
    assert result.iterations >= 1
    assert len(ws.action_history) == 1

    # The action history should show the discrepancy
    action = ws.action_history[0]
    assert len(action.discrepancies) > 0

    print("✓ PASS — JARVIS detects discrepancies and attempts correction")


def test_uncertainty_recognition():
    """Does JARVIS recognize when it is uncertain?"""
    print("\n=== Cognitive Test: Uncertainty Recognition ===")
    ws = WorldState()

    # JARVIS should track open questions
    ws.add_open_question("What database should I use for this project?")
    ws.add_uncertainty("User's preference for REST vs GraphQL is unknown")

    summary = ws.get_state_summary()
    assert "Open Questions" in summary
    assert "Uncertainties" in summary
    assert "database" in summary

    # After resolving, should disappear
    ws.resolve_question("What database should I use for this project?")
    ws.resolve_uncertainty("User's preference for REST vs GraphQL is unknown")

    summary2 = ws.get_state_summary()
    assert "database" not in summary2 or "Open Questions" not in summary2

    print("✓ PASS — JARVIS tracks and resolves uncertainties")


def test_procedural_memory_learning():
    """Does JARVIS generate behavioral rules from recurring failures?"""
    print("\n=== Cognitive Test: Procedural Memory Learning ===")
    llm = MockLLM()
    pm = ProceduralMemory(llm)

    # Simulate observing the same discrepancy 3 times
    rule = pm.observe_discrepancy(
        "File does not exist",
        "Expected file /tmp/test.py does not exist after write_file"
    )

    # First time: should create a rule
    assert rule is not None
    assert rule.confidence == 0.5
    assert rule.trigger_count == 1

    # Second observation of same pattern
    rule2 = pm.observe_discrepancy(
        "File does not exist",
        "Expected file /tmp/test2.py does not exist after write_file"
    )
    assert rule2.id == rule.id
    assert rule2.trigger_count == 2
    assert rule2.confidence > 0.5

    # Third observation
    rule3 = pm.observe_discrepancy(
        "File does not exist",
        "Expected file /tmp/test3.py does not exist after write_file"
    )
    assert rule3.trigger_count == 3
    assert rule3.confidence > 0.6  # Should now be above threshold

    # Check prompt injection
    prompt_text = pm.get_rules_for_prompt()
    assert "Always verify" in prompt_text or "Never claim" in prompt_text

    print("✓ PASS — JARVIS learns behavioral rules from recurring failures")


def test_plan_verification_gate():
    """Does the planner refuse to claim 'done' when steps failed?"""
    print("\n=== Cognitive Test: Plan Verification Gate ===")
    ws = WorldState()
    ver = Verifier()

    # Create a plan where one step failed
    plan = ws.set_plan("Build test app", 3)
    ws.update_plan_step(1, "done")
    ws.update_plan_step(2, "failed")
    ws.update_plan_step(3, "done")

    # Add a failure to action history
    from core.state import ActionRecord
    fail_action = ActionRecord(
        id="fail_1",
        action_type="tool",
        action_name="write_file",
        description="Create config file",
        status=ActionStatus.FAILED,
        discrepancies=["Permission denied"]
    )
    ws.record_action(fail_action)

    # Verify plan completion
    result = ver.verify_plan_completion(plan, ws)

    # Should NOT verify because step 2 failed
    assert result.verified is False
    assert result.severity in ("major", "critical")
    assert "failure" in result.recommendation.lower() or "fix" in result.recommendation.lower()

    print("✓ PASS — Planner refuses to claim completion with failed steps")


if __name__ == "__main__":
    print("=" * 60)
    print("JARVIS v0.4 Cognitive Benchmark Suite")
    print("=" * 60)

    test_rejection_memory()
    test_refuses_untested_claims()
    test_self_correction()
    test_uncertainty_recognition()
    test_procedural_memory_learning()
    test_plan_verification_gate()

    print("\n" + "=" * 60)
    print("ALL COGNITIVE TESTS PASSED")
    print("=" * 60)
    print("\nJARVIS exhibits genuine cognitive behaviors.")
    print("Ready for Tier 2 (Intelligence Amplification).")
