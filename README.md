# JARVIS v0.2

Local-first AI partner with memory, tools, safety, and specialist agents.

## Setup

```bash
# 1. Clone
git clone <your-repo-url>
cd jarvis

# 2. Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 3. Pull a model
ollama pull llama3.1

# 4. Install Python deps
pip install -r requirements.txt

# 5. Run
python main.py

Usage
 
Type messages to chat with JARVIS
 
Type  tools  to see available tools
 
Type  agents  to see available agents
 
Type  exit  to quit
Tools
Tool	Auto-Approve	Description	
`file_read`	Yes	Read file contents	
`file_list`	Yes	List directory contents	
`open_app`	Yes	Open applications	
`shell`	No	Run shell commands	
`write_file`	No	Write text/code to files	
`run_python`	No	Execute Python scripts	
`organize_files`	No	Move files by pattern rules	
Agents
Agent	Description	
`coding_agent`	Plans, writes, tests, and debugs code	
`research_agent`	Gathers and summarizes information	
Architecture
 
 core/jarvis.py  — Overseer (router + persona + safety + agent delegation)
 
 core/memory.py  — SQLite + ChromaDB memory
 
 core/llm.py  — Ollama client
 
 core/router.py  — Tool selection & JSON parsing
 
 core/extractor.py  — Auto fact extraction
 
 core/safety.py  — Approval gate for destructive actions
 
 core/agent_registry.py  — Agent discovery and routing
 
 tools/  — File, shell, computer control, organization tools
 
 agents/  — Specialist coding and research agents
