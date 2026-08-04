from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseTool(ABC):
    """Base class for all JARVIS tools."""
    
    name: str = ""
    description: str = ""
    
    @abstractmethod
    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute the tool. Return a dict with 'success' and 'result' keys."""
        pass
