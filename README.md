JARVIS v0.4 — Cognitive AI Partner

Local-first personal AI with memory, tools, agents, planning, and a cognitive control loop.

JARVIS is a modular, local-first AI assistant designed to become a genuine personal AI system rather than a simple chatbot.

It can remember information across sessions, use tools, delegate work to specialist agents, manage projects and goals, interact with the computer, search the web, generate and modify files, and maintain a structured understanding of its current state.

With v0.4, JARVIS gains a cognitive control layer designed around a simple principle:

«JARVIS should not believe an action succeeded just because an AI said it did. It should check.»

---

🧠 WHAT'S NEW IN v0.4

Cognitive Control Loop — OVC

Observe → Verify → Correct

JARVIS now has a dedicated cognitive control loop around actions.

Instead of:

Plan → Execute → Claim Success

JARVIS moves toward:

Plan
  ↓
Execute
  ↓
Observe
  ↓
Verify
  ↓
Correct if necessary
  ↓
Confirm actual result

The OVC system is designed to make JARVIS verify the real state of the environment rather than trusting an LLM's description of what happened.

---

🔍 Hallucination Detection

AI agents can confidently report that they completed something when they did not.

JARVIS v0.4 introduces verification between an agent's claim and the actual environment.

For example:

Coding Agent:
"I created app.py successfully."

JARVIS:
→ Observe filesystem
→ Verify app.py exists
→ Verify contents
→ Check execution/test result

Result:
✓ Verified

If the file does not exist:

✗ Agent claim does not match reality
→ Record discrepancy
→ Attempt correction
→ Re-verify

This creates an important distinction between:

"The model says it happened"

and

"JARVIS has evidence that it happened."

---

📊 Structured World State

JARVIS now maintains a structured representation of its current state.

The cognitive state can track information such as:

- Active plans
- Current objectives
- Recent failures
- Open questions
- Verification results
- User trust state
- Environment observations
- Current execution context
- State checkpoints

This gives JARVIS something closer to an internal world model rather than relying entirely on conversation history.

---

✅ Plan Verification Gate

JARVIS is designed to avoid declaring a multi-step task complete when the underlying execution state says otherwise.

A plan should not be considered successfully completed when:

- A required step failed
- An agent reported success without evidence
- A verification check failed
- A discrepancy remains unresolved
- The environment does not match the expected result

The planner can therefore distinguish between:

COMPLETED
FAILED
NEEDS CORRECTION
UNVERIFIED

rather than treating every agent response as success.

---

🛡️ Thread-Safe Memory

JARVIS uses persistent memory backed by:

- SQLite
- ChromaDB

The memory layer has been updated for safer concurrent use between components such as the dashboard and conversational runtime.

This is important as JARVIS moves toward a system where multiple processes and agents can interact with the same persistent memory.

---

🧪 Cognitive Test Suite

The repository now includes dedicated testing for the cognitive architecture.

The OVC test coverage verifies core behaviour around:

- Observation
- Verification
- Correction
- State handling
- Cognitive checkpoints

The repository currently contains dedicated OVC testing alongside the existing memory, tool, and agent tests.

---

🤖 CORE CAPABILITIES

Persistent Memory

JARVIS can maintain information beyond a single conversation.

Memory includes:

- Persistent facts
- Conversation context
- Semantic memory
- Long-term retrieval
- Automatic fact extraction

Memory is backed by SQLite and ChromaDB.

---

🧰 Tool Use

JARVIS can interact with its environment through modular tools.

Current tool categories include:

Tool| Purpose
"file_read"| Read files
"file_list"| Inspect directories
"write_file"| Create or modify files
"shell"| Execute shell commands
"run_python"| Execute Python scripts
"open_app"| Launch applications
"web_search"| Search the web
"organize_files"| Organise files
Vision tools| Computer/visual context

Destructive or potentially dangerous operations can be subject to approval through the safety layer.

---

🧠 SPECIALIST AGENTS

JARVIS uses specialist agents rather than forcing one general-purpose prompt to handle every type of task.

Coding Agent

- Software architecture
- Code generation
- Debugging
- Testing
- Refactoring
- Development tasks

Research Agent

- Information gathering
- Documentation research
- Technology comparison
- Research reports

Business Agent

