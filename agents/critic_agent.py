from typing import Dict, Any
from .base import BaseAgent


class CriticAgent(BaseAgent):
    name = "critic_agent"
    description = "Reviews agent outputs for errors, risks, and hallucinations. Use before delivering critical work."

    def __init__(self, llm_client):
        self.llm = llm_client

    def run(self, task: str, context: str = "") -> Dict[str, Any]:
        persona = """You are a ruthless critic. Your job is to find errors, hallucinations, security flaws, and logical gaps in AI-generated work.
Be direct. Be specific. If something is wrong, say exactly why. If something is good, confirm it briefly.
Rate confidence: HIGH / MEDIUM / LOW."""

        prompt = f"""{persona}

Original request: {context}
Work to review: {task}

Review for:
1. Factual errors or hallucinations
2. Security vulnerabilities (especially in code)
3. Logical flaws or missing steps
4. Overconfidence or unsupported claims
5. Suggested fixes

Format:
VERDICT: [PASS / NEEDS_FIX / REJECT]
CONFIDENCE: [HIGH / MEDIUM / LOW]
ISSUES:
- [list each issue]
FIXES:
- [list suggested corrections]
"""

        result = self.llm.generate(prompt, system=persona)

        verdict = "PASS"
        if "VERDICT: REJECT" in result:
            verdict = "REJECT"
        elif "VERDICT: NEEDS_FIX" in result:
            verdict = "NEEDS_FIX"

        return {
            "success": True,
            "result": result,
            "verdict": verdict,
            "review": result
        }
