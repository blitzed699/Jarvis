# JARVIS v0.1

Local-first AI partner with memory and tool use.

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
 
Type  exit  to quit
Architecture
 
 core/jarvis.py  — Overseer (router + persona)
 
 core/memory.py  — SQLite + ChromaDB memory
 
 core/llm.py  — Ollama client
 
 tools/  — File and shell tools
 
 agents/  — Empty (Phase 3)
