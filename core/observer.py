"""
core/observer.py

The Observation Engine — JARVIS's eyes.
After every action, this checks what ACTUALLY happened in the world,
not what the LLM claimed happened.
"""

import os
import re
import subprocess
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field


@dataclass
class ObservationResult:
    """Result of observing the world after an action."""
    observation_type: str
    target: str
    expected: Any
    actual: Any
    match: bool
    discrepancies: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class Observer:
    """
    Observes the actual world state after every action.
    This prevents hallucinations of completion.
    """

    def __init__(self, world_state=None):
        self.state = world_state

    # ------------------------------------------------------------------
    # File system observations
    # ------------------------------------------------------------------
    def observe_file_system(self, expected_paths: List[str]) -> ObservationResult:
        """Check if expected files exist and have non-zero size."""
        discrepancies = []
        actual = {}

        for path in expected_paths:
            exists = os.path.exists(path)
            actual[path] = {
                "exists": exists,
                "size": os.path.getsize(path) if exists else 0,
                "is_file": os.path.isfile(path) if exists else False,
                "is_dir": os.path.isdir(path) if exists else False,
            }
            if not exists:
                discrepancies.append(f"Expected file '{path}' does not exist")
            elif actual[path]["size"] == 0:
                discrepancies.append(f"File '{path}' exists but is empty")

        return ObservationResult(
            observation_type="file_system",
            target=str(expected_paths),
            expected={"paths": expected_paths, "all_exist": True},
            actual=actual,
            match=len(discrepancies) == 0,
            discrepancies=discrepancies
        )

    def observe_file_content(self, path: str, expected_content: Optional[str] = None,
                             expected_patterns: List[str] = None) -> ObservationResult:
        """Observe the content of a file for expected strings or patterns."""
        discrepancies = []

        if not os.path.exists(path):
            return ObservationResult(
                observation_type="file_content",
                target=path,
                expected={"content": expected_content, "patterns": expected_patterns},
                actual=None,
                match=False,
                discrepancies=[f"File '{path}' does not exist"]
            )

        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                actual_content = f.read()
        except Exception as e:
            return ObservationResult(
                observation_type="file_content",
                target=path,
                expected={"content": expected_content},
                actual=None,
                match=False,
                discrepancies=[f"Cannot read file '{path}': {str(e)}"]
            )

        if expected_content and expected_content not in actual_content:
            discrepancies.append(f"Expected content not found in '{path}'")

        if expected_patterns:
            for pattern in expected_patterns:
                if not re.search(pattern, actual_content):
                    discrepancies.append(f"Expected pattern '{pattern}' not found in '{path}'")

        return ObservationResult(
            observation_type="file_content",
            target=path,
            expected={"content": expected_content, "patterns": expected_patterns},
            actual={"content": actual_content[:2000], "length": len(actual_content)},
            match=len(discrepancies) == 0,
            discrepancies=discrepancies
        )

    # ------------------------------------------------------------------
    # Command / execution observations
    # ------------------------------------------------------------------
    def observe_command(self, command: str, expected_output: Optional[str] = None,
                        expected_exit_code: int = 0, timeout: int = 30) -> ObservationResult:
        """Observe the result of a shell command."""
        discrepancies = []

        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=timeout
            )
            actual = {
                "stdout": result.stdout[:3000],
                "stderr": result.stderr[:1500],
                "exit_code": result.returncode,
            }

            if expected_exit_code is not None and result.returncode != expected_exit_code:
                discrepancies.append(
                    f"Expected exit code {expected_exit_code}, got {result.returncode}"
                )

            if expected_output and expected_output not in result.stdout:
                discrepancies.append(f"Expected output '{expected_output}' not found in stdout")

            if result.returncode != 0 and result.stderr:
                discrepancies.append(f"Stderr: {result.stderr[:300]}")

        except subprocess.TimeoutExpired:
            actual = {"stdout": "", "stderr": f"Command timed out after {timeout}s", "exit_code": -1}
            discrepancies.append(f"Command timed out after {timeout}s")
        except Exception as e:
            actual = {"stdout": "", "stderr": str(e), "exit_code": -1}
            discrepancies.append(f"Command execution failed: {str(e)}")

        return ObservationResult(
            observation_type="command",
            target=command,
            expected={"exit_code": expected_exit_code, "output": expected_output},
            actual=actual,
            match=len(discrepancies) == 0,
            discrepancies=discrepancies
        )

    def observe_python_execution(self, code: str, expected_result: Optional[str] = None,
                                  expected_patterns: List[str] = None) -> ObservationResult:
        """Observe the result of Python code execution in a controlled way."""
        discrepancies = []

        try:
            import io
            import sys
            from contextlib import redirect_stdout, redirect_stderr

            stdout_buffer = io.StringIO()
            stderr_buffer = io.StringIO()

            with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                exec(code, {"__builtins__": __builtins__}, {})

            actual_stdout = stdout_buffer.getvalue()
            actual_stderr = stderr_buffer.getvalue()

            actual = {
                "stdout": actual_stdout[:3000],
                "stderr": actual_stderr[:1500],
            }

            if actual_stderr:
                discrepancies.append(f"Python stderr: {actual_stderr[:300]}")

            if expected_result and expected_result not in actual_stdout:
                discrepancies.append(f"Expected result '{expected_result}' not in output")

            if expected_patterns:
                for pattern in expected_patterns:
                    if not re.search(pattern, actual_stdout):
                        discrepancies.append(f"Expected pattern '{pattern}' not in output")

        except Exception as e:
            actual = {"stdout": "", "stderr": str(e)}
            discrepancies.append(f"Python execution failed: {str(e)}")

        return ObservationResult(
            observation_type="python_execution",
            target=code[:120],
            expected={"result": expected_result, "patterns": expected_patterns},
            actual=actual,
            match=len(discrepancies) == 0,
            discrepancies=discrepancies
        )

    # ------------------------------------------------------------------
    # Agent output observations
    # ------------------------------------------------------------------
    def observe_agent_output(self, task: str, output: str,
                             expected_elements: List[str] = None) -> ObservationResult:
        """Observe an agent's output for expected elements and hallucination indicators."""
        discrepancies = []

        if expected_elements:
            for element in expected_elements:
                if element not in output:
                    discrepancies.append(f"Expected element '{element}' not found in output")

        # Detect hallucination of completion
        hallucination_indicators = [
            "I have created", "I have written", "I have saved",
            "I have built", "I have generated", "File created successfully",
            "Code has been written", "The app is ready"
        ]
        claimed_actions = []
        for indicator in hallucination_indicators:
            if indicator.lower() in output.lower():
                claimed_actions.append(indicator)

        # If the agent claims to have created something, we MUST verify it exists
        requires_verification = len(claimed_actions) > 0

        return ObservationResult(
            observation_type="agent_output",
            target=task[:100],
            expected={"elements": expected_elements},
            actual={
                "output_length": len(output),
                "claimed_actions": claimed_actions,
                "requires_verification": requires_verification,
            },
            match=len(discrepancies) == 0,
            discrepancies=discrepancies,
            metadata={
                "claimed_actions": claimed_actions,
                "requires_verification": requires_verification,
                "hallucination_risk": "HIGH" if requires_verification else "LOW"
            }
        )

    # ------------------------------------------------------------------
    # Memory observations
    # ------------------------------------------------------------------
    def observe_memory_retrieval(self, query: str, expected_facts: List[str],
                                  memory_client) -> ObservationResult:
        """Observe whether memory retrieval returned expected facts."""
        discrepancies = []

        try:
            results = memory_client.get_relevant_memories(query)
            retrieved_content = [r.get("content", "") for r in results]

            for fact in expected_facts:
                found = any(fact.lower() in content.lower() for content in retrieved_content)
                if not found:
                    discrepancies.append(f"Expected fact '{fact}' not retrieved")

            actual = {
                "retrieved_count": len(results),
                "retrieved_snippets": [c[:200] for c in retrieved_content[:5]],
            }
        except Exception as e:
            actual = {"error": str(e)}
            discrepancies.append(f"Memory retrieval failed: {str(e)}")

        return ObservationResult(
            observation_type="memory",
            target=query,
            expected={"facts": expected_facts},
            actual=actual,
            match=len(discrepancies) == 0,
            discrepancies=discrepancies
        )

    # ------------------------------------------------------------------
    # Deep diff utility
    # ------------------------------------------------------------------
    def diff(self, expected: Dict[str, Any], actual: Dict[str, Any],
             path: str = "") -> List[str]:
        """Deep diff between expected and actual state."""
        discrepancies = []

        for key in expected:
            current_path = f"{path}.{key}" if path else key
            if key not in actual:
                discrepancies.append(f"Missing key '{current_path}' in actual")
                continue

            exp_val = expected[key]
            act_val = actual[key]

            if isinstance(exp_val, dict) and isinstance(act_val, dict):
                discrepancies.extend(self.diff(exp_val, act_val, current_path))
            elif exp_val != act_val:
                discrepancies.append(
                    f"Mismatch at '{current_path}': expected {repr(exp_val)}, got {repr(act_val)}"
                )

        for key in actual:
            if key not in expected:
                current_path = f"{path}.{key}" if path else key
                discrepancies.append(f"Unexpected key '{current_path}' in actual")

        return discrepancies
