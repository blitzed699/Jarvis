import os
import re
import json
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

    def _extract_path(self, task: str) -> str:
        """Pull a file path like /tmp/hello.py from the task text."""
        match = re.search(r'/\S+\.\w+', task)
        return match.group() if match else None

    def _strip_json_wrapper(self, text: str) -> str:
        """If the LLM wrapped code in JSON, extract just the code string."""
        text = text.strip()
        if text.startswith("{") and text.endswith("}"):
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    for key in ['code', 'content', 'script', 'python']:
                        if key in data:
                            return data[key]
            except (json.JSONDecodeError, ValueError):
                pass
        return text

    def run(self, task: str, context: str = "") -> Dict[str, Any]:
        persona = "You are a coding specialist. Write clean, working code. Output ONLY raw code. No JSON, no markdown fences, no explanations."

        # Generate code
        prompt = f"{persona}\n\nTask: {task}\n\nWrite complete working code. No explanations."
        code = self.llm.generate(prompt, system=persona)
        code = self._strip_json_wrapper(code)

        # Determine where to save
        target_path = self._extract_path(task)
        if target_path:
            temp_path = target_path
        else:
            temp_path = f"/tmp/jarvis_code_{os.urandom(4).hex()}.py"

        # Write file
        self.write_tool.run(path=temp_path, content=code)

        # Test execution
        test = self.run_tool.run(code=f"exec(open('{temp_path}').read())")

        # Fix if broken
        if not test["success"]:
            fix_prompt = f"{persona}\n\nFix this code:\n{code}\n\nError: {test['result']}\n\nReturn only corrected code."
            code = self.llm.generate(fix_prompt, system=persona)
            code = self._strip_json_wrapper(code)
            self.write_tool.run(path=temp_path, content=code)
            test = self.run_tool.run(code=f"exec(open('{temp_path}').read())")

        return {
            "success": test["success"],
            "result": f"Built: {task}\nFile: {temp_path}",
            "code": code,
            "file_path": temp_path,
            "test_output": test.get("result", "")
        }
