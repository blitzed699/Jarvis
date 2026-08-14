import json
import time
import re
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


def _extract_json(text: str):
    """Find the first JSON array or object in text, stripping markdown fences."""
    if not text:
        return None

    # Remove markdown code blocks
    text = re.sub(r'```(?:json)?\s*', '', text)
    text = text.replace('```', '')

    # Find first [ or {
    start_arr = text.find('[')
    start_obj = text.find('{')

    if start_arr == -1 and start_obj == -1:
        return None

    start = min(x for x in [start_arr, start_obj] if x != -1)
    brace = text[start]
    ender = ']' if brace == '[' else '}'

    count = 0
    for i in range(start, len(text)):
        if text[i] == brace:
            count += 1
        elif text[i] == ender:
            count -= 1
            if count == 0:
                return json.loads(text[start:i+1])
    return None


class AutonomousPlanner:
    def __init__(self, llm_client, agent_registry, tool_router, safety_gate, evolution_tracker):
        self.llm = llm_client
        self.agents = agent_registry
        self.router = tool_router
        self.safety = safety_gate
        self.evolution = evolution_tracker
        self.tasks: List[Subtask] = []

    def _build_planner_prompt(self, goal: str) -> str:
        # Dynamically inject ONLY real agents — no hallucinations allowed
        agent_names = list(self.agents.agents.keys())
        valid_agents = agent_names + ["tool", "llm"]

        registry_text = "\n".join(
            f"- {name}: {agent.description}"
            for name, agent in self.agents.agents.items()
        )

        return f"""You are JARVIS's task planner. Break the user's goal into numbered subtasks.

AVAILABLE AGENTS (you MUST use ONLY these names):
{registry_text}
- tool: for file operations, shell commands, web search
- llm: for direct text generation, summaries, explanations

RULES:
1. Each subtask MUST use an agent name from AVAILABLE AGENTS above.
2. NEVER invent agent names like "direct", "system", or "user".
3. Return ONLY a raw JSON array. No markdown, no explanations, no code fences.

JSON FORMAT:
[
  {{"id": 1, "description": "...", "agent": "coding_agent", "depends_on": []}}
]

Goal: {goal}

Subtasks:"""

    def plan(self, goal: str) -> List[Subtask]:
        prompt = self._build_planner_prompt(goal)
        response = self.llm.generate(prompt, max_tokens=1500)

        # Extract JSON
        raw_tasks = _extract_json(response)
        if raw_tasks is None:
            raw_tasks = []

        # Validate agent names
        valid_agents = set(self.agents.agents.keys()) | {"tool", "llm"}
        cleaned = []
        for t in raw_tasks:
            if not isinstance(t, dict):
                continue
            agent = t.get("agent", "")
            if agent not in valid_agents:
                print(f" [Planner] Rejected invalid agent '{agent}', falling back to 'llm'")
                t["agent"] = "llm"
            cleaned.append(t)

        self.tasks = [Subtask(**t) for t in cleaned]
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
            print(f" [Step {task.id}] {task.description} -> {task.agent}")

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
                lines.append(f" - Step {f.id}: {f.description}")
        return "\n".join(lines)
