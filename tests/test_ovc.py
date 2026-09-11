import os
import tempfile

from core.state import WorldState, ActionStatus, ActionRecord
from core.observer import Observer
from core.verifier import Verifier
from core.ovc_loop import OVCLoop


class MockLLM:
    def __init__(self, response="OK"):
        self.response = response
        self.calls = 0

    def generate(self, prompt, max_tokens=None):
        self.calls += 1
        return self.response


def test_world_state():
    print("\n=== Test: World State ===")

    ws = WorldState()

    assert ws.user.trust_level == 0.5
    assert ws.active_plan is None
    assert ws.action_history == []

    ws.user.name = "TestUser"
    ws.user.active_project = "TestProject"
    ws.user.active_goal = "TestGoal"

    assert ws.user.name == "TestUser"
    assert ws.user.active_project == "TestProject"
    assert ws.user.active_goal == "TestGoal"

    print("World state OK")


def test_observer():
    print("\n=== Test: Observer ===")

    observer = Observer()

    with tempfile.NamedTemporaryFile(
        mode="w",
        delete=False,
        encoding="utf-8",
    ) as f:
        f.write("JARVIS observer test")
        test_path = f.name

    try:
        result = observer.observe_file_system([test_path])

        assert result is not None
        assert result.observation_type == "file_system"
        assert result.match is True
        assert result.actual[test_path]["exists"] is True
        assert result.actual[test_path]["is_file"] is True
        assert result.actual[test_path]["size"] > 0

    finally:
        if os.path.exists(test_path):
            os.remove(test_path)

    print("Observer OK")


def test_verifier():
    print("\n=== Test: Verifier ===")

    verifier = Verifier()

    result = verifier.verify(
        expected={"exists": True},
        actual={"exists": True},
        discrepancies=[],
        action_type="tool",
        action_name="test_action",
    )

    assert result is not None
    assert result.verified is True
    assert result.confidence == 1.0
    assert result.severity == "none"
    assert result.is_trustworthy() is True

    print("Verifier OK")


def test_ovc_success():
    print("\n=== Test: OVC Success ===")

    ws = WorldState()
    observer = Observer(ws)
    verifier = Verifier()
    llm = MockLLM()

    loop = OVCLoop(
        llm_client=llm,
        world_state=ws,
        observer=observer,
        verifier=verifier,
    )

    result = loop.execute(
        action_type="plan_step",
        action_name="test_success",
        description="Test successful task",
        execute_fn=lambda: {
            "success": True,
            "result": "Task completed successfully.",
        },
        expected={
            "success": True,
        },
    )

    assert result is not None
    assert result.final_success is True
    assert result.verification.verified is True
    assert result.iterations == 1
    assert result.corrected is False
    assert result.action_record.status == ActionStatus.DONE

    print("OVC success OK")


def test_ovc_failure_then_correction():
    print("\n=== Test: OVC Failure Then Correction ===")

    ws = WorldState()
    observer = Observer(ws)
    verifier = Verifier()
    llm = MockLLM()

    state = {
        "fixed": False,
        "executions": 0,
        "corrections": [],
    }

    def execute_fn():
        state["executions"] += 1

        if not state["fixed"]:
            return {
                "success": False,
                "result": "Expected file does not exist",
            }

        return {
            "success": True,
            "result": "Corrected attempt succeeded",
        }

    def apply_correction_fn(correction, last_result):
        state["corrections"].append(correction)
        state["fixed"] = True
        return True

    loop = OVCLoop(
        llm_client=llm,
        world_state=ws,
        observer=observer,
        verifier=verifier,
    )

    result = loop.execute(
        action_type="plan_step",
        action_name="test_correction",
        description="Test correction flow",
        execute_fn=execute_fn,
        expected={
            "success": True,
        },
        apply_correction_fn=apply_correction_fn,
        max_iterations=3,
    )

    assert result is not None
    assert result.final_success is True
    assert result.corrected is True
    assert result.iterations == 2

    assert state["executions"] == 2
    assert len(state["corrections"]) == 1

    assert result.action_record.status == ActionStatus.CORRECTED
    assert len(result.corrections_history) == 1

    assert loop._correction_stats["total"] == 1
    assert loop._correction_stats["successful"] == 1

    print("OVC correction OK")


def test_ovc_hallucination_detection():
    print("\n=== Test: OVC Hallucination Detection ===")

    observer = Observer()

    result = observer.observe_agent_output(
        task="Create a test file",
        output="I have created the requested file successfully.",
        expected_elements=[],
    )

    assert result is not None
    assert result.match is True
    assert result.metadata["requires_verification"] is True
    assert result.metadata["hallucination_risk"] == "HIGH"

    assert "I have created" in result.metadata["claimed_actions"]

    print("Hallucination detection OK")


