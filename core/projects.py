import sqlite3
from datetime import datetime
from typing import Dict, Any, List, Optional


class ProjectTracker:
    """Track active projects, statuses, and associated context."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._init_table()

    def _init_table(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT,
                description TEXT,
                status TEXT DEFAULT 'active',
                created_at TEXT,
                updated_at TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS project_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT,
                session_id TEXT,
                note TEXT,
                timestamp TEXT,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        """)
        self.conn.commit()

    def create(self, name: str, description: str = "") -> str:
        import hashlib
        pid = f"proj_{hashlib.md5(f'{name}{datetime.now()}'.encode()).hexdigest()[:8]}"
        cursor = self.conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute(
            "INSERT INTO projects (id, name, description, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (pid, name, description, "active", now, now)
        )
        self.conn.commit()
        return pid

    def list_active(self) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM projects WHERE status = 'active' ORDER BY updated_at DESC")
        return [dict(row) for row in cursor.fetchall()]

    def get(self, project_id: str) -> Optional[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def update_status(self, project_id: str, status: str):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE projects SET status = ?, updated_at = ? WHERE id = ?",
            (status, datetime.now().isoformat(), project_id)
        )
        self.conn.commit()

    def log(self, project_id: str, session_id: str, note: str):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO project_logs (project_id, session_id, note, timestamp) VALUES (?, ?, ?, ?)",
            (project_id, session_id, note, datetime.now().isoformat())
        )
        self.conn.commit()

    def get_logs(self, project_id: str) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM project_logs WHERE project_id = ? ORDER BY timestamp DESC", (project_id,))
        return [dict(row) for row in cursor.fetchall()]
