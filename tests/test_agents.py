import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from agents.coding_agent import CodingAgent
from agents.research_agent import ResearchAgent
from agents.business_agent import BusinessAgent
from agents.creative_agent import CreativeAgent


class MockLLM:
    def generate(self, prompt, system=None, temperature=0.7, max_tokens=2000):
        if "coding" in prompt.lower() or "code" in prompt.lower():
            return "print('Hello from mock code')"
        if "research" in prompt.lower():
            return "Mock research: Market is growing."
        if "business" in prompt.lower():
            return "Mock business: Profitable niche found."
        if "creative" in prompt.lower():
            return "Mock creative: Bold brand identity."
        return "Mock response"


def test_coding_agent():
    # Provide a mock broker to satisfy the new broker requirement
    class MockBroker:
        def __init__(self):
            self.calls = []
        def execute_tool(self, tool_call):
            self.calls.append(tool_call)
            # Simplified execution: always succeed with empty result
            return {"success": True, "result": "mocked"}

    agent = CodingAgent(MockLLM(), broker=MockBroker())
    result = agent.run("Build a hello world script")
    assert result['success']
    assert "Built:" in result['result']
    print("CodingAgent: PASS")

def test_research_agent():
    agent = ResearchAgent(MockLLM())
    result = agent.run("Research AI trends")
    assert result['success']
    assert "market" in result['result'].lower()
    print("ResearchAgent: PASS")

def test_business_agent():
    agent = BusinessAgent(MockLLM())
    result = agent.run("Find profitable niches")
    assert result['success']
    assert "niche" in result['result'].lower()
    print("BusinessAgent: PASS")

def test_creative_agent():
    agent = CreativeAgent(MockLLM())
    result = agent.run("Create a brand for coffee shop")
    assert result['success']
    assert "brand" in result['result'].lower()
    print("CreativeAgent: PASS")


if __name__ == "__main__":
    test_coding_agent()
    test_research_agent()
    test_business_agent()
    test_creative_agent()
    print("\nAll agent tests: PASS")
