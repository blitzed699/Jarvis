import json
import time
from typing import Dict, Any, List
from dataclasses import dataclass, asdict


@dataclass
class Subtask:
    id: int
    description: str
    agent: str
    status: str = "pending"
    result: str = ""
    depends_on: List[int] = None

    def __post_init__(self):
        if self.depends_on is None:
            self.depends_on = []


PLANNER_PERSONA = """You are a task planner. Break the user's goal into numbered subtasks.
Each subtask must specify who handles it using ONLY these options:
- coding_agent (for writing code, scripts, apps)
- research_agent (for gathering information, analysis)
- business_agent (for market analysis, business strategy)
- creative_agent (for design, branding, copywriting)
- tool (for file operations, shell commands, web search)
- llm (for direct text generation, summaries, explanations)

Return ONLY a JSON array:
[{"id": 1, "description": "...", "agent": "coding_agent", "depends_on": []}]"""


class AutonomousPlanner:
    def __init__(self, llm_client, agent_registry, tool_router, safety_gate, evolution_tracker):
        self.llm = llm_client
        self.agents = agent_registry
        self.router = tool_router
        self.safety = safety_gate
        self.evolution = evolution_tracker
        self.tasks: List[Subtask] = []

    def plan(self, goal: str) -> List[Subtask]:
        prompt = f"{PLANNER_PERSONA}\n\nGoal: {goal}\n\nSubtasks:"
        response = self.llm.generate(prompt, system=PLANNER_PERSONA, max_tokens=1500)

        try:
            raw_tasks = json.loads(response.strip())
        except json.JSONDecodeError:
            import re
            match = re.search(r'\[.*\]', response, re.DOTALL)
            raw_tasks = json.loads(match.group()) if match else []

        self.tasks = [Subtask(**t) for t in raw_tasks if isinstance(t, dict)]
        return self.tasks

    def execute(self, goal: str, memory) -> Dict[str, Any]:
        if not self.tasks:
            self.plan(goal)

        completed = []
        failed = []

        for task in self.tasks:
            if task.depends_on:
                pending = [t for t in self.tasks if t.id in task.depends_on and t.status != "done"]
                if pending:
                    task.status = "failed"
                    task.result = "Dependencies not met"
                    failed.append(task)
                    continue

            task.status = "running"
            print(f"  [Step {task.id}] {task.description} -> {task.agent}")

            start = time.time()
            try:
                if task.agent == "tool":
                    result = self._execute_tool_task(task.description)
                elif task.agent in self.agents.agents:
                    result = self.agents.delegate(task.agent, task.description)
                else:
                    # llm or unknown — direct generation
                    result = {"success": True, "result": self.llm.generate(task.description)}

                latency = int((time.time() - start) * 1000)
                task.status = "done" if result.get("success") else "failed"
                task.result = result.get("result", "")
                self.evolution.log_action("planner_step", task.agent, result.get("success", False), latency, "", task.description)

                if result.get("success"):
                    completed.append(task)
                else:
                    failed.append(task)

            except Exception as e:
                task.status = "failed"
                task.result = str(e)
                failed.append(task)
                self.evolution.log_action("planner_step", task.agent, False, 0, str(e), task.description)

        return {
            "success": len(failed) == 0,
            "goal": goal,
            "completed": len(completed),
            "failed": len(failed),
            "tasks": [asdict(t) for t in self.tasks],
            "summary": self._summarize(completed, failed)
        }

    def _execute_tool_task(self, description: str) -> Dict[str, Any]:
        prompt = f'Convert this task to a tool call JSON: {description}\nFormat: {{"tool": "name", "params": {{"key": "value"}}}}\nJSON:'
        raw = self.llm.generate(prompt, max_tokens=500)

        try:
            tool_call = json.loads(raw.strip())
        except json.JSONDecodeError:
            return {"success": False, "result": f"Could not parse tool call from: {raw}"}

        is_approved, reason = self.safety.check_tool_call(tool_call.get("tool"), tool_call.get("params", {}))
        if not is_approved:
            return {"success": False, "result": f"Tool '{tool_call['tool']}' requires approval in autonomous mode."}

        return self.router.execute(tool_call)

    def _summarize(self, completed, failed) -> str:
        lines = [f"Completed {len(completed)} of {len(self.tasks)} steps."]
        if failed:
            lines.append(f"Failed steps: {len(failed)}")
            for f in failed:
                lines.append(f"  - Step {f.id}: {f.description}")
        return "\n".join(lines)
