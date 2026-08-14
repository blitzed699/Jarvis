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

    text = re.sub(r'```(?:json)?\s*', '', text)
    text = text.replace('```', '')

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
    # Hardcoded — these are your real agents
    VALID_AGENTS = {
        "coding_agent", "research_agent", "business_agent",
        "creative_agent", "tool", "llm"
    }

    def __init__(self, llm_client, agent_registry, tool_router, safety_gate, evolution_tracker):
        self.llm = llm_client
        self.agents = agent_registry
        self.router = tool_router
        self.safety = safety_gate
        self.evolution = evolution_tracker
        self.tasks: List[Subtask] = []

    def _build_planner_prompt(self, goal: str) -> str:
        registry_text = "\n".join(
            f"- {name}: {agent.description}"
            for name, agent in self.agents.agents.items()
        )

        return f"""You are JARVIS's task planner. Break the user's goal into numbered subtasks.

AVAILABLE AGENTS (you MUST use ONLY these names):
{registry_text}
- tool: for shell commands, web search, opening apps
- llm: for direct text generation, summaries, explanations

RULES:
1. Each subtask MUST use an agent name from AVAILABLE AGENTS above.
2. NEVER invent agent names.
3. If the task involves writing code, scripts, or programs → use coding_agent ONLY.
4. coding_agent handles its own file creation and saving. NEVER add separate tool steps for file operations.
5. Return ONLY a raw JSON array. No markdown, no explanations.

EXAMPLE:
Goal: Write a Python script that says hello world and save it to /tmp/hello.py
[
  {{"id": 1, "description": "Write a Python script that prints 'Hello World' and save it to /tmp/hello.py", "agent": "coding_agent", "depends_on": []}}
]

Goal: {goal}

Subtasks:"""

    def _correct_plan(self, tasks: List[dict], goal: str) -> List[dict]:
        """
        Post-process the LLM-generated plan.
        - Forces coding tasks to coding_agent
        - Removes redundant file-tool steps
        - Merges multiple coding steps into one
        """
        coding_keywords = re.compile(
            r'\b(python|script|code|program|app|function|class|'
            r'write.*\.py|write.*\.js|write.*\.html|build|develop)\b', re.I
        )
        path_pattern = re.compile(r'(/\S+\.\w+)')
        goal_paths = path_pattern.findall(goal)

        # First pass: fix invalid agents
        for t in tasks:
            if not isinstance(t, dict):
                continue
            agent = t.get("agent", "")
            if agent not in self.VALID_AGENTS:
                print(f" [Planner] Replaced invalid agent '{agent}' with 'llm'")
                t["agent"] = "llm"

        # Detect if this is a coding job
        has_coding = any(
            t.get("agent") == "coding_agent" or coding_keywords.search(t.get("description", ""))
            for t in tasks
        )

        if has_coding:
            descriptions = []
            all_paths = list(goal_paths)

            for t in tasks:
                desc = t.get("description", "")
                agent = t.get("agent", "")

                # Collect paths from every step
                paths = path_pattern.findall(desc)
                all_paths.extend(paths)

                # Keep coding descriptions, drop file/save tool steps
                if agent == "coding_agent" or coding_keywords.search(desc):
                    descriptions.append(desc)
                elif agent == "tool" and re.search(r'\b(save|write|create|file)\b', desc, re.I):
                    print(f" [Planner] Removed redundant tool step: {desc[:50]}...")
                    continue
                else:
                    descriptions.append(desc)

            # Deduplicate paths
            seen = set()
            unique_paths = [p for p in all_paths if not (p in seen or seen.add(p))]

            # Build single merged step
            merged_desc = " ".join(descriptions)
            for p in unique_paths:
                if p not in merged_desc:
                    merged_desc += f" Save to {p}."

            return [{
                "id": 1,
                "description": merged_desc,
                "agent": "coding_agent",
                "depends_on": []
            }]

        # Non-coding tasks: just renumber
        corrected = [t for t in tasks if isinstance(t, dict)]
        for i, t in enumerate(corrected, 1):
            t["id"] = i
        return corrected

    def plan(self, goal: str) -> List[Subtask]:
        prompt = self._build_planner_prompt(goal)
        response = self.llm.generate(prompt, max_tokens=1500)

        raw_tasks = _extract_json(response)
        if raw_tasks is None:
            raw_tasks = []

        raw_tasks = self._correct_plan(raw_tasks, goal)

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
            print(f" [Step {task.id}] {task.description} -> {task.agent}")

            context = "\n".join(
                f"[Previous Step {t.id}] {t.agent}: {t.result}"
                for t in self.tasks
                if t.status == "done" and t.result
            )

            start = time.time()
            try:
                if task.agent == "tool":
                    full_desc = f"{context}\n\nCurrent task: {task.description}" if context else task.description
                    result = self._execute_tool_task(full_desc)
                elif task.agent in self.agents.agents:
                    full_task = f"{context}\n\nYour task: {task.description}" if context else task.description
                    result = self.agents.delegate(task.agent, full_task)
                else:
                    full_prompt = f"{context}\n\nNow do this: {task.description}" if context else task.description
                    result = {"success": True, "result": self.llm.generate(full_prompt)}

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
