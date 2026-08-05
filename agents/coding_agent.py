import os
from typing import Dict, Any
from .base import BaseAgent
from tools.computer_tools import WriteFileTool, RunPythonTool


class CodingAgent(BaseAgent):
    name = "coding_agent"
    description = "Creates and debugs software. Use for: building apps, scripts, websites."

    def __init__(self, llm_client):
        self.llm = llm_client
        self.write_tool = WriteFileTool()
        self.run_tool = RunPythonTool()

    def run(self, task: str, context: str = "") -> Dict[str, Any]:
        persona = "You are a coding specialist. Write clean, tested code."
        
        # Generate code
        prompt = f"{persona}\n\nTask: {task}\n\nWrite complete working code. No explanations."
        code = self.llm.generate(prompt, system=persona)
        
        # Write to temp file
        temp_path = f"/tmp/jarvis_code_{os.urandom(4).hex()}.py"
        self.write_tool.run(path=temp_path, content=code)
        
        # Test
        test = self.run_tool.run(code=f"exec(open('{temp_path}').read())")
        
        # Fix if error
        if not test["success"]:
            fix_prompt = f"{persona}\n\nFix this code:\n{code}\n\nError: {test['result']}\n\nReturn only corrected code."
            code = self.llm.generate(fix_prompt, system=persona)
            self.write_tool.run(path=temp_path, content=code)
            test = self.run_tool.run(code=f"exec(open('{temp_path}').read())")
        
        return {
            "success": test["success"],
            "result": f"Built: {task}",
            "code": code,
            "file_path": temp_path,
            "test_output": test.get("result", "")
        }
