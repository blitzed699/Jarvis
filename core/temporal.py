"""
core/temporal.py

Temporal Reasoning — Tier 2 Intelligence Amplification.
JARVIS understands time.

Capabilities:
  - Parse natural language time expressions
  - Track deadlines and due dates
  - Generate cron expressions from descriptions
  - Calculate time remaining / overdue status
  - Time-aware planning ("do this before Friday")

Examples:
  "in 3 days"           → datetime
  "every Monday at 9am" → cron dict
  "tomorrow at 3pm"     → datetime
  "next week"           → datetime
  "before 2026-09-15"   → deadline
  "2 hours from now"    → datetime
"""

import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass


@dataclass
class TemporalExpression:
    expression: str
    parsed_type: str
    target_datetime: Optional[datetime]
    cron_dict: Optional[Dict[str, Any]]
    description: str


class TemporalReasoner:
    RELATIVE_UNITS = {
        "second": 1, "seconds": 1,
        "minute": 60, "minutes": 60,
        "hour": 3600, "hours": 3600,
        "day": 86400, "days": 86400,
        "week": 604800, "weeks": 604800,
        "month": 2592000, "months": 2592000,
    }

    WEEKDAYS = {
        "monday": 0, "mon": 0,
        "tuesday": 1, "tue": 1, "tues": 1,
        "wednesday": 2, "wed": 2,
        "thursday": 3, "thu": 3, "thurs": 3,
        "friday": 4, "fri": 4,
        "saturday": 5, "sat": 5,
        "sunday": 6, "sun": 6,
    }

    def __init__(self, now: datetime = None):
        self._now = now or datetime.now()

    def parse(self, text: str, base_time: datetime = None) -> Optional[TemporalExpression]:
        text_lower = text.lower().strip()
        base = base_time or self._now

        result = (
            self._parse_relative(text_lower, base) or
            self._parse_recurring(text_lower, base) or
            self._parse_absolute(text_lower, base) or
            self._parse_deadline(text_lower, base)
        )

        return result

    def _parse_relative(self, text: str, base: datetime) -> Optional[TemporalExpression]:
        if text == "tomorrow" or text.startswith("tomorrow"):
            dt = base + timedelta(days=1)
            return TemporalExpression(
                expression=text,
                parsed_type="relative",
                target_datetime=dt.replace(hour=9, minute=0, second=0, microsecond=0),
                cron_dict=None,
                description="Tomorrow at 9:00 AM"
            )

        if text == "today":
            return TemporalExpression(
                expression=text,
                parsed_type="relative",
                target_datetime=base,
                cron_dict=None,
                description="Today"
            )

        m = re.match(r'next\s+(week|month|year)', text)
        if m:
            unit = m.group(1)
            if unit == "week":
                dt = base + timedelta(weeks=1)
            elif unit == "month":
                dt = base + timedelta(days=30)
            else:
                dt = base.replace(year=base.year + 1)
            return TemporalExpression(
                expression=text,
                parsed_type="relative",
                target_datetime=dt,
                cron_dict=None,
                description=f"Next {unit}"
            )

        patterns = [
            r'in\s+(\d+)\s+(second|seconds|minute|minutes|hour|hours|day|days|week|weeks|month|months)',
            r'(\d+)\s+(second|seconds|minute|minutes|hour|hours|day|days|week|weeks|month|months)\s+from\s+now',
        ]
        for pattern in patterns:
            m = re.search(pattern, text)
            if m:
                num = int(m.group(1))
                unit = m.group(2)
                seconds = self.RELATIVE_UNITS.get(unit, 86400) * num
                dt = base + timedelta(seconds=seconds)
                return TemporalExpression(
                    expression=text,
                    parsed_type="relative",
                    target_datetime=dt,
                    cron_dict=None,
                    description=f"In {num} {unit}"
                )

        m = re.search(r'in\s+(an?|one)\s+(hour|day|week|month)', text)
        if m:
            unit = m.group(2) + "s"
            seconds = self.RELATIVE_UNITS.get(unit, 86400)
            dt = base + timedelta(seconds=seconds)
            return TemporalExpression(
                expression=text,
                parsed_type="relative",
                target_datetime=dt,
                cron_dict=None,
                description=f"In 1 {m.group(2)}"
            )

        return None

    def _parse_recurring(self, text: str, base: datetime) -> Optional[TemporalExpression]:
        m = re.match(r'every\s+day\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', text)
        if m:
            hour = int(m.group(1))
            minute = int(m.group(2)) if m.group(2) else 0
            ampm = m.group(3)
            if ampm == "pm" and hour != 12:
                hour += 12
            if ampm == "am" and hour == 12:
                hour = 0
            return TemporalExpression(
                expression=text,
                parsed_type="recurring",
                target_datetime=None,
                cron_dict={"day_of_week": None, "hour": hour, "minute": minute},
                description=f"Daily at {hour:02d}:{minute:02d}"
            )

        m = re.match(r'every\s+weekday\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', text)
        if m:
            hour = int(m.group(1))
            minute = int(m.group(2)) if m.group(2) else 0
            ampm = m.group(3)
            if ampm == "pm" and hour != 12:
                hour += 12
            if ampm == "am" and hour == 12:
                hour = 0
            return TemporalExpression(
                expression=text,
                parsed_type="recurring",
                target_datetime=None,
                cron_dict={"day_of_week": "mon-fri", "hour": hour, "minute": minute},
                description=f"Weekdays at {hour:02d}:{minute:02d}"
            )

        m = re.match(r'every\s+(mon|tue|wed|thu|fri|sat|sun)(?:day)?\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', text)
        if m:
            dow = m.group(1)
            hour = int(m.group(2))
            minute = int(m.group(3)) if m.group(3) else 0
            ampm = m.group(4)
            if ampm == "pm" and hour != 12:
                hour += 12
            if ampm == "am" and hour == 12:
                hour = 0
            return TemporalExpression(
                expression=text,
                parsed_type="recurring",
                target_datetime=None,
                cron_dict={"day_of_week": dow, "hour": hour, "minute": minute},
                description=f"Every {dow.capitalize()}day at {hour:02d}:{minute:02d}"
            )

        m = re.match(r'every\s+(\d+)\s+(minute|minutes|hour|hours)', text)
        if m:
            num = int(m.group(1))
            unit = m.group(2)
            return TemporalExpression(
                expression=text,
                parsed_type="recurring",
                target_datetime=None,
                cron_dict={"interval": {unit: num}},
                description=f"Every {num} {unit}"
            )

        return None

    def _parse_absolute(self, text: str, base: datetime) -> Optional[TemporalExpression]:
        m = re.match(r'(\d{4}-\d{2}-\d{2})(?:\s+(\d{1,2}):\s*(\d{2}))?', text)
        if m:
            date_str = m.group(1)
            hour = int(m.group(2)) if m.group(2) else 0
            minute = int(m.group(3)) if m.group(3) else 0
            dt = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=hour, minute=minute)
            return TemporalExpression(
                expression=text,
                parsed_type="absolute",
                target_datetime=dt,
                cron_dict=None,
                description=dt.strftime("%Y-%m-%d %H:%M")
            )

        m = re.match(r'at\s+(\d{1,2}):\s*(\d{2})\s*(am|pm)?', text)
        if m:
            hour = int(m.group(1))
            minute = int(m.group(2))
            ampm = m.group(3)
            if ampm == "pm" and hour != 12:
                hour += 12
            if ampm == "am" and hour == 12:
                hour = 0
            dt = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if dt < base:
                dt += timedelta(days=1)
            return TemporalExpression(
                expression=text,
                parsed_type="absolute",
                target_datetime=dt,
                cron_dict=None,
                description=dt.strftime("Today/Tomorrow at %H:%M")
            )

        return None

    def _parse_deadline(self, text: str, base: datetime) -> Optional[TemporalExpression]:
        m = re.match(r'(before|by|until)\s+(.+)', text)
        if m:
            deadline_text = m.group(2).strip()
            inner = self.parse(deadline_text, base)
            if inner and inner.target_datetime:
                return TemporalExpression(
                    expression=text,
                    parsed_type="deadline",
                    target_datetime=inner.target_datetime,
                    cron_dict=None,
                    description=f"Deadline: {inner.description}"
                )

        return None

    def is_overdue(self, target: datetime) -> bool:
        return datetime.now() > target

    def time_until(self, target: datetime) -> Dict[str, Any]:
        diff = target - datetime.now()
        if diff.total_seconds() < 0:
            return {"overdue": True, "seconds": abs(diff.total_seconds()),
                    "text": self._format_duration(abs(diff)) + " overdue"}
        return {"overdue": False, "seconds": diff.total_seconds(),
                "text": self._format_duration(diff) + " remaining"}

    def _format_duration(self, delta: timedelta) -> str:
        total_seconds = int(delta.total_seconds())
        if total_seconds < 60:
            return f"{total_seconds} second{'s' if total_seconds != 1 else ''}"
        minutes = total_seconds // 60
        if minutes < 60:
            return f"{minutes} minute{'s' if minutes != 1 else ''}"
        hours = minutes // 60
        if hours < 24:
            remaining_mins = minutes % 60
            return f"{hours}h {remaining_mins}m"
        days = hours // 24
        remaining_hours = hours % 24
        return f"{days} day{'s' if days != 1 else ''} {remaining_hours}h"

    def to_scheduler_args(self, expr: TemporalExpression) -> Optional[Dict[str, Any]]:
        if expr.parsed_type == "recurring" and expr.cron_dict:
            cd = expr.cron_dict
            if "interval" in cd:
                return {"trigger": "interval", "trigger_args": cd["interval"]}
            return {"trigger": "cron", "trigger_args": cd}

        if expr.target_datetime:
            return {
                "trigger": "date",
                "trigger_args": {"datetime": expr.target_datetime.isoformat()}
            }

        return None

    def suggest_schedule(self, task_description: str, llm_client) -> Optional[TemporalExpression]:
        if not llm_client:
            return None

        prompt = f"""When should this task be scheduled? Respond with ONLY a time expression.

Task: {task_description}

Examples of valid responses:
- "in 30 minutes"
- "every day at 9am"
- "tomorrow at 3pm"
- "every Monday at 10am"
- "2026-09-15 14:00"

Time expression:"""

        try:
            response = llm_client.generate(prompt, max_tokens=30, temperature=0.3).strip()
            return self.parse(response)
        except Exception:
            return None
