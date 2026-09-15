# JARVIS — Cognitive AI Partner

**Local-first personal AI with persistent memory, specialist agents, planning, verification, replanning, and a structured world model.**

JARVIS is a modular, local-first AI assistant designed to become a genuine personal AI system rather than a simple chatbot.

It can remember information across sessions, use tools, delegate work to specialist agents, manage projects and goals, interact with the computer, search the web, generate and modify files, execute multi-step plans, verify actions against the real environment, and maintain a structured representation of its current state.

The project is deliberately being developed incrementally. The goal is not simply to connect a language model to more tools, but to build the surrounding cognitive architecture that allows JARVIS to **plan, act, observe, verify, recover, and improve**.

---

## 🧠 CURRENT ARCHITECTURE

JARVIS is currently built around several cooperating layers:


User Goal
   │
   ▼
JARVIS Core
   │
   ├── Memory
   ├── Knowledge Graph
   ├── Temporal Reasoning
   ├── Planner
   ├── Replanning Engine
   ├── Scheduler
   ├── Specialist Agents
   └── Tool Router
            │
            ▼
      Execution Broker
            │
      ┌─────┴─────┐
      ▼           ▼
 Safety Gate     OVC
                  │
          Observe → Verify
                  │
             Correct /
             Replan
                  │
                  ▼
             World State


The **Execution Broker** is the central execution gateway for tools and agents.

This creates a controlled path between JARVIS's reasoning systems and actions that affect the environment.

The **OVC loop** provides the cognitive verification layer:

Observe → Verify → Correct

The **World State** maintains structured information about plans, actions, failures, uncertainties, questions, environment state, and checkpoints.

The **Replanning Engine** allows JARVIS to respond to failed plan steps instead of simply stopping or falsely reporting success.

---

## 🔐 CORE DESIGN PRINCIPLE

JARVIS should not believe an action succeeded simply because an AI said it did.

It should check.

Instead of:


Plan → Execute → Claim Success


JARVIS is being developed toward:


Plan
  ↓
Execute
  ↓
Observe
  ↓
Verify
  ↓
Correct / Replan if necessary
  ↓
Verify again
  ↓
Report the actual result


This distinction is fundamental to the project.

> **"The model says it happened" is not the same as "JARVIS has evidence that it happened."**

---

## 🧠 OVC — OBSERVE, VERIFY, CORRECT

The OVC system provides verification around actions performed by JARVIS.

For example, an agent may report:


"I created app.py successfully."


JARVIS can instead:

Observe filesystem
      ↓
Verify app.py exists
      ↓
Verify expected state
      ↓
Check execution/test result
      ↓
Confirm or identify discrepancy


If reality does not match the expected result, the discrepancy becomes part of JARVIS's structured state and can feed into correction or replanning.

OVC is used in the execution architecture rather than existing as an isolated feature.

Live verification has been tested through the actual:


JARVISCore
    ↓
ExecutionBroker
    ↓
Safety
    ↓
OVC
    ↓
Tool / Agent
    ↓
Observer
    ↓
Verifier


execution path.

---

## 🛡️ EXECUTION BROKER

The Execution Broker is the central gateway for execution.

Tools and specialist agents are routed through the broker rather than directly performing unrestricted execution.

Its responsibilities include:

* Safety checks
* Tool execution
* Agent execution
* OVC integration
* Evidence collection
* Verification results
* Correction handling
* Structured execution results

This provides a single architectural boundary between **reasoning** and **action**.

The broker is also used by the planner/replanning execution path, allowing planned tasks to use the same controlled execution infrastructure.

---

## 🌍 STRUCTURED WORLD STATE

JARVIS maintains a structured world model rather than relying entirely on conversation history.

World State can track:

* Active plans
* Plan step status
* Action history
* Recent failures
* Corrections
* Open questions
* Uncertainties
* Environment observations
* User state
* Execution context
* Session information
* Checkpoints

World State can also be saved and restored through checkpoints.

This allows cognitive state to persist beyond a single execution cycle and provides later components with structured context about what JARVIS believes has happened.

---

## 🔄 PLANNING + REPLANNING

JARVIS can break a high-level goal into executable subtasks.

A plan is registered with World State when it is created, allowing plan execution and final verification to operate on the same structured state.

When a task fails, the Replanning Engine can analyse the failure and determine an appropriate recovery strategy.

Possible strategies include:

* Retry
* Retry with a fix
* Skip
* Substitute
* Replan from a different point
* Abort

