from typing import Dict, Any
from .base import BaseAgent


class CreativeAgent(BaseAgent):
    name = "creative_agent"
    description = "Creates brands, designs, marketing concepts."

    def __init__(self, llm_client):
        self.llm = llm_client

    def run(self, task: str, context: str = "") -> Dict[str, Any]:
        persona = "You are a creative director."
        prompt = f"{persona}\n\nTask: {task}\n\nProvide concept overview, visual direction, copy suggestions, and launch strategy."
        result = self.llm.generate(prompt, system=persona)
        return {"success": True, "result": result, "concepts": result}
