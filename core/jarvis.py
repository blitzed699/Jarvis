import json
import time
import sys
import re
from typing import Dict, Any
from .memory import JARVISMemory
from .llm import OllamaClient
from core.model_router import ModelRouter
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

from core.state import WorldState
from core.observer import Observer
from core.verifier import Verifier
from core.ovc_loop import OVCLoop
from core.memory_threadsafe import ThreadSafeMemory
from core.procedural_memory import ProceduralMemory

from core.replanning import ReplanningEngine
from core.scheduler import BackgroundScheduler
from core.knowledge_graph import KnowledgeGraph
from core.temporal import TemporalReasoner
from core.execution_broker import ExecutionBroker

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

        # v0.5 — Model Router
        self.model_router = ModelRouter({
            "model": self.config.get("model", model),
            "fast_model": self.config.get("fast_model", "llama3.2:1b"),
            "strong_model": self.config.get("strong_model", "qwen2.5-coder:14b"),
            "vision_model": self.config.get("vision_model", "llava"),
            "openai_api_key": self.config.get("openai_api_key"),
            "base_url": self.config.get("base_url")
        })
        self.llm = self.model_router

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

        # v0.4 — Procedural Memory
        self.procedural_memory = ProceduralMemory(self.llm)

        # v0.4 — OVC Loop with proper critic integration
        self.ovc = OVCLoop(
            self.llm, self.world_state, self.observer, self.verifier,
            critic_fn=self._run_critic
        )

        # NEW: Execution Broker — central gateway for ALL execution
        self.broker = ExecutionBroker(
            self.router, self.safety, self.ovc, self.world_state
        )

        # Inject broker into agents so they can't bypass safety
        self.agents.broker = self.broker

        # v0.4 — Planner wired with OVC and world state
        self.planner = AutonomousPlanner(
            self.llm, self.agents, self.router, self.safety, self.evolution,
            ovc_loop=self.ovc
        )
        self.planner.world_state = self.world_state

        # v0.5 — Tier 2
        self.replanner = ReplanningEngine(
            self.llm, self.planner, self.world_state, self.ovc
        )
        self.scheduler = BackgroundScheduler(jarvis_core=self)
        self.knowledge_graph = KnowledgeGraph()
        self.temporal = TemporalReasoner()

        self.voice = VoiceSynthesizer(enabled=self.config.get("voice_enabled", False))
        self.current_project = None

    def _run_critic(self, task: str, output: str) -> Dict[str, Any]:
        """v0.4 — Wrapper for critic agent to inject into OVC loop."""
        return self.agents.critique(task, output)

    def _notify_dashboard(self, event_type: str, data: dict = None):
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

        state_summary = self.world_state.get_state_summary()
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

    def _check_procedural_learning(self) -> None:
        pattern = self.world_state.get_recurring_discrepancy_pattern()
        if pattern:
            recent = [a for a in self.world_state.action_history if any(pattern in d for d in a.discrepancies)]
            if recent:
                descriptions = [a.description for a in recent[-3:]]
                rule = self.procedural_memory.observe_discrepancy(pattern, descriptions[-1])
                if rule and rule.trigger_count == 1:
                    print(f"  [Procedural Memory: Learned new rule — {rule.rule_text}]")

    # ==================================================================
    # v0.4.1: ALL tool execution routes through the broker
    # ==================================================================
    def _execute_with_safety(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool through the central broker (safety + OVC + evidence)."""
        return self.broker.execute_tool(
            tool_call,
            description=f"Execute {tool_call.get('tool')} with {tool_call.get('params')}",
            project_id=self.current_project
        )

    # ==================================================================
    # v0.4.1: ALL agent execution routes through the broker
    # ==================================================================
    def _handle_agent_task(self, user_input: str) -> str:
        agent_name, reason = self.agents.select(user_input)
        if agent_name is None:
            return None

        self._notify_dashboard("flare_burst", {"intensity": "high", "reason": f"agent:{agent_name}"})
        print(f"  [Delegating to {agent_name}]")
        start = time.time()

        expected_files = []
        if agent_name == "coding_agent":
            expected_files = re.findall(r'/\S+\.\w+', user_input)

        agent_instance = self.agents.agents.get(agent_name)
        if not agent_instance:
            return f"Agent {agent_name} not available."

        result = self.broker.execute_agent(
            agent_name=agent_name,
            task=user_input,
            agent_instance=agent_instance,
            expected_files=expected_files
        )

        agent_output = result.get("result", "")
        if isinstance(agent_output, dict):
            agent_output = agent_output.get("result", "")
        latency = int((time.time() - start) * 1000)

        if not result.get("success"):
            self.world_state.user.add_rejection(user_input)

        self._check_procedural_learning()

        self.evolution.log_action(
            "agent", agent_name, result.get("success", False),
            latency, result.get("recommendation", ""), user_input
        )

        self.memory.log_message("user", user_input, tool_call=f"delegate:{agent_name}")
        synthesis_prompt = f"""{JARVIS_PERSONA}\n\nYou delegated to {agent_name}. Result:\n{agent_output}\n\nRespond naturally. Summarize what was accomplished. Be concise.\n\nUser: {user_input}\nJARVIS:"""
        final = self.llm.generate(synthesis_prompt, system=JARVIS_PERSONA)
        self.memory.log_message("jarvis", final, tool_call=f"delegate:{agent_name}")
        self._extract_facts(user_input, final)
        self._notify_dashboard("flare_state", {"state": "normal"})
        return final

    # ==================================================================
    # v0.5: Autonomous planning with replanning
    # ==================================================================
    def _handle_autonomous(self, goal: str) -> str:
        self._notify_dashboard("flare_burst", {"intensity": "high", "reason": "autonomous_plan"})
        print(f"\n  [Autonomous Planning: {goal}]")
        self.planner.tasks = []
        tasks = self.planner.plan(goal)
        print(f"  [Plan: {len(tasks)} steps]")
        for t in tasks:
            print(f"    Step {t.id}: {t.description} ({t.agent})")

        result = self._execute_plan_with_replanning(goal, tasks)

        if self.current_project:
            self.projects.log(self.current_project, self.memory.current_session_id,
                              f"Autonomous task: {goal} -> {result['summary']}")
        self.memory.log_message("user", f"plan: {goal}")
        self.memory.log_message("jarvis", result["summary"], tool_call="planner")
        synth = f"""{JARVIS_PERSONA}\n\nYou completed a multi-step task:\n{result['summary']}\n\nRespond to the user with the outcome. Be concise.\n\nUser: {goal}\nJARVIS:"""
        final = self.llm.generate(synth, system=JARVIS_PERSONA)
        self._extract_facts(goal, final)

        try:
            self.knowledge_graph.extract_from_text(result["summary"], self.llm)
        except Exception:
            pass

        self._notify_dashboard("flare_state", {"state": "normal"})
        return final

    def _execute_plan_with_replanning(self, goal: str, tasks) -> Dict[str, Any]:
        """Execute a plan with automatic replanning on step failure."""
        from core.planner import Subtask

        completed = []
        failed = []
        attempt_counts = {}

        i = 0
        while i < len(tasks):
            task = tasks[i]
            attempt_counts[task.id] = attempt_counts.get(task.id, 0) + 1

            if task.depends_on:
                pending = [t for t in tasks if t.id in task.depends_on and t.status != "done"]
                if pending:
                    task.status = "failed"
                    task.result = "Dependencies not met"
                    failed.append(task)
                    if self.world_state:
                        self.world_state.update_plan_step(task.id, "failed")
                    i += 1
                    continue

            task.status = "running"
            print(f" [Step {task.id}] {task.description} -> {task.agent}")
            if self.world_state:
                self.world_state.update_plan_step(task.id, "running")

            context = "\n".join(
                f"[Previous Step {t.id}] {t.agent}: {t.result}"
                for t in tasks if t.status == "done" and t.result
            )

            start = time.time()
            result = {"success": False, "result": "No execution performed"}

            # v0.4.1: Route ALL plan steps through the broker
            if task.agent == "tool":
                full_desc = f"{context}\n\nCurrent task: {task.description}" if context else task.description
                tool_call = self._task_to_tool_call(full_desc)
                if tool_call:
                    result = self.broker.execute_tool(
                        tool_call,
                        description=task.description,
                        project_id=self.current_project
                    )
                else:
                    result = {"success": False, "result": "Could not convert task to tool call"}
            elif task.agent in self.agents.agents:
                full = f"{context}\n\nYour task: {task.description}" if context else task.description
                agent_instance = self.agents.agents[task.agent]
                result = self.broker.execute_agent(
                    agent_name=task.agent,
                    task=full,
                    agent_instance=agent_instance
                )
            else:
                full = f"{context}\n\nNow do this: {task.description}" if context else task.description
                result = {"success": True, "result": self.llm.generate(full)}

            latency = int((time.time() - start) * 1000)
            task.status = "done" if result.get("success") else "failed"
            task.result = str(result.get("result", ""))

            if self.world_state:
                self.world_state.update_plan_step(task.id, "done" if result.get("success") else "failed")
            self.evolution.log_action("planner_step", task.agent,
                                       result.get("success", False), latency, "", task.description)

            if result.get("success"):
                completed.append(task)
                i += 1
            else:
                failed.append(task)
                discrepancies = result.get("ovc", {}).get("discrepancies", [])
                if not discrepancies and not result.get("success"):
                    discrepancies = [result.get("result", "Unknown failure")]

                recovery_plan, analysis = self.replanner.execute_recovery(
                    goal, task, result, discrepancies,
                    completed, tasks[i+1:], attempt_counts[task.id]
                )

                print(f"  [Replanning] {recovery_plan.strategy.value}: {recovery_plan.reason}")

                if recovery_plan.strategy.value == "abort":
                    break
                elif recovery_plan.strategy.value == "skip":
                    task.status = "skipped"
                    i += 1
                elif recovery_plan.strategy.value == "retry":
                    task.status = "pending"
                    continue
                elif recovery_plan.strategy.value in ("retry_with_fix", "substitute", "replan_from"):
                    if recovery_plan.new_steps:
                        new_subtasks = [Subtask(**s) for s in recovery_plan.new_steps]
                        offset = max(t.id for t in tasks) + 10
                        for ns in new_subtasks:
                            ns.id += offset
                        tasks = tasks[:i] + new_subtasks + tasks[i+1:]
                        for ns in new_subtasks:
                            attempt_counts[ns.id] = 0
                        continue
                    else:
                        i += 1
                else:
                    i += 1

        if self.world_state and self.ovc:
            plan_verification = self.ovc.verifier.verify_plan_completion(
                self.world_state.active_plan, self.world_state
            )
            if not plan_verification.verified:
                return {
                    "success": False, "goal": goal,
                    "completed": len(completed), "failed": len(failed),
                    "tasks": [{"id": t.id, "description": t.description,
                               "status": t.status, "agent": t.agent} for t in tasks],
                    "summary": f"Plan execution had issues. {plan_verification.recommendation}"
                }

        return {
            "success": len(failed) == 0,
            "goal": goal,
            "completed": len(completed),
            "failed": len(failed),
            "tasks": [{"id": t.id, "description": t.description,
                       "status": t.status, "agent": t.agent} for t in tasks],
            "summary": self.planner._summarize(completed, failed)
        }

    def _task_to_tool_call(self, description: str) -> Dict[str, Any]:
        """Convert a natural language task to a tool call JSON."""
        prompt = f'Convert this task to a tool call JSON: {description}\nFormat: {{"tool": "name", "params": {{"key": "value"}}}}\nJSON:'
        raw = self.llm.generate(prompt, max_tokens=500)
        try:
            return json.loads(raw.strip())
        except json.JSONDecodeError:
            return None

    # ==================================================================
    # v0.4.1: Vision routed through ModelRouter, not hardcoded Ollama
    # ==================================================================
    def _handle_vision(self, user_input: str) -> str:
        if "vision" not in self.tools:
            return "Vision tool not available. Install a vision model: ollama pull llava"

        query = user_input.replace("look", "").replace("see", "").replace("what do you", "").strip() or "Describe what you see."
        print("  [Capturing screen...]")

        # Use the vision tool directly (it handles its own model via ModelRouter now)
        result = self.tools["vision"].run(mode="screen", query=query)

        if result.get("success"):
            self.memory.log_message("user", user_input, tool_call="vision", tool_result=result["result"][:200])
            self.memory.log_message("jarvis", result["result"], tool_call="vision")
            return result["result"]
        else:
            return f"Vision failed: {result.get('result')}"

    # ==================================================================
    # Command handlers
    # ==================================================================
    def _handle_command(self, user_input: str) -> bool:
        cmd = user_input.lower().strip()

        if cmd == "exit":
            self.memory.end_session("User exited.")
            self.memory.close()
            self.world_state.save_checkpoint()
            self.scheduler.stop()
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

        if cmd == "routing":
            stats = self.model_router.get_stats()
            print(f"  Routing Stats:")
            print(f"    Total requests: {stats['total_requests']}")
            if stats['total_requests'] > 0:
                print(f"    Avg latency: {stats['avg_latency_ms']}ms")
                print(f"    Total cost: {stats['total_cost']} units")
                print(f"    Backend distribution: {stats['backend_distribution']}")
            print(f"    Available backends: {', '.join(stats['backends_available'])}")
            return True

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

        if cmd == "jobs":
            jobs = self.scheduler.list_jobs()
            if jobs:
                print(f"  Scheduled jobs ({len(jobs)}):")
                for j in jobs:
                    status_icon = "●" if j.status == "pending" else "○" if j.status == "completed" else "✗"
                    next_run = j.next_run or "N/A"
                    print(f"    {status_icon} [{j.id}] {j.name} ({j.job_type}) — next: {next_run}")
            else:
                print("  No scheduled jobs.")
            return True

        if cmd.startswith("schedule "):
            rest = user_input[9:].strip()
            parsed = self.scheduler.parse_natural_schedule(rest)
            if parsed:
                task_desc = rest
                job_type = "reminder"
                job_args = {"message": task_desc}

                if any(k in rest.lower() for k in ["code", "script", "python", "build"]):
                    job_type = "agent"
                    job_args = {"agent": "coding_agent", "task": task_desc}
                elif any(k in rest.lower() for k in ["research", "find", "search"]):
                    job_type = "agent"
                    job_args = {"agent": "research_agent", "task": task_desc}
                elif any(k in rest.lower() for k in ["shell", "command", "run"]):
                    job_type = "shell"
                    job_args = {"command": task_desc}

                jid = self.scheduler.add_job(
                    name=task_desc[:40],
                    trigger=parsed["trigger"],
                    trigger_args=parsed["trigger_args"],
                    job_type=job_type,
                    job_args=job_args
                )
                print(f"  Scheduled: {jid} — {task_desc[:50]}")
            else:
                print("  Could not parse schedule. Try: 'every 5 minutes check email'")
            return True

        if cmd.startswith("cancel "):
            job_id = user_input[7:].strip()
            if self.scheduler.cancel_job(job_id):
                print(f"  Cancelled job {job_id}")
            else:
                print(f"  Job {job_id} not found")
            return True

        if cmd.startswith("kg add "):
            rest = user_input[7:].strip()
            m = re.match(r'(.+?)\s+is\s+a\s+(.+)', rest, re.I)
            if m:
                name, etype = m.group(1).strip(), m.group(2).strip()
                self.knowledge_graph.add_entity(name, etype)
                print(f"  Added entity: {name} ({etype})")
            else:
                m = re.match(r'(.+?)\s+(uses|depends on|created by|part of|requires)\s+(.+)', rest, re.I)
                if m:
                    from_name, rel, to_name = m.group(1).strip(), m.group(2).strip().replace(" ", "_"), m.group(3).strip()
                    self.knowledge_graph.add_relation(from_name, rel, to_name)
                    print(f"  Added relation: {from_name} {rel} {to_name}")
                else:
                    print("  Usage: kg add <name> is a <type>")
                    print("         kg add <name> uses <other>")
            return True

        if cmd.startswith("kg query "):
            query = user_input[9:].strip()
            results = self.knowledge_graph.query(entity_name=query)
            if results["entities"] or results["relations"]:
                print(f"  Knowledge Graph results for '{query}':")
                for e in results["entities"][:5]:
                    print(f"    📦 {e['name']} ({e['type']})")
                for r in results["relations"][:5]:
                    print(f"    🔗 {r['from_name']} {r['relation']} {r['to_name']}")
            else:
                print(f"  No knowledge found for '{query}'")
            return True

        if cmd == "kg stats":
            stats = self.knowledge_graph.get_stats()
            print(f"  Knowledge Graph: {stats['entities']} entities, {stats['relations']} relations")
            if stats['entity_types']:
                print("  Entity types:", ", ".join(f"{k}:{v}" for k, v in stats['entity_types'].items()))
            return True

        if cmd.startswith("kg summarize "):
            name = user_input[13:].strip()
            summary = self.knowledge_graph.summarize_entity(name)
            print(summary)
            return True

        if cmd.startswith("deadline "):
            rest = user_input[9:].strip()
            expr = self.temporal.parse(rest)
            if expr and expr.target_datetime:
                status = self.temporal.time_until(expr.target_datetime)
                print(f"  Deadline: {expr.description}")
                print(f"  Status: {status['text']}")
                self.memory.store_fact(f"Deadline: {rest} — {status['text']}", category="deadline")
            else:
                print("  Could not parse deadline. Try: 'deadline 2026-09-15' or 'deadline next Friday'")
            return True

        if cmd == "replan stats":
            stats = self.replanner.get_stats()
            print(f"  Replanning stats: {stats}")
            return True

        return False

    def process(self, user_input: str) -> str:
        self._notify_dashboard("flare_burst", {"intensity": "high", "reason": "processing"})

        if self._handle_command(user_input):
            self._notify_dashboard("flare_state", {"state": "normal"})
            return ""

        vision_triggers = ["look", "what do you see", "what is on my screen", "describe my screen", "see this"]
        if any(t in user_input.lower() for t in vision_triggers):
            result = self._handle_vision(user_input)
            self._notify_dashboard("flare_state", {"state": "normal"})
            return result

        if user_input.lower().startswith("plan "):
            result = self._handle_autonomous(user_input[5:].strip())
            self._notify_dashboard("flare_state", {"state": "normal"})
            return result

        agent_response = self._handle_agent_task(user_input)
        if agent_response is not None:
            self._notify_dashboard("flare_state", {"state": "normal"})
            return agent_response

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

            try:
                self.knowledge_graph.extract_from_text(
                    f"User: {user_input}\nJARVIS: {final_response}",
                    self.llm
                )
            except Exception:
                pass

            self._notify_dashboard("flare_state", {"state": "normal"})
            return final_response
        else:
            self.memory.log_message("user", user_input)
            self.memory.log_message("jarvis", raw_response)
            self._extract_facts(user_input, raw_response)

            try:
                self.knowledge_graph.extract_from_text(
                    f"User: {user_input}\nJARVIS: {raw_response}",
                    self.llm
                )
            except Exception:
                pass

            self._notify_dashboard("flare_state", {"state": "normal"})
            return raw_response

    def chat_loop(self):
        print("=" * 50)
        print("JARVIS v0.5 — Intelligent Cognitive AI Partner")
        print("=" * 50)
        print("Commands: exit | tools | agents | goals | projects | rules | routing")
        print("          goal <title> | project <name> | voice on/off")
        print("          feedback <1-5> [comment] | insights")
        print("          forget rule <id>  — delete a learned rule")
        print("          plan <goal>  — autonomous multi-step execution")
        print("          look / what do you see  — vision (needs llava)")
        print("  —— Tier 2 ——")
        print("          schedule <task> every N minutes/hours/days")
        print("          schedule <task> at HH:MM | in N minutes")
        print("          schedule <task> every Monday at 9am")
        print("          jobs  — list scheduled jobs")
        print("          cancel <job_id>")
        print("          kg add <name> is a <type>")
        print("          kg add <name> uses <other>")
        print("          kg query <name> | kg stats | kg summarize <name>")
        print("          deadline <time expression>")
        print("          replan stats")
        print()

        self.scheduler.start()

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
                self.scheduler.stop()
                break
            except Exception as e:
                print(f"[SYSTEM ERROR] {e}")


if __name__ == "__main__":
    jarvis = JARVISCore()
    jarvis.chat_loop()
