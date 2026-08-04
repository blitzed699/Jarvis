import json
import sys
from typing import Dict, Any, Optional
from .memory import JARVISMemory
from .llm import OllamaClient
from .router import ToolRouter
import importlib
import os


JARVIS_PERSONA = """You are JARVIS — a calm, intelligent, and composed digital partner.
You assist your owner with precision and care. You remember past conversations and preferences.
You have access to tools to interact with the computer.

When a task requires a tool, respond with ONLY this JSON format:
{"tool": "tool_name", "params": {"key": "value"}}

Otherwise, respond naturally in character. Do not explain that you are an AI."""


class JARVISCore:
    def __init__(self, model: str = "llama3.1"):
        self.memory = JARVISMemory()
        self.llm = OllamaClient(model=model)
        self.tools = self._load_tools()
        self.router = ToolRouter(self.tools)
    
    def _load_tools(self) -> Dict[str, Any]:
        """Dynamically load all tools from tools/ directory."""
        tools = {}
        tools_dir = os.path.join(os.path.dirname(__file__), "..", "tools")
        if not os.path.exists(tools_dir):
            return tools
        
        for filename in os.listdir(tools_dir):
            if filename.endswith(".py") and filename not in ["__init__.py", "base.py"]:
                module_name = f"tools.{filename[:-3]}"
                try:
                    module = importlib.import_module(module_name)
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (isinstance(attr, type) and 
                            hasattr(attr, 'name') and 
                            attr_name != 'BaseTool'):
                            instance = attr()
                            tools[instance.name] = instance
                except Exception as e:
                    print(f"[WARN] Could not load tool {filename}: {e}")
        return tools
    
    def _build_prompt(self, user_input: str) -> str:
        """Build the full prompt with working memory and tools."""
        wm = self.memory.get_working_memory(current_query=user_input)
        context = self.memory.format_working_memory_for_prompt(wm)
        tools_desc = self.router.get_tools_description()
        
        prompt = f"""{JARVIS_PERSONA}

{tools_desc}

{context}

User: {user_input}
JARVIS:"""
        return prompt
    
    def process(self, user_input: str) -> str:
        """Main entry point. Process user input and return response."""
        prompt = self._build_prompt(user_input)
        raw_response = self.llm.generate(prompt, system=JARVIS_PERSONA)
        
        # Use router to handle tool calls
        tool_result, used_tool = self.router.handle_tool_use(
            user_input, raw_response, self.memory
        )
        
        if used_tool:
            # Build follow-up prompt with tool result
            follow_up_prompt = f"""{JARVIS_PERSONA}

You just used a tool and received this result:
{tool_result}

Respond to the user naturally based on this result. Be concise.

User: {user_input}
JARVIS:"""
            
            final_response = self.llm.generate(follow_up_prompt, system=JARVIS_PERSONA)
            self.memory.log_message("jarvis", final_response, tool_call="[routed]")
            return final_response
        else:
            # Direct response
            self.memory.log_message("user", user_input)
            self.memory.log_message("jarvis", raw_response)
            return raw_response
    
    def chat_loop(self):
        """Simple REPL."""
        print("=" * 50)
        print("JARVIS v0.1 — Local AI Partner")
        print("=" * 50)
        print("Type 'exit' to quit, 'tools' to list tools.")
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
                    print("Available tools:", list(self.tools.keys()))
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
