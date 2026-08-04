import json
import re
from typing import Dict, Any, Optional, Tuple
from .memory import JARVISMemory


class ToolRouter:
    """Clean tool selection and execution. Replaces brittle JSON parsing."""
    
    def __init__(self, tools: Dict[str, Any]):
        self.tools = tools
    
    def get_tools_description(self) -> str:
        """Format tool descriptions for the system prompt."""
        lines = ["Available tools:"]
        for name, tool in self.tools.items():
            lines.append(f"- {name}: {tool.description}")
        lines.append("")
        lines.append("TOOL USE FORMAT (respond with ONLY this JSON, no markdown fences):")
        lines.append('{"tool": "tool_name", "params": {"key": "value"}}')
        lines.append("")
        lines.append("If no tool is needed, respond normally.")
        return "\n".join(lines)
    
    def parse_response(self, response: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Parse LLM response for tool calls.
        Returns: (is_tool_call, tool_call_dict_or_none)
        """
        response = response.strip()
        
        # Try to extract JSON from markdown code blocks
        # Pattern: ```json\n{...}\n``` or ```\n{...}\n```
        code_block_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
        matches = re.findall(code_block_pattern, response, re.DOTALL)
        
        if matches:
            for match in matches:
                result = self._try_parse_json(match)
                if result:
                    return True, result
        
        # Try the whole response as JSON
        if response.startswith("{") and response.endswith("}"):
            result = self._try_parse_json(response)
            if result:
                return True, result
        
        # Try to find JSON object anywhere in the text
        json_pattern = r'(\{[^{}]*"tool"[^{}]*\})'
        matches = re.findall(json_pattern, response, re.DOTALL)
        for match in matches:
            result = self._try_parse_json(match)
            if result:
                return True, result
        
        return False, None
    
    def _try_parse_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Try to parse text as a tool call JSON."""
        try:
            data = json.loads(text.strip())
            if "tool" in data and "params" in data:
                return data
        except (json.JSONDecodeError, ValueError):
            pass
        return None
    
    def validate_tool_call(self, tool_call: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate a tool call before execution."""
        tool_name = tool_call.get("tool")
        params = tool_call.get("params", {})
        
        if not tool_name:
            return False, "No tool name specified"
        
        if tool_name not in self.tools:
            available = ", ".join(self.tools.keys())
            return False, f"Unknown tool '{tool_name}'. Available: {available}"
        
        if not isinstance(params, dict):
            return False, "Params must be a dictionary"
        
        return True, ""
    
    def execute(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a validated tool call."""
        is_valid, error_msg = self.validate_tool_call(tool_call)
        
        if not is_valid:
            return {"success": False, "result": error_msg}
        
        tool_name = tool_call["tool"]
        params = tool_call["params"]
        tool = self.tools[tool_name]
        
        try:
            return tool.run(**params)
        except Exception as e:
            return {"success": False, "result": f"Tool execution failed: {str(e)}"}
    
    def handle_tool_use(self, user_input: str, llm_response: str, memory: JARVISMemory) -> Tuple[str, bool]:
        """
        Handle potential tool use from LLM response.
        Returns: (final_response, used_tool)
        """
        is_tool, tool_call = self.parse_response(llm_response)
        
        if not is_tool:
            return llm_response, False
        
        # Log the tool call
        memory.log_message(
            "user", user_input,
            tool_call=tool_call["tool"],
            tool_result="[PENDING]"
        )
        
        # Execute
        result = self.execute(tool_call)
        
        if result.get("success"):
            result_str = json.dumps(result.get("result"), indent=2)
        else:
            result_str = f"[ERROR] {result.get('result')}"
        
        return result_str, True
