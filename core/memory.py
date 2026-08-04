import sqlite3
import chromadb
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
import hashlib
import os


@dataclass
class Message:
    role: str
    content: str
    timestamp: str
    session_id: str
    tool_call: Optional[str] = None
    tool_result: Optional[str] = None


@dataclass
class Fact:
    fact_text: str
    category: str
    source_session_id: str
    timestamp: str
    id: Optional[str] = None


class JARVISMemory:
    def __init__(self, db_path: str = "memory/jarvis_memory.db", chroma_path: str = "memory/chroma_db"):
        self.db_path = db_path
        self.chroma_path = chroma_path
        
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        os.makedirs(chroma_path, exist_ok=True)
        
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_sqlite()
        
        self.chroma_client = chromadb.PersistentClient(path=chroma_path)
        self.conversation_collection = self.chroma_client.get_or_create_collection("conversations")
        self.facts_collection = self.chroma_client.get_or_create_collection("facts")
        
        self.current_session_id = self._generate_session_id()
        self._start_session()
    
    def _generate_session_id(self) -> str:
        return f"sess_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hashlib.md5(os.urandom(8)).hexdigest()[:6]}"
    
    def _init_sqlite(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                start_time TEXT,
                end_time TEXT,
                summary TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                role TEXT,
                content TEXT,
                tool_call TEXT,
                tool_result TEXT,
                timestamp TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id TEXT PRIMARY KEY,
                fact_text TEXT,
                category TEXT,
                source_session_id TEXT,
                timestamp TEXT
            )
        """)
        self.conn.commit()
    
    def _start_session(self):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO sessions (id, start_time) VALUES (?, ?)",
            (self.current_session_id, datetime.now().isoformat())
        )
        self.conn.commit()
    
    def log_message(self, role: str, content: str, tool_call: Optional[str] = None, 
                    tool_result: Optional[str] = None) -> Message:
        msg = Message(
            role=role,
            content=content,
            timestamp=datetime.now().isoformat(),
            session_id=self.current_session_id,
            tool_call=tool_call,
            tool_result=tool_result
        )
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO conversations (session_id, role, content, tool_call, tool_result, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (msg.session_id, msg.role, msg.content, msg.tool_call, msg.tool_result, msg.timestamp))
        self.conn.commit()
        
        doc_id = f"conv_{cursor.lastrowid}"
        self.conversation_collection.add(
            documents=[content],
            metadatas=[{
                "role": role,
                "session_id": msg.session_id,
                "timestamp": msg.timestamp,
                "tool_call": tool_call or "",
                "tool_result": tool_result or ""
            }],
            ids=[doc_id]
        )
        return msg
    
    def get_recent_context(self, n: int = 10) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT role, content, tool_call, tool_result, timestamp
            FROM conversations
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (self.current_session_id, n))
        rows = cursor.fetchall()
        return [dict(row) for row in reversed(rows)]
    
    def get_relevant_memories(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        conv_results = self.conversation_collection.query(
            query_texts=[query],
            n_results=n_results
        )
        memories = []
        if conv_results['documents'] and conv_results['documents'][0]:
            for i, doc in enumerate(conv_results['documents'][0]):
                memories.append({
                    "type": "conversation",
                    "content": doc,
                    "metadata": conv_results['metadatas'][0][i] if conv_results['metadatas'] else {},
                    "distance": conv_results['distances'][0][i] if conv_results['distances'] else 0
                })
        fact_results = self.facts_collection.query(
            query_texts=[query],
            n_results=min(n_results, 3)
        )
        if fact_results['documents'] and fact_results['documents'][0]:
            for i, doc in enumerate(fact_results['documents'][0]):
                memories.append({
                    "type": "fact",
                    "content": doc,
                    "metadata": fact_results['metadatas'][0][i] if fact_results['metadatas'] else {},
                    "distance": fact_results['distances'][0][i] if fact_results['distances'] else 0
                })
        memories.sort(key=lambda x: x['distance'])
        return memories[:n_results + 2]
    
    def store_fact(self, fact_text: str, category: str = "other") -> Fact:
        fact_id = f"fact_{hashlib.md5(fact_text.encode()).hexdigest()[:12]}"
        fact = Fact(
            id=fact_id,
            fact_text=fact_text,
            category=category,
            source_session_id=self.current_session_id,
            timestamp=datetime.now().isoformat()
        )
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO facts (id, fact_text, category, source_session_id, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (fact.id, fact.fact_text, fact.category, fact.source_session_id, fact.timestamp))
        self.conn.commit()
        self.facts_collection.add(
            documents=[fact_text],
            metadatas=[{
                "category": category,
                "source_session": fact.source_session_id,
                "timestamp": fact.timestamp
            }],
            ids=[fact_id]
        )
        return fact
    
    def get_working_memory(self, current_query: str = "", recent_n: int = 10, 
                           relevant_n: int = 5) -> Dict[str, Any]:
        recent = self.get_recent_context(n=recent_n)
        relevant = self.get_relevant_memories(query=current_query, n_results=relevant_n) if current_query else []
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT fact_text, category, timestamp FROM facts
            ORDER BY timestamp DESC
            LIMIT 5
        """)
        recent_facts = [dict(row) for row in cursor.fetchall()]
        return {
            "recent_conversation": recent,
            "relevant_memories": relevant,
            "recent_facts": recent_facts,
            "session_id": self.current_session_id
        }
    
    def format_working_memory_for_prompt(self, working_memory: Dict[str, Any]) -> str:
        parts = []
        if working_memory["recent_facts"]:
            parts.append("## Known Facts About User")
            for f in working_memory["recent_facts"]:
                parts.append(f"- [{f['category']}] {f['fact_text']}")
            parts.append("")
        if working_memory["relevant_memories"]:
            parts.append("## Relevant Past Context")
            for m in working_memory["relevant_memories"]:
                if m["type"] == "fact":
                    parts.append(f"- [Memory] {m['content']}")
                else:
                    meta = m.get("metadata", {})
                    role = meta.get("role", "unknown")
                    parts.append(f"- [Past {role}] {m['content']}")
            parts.append("")
        if working_memory["recent_conversation"]:
            parts.append("## Recent Conversation")
            for msg in working_memory["recent_conversation"]:
                role_label = "User" if msg["role"] == "user" else "JARVIS"
                if msg["tool_call"]:
                    parts.append(f"- [{role_label}] (used tool: {msg['tool_call']}) {msg['content']}")
                else:
                    parts.append(f"- [{role_label}] {msg['content']}")
        return "\n".join(parts)
    
    def end_session(self, summary: str = ""):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE sessions SET end_time = ?, summary = ? WHERE id = ?",
            (datetime.now().isoformat(), summary, self.current_session_id)
        )
        self.conn.commit()
    
    def close(self):
        self.conn.close()


if __name__ == "__main__":
    mem = JARVISMemory()
    mem.log_message("user", "My name is Alex. I prefer dark mode.")
    mem.log_message("jarvis", "Noted, Alex. Dark mode preference saved.")
    mem.store_fact("User's name is Alex", category="person")
    mem.store_fact("User prefers dark mode", category="preference")
    mem.log_message("user", "What do you know about me?")
    wm = mem.get_working_memory(current_query="What do you know about me?")
    print(mem.format_working_memory_for_prompt(wm))
    mem.close()
