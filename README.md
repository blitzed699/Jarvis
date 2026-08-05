# JARVIS v0.3
Local-First AI Assistant

A modular, local-first AI assistant with persistent memory, intelligent tool use, specialist agents, safety controls, and automated testing.

══════════════════════════════════════════════
SETUP
══════════════════════════════════════════════

Clone the repository:

git clone https://github.com/blitzed699/Jarvis
cd jarvis

Install Ollama:

curl -fsSL https://ollama.com/install.sh | sh

Download the default language model:

ollama pull llama3.1

Install Python requirements:

pip install -r requirements.txt

Start JARVIS:

python main.py

══════════════════════════════════════════════
USAGE
══════════════════════════════════════════════

• Chat naturally with JARVIS.
• Type "tools" to display all installed tools.
• Type "agents" to display all available specialist agents.
• Type "exit" to close JARVIS.

══════════════════════════════════════════════
TOOLS (7)
══════════════════════════════════════════════

1. file_read
   Auto Approved: Yes
   Reads the contents of files.

2. file_list
   Auto Approved: Yes
   Lists files and folders inside directories.

3. open_app
   Auto Approved: Yes
   Launches installed desktop applications.

4. shell
   Auto Approved: No
   Executes terminal or shell commands.

5. write_file
   Auto Approved: No
   Creates or modifies files containing text or source code.

6. run_python
   Auto Approved: No
   Executes Python scripts.

7. organize_files
   Auto Approved: No
   Automatically sorts and moves files according to configurable rules.

══════════════════════════════════════════════
SPECIALIST AGENTS (4)
══════════════════════════════════════════════

coding_agent
• Plans software architecture
• Writes production-ready code
• Debugs applications
• Runs and interprets tests
• Refactors existing code

research_agent
• Searches for technical information
• Summarizes documentation
• Compares technologies
• Produces research reports

business_agent
• Performs market analysis
• Identifies business opportunities
• Suggests monetization strategies
• Evaluates niches and competition

creative_agent
• Generates product ideas
• Creates branding concepts
• Writes marketing material
• Brainstorms names and slogans

══════════════════════════════════════════════
TEST SUITE
══════════════════════════════════════════════

Run individual tests:

python tests/test_memory.py
python tests/test_tools.py
python tests/test_agents.py

══════════════════════════════════════════════
SYSTEM ARCHITECTURE
══════════════════════════════════════════════

core/jarvis.py
• Main overseer
• Conversation management
• Persona
• Safety checks
• Tool routing
• Agent delegation

core/memory.py
• Persistent SQLite memory
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
• Prevents destructive actions without confirmation

core/agent_registry.py
• Discovers available agents
• Routes complex tasks to specialists

tools/
• File management
• Shell execution
• Computer control
• File organization
• Future extensions

agents/
• Coding Agent
• Research Agent
• Business Agent
• Creative Agent

tests/
• Memory testing
• Tool testing
• Agent testing

══════════════════════════════════════════════
FEATURES
══════════════════════════════════════════════

✔ Runs completely locally using Ollama
✔ Persistent long-term memory
✔ Semantic memory search with ChromaDB
✔ Modular architecture
✔ Tool execution system
✔ Specialist AI agents
✔ Safety approval for dangerous actions
✔ Extensible plugin structure
✔ Automated testing
✔ Designed to evolve into a full personal AI assistant
