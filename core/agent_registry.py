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
        prompt = f"You are JARVIS router.\n{desc}\n\nRequest: {user_input}\n\nRespond ONLY with:\n- AGENT: coding_agent\n- AGENT: research_agent\n- DIRECT"
        response = self.llm.generate(prompt).strip().lower()
        for name in self.agents:
            if f"agent: {name}" in response:
                return name, f"Routed to {name}"
        return None, "Direct"
    
    def delegate(self, agent_name: str, task: str, context: str = "") -> Dict[str, Any]:
        if agent_name not in self.agents:
            return {"success": False, "result": f"Agent '{agent_name}' not found"}
        return self.agents[agent_name].run(task, context)
