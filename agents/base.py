from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseAgent(ABC):
    """Base class for all JARVIS specialist agents."""
    
    name: str = ""
    description: str = ""
    
    @abstractmethod
    def run(self, task: str, context: str = "") -> Dict[str, Any]:
        """
        Execute the agent's specialty on a task.
        Returns: {"success": bool, "result": str, "artifacts": list}
        """
        pass
