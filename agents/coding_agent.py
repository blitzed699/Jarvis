import os
import re
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

    def _clean_code(self, text: str) -> str:
        """
        Aggressively extract only executable code from LLM output.
        Handles markdown fences, JSON wrappers, and chitchat.
        """
        text = text.strip()

        # Case 1: JSON wrapper like {"code": "..."}
        if text.startswith("{") and text.endswith("}"):
            try:
                import json
                data = json.loads(text)
                for key in ['code', 'content', 'script', 'python', 'source']:
                    if key in data and isinstance(data[key], str):
                        return self._clean_code(data[key])
            except (json.JSONDecodeError, ValueError):
                pass

        # Case 2: Markdown code block ```python ... ```
        # Find first triple-backtick block
        fence_match = re.search(r'```(?:\w+)?\n(.*?)\n```', text, re.DOTALL)
        if fence_match:
            return fence_match.group(1).strip()

        # Case 3: No fences, but mixed with explanations — extract leading code
        # Split into lines, keep lines that look like code until we hit prose
        lines = text.splitlines()
        code_lines = []
        in_code = False

        for line in lines:
            stripped = line.strip()

            # Start collecting at first code-like line
            if not in_code:
                if re.match(r'^(#|import |from |def |class |print\(|if |for |while |try:|with |'
                           r'[a-zA-Z_][a-zA-Z0-9_]*\s*=|'
                           r'[a-zA-Z_][a-zA-Z0-9_]*\s*\(|'
                           r'""")', stripped):
                    in_code = True
                    code_lines.append(line)
                continue

            # Stop collecting when we hit obvious prose
            if re.match(r'^(Here|Actually|However|If you|Note:|This|But |And |'
                       r'Alternatively|You can|To |For |When |The )', stripped):
                break

            # Blank line after code + more text = stop
            if not stripped and code_lines:
                # Peek ahead — if next non-empty line is prose, stop
                remaining = "\n".join(lines[lines.index(line):])
                if re.search(r'\n\s*[A-Z][a-z]+', remaining):
                    break

            code_lines.append(line)

        if code_lines:
            return "\n".join(code_lines).strip()

        # Fallback: return everything, hope for the best
        return text

    def run(self, task: str, context: str = "") -> Dict[str, Any]:
        persona = ("You are a coding specialist. Write clean, working code. "
                   "Output ONLY raw code. No markdown, no explanations, no JSON.")

        # Generate code
        prompt = f"{persona}\n\nTask: {task}\n\nWrite complete working code."
        raw = self.llm.generate(prompt, system=persona)
        code = self._clean_code(raw)

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
            raw_fix = self.llm.generate(fix_prompt, system=persona)
            code = self._clean_code(raw_fix)
            self.write_tool.run(path=temp_path, content=code)
            test = self.run_tool.run(code=f"exec(open('{temp_path}').read())")

        return {
            "success": test["success"],
            "result": f"Built: {task}\nFile: {temp_path}",
            "code": code,
            "file_path": temp_path,
            "test_output": test.get("result", "")
        }
