"""
core/scheduler.py

Background Scheduler — Tier 2 Intelligence Amplification.
JARVIS can now work while you sleep.

Features:
  - Cron-like recurring jobs
  - One-shot delayed jobs
  - Persistent SQLite store (survives restarts)
  - Thread-safe execution
  - OVC-wrapped task execution for safety
  - Job types: agent, tool, plan, shell, python, reminder

Commands:
  schedule <name> every <interval> <task>
  schedule <name> at <time> <task>
  schedule <name> in <duration> <task>
  jobs
  cancel <job_id>
"""

import json
import sqlite3
import threading
import time
import uuid
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum


class JobTrigger(Enum):
    INTERVAL = "interval"
    CRON = "cron"
    DATE = "date"
    DELAY = "delay"


class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(Enum):
    AGENT = "agent"
    TOOL = "tool"
    PLAN = "plan"
    SHELL = "shell"
    PYTHON = "python"
    REMINDER = "reminder"
    FUNCTION = "function"


@dataclass
class ScheduledJob:
    id: str
    name: str
    trigger: str
    trigger_args: Dict[str, Any]
    job_type: str
    job_args: Dict[str, Any]
    status: str
    created_at: str
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    run_count: int = 0
    max_runs: Optional[int] = None
    error_log: List[str] = None

    def __post_init__(self):
        if self.error_log is None:
            self.error_log = []


