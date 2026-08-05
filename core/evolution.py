import sqlite3
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional


class EvolutionTracker:
    """Track JARVIS performance, user feedback, and tool/agent success rates."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._init_tables()

    def _init_tables(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS performance_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT,
                action_name TEXT,
                success INTEGER,
                user_feedback INTEGER,
                latency_ms INTEGER,
                error_msg TEXT,
                context TEXT,
                timestamp TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                rating INTEGER,
                comment TEXT,
                timestamp TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategy_memory (
                id TEXT PRIMARY KEY,
                strategy TEXT,
                context TEXT,
                success_rate REAL,
                uses INTEGER,
                last_used TEXT
            )
        """)
        self.conn.commit()

    def log_action(self, action_type: str, action_name: str, success: bool,
                   latency_ms: int = 0, error_msg: str = "", context: str = ""):
        """Log every tool use and agent delegation."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO performance_log (action_type, action_name, success, latency_ms, error_msg, context, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (action_type, action_name, 1 if success else 0, latency_ms, error_msg, context, datetime.now().isoformat()))
        self.conn.commit()

    def log_feedback(self, session_id: str, rating: int, comment: str = ""):
        """User rates JARVIS performance (1-5)."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO user_feedback (session_id, rating, comment, timestamp)
            VALUES (?, ?, ?, ?)
        """, (session_id, rating, comment, datetime.now().isoformat()))
        self.conn.commit()

    def get_success_rate(self, action_type: str, action_name: str, days: int = 7) -> float:
        """Calculate success rate for a tool or agent."""
        cursor = self.conn.cursor()
        since = (datetime.now() - timedelta(days=days)).isoformat()
        cursor.execute("""
            SELECT COUNT(*) as total, SUM(success) as successes
            FROM performance_log
            WHERE action_type = ? AND action_name = ? AND timestamp > ?
        """, (action_type, action_name, since))
        row = cursor.fetchone()
        total, successes = row['total'], row['successes'] or 0
        return (successes / total * 100) if total > 0 else 0.0

    def get_top_failures(self, days: int = 7, limit: int = 5) -> List[Dict[str, Any]]:
        """Find what's breaking most often."""
        cursor = self.conn.cursor()
        since = (datetime.now() - timedelta(days=days)).isoformat()
        cursor.execute("""
            SELECT action_name, COUNT(*) as failures
            FROM performance_log
            WHERE success = 0 AND timestamp > ?
            GROUP BY action_name
            ORDER BY failures DESC
            LIMIT ?
        """, (since, limit))
        return [dict(row) for row in cursor.fetchall()]

    def record_strategy(self, strategy: str, context: str, worked: bool):
        """Learn which approaches work for which tasks."""
        strategy_id = f"strat_{hash(strategy) % 10000000}"
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM strategy_memory WHERE id = ?", (strategy_id,))
        existing = cursor.fetchone()

        if existing:
            new_uses = existing['uses'] + 1
            new_rate = ((existing['success_rate'] * existing['uses']) + (1 if worked else 0)) / new_uses
            cursor.execute("""
                UPDATE strategy_memory SET success_rate = ?, uses = ?, last_used = ?
                WHERE id = ?
            """, (new_rate, new_uses, datetime.now().isoformat(), strategy_id))
        else:
            cursor.execute("""
                INSERT INTO strategy_memory (id, strategy, context, success_rate, uses, last_used)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (strategy_id, strategy, context, 1.0 if worked else 0.0, 1, datetime.now().isoformat()))
        self.conn.commit()

    def get_insights(self) -> str:
        """Generate a performance summary for JARVIS to include in prompts."""
        cursor = self.conn.cursor()
        since = (datetime.now() - timedelta(days=7)).isoformat()

        # Overall success rate
        cursor.execute("SELECT COUNT(*) as total, SUM(success) as successes FROM performance_log WHERE timestamp > ?", (since,))
        row = cursor.fetchone()
        total, successes = row['total'], row['successes'] or 0
        overall = (successes / total * 100) if total > 0 else 0

        # Best performing agent
        cursor.execute("""
            SELECT action_name, AVG(success) as rate
            FROM performance_log
            WHERE action_type = 'agent' AND timestamp > ?
            GROUP BY action_name
            ORDER BY rate DESC
            LIMIT 1
        """, (since,))
        best_agent = cursor.fetchone()

        # Best performing tool
        cursor.execute("""
            SELECT action_name, AVG(success) as rate
            FROM performance_log
            WHERE action_type = 'tool' AND timestamp > ?
            GROUP BY action_name
            ORDER BY rate DESC
            LIMIT 1
        """, (since,))
        best_tool = cursor.fetchone()

        lines = [f"## JARVIS Performance (Last 7 Days)"]
        lines.append(f"- Overall success rate: {overall:.1f}%")
        if best_agent:
            lines.append(f"- Best agent: {best_agent['action_name']} ({best_agent['rate']*100:.0f}%)")
        if best_tool:
            lines.append(f"- Best tool: {best_tool['action_name']} ({best_tool['rate']*100:.0f}%)")

        # Top failures
        failures = self.get_top_failures(days=7, limit=3)
        if failures:
            lines.append("- Recent failures:")
            for f in failures:
                lines.append(f"  * {f['action_name']}: {f['failures']} times")

        return "\n".join(lines)
