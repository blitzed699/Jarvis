import subprocess
from typing import Dict, Any
from .base import BaseTool


class ShellTool(BaseTool):
    name = "shell"
    description = "Run a shell command. Params: command (str). USE WITH CAUTION."
    
    def run(self, command: str) -> Dict[str, Any]:
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]: {result.stderr}"
            return {
                "success": result.returncode == 0,
                "result": output,
                "returncode": result.returncode
            }
        except Exception as e:
            return {"success": False, "result": str(e)}