def test_state_checkpoint():
    print(
        "\n=== Test: State Checkpoint Persistence ==="
    )

    ws = WorldState()

    # --------------------------------------------------------------
    # Populate user state
    # --------------------------------------------------------------
    ws.user.name = "TestUser"
    ws.user.active_project = "TestProject"
    ws.user.active_goal = "Test checkpoint persistence"

    ws.user.preferences["response_style"] = "direct"

    ws.user.add_rejection(
        "Use the old implementation"
    )

    # --------------------------------------------------------------
    # Populate environment state
    # --------------------------------------------------------------
    ws.environment.track_file_creation(
        "/tmp/jarvis_created.txt"
    )

    ws.environment.track_file_modification(
        "/tmp/jarvis_modified.txt"
    )

    ws.environment.last_command_output = (
        "checkpoint test output"
    )

    ws.environment.last_command_exit_code = 0

    # --------------------------------------------------------------
    # Populate plan state
    # --------------------------------------------------------------
    ws.set_plan(
        "Test persistent plan",
        3,
    )

    ws.update_plan_step(
        1,
        "done",
    )

    ws.update_plan_step(
        2,
        "running",
    )

    # --------------------------------------------------------------
    # Populate action history
    # --------------------------------------------------------------
    action = ActionRecord(
        id="checkpoint_action_1",
        action_type="tool",
        action_name="write_file",
        description="Write checkpoint test file",
        expected_result={
            "exists": True,
        },
        actual_result={
            "exists": True,
        },
        status=ActionStatus.DONE,
        confidence=0.95,
        discrepancies=[
            "Initial test discrepancy"
        ],
        corrections_applied=[
            "Retried with correct path"
        ],
        latency_ms=42,
    )

    ws.record_action(action)

    # --------------------------------------------------------------
    # Populate questions / uncertainties
    # --------------------------------------------------------------
    ws.add_open_question(
        "Does checkpoint persistence survive restart?"
    )

    ws.add_uncertainty(
        "Checkpoint format may evolve."
    )

    # --------------------------------------------------------------
    # Save checkpoint
    # --------------------------------------------------------------
    checkpoint_path = (
        "/tmp/jarvis_test_checkpoint.json"
    )

    ws.save_checkpoint(
        checkpoint_path
    )

    assert os.path.exists(
        checkpoint_path
    )

    # --------------------------------------------------------------
    # Restore into a fresh WorldState
    # --------------------------------------------------------------
    restored = WorldState.load_checkpoint(
        checkpoint_path
    )

    assert restored is not None

    # --------------------------------------------------------------
    # Verify core state
    # --------------------------------------------------------------
    assert (
        restored.session_id
        == ws.session_id
    )

    assert (
        restored._state_version
        == ws._state_version
    )

    # --------------------------------------------------------------
    # Verify user state
    # --------------------------------------------------------------
    assert (
        restored.user.name
        == "TestUser"
    )

    assert (
        restored.user.active_project
        == "TestProject"
    )

    assert (
        restored.user.active_goal
        == "Test checkpoint persistence"
    )

    assert (
        restored.user.preferences[
            "response_style"
        ]
        == "direct"
    )

    assert (
        restored.user.recent_rejections
        == ["Use the old implementation"]
    )

    # add_rejection reduces trust from 0.5 to 0.45
    assert (
        restored.user.trust_level
        == 0.45
    )

    # --------------------------------------------------------------
    # Verify environment state
    # --------------------------------------------------------------
    assert (
        "/tmp/jarvis_created.txt"
        in restored.environment.files_created_this_session
    )

    assert (
        "/tmp/jarvis_modified.txt"
        in restored.environment.files_modified_this_session
    )

    assert (
        restored.environment.last_command_output
        == "checkpoint test output"
    )

    assert (
        restored.environment.last_command_exit_code
        == 0
    )

    # --------------------------------------------------------------
    # Verify plan state
    # --------------------------------------------------------------
    assert restored.active_plan is not None

    assert (
        restored.active_plan.goal
        == "Test persistent plan"
    )

    assert (
        restored.active_plan.total_steps
        == 3
    )

    assert (
        restored.active_plan.step_statuses[1]
        == "done"
    )

    assert (
        restored.active_plan.step_statuses[2]
        == "running"
    )

    assert (
        restored.active_plan.step_statuses[3]
        == "pending"
    )

    # --------------------------------------------------------------
    # Verify action history
    # --------------------------------------------------------------
    assert len(
        restored.action_history
    ) == 1

    restored_action = (
        restored.action_history[0]
    )

    assert (
        restored_action.id
        == "checkpoint_action_1"
    )

    assert (
        restored_action.action_type
        == "tool"
    )

    assert (
        restored_action.action_name
        == "write_file"
    )

    assert (
        restored_action.description
        == "Write checkpoint test file"
    )

    assert (
        restored_action.expected_result
        == {"exists": True}
    )

    assert (
        restored_action.actual_result
        == {"exists": True}
    )

    assert (
        restored_action.status
        == ActionStatus.DONE
    )

    assert (
        restored_action.confidence
        == 0.95
    )

    assert (
        restored_action.discrepancies
        == ["Initial test discrepancy"]
    )

    assert (
        restored_action.corrections_applied
        == ["Retried with correct path"]
    )

    assert (
        restored_action.latency_ms
        == 42
    )

    # --------------------------------------------------------------
    # Verify questions / uncertainties
    # --------------------------------------------------------------
    assert (
        restored.open_questions
        == [
            "Does checkpoint persistence survive restart?"
        ]
    )

    assert (
        restored.uncertainties
        == [
            "Checkpoint format may evolve."
        ]
    )

    # --------------------------------------------------------------
    # Cleanup
    # --------------------------------------------------------------
    if os.path.exists(
        checkpoint_path
    ):
        os.remove(
            checkpoint_path
        )

    print(
        "State checkpoint persistence OK"
    )


if __name__ == "__main__":
    test_world_state()
    test_observer()
    test_verifier()
    test_ovc_success()
    test_ovc_failure_then_correction()
    test_ovc_hallucination_detection()
    test_state_checkpoint()