This moves JARVIS beyond simple linear task execution toward **failure-aware execution**.

---

## 🧪 VERIFIED DEVELOPMENT STATUS

The current architecture is being developed and verified incrementally.

Latest verified regression baseline:


42 passed
24 warnings


The warnings are currently from third-party ChromaDB/Pydantic compatibility/deprecation messages rather than failing JARVIS tests.

The project follows a strict development principle:

> **Do not claim a capability works until it has been exercised and verified.**

---
## ⚙️ CURRENT CAPABILITIES

JARVIS currently includes the following major capabilities.

### 💾 Persistent Memory

JARVIS uses persistent memory to retain useful information across sessions.

Memory is intended to provide continuity rather than simply storing raw conversation history.

Current memory functionality includes:

* Persistent storage
* Semantic retrieval
* User/project context
* Procedural memory
* Memory-aware reasoning
* Cross-session continuity

---

### 🧠 Specialist Agents

JARVIS uses specialist agents rather than forcing every task through a single generic reasoning path.

Current registered agents include:

| Agent            | Purpose                               |
| ---------------- | ------------------------------------- |
| `research_agent` | Research and information gathering    |
| `business_agent` | Business-oriented analysis and tasks  |
| `creative_agent` | Creative generation and refinement    |
| `coding_agent`   | Coding and software-development tasks |
| `critic_agent`   | Evaluation and critique               |

Agents are managed through the central Agent Registry.

Agent execution can pass through the Execution Broker and OVC verification pipeline.

---

### 🛠️ Tool System

JARVIS has a modular tool architecture with a central Tool Router.

Current tool categories include:

* File reading
* File listing
* File writing
* File organisation
* Shell execution
* Python execution
* Application launching
* Vision
* Web search

Tools are routed through the execution architecture rather than being directly invoked by individual agents.

---

### 📋 Planning

The Planner converts high-level goals into structured subtasks.

Each subtask contains information such as:

* ID
* Description
* Assigned agent
* Dependencies
* Status
* Result

Example:


Goal
 ↓
Planner
 ↓
┌─────────────────────────────┐
│ Step 1 → research_agent     │
│ Step 2 → coding_agent       │
│ Step 3 → creative_agent     │
│ Step 4 → llm                │
└─────────────────────────────┘


Plans are registered with World State when generated so that execution and verification operate against the same plan state.

---

## 🔄 REPLANNING ENGINE

The Replanning Engine provides recovery when execution does not go according to plan.

Instead of treating every failed task as the end of an operation, JARVIS can analyse the failure and determine whether recovery is possible.

The recovery system supports strategies including:


FAILURE
   │
   ▼
Analyse discrepancy
   │
   ▼
Replanning Engine
   │
   ├── Retry
   ├── Retry with fix
   ├── Substitute
   ├── Skip
   ├── Replan from point
   └── Abort


Replanning also receives structured World State context, allowing recovery decisions to consider what JARVIS already knows about the current execution.

---

## 🕐 TEMPORAL REASONING

JARVIS includes a Temporal Reasoning component for reasoning about time-related information.

The system supports concepts including:

* Relative time expressions
* Deadlines
* Recurring events
* Temporal relationships
* Scheduled events
* Time-aware reasoning

Examples of concepts the system can reason about include:

tomorrow
next week
in 3 hours
every Monday
before the deadline
after the previous task


Temporal reasoning is designed to become part of JARVIS's broader cognitive state rather than functioning as an isolated date parser.

---

## 🕸️ KNOWLEDGE GRAPH

JARVIS includes a Knowledge Graph for representing relationships between entities and concepts.

The graph can extract and maintain:

* Entities
* Relationships
* Connections between concepts
* Structured knowledge derived from information

This provides a representation that complements semantic memory.

Conceptually:

Memory
  │
  ├── Semantic information
  │
  └── Knowledge Graph
          │
          ├── Entity
          │    └── Relationship
          │          └── Entity
          │
          └── Concept


The long-term goal is to allow JARVIS to reason over both remembered information and explicit relationships.

---

## ⏰ SCHEDULER

JARVIS includes a Scheduler component for managing time-based tasks and events.

The Scheduler is designed to work alongside:

* Temporal Reasoning
* World State
* Planning
* Goals
* Future execution

This provides the foundation for eventually allowing JARVIS to maintain ongoing responsibilities rather than only reacting to immediate user messages.

---

## 💾 CHECKPOINT RESTORATION

JARVIS supports structured World State checkpoints.

A checkpoint can preserve cognitive state including:

