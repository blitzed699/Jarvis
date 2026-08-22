"""
core/memory_threadsafe.py

Drop-in thread-safe wrapper for JARVISMemory.

PROBLEM in v0.3:
  JARVISMemory uses a single sqlite3 connection with check_same_thread=False.
  The dashboard server runs in a separate thread. Concurrent writes corrupt
  the database or raise "SQLite objects created in a thread can only be used
  in that same thread".

SOLUTION:
  ThreadSafeMemory wraps JARVISMemory with:
  1. A threading.Lock() around ALL write operations
  2. Per-thread SQLite connections for reads
  3. A write queue for the dashboard thread

USAGE (replace in core/jarvis.py):
    from core.memory_threadsafe import ThreadSafeMemory
    self.memory = ThreadSafeMemory(self.config.get("memory_db"), self.config.get("chroma_path"))
    # ... then use self.memory exactly like JARVISMemory
"""

import os
import sqlite3
import threading
import queue
import time
from typing import Optional, List, Dict, Any

# Import the base memory class
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.memory import JARVISMemory


class ThreadSafeMemory:
    """
    Thread-safe drop-in replacement for JARVISMemory.
    Preserves the entire public API while fixing concurrency.
    """

    def __init__(self, db_path: str = "memory/jarvis_memory.db",
                 chroma_path: str = "memory/chroma_db"):
        self.db_path = db_path
        self.chroma_path = chroma_path

        # The "main" memory instance lives in the main thread
        self._main_memory = JARVISMemory(db_path=db_path, chroma_path=chroma_path)
        self._write_lock = threading.RLock()

        # Thread-local connections for reads
        self._local = threading.local()

        # Write queue for background thread operations
        self._write_queue = queue.Queue()
        self._write_thread = threading.Thread(target=self._write_worker, daemon=True)
        self._write_thread.start()

        # Expose public attributes that external code accesses directly
        self.conn = self._main_memory.conn
        self.current_session_id = self._main_memory.current_session_id
        self.conversation_collection = self._main_memory.conversation_collection
        self.facts_collection = self._main_memory.facts_collection

    def _get_local_conn(self):
        """Get a thread-local SQLite connection."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0
            )
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _write_worker(self):
        """Background thread that processes queued writes."""
        while True:
            try:
                task = self._write_queue.get(timeout=1.0)
                if task is None:
                    break
                method_name, args, kwargs = task
                with self._write_lock:
                    method = getattr(self._main_memory, method_name)
                    method(*args, **kwargs)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[ThreadSafeMemory] Write worker error: {e}")

    # ------------------------------------------------------------------
    # Public API — all methods from JARVISMemory, wrapped for safety
    # ------------------------------------------------------------------

    def log_message(self, role: str, content: str, tool_call: Optional[str] = None,
                    tool_result: Optional[str] = None):
        """Thread-safe message logging."""
        with self._write_lock:
            return self._main_memory.log_message(role, content, tool_call, tool_result)

    def get_recent_context(self, n: int = 10) -> List[Dict[str, Any]]:
        """Thread-safe recent context retrieval."""
        with self._write_lock:
            return self._main_memory.get_recent_context(n)

    def get_relevant_memories(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Thread-safe semantic memory retrieval."""
        with self._write_lock:
            return self._main_memory.get_relevant_memories(query, n_results)

    def store_fact(self, fact_text: str, category: str = "other"):
        """Thread-safe fact storage."""
        with self._write_lock:
            return self._main_memory.store_fact(fact_text, category)

    def get_working_memory(self, current_query: str = "", recent_n: int = 10,
                           relevant_n: int = 5) -> Dict[str, Any]:
        """Thread-safe working memory assembly."""
        with self._write_lock:
            return self._main_memory.get_working_memory(current_query, recent_n, relevant_n)

    def format_working_memory_for_prompt(self, working_memory: Dict[str, Any]) -> str:
        """Formatting is read-only, no lock needed."""
        return self._main_memory.format_working_memory_for_prompt(working_memory)

    def end_session(self, summary: str = ""):
        """Thread-safe session end."""
        with self._write_lock:
            return self._main_memory.end_session(summary)

    def close(self):
        """Thread-safe cleanup."""
        self._write_queue.put(None)
        self._write_thread.join(timeout=2.0)
        with self._write_lock:
            return self._main_memory.close()

    # ------------------------------------------------------------------
    # Passthrough for any other attributes
    # ------------------------------------------------------------------
    def __getattr__(self, name):
        """Pass through any other attribute access to the main memory."""
        return getattr(self._main_memory, name)
