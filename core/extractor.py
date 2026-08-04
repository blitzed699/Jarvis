import json
import re
from typing import List, Dict, Any, Optional
from .memory import JARVISMemory


FACT_EXTRACTION_PROMPT = """You are a memory extraction system. Analyze this conversation and extract facts about the user.

Extract ONLY new, specific facts. Skip generic statements. Skip facts already known.

Return ONLY a JSON array. Each object:
{
  "fact": "clear third-person statement",
  "category": "person" | "preference" | "goal" | "project" | "other"
}

If no new facts, return [].

Conversation:
User: {user_msg}
JARVIS: {jarvis_msg}

Facts:"""


class FactExtractor:
    """Automatically extracts facts from conversations and stores them in memory."""
    
    def __init__(self, llm_client):
        self.llm = llm_client
    
    def extract(self, user_msg: str, jarvis_msg: str, 
                memory: JARVISMemory) -> List[Dict[str, str]]:
        """
        Extract facts from a conversation exchange.
        Returns list of extracted facts (may be empty).
        """
        prompt = FACT_EXTRACTION_PROMPT.format(
            user_msg=user_msg,
            jarvis_msg=jarvis_msg
        )
        
        try:
            response = self.llm.generate(prompt, max_tokens=500)
            facts = self._parse_facts(response)
            
            # Store each valid fact
            stored = []
            for fact in facts:
                if self._is_valid_fact(fact):
                    memory.store_fact(fact["fact"], fact.get("category", "other"))
                    stored.append(fact)
            
            return stored
        
        except Exception as e:
            # Silently fail — fact extraction is a bonus, not a requirement
            return []
    
    def _parse_facts(self, response: str) -> List[Dict[str, str]]:
        """Parse LLM response into list of fact dicts."""
        response = response.strip()
        
        # Try to extract JSON array
        # Look for [...] block
        array_match = re.search(r'\[.*\]', response, re.DOTALL)
        if array_match:
            try:
                return json.loads(array_match.group())
            except json.JSONDecodeError:
                pass
        
        # Try the whole response
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        
        # Try individual JSON objects
        objects = re.findall(r'\{[^{}]*"fact"[^{}]*\}', response)
        facts = []
        for obj in objects:
            try:
                facts.append(json.loads(obj))
            except:
                pass
        
        return facts
    
    def _is_valid_fact(self, fact: Dict[str, Any]) -> bool:
        """Check if a fact dict is well-formed and non-trivial."""
        if not isinstance(fact, dict):
            return False
        
        fact_text = fact.get("fact", "").strip()
        if len(fact_text) < 5:
            return False
        
        # Skip generic/self-referential facts
        skip_phrases = [
            "user is talking to", "user asked", "jarvis responded",
            "user said", "the user is", "as an ai", "i am an ai"
        ]
        lower = fact_text.lower()
        if any(phrase in lower for phrase in skip_phrases):
            return False
        
        return True