* Session information
* Active plans
* Plan step statuses
* Action history
* Open questions
* Uncertainties
* Environment state
* User state

When restored, JARVIS reconstructs structured state rather than merely restoring a session identifier.

This is important for long-running autonomous workflows where losing process state should not require rebuilding the entire context from scratch.

---

## 🎯 PROJECT + GOAL CONTEXT

JARVIS includes project and goal management so that tasks can be understood within a larger objective.

This provides context for:

* Long-running projects
* Multi-step work
* Planning
* Agent delegation
* Progress tracking
* Future scheduling

The intention is for JARVIS to understand not only **what task is being requested**, but also **what larger project that task belongs to**.

---

## 🔍 VERIFICATION-FIRST EXECUTION

Verification is treated as a first-class component of execution.

For actions where an expected outcome can be defined, JARVIS can compare:

EXPECTED STATE
      │
      ▼
   EXECUTE
      │
      ▼
 OBSERVED STATE
      │
      ▼
   VERIFY
      │
   ┌──┴──┐
   │     │
 MATCH  MISMATCH
   │     │
   ▼     ▼
SUCCESS CORRECT / REPLAN


This architecture is specifically intended to reduce false success reports and make failures visible to the rest of the cognitive system.

---

## 🧩 COGNITIVE ARCHITECTURE

The current cognitive architecture can therefore be viewed as several cooperating systems:

| Component          | Responsibility                             |
| ------------------ | ------------------------------------------ |
| Memory             | Persistent semantic/contextual information |
| Procedural Memory  | Reusable procedures and learned workflows  |
| Knowledge Graph    | Explicit entities and relationships        |
| Temporal Reasoning | Time and temporal relationships            |
| Planner            | Goal decomposition                         |
| Replanning         | Failure recovery and adaptive planning     |
| Scheduler          | Time-based execution                       |
| World State        | Structured current state                   |
| Observer           | Reality/environment observation            |
| Verifier           | Expected vs actual validation              |
| OVC                | Observe → Verify → Correct cycle           |
| Execution Broker   | Central execution gateway                  |
| Agent Registry     | Specialist-agent management                |
| Tool Router        | Tool dispatch and execution                |

Together these components form the foundation for JARVIS as a **cognitive system**, rather than simply an LLM wrapper.
## 📁 PROJECT STRUCTURE

The repository is organised into separate layers for cognition, execution, agents, tools, interfaces, and testing.

Jarvis/
│
├── core/
│   ├── jarvis.py
│   ├── planner.py
│   ├── replanning.py
│   ├── execution_broker.py
│   ├── ovc_loop.py
│   ├── observer.py
│   ├── verifier.py
│   ├── state.py
│   ├── scheduler.py
│   ├── temporal.py
│   ├── knowledge_graph.py
│   ├── router.py
│   ├── agent_registry.py
│   └── ...
│
├── agents/
│   ├── coding_agent.py
│   ├── research_agent.py
│   ├── business_agent.py
│   ├── creative_agent.py
│   ├── critic_agent.py
│   └── ...
│
├── tools/
│   ├── base.py
│   ├── file_tools.py
│   ├── computer_tools.py
│   ├── shell_tool.py
│   ├── organize_tool.py
│   ├── vision_tool.py
│   ├── web_search.py
│   └── ...
│
├── tests/
│   ├── test_memory.py
│   ├── test_model_router.py
│   ├── test_cognitive.py
│   ├── test_ovc.py
│   ├── test_tools.py
│   ├── test_agents.py
│   ├── test_tier2.py
│   └── ...
│
├── main.py
├── requirements.txt
├── README.md
└── ...


The repository contains additional supporting modules and project files; the structure above highlights the major architectural components.

---

## 🧪 TESTING

JARVIS is developed using incremental verification.

Tests are run after meaningful architectural changes rather than relying solely on manual inspection.

### Current regression baseline

42 passed
24 warnings

The current test suite covers areas including:

* Memory
* Model routing
* Cognitive components
* OVC
* Tools
* Agents
* Tier 2 intelligence
* Planning-related behaviour
* Temporal reasoning
* Knowledge graph
* Scheduler functionality

### OVC / Cognitive verification

The cognitive and OVC test coverage currently includes:

13 passed

### Tier 2 verification

Tier 2 functionality currently includes tests covering:

14 passed

The project uses these tests as regression protection while the architecture continues to evolve.

---

## 🏗️ DEVELOPMENT MILESTONES

JARVIS development is organised into incremental architectural milestones.

