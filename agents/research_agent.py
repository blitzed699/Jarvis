from typing import Dict, Any
from .base import BaseAgent


class ResearchAgent(BaseAgent):
    name = "research_agent"
    description = "Gathers and summarizes information. Use for: finding facts, analyzing topics, validating ideas."

    def __init__(self, llm_client):
        self.llm = llm_client

    def run(self, task: str, context: str = "") -> Dict[str, Any]:
        persona = "You are a research specialist. Gather facts, analyze, and summarize clearly."
        
        prompt = f"{persona}\n\nResearch task: {task}\nContext: {context}\n\nProvide a thorough but concise summary with key findings."
        
        result = self.llm.generate(prompt, system=persona)
        
        return {
            "success": True,
            "result": result,
            "findings": result
        }
