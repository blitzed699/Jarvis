import re
from typing import Dict, Any, Tuple


DESTRUCTIVE_PATTERNS = [
    r'\brm\s+-[rf]+\b',
    r'\bmkfs\b',
    r'\bdd\s+if=',
    r'\bformat\b',
    r'\bdel\s+/[fqs]+\b',
    r'\b:(){ :|:& };:\b',  # Fork bomb
    r'\bshutdown\b',
    r'\breboot\b',
    r'\bchmod\s+-R\s+777\b',
    r'\bchown\s+-R\b',
    r'\bwget.*\|\s*sh\b',
    r'\bcurl.*\|\s*sh\b',
    r'\b>\s*/dev/[sh]da\b',
    r'\bmv\s+/.*\s+/dev/null\b',
]

DESTRUCTIVE_TOOL_NAMES = {"shell"}

READONLY_TOOL_NAMES = {"file_read", "file_list"}


class SafetyGate:
    """Intercepts destructive actions and requires user approval."""
    
    def __init__(self, auto_approve_readonly: bool = True):
        self.auto_approve_readonly = auto_approve_readonly
    
    def check_tool_call(self, tool_name: str, params: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Check if a tool call requires approval.
        Returns: (is_approved, reason_or_empty)
        """
        # Readonly tools auto-approve
        if tool_name in READONLY_TOOL_NAMES:
            return True, ""
        
        # Destructive tools always require approval
        if tool_name in DESTRUCTIVE_TOOL_NAMES:
            command = params.get("command", "")
            danger = self._is_dangerous_command(command)
            if danger:
                return False, f"DANGEROUS: '{command}' matches destructive pattern."
            return False, f"Tool '{tool_name}' requires approval: {params}"
        
        # Unknown tools require approval
        return False, f"Unknown tool '{tool_name}' requires approval."
    
    def _is_dangerous_command(self, command: str) -> bool:
        """Check if a shell command matches known destructive patterns."""
        for pattern in DESTRUCTIVE_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return True
        return False
    
    def request_approval(self, tool_name: str, params: Dict[str, Any], 
                         reason: str) -> bool:
        """
        Prompt user for approval. Returns True if approved.
        Override this for GUI/voice approval later.
        """
        print(f"\n  [APPROVAL REQUIRED]")
        print(f"  Tool: {tool_name}")
        print(f"  Params: {params}")
        if reason:
            print(f"  Reason: {reason}")
        print()
        
        while True:
            choice = input("  Approve? [y/n]: ").strip().lower()
            if choice in ('y', 'yes'):
                return True
            if choice in ('n', 'no'):
                return False
            print("  Please enter 'y' or 'n'.")