### B1 — Universal Execution Broker

**Status: COMPLETE**

The Execution Broker became the central gateway for tool and agent execution.

Completed objectives include:

* Centralised execution
* Safety integration
* OVC integration
* Evidence collection
* Agent execution through the broker
* Removal of direct execution fallbacks from `CodingAgent`

---

### B2.1 — World State Checkpoint Restoration

**Status: COMPLETE**

World State checkpoints were extended so that restoration reconstructs structured cognitive state rather than only restoring a session identifier.

Restored state includes structured plan and execution context.

---

### B2.2 — Planning + Replanning Integration

**Status: IN PROGRESS / ACTIVE DEVELOPMENT**

Current B2.2 work has established integration between:

Planner
   ↓
World State
   ↓
Execution
   ↓
OVC
   ↓
Failure Detection
   ↓
Replanning
   ↓
Recovery


The planner now registers newly generated plans with World State before execution.

This allows final plan verification to inspect the actual active plan rather than operating without plan state.

A verified multi-step execution currently completes successfully through the replanning execution path.

---

## 🔬 VERIFIED EXECUTION PATHS

The architecture has been tested through the real JARVIS entry point rather than only isolated unit tests.

### Tool execution

A live `file_list` operation successfully passed through:

JARVISCore
   ↓
ExecutionBroker
   ↓
Safety Gate
   ↓
OVC
   ↓
ToolRouter
   ↓
file_list
   ↓
Observer
   ↓
Verifier


Result:

SUCCESS: True
OVC SUCCESS: True
ITERATIONS: 1
EVIDENCE: 1
DISCREPANCIES: []


### Agent execution

A live research-agent task successfully passed through:


JARVISCore
   ↓
ExecutionBroker
   ↓
Research Agent
   ↓
OVC
   ↓
Critic


Result:

SUCCESS: True
OVC SUCCESS: True
ITERATIONS: 1
CRITIC: PASS
EVIDENCE: 1
DISCREPANCIES: []


### Multi-step planning

A live multi-step plan was executed through the planning/replanning path.

Verified result:


3 steps completed
0 failed
SUCCESS: True


This confirms that generated plans are now registered in World State and can subsequently be verified at plan completion.

---

## 🔐 LOCAL-FIRST DESIGN

JARVIS is designed around local-first operation.

The project aims to minimise unnecessary external dependencies and keep personal AI functionality under the user's control.

The architecture is compatible with locally hosted language models and is intended to support private, offline-capable workflows wherever the required functionality is available locally.

External services such as web search can exist as explicit tools rather than being required for every interaction.

---

## 🚧 CURRENT DEVELOPMENT STATUS

JARVIS is **not a finished autonomous AGI system**.

It is an actively developed cognitive architecture.

Implemented components should be distinguished from future goals.

### Currently implemented

* Persistent memory
* Specialist agents
* Tool routing
* Execution Broker
* Safety gating
* OVC verification
* Structured World State
* World State checkpoints
* Planning
* Replanning/recovery
* Temporal reasoning
* Knowledge graph
* Scheduler
* Project/goal context
* Agent critique
* Incremental regression testing

### Future development

Planned capabilities may include:

* More advanced autonomous task execution
* Richer long-term memory
* Improved self-correction
* More sophisticated environmental awareness
* Image generation
* Video generation
* Expanded multimodal interaction
* More capable voice interaction
* Deeper project management
* More advanced learning and adaptation

These are **development goals**, not claims that the capabilities are already complete.

---

## 🧭 DEVELOPMENT PHILOSOPHY

JARVIS is being built incrementally.

The project prioritises:

1. Understanding the existing architecture before modifying it.
2. Making small architectural changes.
3. Keeping responsibilities separated between components.
4. Verifying behaviour through real execution.
5. Maintaining regression tests.
6. Recording meaningful changes in Git.
7. Avoiding false claims about capabilities.
8. Preserving local-first and privacy-focused design goals.

The objective is not to make JARVIS appear intelligent.

The objective is to make its intelligence **observable, testable, recoverable, and progressively more capable**.

---

## 📌 PROJECT STATUS

**JARVIS is an active research and development project.**

The architecture is functional and increasingly integrated, but substantial development remains before the system can be considered a mature general-purpose personal AI.

Current verified regression baseline:


42 passed
24 warnings

The warnings currently originate from third-party ChromaDB/Pydantic compatibility behaviour and are not failing JARVIS tests.

Development continues incrementally from the existing architecture.

