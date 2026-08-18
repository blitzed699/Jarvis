# JARVIS v0.3
Local-First AI Assistant

A modular, local-first AI assistant with persistent memory, intelligent tool use, specialist agents, project management, goal tracking, voice support, safety controls, and automated testing.

══════════════════════════════════════════════
SETUP
══════════════════════════════════════════════

Clone the repository:

```bash
git clone github.com/blitzed699/Jarvis
cd jarvis
```

Install Ollama:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Download the default language model:

```bash
ollama pull llama3.1
```

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Launch JARVIS:

```bash
python main.py
```

══════════════════════════════════════════════
COMMANDS
══════════════════════════════════════════════

| Command | Action |
|---------|--------|
| `exit` | Quit JARVIS |
| `tools` | List all available tools |
| `agents` | List all specialist agents |
| `goals` | Display active goals |
| `projects` | Display active projects |
| `goal <title>` | Create a new goal |
| `project <name>` | Create a new project |
| `voice on` | Enable voice output |
| `voice off` | Disable voice output |

══════════════════════════════════════════════
TOOLS (8)
══════════════════════════════════════════════

| Tool | Auto-Approve | Description |
|------|--------------|-------------|
| file_read | Yes | Read file contents |
| file_list | Yes | List directory contents |
| open_app | Yes | Launch desktop applications |
| web_search | Yes | Search the web |
| shell | No | Execute shell commands |
| write_file | No | Create or edit files |
| run_python | No | Execute Python scripts |
| organize_files | No | Automatically organize files using rules |

══════════════════════════════════════════════
SPECIALIST AGENTS (4)
══════════════════════════════════════════════

### coding_agent
• Plans software architecture
• Writes production-ready code
• Debugs applications
• Executes tests
• Refactors existing code

### research_agent
• Searches for information
• Summarizes documentation
• Compares technologies
• Produces research reports

### business_agent
• Performs market analysis
• Identifies profitable niches
• Suggests monetization strategies
• Evaluates competition

### creative_agent
• Generates product ideas
• Creates branding concepts
• Writes marketing copy
• Brainstorms names and slogans

══════════════════════════════════════════════
GOALS
══════════════════════════════════════════════

JARVIS can:

• Store long-term goals
• Track progress
• Prioritize objectives
• Display all active goals
• Link goals to projects

Examples:

goal Build a smart home assistant

goal Learn Rust programming

══════════════════════════════════════════════
PROJECTS
══════════════════════════════════════════════

Projects organize conversations, files, goals, and memory into dedicated workspaces.

Each project can contain:

• Multiple goals
• Notes
• Generated code
• Research
• Task history
• Associated memories

Example:

project Jarvis AI

══════════════════════════════════════════════
VOICE
══════════════════════════════════════════════

Voice can be enabled or disabled at any time.

Commands:

voice on
voice off

Voice features:

✔ Natural speech output
✔ Hands-free interaction
✔ Future wake-word support

══════════════════════════════════════════════
CONFIGURATION
══════════════════════════════════════════════

Edit `config.yaml` to customize JARVIS.

Available options:

model
• Ollama model to load

voice_enabled
• true / false

temperature
• LLM creativity level (0.0 - 1.0)

auto_approve_readonly
• Skip approval prompts for safe read-only tools

══════════════════════════════════════════════
TESTING
══════════════════════════════════════════════

Run the automated test suite:

```bash
python tests/test_memory.py
python tests/test_tools.py
python tests/test_agents.py
```

══════════════════════════════════════════════
SYSTEM ARCHITECTURE
══════════════════════════════════════════════

core/jarvis.py
• Main overseer
• Conversation manager
• Persona
• Safety checks
• Tool routing
• Agent delegation

core/memory.py
• SQLite persistent memory
• ChromaDB semantic memory
• Long-term memory retrieval

core/llm.py
• Ollama interface
• Local model communication

core/router.py
• Intent recognition
• Tool selection
• JSON parsing

core/extractor.py
• Automatic fact extraction
• Memory generation

core/safety.py
• Approval system
• Protects against destructive actions

core/agent_registry.py
• Agent discovery
• Intelligent task routing

tools/
• File management
• Shell execution
• Web search
• Computer control
• File organization

agents/
• Coding Agent
• Research Agent
• Business Agent
• Creative Agent

tests/
• Memory tests
• Tool tests
• Agent tests

══════════════════════════════════════════════
FEATURES
══════════════════════════════════════════════

✔ Fully local AI powered by Ollama
✔ Persistent long-term memory
✔ Semantic memory using ChromaDB
✔ Intelligent tool routing
✔ Eight integrated tools
✔ Specialist AI agents
✔ Goal management
✔ Project management
✔ Voice support
✔ Safety approval system
✔ Modular architecture
✔ Automated testing
✔ Extensible plugin-ready design
✔ Built as the foundation for a true personal AI operating system
