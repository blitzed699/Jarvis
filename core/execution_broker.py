"""
core/execution_broker.py

Execution Broker — Central gateway for ALL tool and agent execution.
Every file write, shell command, Python execution, and agent task
must pass through here. No exceptions.

Responsibilities:
  1. Safety gate (capability checks + approval)
  2. OVC loop (observe, verify, correct)
  3. Evidence collection
  4. Correction application
"""

import re
from typing import Dict, Any, Optional, Callable


class ExecutionBroker:
    """
    Central execution gateway. All agents and tools route through here.
    """

    def __init__(self, tool_router, safety_gate, ovc_loop, world_state):
        self.router = tool_router
        self.safety = safety_gate
        self.ovc = ovc_loop
        self.state = world_state

    # ==================================================================
    # TOOL EXECUTION
    # ==================================================================
    def execute_tool(self, tool_call: Dict[str, Any], description: str = "",
                     expected: Dict[str, Any] = None,
                     project_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute a tool call through the full safety + OVC pipeline.
        """
        tool_name = tool_call.get("tool", "")
        params = tool_call.get("params", {})

        # 1. Safety gate
        is_approved, reason = self.safety.check_tool_call(tool_name, params)
        if not is_approved:
            approved = self.safety.request_approval(tool_name, params, reason)
            if not approved:
                return {
                    "success": False,
                    "result": f"Safety gate denied: {reason}",
                    "evidence": [],
                    "safety_blocked": True
                }

        # 2. Predict expected outcome
        predicted = expected or self._predict_tool_outcome(tool_name, params)

        # 3. OVC execution with correction support
        def execute_fn():
            return self.router.execute(tool_call)

        def apply_correction(correction: str, last_result: Dict[str, Any]) -> bool:
            return self._apply_tool_correction(correction, tool_call, last_result)

        ovc_result = self.ovc.execute(
            action_type="tool",
            action_name=tool_name,
            description=description or f"Execute {tool_name}",
            execute_fn=execute_fn,
            expected=predicted,
            apply_correction_fn=apply_correction,
            project_id=project_id
        )

        return {
            "success": ovc_result.final_success,
            "result": ovc_result.action_record.actual_result,
            "ovc": ovc_result.to_dict(),
            "evidence": [e.__dict__ for e in ovc_result.evidence],
            "discrepancies": ovc_result.observation.discrepancies,
            "recommendation": ovc_result.verification.recommendation
        }

    # ==================================================================
    # AGENT EXECUTION
    # ==================================================================
    def execute_agent(self, agent_name: str, task: str, agent_instance,
                      expected_files: list = None) -> Dict[str, Any]:
        """
        Execute an agent task through the full OVC + critic pipeline.
        """
        def execute_fn():
            return agent_instance.run(task)

        def apply_correction(correction: str, last_result: Dict[str, Any]) -> bool:
            # Agent corrections are domain-specific
            # For now, we cannot automatically patch agent outputs
            # The correction is logged and the agent must be re-invoked externally
            return False

        ovc_result = self.ovc.execute(
            action_type="agent",
            action_name=agent_name,
            description=task,
            execute_fn=execute_fn,
            expected={"file_paths": expected_files or [], "success": True},
            apply_correction_fn=apply_correction,
            run_critic=True  # Enable critic gate for all agent tasks
        )

        return {
            "success": ovc_result.final_success,
            "result": ovc_result.action_record.actual_result,
            "ovc": ovc_result.to_dict(),
            "evidence": [e.__dict__ for e in ovc_result.evidence],
            "critic_verdict": ovc_result.critic_verdict,
            "discrepancies": ovc_result.observation.discrepancies
        }

    # ==================================================================
    # CORRECTION APPLICATION (Tool-specific)
    # ==================================================================
    def _apply_tool_correction(self, correction: str, tool_call: Dict[str, Any],
                                last_result: Dict[str, Any]) -> bool:
        """
        Heuristic correction parser for common tool failures.
        Returns True if the tool_call was successfully modified.
        """
        params = tool_call.get("params", {})
        tool_name = tool_call.get("tool", "")

        # File path corrections
        if tool_name in ("write_file", "file_read", "file_list"):
            # Look for absolute path suggestions
            path_match = re.search(r'(?:absolute path|path|to)\s+([/\w\.\-]+)', correction, re.I)
            if path_match:
                new_path = path_match.group(1).strip()
                params["path"] = new_path
                return True

            # Create parent directories
            if "parent director" in correction.lower() or "makedirs" in correction.lower():
                import os
                path = params.get("path", "")
                if path:
                    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
                    return True

        # Shell command corrections
        if tool_name == "shell":
            # Change python to python3
            if "python3" in correction.lower() and "python" in params.get("command", ""):
                params["command"] = params["command"].replace("python ", "python3 ")
                return True

            # Add timeout
            timeout_match = re.search(r'timeout[=:]?\s*(\d+)', correction, re.I)
            if timeout_match:
                # Can't easily add timeout to existing command, but we note it
                pass

            # Install missing package
            pkg_match = re.search(r'pip install\s+([a-zA-Z0-9_\-]+)', correction, re.I)
            if pkg_match:
                pkg = pkg_match.group(1)
                params["command"] = f"pip install {pkg} && {params.get('command', '')}"
                return True

        # Python code corrections
        if tool_name == "run_python":
            # Add missing import
            import_match = re.search(r'import\s+([a-zA-Z0-9_\.]+)', correction, re.I)
            if import_match:
                module = import_match.group(1)
                params["code"] = f"import {module}\n" + params.get("code", "")
                return True

            # Add shebang (only relevant if writing to file, not run_python)
            if "shebang" in correction.lower():
                pass  # Not applicable to inline execution

        return False

    # ==================================================================
    # EXPECTATION PREDICTION
    # ==================================================================
    def _predict_tool_outcome(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name in ("write_file", "file_read"):
            return {"path": params.get("path"), "exists": True}
        elif tool_name == "shell":
            return {"command": params.get("command"), "exit_code": 0}
        elif tool_name == "run_python":
            return {"code": params.get("code"), "success": True}
        elif tool_name == "file_list":
            return {"path": params.get("path", "."), "exists": True}
        return {}
