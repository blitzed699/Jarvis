import importlib
import os
from typing import Dict, Any


class AgentRegistry:
    def __init__(self, llm_client):
        self.llm = llm_client
        self.agents = self._load_agents()

    def _load_agents(self) -> Dict[str, Any]:
        agents = {}
        agents_dir = os.path.join(os.path.dirname(__file__), "..", "agents")
        if not os.path.exists(agents_dir):
            return agents
        for filename in os.listdir(agents_dir):
            if filename.endswith(".py") and filename not in ["__init__.py", "base.py"]:
                try:
                    module = importlib.import_module(f"agents.{filename[:-3]}")
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if isinstance(attr, type) and hasattr(attr, 'name') and attr_name != 'BaseAgent':
                            instance = attr(self.llm)
                            agents[instance.name] = instance
                except Exception as e:
                    print(f"[WARN] Agent load error: {e}")
        return agents

    def get_descriptions(self) -> str:
        return "\n".join([f"- {n}: {a.description}" for n, a in self.agents.items()])

    def select(self, user_input: str) -> tuple:
        desc = self.get_descriptions()
        prompt = f"""You are JARVIS — a task router. Decide if a specialist agent should handle this request.

Available agents:
{desc}

ROUTING RULES:
- DIRECT for: greetings, small talk, questions about memory, personal info, simple facts, "what do you know", "what can you do"
- AGENT for: specific tasks requiring expertise (coding, research, business analysis, creative design)

User request: "{user_input}"

Respond with EXACTLY one line:
DIRECT
or
AGENT: <agent_name>"""

        response = self.llm.generate(prompt).strip().lower()

        # v0.4 — Strict routing to prevent false positives
        response_clean = response.strip().lower()
        if response_clean == "direct" or (response_clean.startswith("direct") and "agent:" not in response_clean):
            return None, "Direct"

        # Check for agent routing
        for name in self.agents:
            if f"agent: {name}" in response:
                return name, f"Routed to {name}"

        # Default to direct for anything ambiguous
        return None, "Direct"

    def delegate(self, agent_name: str, task: str, context: str = "") -> Dict[str, Any]:
        if agent_name not in self.agents:
            return {"success": False, "result": f"Agent '{agent_name}' not found"}
        return self.agents[agent_name].run(task, context)

    def critique(self, original_task: str, agent_output: str) -> Dict[str, Any]:
        """Run critic agent on another agent's output."""
        if "critic_agent" not in self.agents:
            return {"success": True, "verdict": "PASS", "review": "No critic available"}
        return self.agents["critic_agent"].run(agent_output, context=original_task)
