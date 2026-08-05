from typing import Dict, Any
from .base import BaseAgent


class BusinessAgent(BaseAgent):
    name = "business_agent"
    description = "Analyzes markets, finds niches, evaluates opportunities."

    def __init__(self, llm_client):
        self.llm = llm_client

    def run(self, task: str, context: str = "") -> Dict[str, Any]:
        persona = "You are a business intelligence specialist."
        prompt = f"{persona}\n\nTask: {task}\n\nProvide market analysis, niche opportunities, risk assessment, and next steps."
        result = self.llm.generate(prompt, system=persona)
        return {"success": True, "result": result, "analysis": result}
