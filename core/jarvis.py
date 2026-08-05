import json
import sys
from typing import Dict, Any
from .memory import JARVISMemory
from .llm import OllamaClient
from .router import ToolRouter
from .extractor import FactExtractor
from .safety import SafetyGate
from .agent_registry import AgentRegistry
import importlib
import os


JARVIS_PERSONA = """You are JARVIS — a calm, intelligent, and composed digital partner.
You assist your owner with precision and care. You remember past conversations and preferences.
You have access to tools and specialist agents.

When a task requires a tool, respond with ONLY this JSON:
{"tool": "tool_name", "params": {"key": "value"}}

Otherwise, respond naturally in character. Do not explain that you are an AI."""


class JARVISCore:
    def __init__(self, model: str = "llama3.1"):
        self.memory = JARVISMemory()
        self.llm = OllamaClient(model=model)
        self.tools = self._load_tools()
        self.router = ToolRouter(self.tools)
        self.extractor = FactExtractor(self.llm)
        self.safety = SafetyGate()
        self.agents = AgentRegistry(self.llm)
    
    def _load_tools(self) -> Dict[str, Any]:
        tools = {}
        tools_dir = os.path.join(os.path.dirname(__file__), "..", "tools")
        if not os.path.exists(tools_dir):
            return tools
        for filename in os.listdir(tools_dir):
            if filename.endswith(".py") and filename not in ["__init__.py", "base.py"]:
                try:
                    module = importlib.import_module(f"tools.{filename[:-3]}")
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if isinstance(attr, type) and hasattr(attr, 'name') and attr_name != 'BaseTool':
                            instance = attr()
                            tools[instance.name] = instance
                except Exception as e:
                    print(f"[WARN] Tool load error: {e}")
        return tools
    
    def _build_prompt(self, user_input: str) -> str:
        wm = self.memory.get_working_memory(current_query=user_input)
        context = self.memory.format_working_memory_for_prompt(wm)
        tools_desc = self.router.get_tools_description()
        agents_desc = self.agents.get_descriptions()
        
        prompt = f"""{JARVIS_PERSONA}

{tools_desc}

{agents_desc}

{context}

User: {user_input}
JARVIS:"""
        return prompt
    
    def _extract_facts(self, user_input: str, response: str):
        try:
            facts = self.extractor.extract(user_input, response, self.memory)
            if facts:
                print(f"  [Memory: stored {len(facts)} fact(s)]")
        except Exception:
            pass
    
    def _execute_with_safety(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        tool_name = tool_call.get("tool")
        params = tool_call.get("params", {})
        is_approved, reason = self.safety.check_tool_call(tool_name, params)
        if not is_approved:
            approved = self.safety.request_approval(tool_name, params, reason)
            if not approved:
                return {"success": False, "result": "User denied approval."}
        return self.router.execute(tool_call)
    
    def _handle_agent_task(self, user_input: str) -> str:
        """Check if an agent should handle this, delegate if so."""
        agent_name, reason = self.agents.select(user_input)
        
        if agent_name is None:
            return None  # No agent needed, handle normally
        
        print(f"  [Delegating to {agent_name}]")
        
        # Log delegation
        self.memory.log_message("user", user_input, tool_call=f"delegate:{agent_name}")
        
        # Execute through agent
        result = self.agents.delegate(agent_name, user_input)
        
        # Synthesize agent result through JARVIS persona
        agent_output = result.get("result", "")
        agent_code = result.get("code", "")
        
        synthesis_prompt = f"""{JARVIS_PERSONA}

You delegated to the {agent_name}. Here is the result:
{agent_output}

Respond to the user naturally. Summarize what was accomplished. Be concise.

User: {user_input}
JARVIS:"""
        
        final = self.llm.generate(synthesis_prompt, system=JARVIS_PERSONA)
        self.memory.log_message("jarvis", final, tool_call=f"delegate:{agent_name}")
        self._extract_facts(user_input, final)
        return final
    
    def process(self, user_input: str) -> str:
        # Try agent delegation first
        agent_response = self._handle_agent_task(user_input)
        if agent_response is not None:
            return agent_response
        
        # Fall back to normal tool/direct flow
        prompt = self._build_prompt(user_input)
        raw_response = self.llm.generate(prompt, system=JARVIS_PERSONA)
        
        is_tool, tool_call = self.router.parse_response(raw_response)
        
        if is_tool:
            self.memory.log_message("user", user_input, tool_call=tool_call["tool"], tool_result="[PENDING]")
            result = self._execute_with_safety(tool_call)
            
            if result.get("success"):
                result_str = json.dumps(result.get("result"), indent=2)
            else:
                result_str = f"[ERROR] {result.get('result')}"
            
            follow_up = f"""{JARVIS_PERSONA}

You used tool '{tool_call['tool']}' with result:
{result_str}

Respond naturally. Be concise.

User: {user_input}
JARVIS:"""
            
            final_response = self.llm.generate(follow_up, system=JARVIS_PERSONA)
            self.memory.log_message("jarvis", final_response, tool_call=tool_call["tool"])
            self._extract_facts(user_input, final_response)
            return final_response
        else:
            self.memory.log_message("user", user_input)
            self.memory.log_message("jarvis", raw_response)
            self._extract_facts(user_input, raw_response)
            return raw_response
    
    def chat_loop(self):
        print("=" * 50)
        print("JARVIS v0.2 — Local AI Partner")
        print("=" * 50)
        print("Type 'exit' to quit, 'tools' to list tools, 'agents' to list agents.")
        print()
        
        while True:
            try:
                user_input = input("You: ").strip()
                if not user_input:
                    continue
                if user_input.lower() == "exit":
                    self.memory.end_session("User exited.")
                    self.memory.close()
                    print("JARVIS: Goodbye.")
                    break
                if user_input.lower() == "tools":
                    print("Tools:", list(self.tools.keys()))
                    continue
                if user_input.lower() == "agents":
                    print("Agents:", list(self.agents.agents.keys()))
                    continue
                
                response = self.process(user_input)
                print(f"JARVIS: {response}")
                print()
            
            except KeyboardInterrupt:
                print("\nJARVIS: Session interrupted.")
                self.memory.end_session("Interrupted.")
                self.memory.close()
                break
            except Exception as e:
                print(f"[SYSTEM ERROR] {e}")


if __name__ == "__main__":
    jarvis = JARVISCore()
    jarvis.chat_loop()