- Market analysis
- Business ideas
- Monetisation strategies
- Competitive analysis

Creative Agent

- Product ideas
- Branding
- Creative concepts
- Marketing copy
- Naming and slogans

Critic Agent

Provides an additional layer for evaluating work and identifying problems.

---

🗂️ PROJECT MANAGEMENT

JARVIS can organise work into projects.

Projects provide a workspace for:

- Goals
- Notes
- Generated code
- Research
- Task history
- Related memories

Example:

project Jarvis AI

The long-term goal is for projects to become persistent working contexts that JARVIS can understand and continue across sessions.

---

🎯 GOAL MANAGEMENT

JARVIS can maintain long-term objectives and track their progress.

Examples:

goal Build a smart home assistant

goal Learn Rust programming

Goals can be connected to projects and used by JARVIS when planning future work.

---

🧭 PLANNING

JARVIS includes a dedicated planning layer for breaking larger objectives into actionable steps.

The v0.4 cognitive architecture adds verification around this process so that planning is not simply:

Make a plan → execute → assume success

but instead:

Plan
↓
Execute
↓
Observe
↓
Verify
↓
Correct
↓
Continue

This is a major architectural step toward autonomous task execution.

---

🔄 EVOLUTION

JARVIS also contains an evolution layer intended to support the system becoming better over time.

The long-term direction is for JARVIS to learn from:

- Failures
- Successful actions
- Corrections
- User feedback
- Repeated tasks
- Verification results

The goal is not merely to make the language model larger.

The goal is to make the system around the model smarter.

---

🗣️ VOICE

JARVIS supports voice output and can be enabled or disabled.

voice on
voice off

Voice support is intended to evolve toward a more natural hands-free interface.

---

🖥️ JARVIS DASHBOARD

JARVIS includes a dedicated web dashboard for interacting with and monitoring the system.

The Dashboard provides a visual interface around the JARVIS runtime while the core remains modular and Python-based.

Current dashboard components live under:

Dashboard/
├── index.html
└── server.py

The dashboard is intended to become the visual command centre for the JARVIS system.

---

🏗️ ARCHITECTURE

Current repository structure:

Jarvis/
│
├── Dashboard/
│   ├── index.html
│   └── server.py
│
├── agents/
│   ├── base.py
│   ├── coding_agent.py
│   ├── research_agent.py
│   ├── business_agent.py
│   ├── creative_agent.py
│   └── critic_agent.py
│
├── core/
│   ├── jarvis.py
│   ├── llm.py
│   ├── router.py
│   ├── memory.py
│   ├── Memory_threadsafe.py
│   ├── extractor.py
│   ├── safety.py
│   ├── agent_registry.py
│   ├── config.py
│   ├── goals.py
│   ├── projects.py
│   ├── planner.py
│   ├── evolution.py
│   │
│   ├── Observer.py
│   ├── Verifier.py
│   ├── Ovc_loop.py
│   ├── State.py
│   └── Test_ovc.py
│
├── tools/
│   ├── base.py
│   ├── computer_tools.py
│   ├── file_tools.py
│   ├── organize_tool.py
│   ├── shell_tool.py
│   ├── vision_tool.py
│   └── web_search.py
│
├── tests/
│   ├── test_agents.py
│   ├── test_memory.py
│   ├── test_ovc.py
│   └── test_tools.py
│
├── main.py
├── requirements.txt
└── README.md

---

🧩 SYSTEM LAYERS

LLM Layer

Handles communication with the local language model through Ollama.

Memory Layer

Stores and retrieves persistent information using SQLite and ChromaDB.

Router

Determines intent and selects the appropriate tool or agent.

Tool Layer

Provides JARVIS with controlled access to files, shell commands, Python execution, web search, applications, and computer/vision functionality.

Agent Layer

Specialist agents perform domain-specific work.

Planner

Breaks larger objectives into executable plans.

Safety Layer

Controls potentially dangerous operations and approval requirements.

Cognitive Layer

The v0.4 OVC system observes and verifies what actually happened.

World State

Maintains structured information about JARVIS's current beliefs, plans, failures, questions, and environment.

Dashboard

Provides a visual interface for interacting with and monitoring JARVIS.

---

🔐 SAFETY

JARVIS is designed around controlled tool execution.

Read-only operations can be automatically approved where configured.

