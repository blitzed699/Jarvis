import sqlite3
from datetime import datetime
from typing import Dict, Any, List, Optional


class GoalTracker:
    """Track user goals, milestones, and progress."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._init_table()

    def _init_table(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS goals (
                id TEXT PRIMARY KEY,
                title TEXT,
                description TEXT,
                category TEXT DEFAULT 'personal',
                status TEXT DEFAULT 'active',
                progress INTEGER DEFAULT 0,
                target_date TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS goal_milestones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal_id TEXT,
                milestone TEXT,
                completed INTEGER DEFAULT 0,
                timestamp TEXT,
                FOREIGN KEY (goal_id) REFERENCES goals(id)
            )
        """)
        self.conn.commit()

    def add(self, title: str, description: str = "", category: str = "personal", target_date: str = "") -> str:
        import hashlib
        gid = f"goal_{hashlib.md5(f'{title}{datetime.now()}'.encode()).hexdigest()[:8]}"
        now = datetime.now().isoformat()
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO goals (id, title, description, category, status, progress, target_date, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (gid, title, description, category, "active", 0, target_date, now, now)
        )
        self.conn.commit()
        return gid

    def list_active(self) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM goals WHERE status = 'active' ORDER BY updated_at DESC")
        return [dict(row) for row in cursor.fetchall()]

    def update_progress(self, goal_id: str, progress: int):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE goals SET progress = ?, updated_at = ? WHERE id = ?",
            (min(100, max(0, progress)), datetime.now().isoformat(), goal_id)
        )
        self.conn.commit()

    def complete(self, goal_id: str):
        self.update_progress(goal_id, 100)
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE goals SET status = 'completed', updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), goal_id)
        )
        self.conn.commit()

    def add_milestone(self, goal_id: str, milestone: str):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO goal_milestones (goal_id, milestone, timestamp) VALUES (?, ?, ?)",
            (goal_id, milestone, datetime.now().isoformat())
        )
        self.conn.commit()

    def get_milestones(self, goal_id: str) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM goal_milestones WHERE goal_id = ? ORDER BY timestamp DESC", (goal_id,))
        return [dict(row) for row in cursor.fetchall()]
