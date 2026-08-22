"""
core/procedural_memory.py

Procedural Memory — behavioral rules learned from failure.

When JARVIS makes the same mistake 3 times, it generates a rule:
"Never claim a coding task is complete until the generated project has been
executed/tested successfully."

That rule gets injected into every future system prompt.
JARVIS literally learns from its own failures.
"""

import os
import json
import hashlib
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ProceduralRule:
    """A learned behavioral rule."""
    id: str
    pattern: str          # What failure pattern triggered this
    rule_text: str        # The behavioral instruction
    confidence: float     # 0.0-1.0, increases with more observations
    created_at: str
    last_triggered: Optional[str] = None
    trigger_count: int = 1
    category: str = "general"  # coding, memory, planning, tool_use, verification

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "pattern": self.pattern,
            "rule": self.rule_text,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "last_triggered": self.last_triggered,
            "trigger_count": self.trigger_count,
            "category": self.category,
        }


class ProceduralMemory:
    """
    Learns behavioral rules from recurring discrepancies.
    Stores rules in a JSON file and injects them into prompts.
    """

    RULES_FILE = "memory/procedural_rules.json"
    CONFIDENCE_THRESHOLD = 0.6  # Only inject rules above this confidence
    MAX_RULES = 20

    def __init__(self, llm_client=None):
        self.llm = llm_client
        self.rules: List[ProceduralRule] = []
        self._load_rules()

    def _load_rules(self) -> None:
        """Load existing rules from disk."""
        if os.path.exists(self.RULES_FILE):
            try:
                with open(self.RULES_FILE, "r") as f:
                    data = json.load(f)
                    for r in data:
                        self.rules.append(ProceduralRule(**r))
            except Exception:
                pass

    def _save_rules(self) -> None:
        """Persist rules to disk."""
        os.makedirs(os.path.dirname(self.RULES_FILE), exist_ok=True)
        with open(self.RULES_FILE, "w") as f:
            json.dump([r.to_dict() for r in self.rules], f, indent=2)

    def _generate_rule_id(self, pattern: str) -> str:
        return f"rule_{hashlib.md5(pattern.encode()).hexdigest()[:8]}"

    def _generate_rule_text(self, pattern: str, examples: List[str]) -> Optional[str]:
        """
        Use LLM to generate a concise behavioral rule from failure examples.
        """
        if not self.llm:
            return None

        examples_text = "\n".join(f"- {ex}" for ex in examples[-5:])

        prompt = f"""You are JARVIS's procedural memory system. JARVIS has made the same mistake multiple times.

Failure pattern: {pattern}

Recent occurrences:
{examples_text}

Generate ONE concise behavioral rule that JARVIS should follow to avoid this mistake in the future.

Requirements:
- Start with "Always" or "Never"
- Be extremely specific and actionable
- One sentence only
- Focus on what JARVIS should DO differently, not what it should know

Good examples:
- "Always verify a file exists on disk before claiming it was created."
- "Never claim a coding task is complete until tests have been executed successfully."
- "Always create parent directories with os.makedirs() before writing files."
- "Always check the exit code of shell commands before assuming they succeeded."

Bad examples:
- "Be careful with files"
- "Make sure things work"
- "Check code before running it"

Behavioral rule:"""

        try:
            rule = self.llm.generate(prompt, max_tokens=100, temperature=0.3).strip()
            # Validation
            if len(rule) < 15:
                return None
            if not rule.lower().startswith(("always", "never", "when", "before")):
                # Try to fix
                if "verify" in rule.lower():
                    rule = "Always " + rule[0].lower() + rule[1:]
                elif "check" in rule.lower():
                    rule = "Always " + rule[0].lower() + rule[1:]
                elif "claim" in rule.lower():
                    rule = "Never " + rule[0].lower() + rule[1:]
            return rule
        except Exception:
            return None

    def observe_discrepancy(self, pattern: str, description: str) -> Optional[ProceduralRule]:
        """
        Called when a discrepancy is observed. If the same pattern occurs
        3 times, auto-generate or strengthen a rule.
        """
        # Check if we already have a rule for this pattern
        rule_id = self._generate_rule_id(pattern)
        existing = next((r for r in self.rules if r.id == rule_id), None)

        if existing:
            # Strengthen existing rule
            existing.trigger_count += 1
            existing.last_triggered = datetime.now().isoformat()
            existing.confidence = min(1.0, existing.confidence + 0.15)
            self._save_rules()
            return existing

        # Count how many times we've seen this pattern recently
        # (In practice, the caller should track this, but we approximate)
        # For now, we trust the caller (world_state.get_recurring_discrepancy_pattern)
        # to only call us when the pattern is real.

        # Generate new rule
        rule_text = self._generate_rule_text(pattern, [description])
        if not rule_text:
            return None

        # Categorize
        category = "general"
        if any(k in pattern.lower() for k in ["file", "path", "directory", "write"]):
            category = "coding"
        elif any(k in pattern.lower() for k in ["command", "shell", "exit", "timeout"]):
            category = "tool_use"
        elif any(k in pattern.lower() for k in ["memory", "remember", "forget"]):
            category = "memory"
        elif any(k in pattern.lower() for k in ["plan", "step", "goal"]):
            category = "planning"
        elif any(k in pattern.lower() for k in ["verify", "check", "test"]):
            category = "verification"

        new_rule = ProceduralRule(
            id=rule_id,
            pattern=pattern,
            rule_text=rule_text,
            confidence=0.5,  # Start medium, grows with triggers
            created_at=datetime.now().isoformat(),
            last_triggered=datetime.now().isoformat(),
            trigger_count=1,
            category=category
        )

        self.rules.append(new_rule)

        # Keep only top rules by confidence
        if len(self.rules) > self.MAX_RULES:
            self.rules.sort(key=lambda r: r.confidence, reverse=True)
            self.rules = self.rules[:self.MAX_RULES]

        self._save_rules()
        return new_rule

    def get_rules_for_prompt(self, category: Optional[str] = None) -> str:
        """
        Get formatted rules for injection into system prompt.
        Only returns rules above confidence threshold.
        """
        active_rules = [r for r in self.rules if r.confidence >= self.CONFIDENCE_THRESHOLD]
        if category:
            active_rules = [r for r in active_rules if r.category == category]

        if not active_rules:
            return ""

        lines = ["## Learned Behavioral Rules"]
        for r in sorted(active_rules, key=lambda x: x.confidence, reverse=True)[:10]:
            icon = "🔒" if r.confidence > 0.9 else "⚡" if r.confidence > 0.75 else "•"
            lines.append(f"{icon} {r.rule_text} (confidence: {r.confidence:.0%})")

        return "\n".join(lines)

    def get_all_rules(self) -> List[Dict[str, Any]]:
        """Return all rules as dicts."""
        return [r.to_dict() for r in self.rules]

    def get_rule_by_id(self, rule_id: str) -> Optional[ProceduralRule]:
        return next((r for r in self.rules if r.id == rule_id), None)

    def delete_rule(self, rule_id: str) -> bool:
        """Delete a rule (e.g., if user says it's wrong)."""
        original_len = len(self.rules)
        self.rules = [r for r in self.rules if r.id != rule_id]
        if len(self.rules) < original_len:
            self._save_rules()
            return True
        return False