Potentially destructive actions can require explicit approval.

The cognitive verification layer adds another safety boundary by checking the actual result of operations rather than trusting generated text.

---

💻 SETUP

1. Clone the repository

git clone https://github.com/blitzed699/Jarvis.git
cd Jarvis

2. Install Ollama

curl -fsSL https://ollama.com/install.sh | sh

3. Download the default model

ollama pull llama3.1

4. Install Python dependencies

pip install -r requirements.txt

5. Launch JARVIS

python main.py --dashboard

---

🎮 COMMANDS

Command| Action
"exit"| Quit JARVIS
"tools"| List available tools
"agents"| List specialist agents
"goals"| Display active goals
"projects"| Display active projects
"goal <title>"| Create a goal
"project <name>"| Create a project
"voice on"| Enable voice
"voice off"| Disable voice

---

🧪 TESTING

Run the existing test suites:

python tests/test_memory.py
python tests/test_tools.py
python tests/test_agents.py
python tests/test_ovc.py

The v0.4 test suite specifically exercises the cognitive control architecture.

---

🔬 DEVELOPMENT PHILOSOPHY

JARVIS is being built around several principles:

1. Local First

The core AI should run locally wherever practical.

2. Persistent

JARVIS should remember useful information across sessions.

3. Modular

Tools, agents, memory, planning, safety, and cognition should remain independently extensible.

4. Verifiable

JARVIS should verify important claims against reality.

5. Correctable

Failure should trigger investigation and correction rather than being silently accepted.

6. Transparent

JARVIS should be able to explain what it believes happened and why.

7. Autonomous — But Controlled

The objective is not blind automation.

The objective is an AI that can independently perform useful work while respecting safety boundaries and verifying its own actions.

---

🚀 THE LONG-TERM VISION

JARVIS is being developed as the foundation for a personal AI operating system.

The eventual goal is a system that can:

Understand the user
        ↓
Remember context
        ↓
Understand goals
        ↓
Plan
        ↓
Delegate
        ↓
Execute
        ↓
Observe
        ↓
Verify
        ↓
Correct
        ↓
Learn
        ↓
Improve

Instead of simply generating an answer, JARVIS should eventually be capable of taking a high-level objective such as:

"Build me an app that tracks my wife's ovulation cycle."

and turn that objective into a complete workflow:

Understand requirements
        ↓
Create project
        ↓
Plan architecture
        ↓
Delegate development
        ↓
Write code
        ↓
Run tests
        ↓
Observe results
        ↓
Verify implementation
        ↓
Identify failures
        ↓
Correct failures
        ↓
Re-test
        ↓
Report only what was actually completed

That is the direction of JARVIS.

Not just an AI that talks.

An AI system that can think through work, act on the environment, check itself, and correct its own mistakes.

---

📌 CURRENT VERSION

JARVIS v0.4 — Cognitive AI Partner

Current major capabilities:

- 🧠 Cognitive OVC control loop
- 🔍 Action verification
- 🛡️ Hallucination/discrepancy detection
- 📊 Structured world state
- ✅ Plan verification
- 💾 Persistent SQLite memory
- 🧠 ChromaDB semantic memory
- 🔒 Thread-safe memory
- 🤖 Specialist agents
- 🧑‍💻 Coding agent
- 🔬 Research agent
- 💼 Business agent
- 🎨 Creative agent
- 🧐 Critic agent
- 🧰 Modular tools
- 🌐 Web search
- 🖥️ Computer interaction
- 👁️ Vision tooling
- 🐍 Python execution
- 📁 File management
- 🐚 Shell execution
- 🎯 Goal management
- 🗂️ Project management
- 🧭 Planning
- 🔄 Evolution layer
- 🗣️ Voice support
- 🖥️ Web dashboard
- 🧪 Automated testing
- 🔐 Safety and approval controls

---

⚠️ DEVELOPMENT STATUS

JARVIS is an active development project.

v0.4 represents a significant architectural transition from a traditional tool-using assistant toward a cognitive agent architecture.

The OVC system, structured world state, verification gates, planning, memory, agents, tools, dashboard, and evolution layers are the foundation for future autonomous capabilities.

Expect rapid architectural changes as the system continues to evolve.

---

License

See the repository for current licensing information.
