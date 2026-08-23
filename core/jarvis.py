import json
import time
import sys
import re
from typing import Dict, Any
from .memory import JARVISMemory
from .llm import OllamaClient
from .router import ToolRouter
from .extractor import FactExtractor
from .safety import SafetyGate
from .agent_registry import AgentRegistry
from .projects import ProjectTracker
from .goals import GoalTracker
from .voice import VoiceSynthesizer
from .config import Config
from .evolution import EvolutionTracker
from .planner import AutonomousPlanner
import importlib
import os

# v0.4 — Cognitive Core imports
from core.state import WorldState
from core.observer import Observer
from core.verifier import Verifier
from core.ovc_loop import OVCLoop
from core.memory_threadsafe import ThreadSafeMemory
from core.procedural_memory import ProceduralMemory  # v0.4 — procedural memory


JARVIS_PERSONA = """You are JARVIS — a calm, intelligent, and composed digital partner.
You assist your owner with precision and care. You remember past conversations and preferences.
You have access to tools and specialist agents.

When a task requires a tool, respond with ONLY this JSON:
{"tool": "tool_name", "params": {"key": "value"}}

Otherwise, respond naturally in character. Do not explain that you are an AI."""


class JARVISCore:
    def __init__(self, model: str = "llama3.1"):
        self.config = Config()

        # v0.4 — Thread-safe memory
        self.memory = ThreadSafeMemory(
            db_path=self.config.get("memory_db"),
            chroma_path=self.config.get("chroma_path")
        )

        self.llm = OllamaClient(
            model=self.config.get("model", model),
            base_url=self.config.get("base_url")
        )
        self.tools = self._load_tools()
        self.router = ToolRouter(self.tools)
        self.extractor = FactExtractor(self.llm)
        self.safety = SafetyGate(
            auto_approve_readonly=self.config.get("auto_approve_readonly", True)
        )
        self.agents = AgentRegistry(self.llm)
        self.projects = ProjectTracker(self.memory.conn)
        self.goals = GoalTracker(self.memory.conn)
        self.evolution = EvolutionTracker(self.memory.conn)

        # v0.4 — Cognitive Core
        self.world_state = WorldState()
        self.observer = Observer(self.world_state)
        self.verifier = Verifier(self.llm)

        # v0.4 — Procedural Memory (learns from failures)
        self.procedural_memory = ProceduralMemory(self.llm)

        # v0.4 — OVC Loop with mandatory critic gate
        self.ovc = OVCLoop(
            self.llm, self.world_state, self.observer, self.verifier,
            critic_fn=self._run_critic  # v0.4 — mandatory critic
        )

        # v0.4 — Planner wired with OVC and world state
        self.planner = AutonomousPlanner(
            self.llm, self.agents, self.router, self.safety, self.evolution,
            ovc_loop=self.ovc
        )
        self.planner.world_state = self.world_state

        self.voice = VoiceSynthesizer(enabled=self.config.get("voice_enabled", False))
        self.current_project = None

    def _run_critic(self, task: str, output: str) -> Dict[str, Any]:
        """v0.4 — Wrapper for critic agent to inject into OVC loop."""
        return self.agents.critique(task, output)

    def _notify_dashboard(self, event_type: str, data: dict = None):
        """Broadcast state changes to the web dashboard if running."""
        try:
            from dashboard.server import _broadcast
            import asyncio
            payload = {"type": event_type}
            if data:
                payload.update(data)
            asyncio.create_task(_broadcast(payload))
        except Exception:
            pass

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
        insights = self.evolution.get_insights()

        active_goals = self.goals.list_active()
        active_projects = self.projects.list_active()
        extra_context = ""
        if active_goals:
            extra_context += "\n## Active Goals\n" + "\n".join([f"- [{g['progress']}%] {g['title']}" for g in active_goals[:3]])
        if active_projects:
            extra_context += "\n## Active Projects\n" + "\n".join([f"- {p['name']}: {p['status']}" for p in active_projects[:3]])

        # v0.4 — Inject structured world state
        state_summary = self.world_state.get_state_summary()

        # v0.4 — Inject learned behavioral rules from procedural memory
        procedural_rules = self.procedural_memory.get_rules_for_prompt()

        prompt = f"""{JARVIS_PERSONA}

{procedural_rules}

{tools_desc}

{agents_desc}

{insights}

{state_summary}

{context}{extra_context}

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

    # v0.4 — Predict what a tool should produce
    def _predict_tool_outcome(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Predict what should happen after a tool runs."""
        if tool_name in ("write_file", "file_read"):
            return {"path": params.get("path"), "exists": True}
        elif tool_name == "shell":
            return {"command": params.get("command"), "exit_code": 0}
        elif tool_name == "run_python":
            return {"code": params.get("code"), "success": True}
        elif tool_name == "file_list":
            return {"path": params.get("path", "."), "exists": True}
        return {}

    # v0.4 — Check for recurring patterns and learn rules
    def _check_procedural_learning(self) -> None:
        """After actions, check if JARVIS should learn a new behavioral rule."""
        pattern = self.world_state.get_recurring_discrepancy_pattern()
        if pattern:
            # Get the most recent action with this discrepancy for context
            recent = [a for a in self.world_state.action_history if any(pattern in d for d in a.discrepancies)]
            if recent:
                descriptions = [a.description for a in recent[-3:]]
                rule = self.procedural_memory.observe_discrepancy(pattern, descriptions[-1])
                if rule and rule.trigger_count == 1:
                    print(f"  [Procedural Memory: Learned new rule — {rule.rule_text}]")

    # v0.4 — OVC-wrapped tool execution
    def _execute_with_safety(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        tool_name = tool_call.get("tool")
        params = tool_call.get("params", {})

        # Safety gate
        is_approved, reason = self.safety.check_tool_call(tool_name, params)
        if not is_approved:
            approved = self.safety.request_approval(tool_name, params, reason)
            if not approved:
                return {"success": False, "result": "User denied approval."}

        # v0.4 — OVC Loop: observe, verify, correct
        expected = self._predict_tool_outcome(tool_name, params)

        def execute_fn():
            return self.router.execute(tool_call)

        ovc_result = self.ovc.execute(
            action_type="tool",
            action_name=tool_name,
            description=f"Execute {tool_name} with {params}",
            execute_fn=execute_fn,
            expected=expected
        )

        # v0.4 — Learn from any discrepancies
        self._check_procedural_learning()

        if ovc_result.final_success:
            return {"success": True, "result": ovc_result.action_record.actual_result}
        else:
            return {
                "success": False,
                "result": f"{ovc_result.verification.recommendation} | Discrepancies: {ovc_result.observation.discrepancies}"
            }

    # v0.4 — OVC-wrapped agent delegation
    def _handle_agent_task(self, user_input: str) -> str:
        agent_name, reason = self.agents.select(user_input)
        if agent_name is None:
            return None

        self._notify_dashboard("flare_burst", {"intensity": "high", "reason": f"agent:{agent_name}"})
        print(f"  [Delegating to {agent_name}]")
        start = time.time()

        # v0.4 — Extract file paths for coding agent verification
        expected_files = []
        if agent_name == "coding_agent":
            expected_files = re.findall(r'/\S+\.\w+', user_input)

        # v0.4 — OVC-wrapped agent execution (critic is now mandatory inside OVC)
        def execute_agent():
            return self.agents.delegate(agent_name, user_input)

        ovc_result = self.ovc.execute(
            action_type="agent",
            action_name=agent_name,
            description=user_input,
            execute_fn=execute_agent,
            expected={"file_paths": expected_files, "success": True}
        )

        result = {
            "success": ovc_result.final_success,
            "result": ovc_result.action_record.actual_result.get("result", "")
            if isinstance(ovc_result.action_record.actual_result, dict)
            else str(ovc_result.action_record.actual_result)
        }
        agent_output = result.get("result", "")
        latency = int((time.time() - start) * 1000)

        # Track rejections in world state
        if not ovc_result.final_success:
            self.world_state.user.add_rejection(user_input)

        # v0.4 — Learn from any discrepancies (including critic rejections)
        self._check_procedural_learning()

        # v0.4 — Critic is now handled INSIDE the OVC loop, not post-hoc
        # The code below handles critic verdicts that came through the OVC loop
        if ovc_result.critic_verdict == "REJECT":
            self.evolution.log_action("agent", agent_name, False, latency, "Rejected by critic (OVC gate)", user_input)
            return "I need to reconsider that approach. Let me try again."
        elif ovc_result.critic_verdict == "NEEDS_FIX":
            self.evolution.log_action("agent", agent_name, False, latency, "Needs fix per critic (OVC gate)", user_input)
            fix_prompt = f"""{JARVIS_PERSONA}\n\nOriginal task: {user_input}\n\nFirst attempt had issues per critic review.\n\nProvide a corrected response.\n\nUser: {user_input}\nJARVIS:"""
            agent_output = self.llm.generate(fix_prompt, system=JARVIS_PERSONA)
            result["result"] = agent_output
        else:
            self.evolution.log_action("agent", agent_name, True, latency, "", user_input)

        self.memory.log_message("user", user_input, tool_call=f"delegate:{agent_name}")
        synthesis_prompt = f"""{JARVIS_PERSONA}\n\nYou delegated to {agent_name}. Result:\n{agent_output}\n\nRespond naturally. Summarize what was accomplished. Be concise.\n\nUser: {user_input}\nJARVIS:"""
        final = self.llm.generate(synthesis_prompt, system=JARVIS_PERSONA)
        self.memory.log_message("jarvis", final, tool_call=f"delegate:{agent_name}")
        self._extract_facts(user_input, final)
        self._notify_dashboard("flare_state", {"state": "normal"})
        return final

    def _handle_autonomous(self, goal: str) -> str:
        self._notify_dashboard("flare_burst", {"intensity": "high", "reason": "autonomous_plan"})
        print(f"\n  [Autonomous Planning: {goal}]")
        self.planner.tasks = []
        tasks = self.planner.plan(goal)
        print(f"  [Plan: {len(tasks)} steps]")
        for t in tasks:
            print(f"    Step {t.id}: {t.description} ({t.agent})")
        result = self.planner.execute(goal, self.memory)
        if self.current_project:
            self.projects.log(self.current_project, self.memory.current_session_id, f"Autonomous task: {goal} -> {result['summary']}")
        self.memory.log_message("user", f"plan: {goal}")
        self.memory.log_message("jarvis", result["summary"], tool_call="planner")
        synth = f"""{JARVIS_PERSONA}\n\nYou completed a multi-step task:\n{result['summary']}\n\nRespond to the user with the outcome. Be concise.\n\nUser: {goal}\nJARVIS:"""
        final = self.llm.generate(synth, system=JARVIS_PERSONA)
        self._extract_facts(goal, final)
        self._notify_dashboard("flare_state", {"state": "normal"})
        return final

    def _handle_vision(self, user_input: str) -> str:
        """Handle vision requests directly."""
        if "vision" not in self.tools:
            return "Vision tool not available. Install a vision model: ollama pull llava"
        query = user_input.replace("look", "").replace("see", "").replace("what do you", "").strip() or "Describe what you see."
        print("  [Capturing screen...]")
        result = self.tools["vision"].run(mode="screen", query=query)
        if result.get("success"):
            self.memory.log_message("user", user_input, tool_call="vision", tool_result=result["result"][:200])
            self.memory.log_message("jarvis", result["result"], tool_call="vision")
            return result["result"]
        else:
            return f"Vision failed: {result.get('result')}"

    def _handle_command(self, user_input: str) -> bool:
        cmd = user_input.lower().strip()

        if cmd == "exit":
            self.memory.end_session("User exited.")
            self.memory.close()
            self.world_state.save_checkpoint()  # v0.4 — persist state for crash recovery
            print("JARVIS: Goodbye.")
            return True

        if cmd == "tools":
            print("Tools:", list(self.tools.keys()))
            return True

        if cmd == "agents":
            print("Agents:", list(self.agents.agents.keys()))
            return True

        if cmd == "goals":
            goals = self.goals.list_active()
            if goals:
                for g in goals:
                    print(f"  [{g['progress']}%] {g['title']}")
            else:
                print("  No active goals.")
            return True

        if cmd == "projects":
            projects = self.projects.list_active()
            if projects:
                for p in projects:
                    print(f"  {p['name']} ({p['status']})")
            else:
                print("  No active projects.")
            return True

        if cmd.startswith("goal "):
            title = user_input[5:].strip()
            gid = self.goals.add(title)
            print(f"  Goal added: {title} ({gid})")
            return True

        if cmd.startswith("project "):
            name = user_input[8:].strip()
            pid = self.projects.create(name)
            self.current_project = pid
            print(f"  Project created: {name} ({pid})")
            return True

        if cmd == "voice on":
            self.config.set("voice_enabled", True)
            self.voice.enabled = True
            print("  Voice enabled.")
            return True

        if cmd == "voice off":
            self.config.set("voice_enabled", False)
            self.voice.enabled = False
            print("  Voice disabled.")
            return True

        if cmd.startswith("feedback "):
            try:
                rating = int(user_input.split()[1])
                comment = " ".join(user_input.split()[2:]) if len(user_input.split()) > 2 else ""
                self.evolution.log_feedback(self.memory.current_session_id, rating, comment)
                print(f"  Feedback recorded: {rating}/5")
            except (ValueError, IndexError):
                print("  Usage: feedback <1-5> [comment]")
            return True

        if cmd == "insights":
            print(self.evolution.get_insights())
            return True

        # v0.4 — Procedural memory commands
        if cmd == "rules":
            rules = self.procedural_memory.get_all_rules()
            if rules:
                print("  Learned behavioral rules:")
                for r in rules:
                    print(f"    [{r['confidence']:.0%}] {r['rule']}")
            else:
                print("  No learned rules yet.")
            return True

        if cmd.startswith("forget rule "):
            rule_id = user_input[12:].strip()
            if self.procedural_memory.delete_rule(rule_id):
                print(f"  Rule {rule_id} deleted.")
            else:
                print(f"  Rule {rule_id} not found.")
            return True

        return False

    def process(self, user_input: str) -> str:
        self._notify_dashboard("flare_burst", {"intensity": "high", "reason": "processing"})

        if self._handle_command(user_input):
            self._notify_dashboard("flare_state", {"state": "normal"})
            return ""

        # Vision shortcuts
        vision_triggers = ["look", "what do you see", "what is on my screen", "describe my screen", "see this"]
        if any(t in user_input.lower() for t in vision_triggers):
            result = self._handle_vision(user_input)
            self._notify_dashboard("flare_state", {"state": "normal"})
            return result

        # Autonomous planning
        if user_input.lower().startswith("plan "):
            result = self._handle_autonomous(user_input[5:].strip())
            self._notify_dashboard("flare_state", {"state": "normal"})
            return result

        # Agent delegation
        agent_response = self._handle_agent_task(user_input)
        if agent_response is not None:
            self._notify_dashboard("flare_state", {"state": "normal"})
            return agent_response

        # Normal tool/direct flow
        prompt = self._build_prompt(user_input)
        raw_response = self.llm.generate(prompt, system=JARVIS_PERSONA)

        is_tool, tool_call = self.router.parse_response(raw_response)

        if is_tool:
            self.memory.log_message("user", user_input, tool_call=tool_call["tool"], tool_result="[PENDING]")
            start = time.time()
            result = self._execute_with_safety(tool_call)
            latency = int((time.time() - start) * 1000)

            success = result.get("success", False)
            self.evolution.log_action("tool", tool_call["tool"], success, latency, result.get("result", "") if not success else "", user_input)

            if success:
                result_str = json.dumps(result.get("result"), indent=2)
            else:
                result_str = f"[ERROR] {result.get('result')}"

            follow_up = f"""{JARVIS_PERSONA}\n\nYou used tool '{tool_call['tool']}' with result:\n{result_str}\n\nRespond naturally. Be concise.\n\nUser: {user_input}\nJARVIS:"""
            final_response = self.llm.generate(follow_up, system=JARVIS_PERSONA)
            self.memory.log_message("jarvis", final_response, tool_call=tool_call["tool"])
            self._extract_facts(user_input, final_response)
            self._notify_dashboard("flare_state", {"state": "normal"})
            return final_response
        else:
            self.memory.log_message("user", user_input)
            self.memory.log_message("jarvis", raw_response)
            self._extract_facts(user_input, raw_response)
            self._notify_dashboard("flare_state", {"state": "normal"})
            return raw_response

    def chat_loop(self):
        print("=" * 50)
        print("JARVIS v0.4 — Cognitive AI Partner")
        print("=" * 50)
        print("Commands: exit | tools | agents | goals | projects | rules")
        print("          goal <title> | project <name> | voice on/off")
        print("          feedback <1-5> [comment] | insights")
        print("          forget rule <id>  — delete a learned rule")
        print("          plan <goal>  — autonomous multi-step execution")
        print("          look / what do you see  — vision (needs llava)")
        print()

        while True:
            try:
                user_input = input("You: ").strip()
                if not user_input:
                    continue

                response = self.process(user_input)
                if response:
                    print(f"JARVIS: {response}")
                    self.voice.speak(response)
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