class BackgroundScheduler:
    """
    Persistent background job scheduler for JARVIS.
    Runs in a daemon thread, checking for due jobs every 10 seconds.
    """

    CHECK_INTERVAL = 10  # seconds

    def __init__(self, jarvis_core=None, db_path: str = "memory/scheduler.db"):
        self.jarvis = jarvis_core
        self.db_path = db_path
        self._lock = threading.RLock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    trigger TEXT NOT NULL,
                    trigger_args TEXT NOT NULL,
                    job_type TEXT NOT NULL,
                    job_args TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TEXT,
                    last_run TEXT,
                    next_run TEXT,
                    run_count INTEGER DEFAULT 0,
                    max_runs INTEGER,
                    error_log TEXT DEFAULT '[]'
                )
            """)
            conn.commit()

    def _db_conn(self):
        return sqlite3.connect(self.db_path)

    def _row_to_job(self, row) -> ScheduledJob:
        return ScheduledJob(
            id=row[0],
            name=row[1],
            trigger=row[2],
            trigger_args=json.loads(row[3]),
            job_type=row[4],
            job_args=json.loads(row[5]),
            status=row[6],
            created_at=row[7],
            last_run=row[8],
            next_run=row[9],
            run_count=row[10] or 0,
            max_runs=row[11],
            error_log=json.loads(row[12]) if row[12] else []
        )

    def add_job(self, name: str, trigger: str, trigger_args: Dict[str, Any],
                job_type: str, job_args: Dict[str, Any],
                max_runs: Optional[int] = None) -> str:
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        now = datetime.now().isoformat()
        next_run = self._compute_next_run(trigger, trigger_args, now)

        with self._lock:
            with self._db_conn() as conn:
                conn.execute("""
                    INSERT INTO jobs (id, name, trigger, trigger_args, job_type,
                                      job_args, status, created_at, next_run, max_runs)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    job_id, name, trigger, json.dumps(trigger_args),
                    job_type, json.dumps(job_args), "pending",
                    now, next_run, max_runs
                ))
                conn.commit()

        return job_id

    def _compute_next_run(self, trigger: str, trigger_args: Dict[str, Any],
                          from_time: Optional[str] = None) -> Optional[str]:
        base = datetime.fromisoformat(from_time) if from_time else datetime.now()

        if trigger == "delay":
            seconds = trigger_args.get("seconds", 0)
            seconds += trigger_args.get("minutes", 0) * 60
            seconds += trigger_args.get("hours", 0) * 3600
            seconds += trigger_args.get("days", 0) * 86400
            return (base + timedelta(seconds=seconds)).isoformat()

        if trigger == "date":
            dt_str = trigger_args.get("datetime")
            if dt_str:
                return datetime.fromisoformat(dt_str).isoformat()
            return None

        if trigger == "interval":
            seconds = trigger_args.get("seconds", 0)
            seconds += trigger_args.get("minutes", 0) * 60
            seconds += trigger_args.get("hours", 0) * 3600
            seconds += trigger_args.get("days", 0) * 86400
            if seconds == 0:
                seconds = 300
            return (base + timedelta(seconds=seconds)).isoformat()

        if trigger == "cron":
            return self._next_cron(trigger_args, base).isoformat()

        return None

    def _next_cron(self, args: Dict[str, Any], base: datetime) -> datetime:
        dow_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
        target_dow = args.get("day_of_week")
        target_hour = args.get("hour", 0)
        target_minute = args.get("minute", 0)

        current = base.replace(second=0, microsecond=0)
        if current.minute >= target_minute:
            current += timedelta(minutes=1)

        for _ in range(366 * 24 * 60):
            if target_dow is not None:
                dow = current.weekday()
                expected = dow_map.get(target_dow.lower(), dow)
                if dow != expected:
                    current += timedelta(days=1)
                    current = current.replace(hour=0, minute=0)
                    continue

            if current.hour == target_hour and current.minute == target_minute:
                if current > base:
                    return current

            current += timedelta(minutes=1)

        return base + timedelta(days=1)

    def cancel_job(self, job_id: str) -> bool:
        with self._lock:
            with self._db_conn() as conn:
                cur = conn.execute("UPDATE jobs SET status = ? WHERE id = ?",
                                   ("cancelled", job_id))
                conn.commit()
                return cur.rowcount > 0

    def list_jobs(self, status: Optional[str] = None) -> List[ScheduledJob]:
        with self._lock:
            with self._db_conn() as conn:
                if status:
                    rows = conn.execute(
                        "SELECT * FROM jobs WHERE status = ? ORDER BY next_run",
                        (status,)
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM jobs ORDER BY next_run"
                    ).fetchall()
                return [self._row_to_job(r) for r in rows]

    def get_job(self, job_id: str) -> Optional[ScheduledJob]:
        with self._lock:
            with self._db_conn() as conn:
                row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
                return self._row_to_job(row) if row else None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        print(f"[Scheduler] Started. Checking every {self.CHECK_INTERVAL}s.")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _run_loop(self):
        while self._running:
            try:
                self._check_and_run()
            except Exception as e:
                print(f"[Scheduler] Loop error: {e}")
            time.sleep(self.CHECK_INTERVAL)

    def _check_and_run(self):
        now = datetime.now().isoformat()
        with self._lock:
            with self._db_conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM jobs WHERE status = 'pending' AND next_run <= ?",
                    (now,)
                ).fetchall()

        for row in rows:
            job = self._row_to_job(row)
            if job.status != "pending":
                continue

            with self._lock:
                with self._db_conn() as conn:
                    conn.execute(
                        "UPDATE jobs SET status = ?, last_run = ? WHERE id = ?",
                        ("running", now, job.id)
                    )
                    conn.commit()

            t = threading.Thread(
                target=self._execute_job,
                args=(job,),
                daemon=True
            )
            t.start()

    def _execute_job(self, job: ScheduledJob):
        print(f"[Scheduler] Executing job: {job.name} ({job.job_type})")
        result = {"success": False, "result": ""}

        try:
            if not self.jarvis:
                result = {"success": False, "result": "JARVIS core not available"}
            else:
                result = self._dispatch_job(job)

            new_count = job.run_count + 1
            new_status = "completed" if result.get("success") else "failed"

            next_run = None
            if job.trigger in ("interval", "cron"):
                if job.max_runs is None or new_count < job.max_runs:
                    next_run = self._compute_next_run(job.trigger, job.trigger_args)
                    new_status = "pending"

            error_log = job.error_log
            if not result.get("success"):
                error_log.append(f"{datetime.now().isoformat()}: {result.get('result', 'Unknown error')}")
                error_log = error_log[-10:]

            with self._lock:
                with self._db_conn() as conn:
                    conn.execute("""
                        UPDATE jobs SET status = ?, run_count = ?, next_run = ?, error_log = ?
                        WHERE id = ?
                    """, (new_status, new_count, next_run, json.dumps(error_log), job.id))
                    conn.commit()

            print(f"[Scheduler] Job {job.name}: {new_status}")

        except Exception as e:
            error_log = job.error_log + [f"{datetime.now().isoformat()}: {str(e)}"]
            with self._lock:
                with self._db_conn() as conn:
                    conn.execute("""
                        UPDATE jobs SET status = ?, run_count = ?, error_log = ?
                        WHERE id = ?
                    """, ("failed", job.run_count + 1, json.dumps(error_log[-10:]), job.id))
                    conn.commit()

    def _dispatch_job(self, job: ScheduledJob) -> Dict[str, Any]:
        jt = job.job_type
        args = job.job_args

        if jt == "agent":
            agent_name = args.get("agent", "coding_agent")
            task = args.get("task", "")
            return self.jarvis.agents.delegate(agent_name, task)

        if jt == "tool":
            tool_call = args.get("tool_call", {})
            return self.jarvis._execute_with_safety(tool_call)

        if jt == "plan":
            goal = args.get("goal", "")
            return {"success": True, "result": self.jarvis._handle_autonomous(goal)}

        if jt == "shell":
            command = args.get("command", "")
            import subprocess
            r = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=300)
            return {
                "success": r.returncode == 0,
                "result": r.stdout if r.returncode == 0 else r.stderr
            }

        if jt == "python":
            code = args.get("code", "")
            import io, sys
            from contextlib import redirect_stdout, redirect_stderr
            out = io.StringIO()
            err = io.StringIO()
            try:
                with redirect_stdout(out), redirect_stderr(err):
                    exec(code, {"__builtins__": __builtins__}, {})
                return {"success": True, "result": out.getvalue()}
            except Exception as e:
                return {"success": False, "result": f"{err.getvalue()}\n{str(e)}"}

        if jt == "reminder":
            message = args.get("message", "Reminder from JARVIS")
            if hasattr(self.jarvis, 'memory'):
                self.jarvis.memory.store_fact(f"[REMINDER] {message}", category="reminder")
            return {"success": True, "result": message}

        if jt == "function":
            fn_name = args.get("function", "")
            fn_args = args.get("args", {})
            if hasattr(self.jarvis, fn_name):
                fn = getattr(self.jarvis, fn_name)
                try:
                    r = fn(**fn_args)
                    return {"success": True, "result": str(r)}
                except Exception as e:
                    return {"success": False, "result": str(e)}
            return {"success": False, "result": f"Function {fn_name} not found"}

        return {"success": False, "result": f"Unknown job type: {jt}"}

    def parse_natural_schedule(self, text: str) -> Optional[Dict[str, Any]]:
        text_lower = text.lower().strip()
        import re

        m = re.search(r'every\s+(\d+)\s+(minute|minutes|hour|hours|day|days|week|weeks)', text_lower)
        if m:
            num = int(m.group(1))
            unit = m.group(2).rstrip('s')
            return {
                "trigger": "interval",
                "trigger_args": {f"{unit}s": num},
            }

        m = re.search(r'every\s+(mon|tue|wed|thu|fri|sat|sun)(?:day)?\s+at\s+(\d+)(?::(\d+))?\s*(am|pm)?', text_lower)
        if m:
            dow = m.group(1)
            hour = int(m.group(2))
            minute = int(m.group(3)) if m.group(3) else 0
            ampm = m.group(4)
            if ampm == "pm" and hour != 12:
                hour += 12
            if ampm == "am" and hour == 12:
                hour = 0
            return {
                "trigger": "cron",
                "trigger_args": {"day_of_week": dow, "hour": hour, "minute": minute},
            }

        m = re.search(r'in\s+(\d+)\s+(minute|minutes|hour|hours|day|days)', text_lower)
        if m:
            num = int(m.group(1))
            unit = m.group(2).rstrip('s')
            return {
                "trigger": "delay",
                "trigger_args": {f"{unit}s": num},
            }

        m = re.search(r'at\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})', text_lower)
        if m:
            return {
                "trigger": "date",
                "trigger_args": {"datetime": m.group(1)},
            }

        m = re.search(r'at\s+(\d{1,2}):\s*(\d{2})\s*(am|pm)?', text_lower)
        if m:
            hour = int(m.group(1))
            minute = int(m.group(2))
            ampm = m.group(3)
            if ampm == "pm" and hour != 12:
                hour += 12
            if ampm == "am" and hour == 12:
                hour = 0
            dt = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
            if dt < datetime.now():
                dt += timedelta(days=1)
            return {
                "trigger": "date",
                "trigger_args": {"datetime": dt.isoformat()},
            }

        return None
