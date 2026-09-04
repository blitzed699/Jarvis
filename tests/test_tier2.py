"""
tests/test_tier2.py

Tier 2 Intelligence Amplification — Full Test Suite.
Tests: Replanning, Scheduler, Knowledge Graph, Temporal Reasoning.

Run: python tests/test_tier2.py
"""

import sys
import os
import time
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.replanning import ReplanningEngine, FailureCategory, RecoveryStrategy
from core.scheduler import BackgroundScheduler, JobStatus
from core.knowledge_graph import KnowledgeGraph, Entity, Relation
from core.temporal import TemporalReasoner, TemporalExpression


# ── Mocks ──────────────────────────────────────────────────────────

class MockLLM:
    def generate(self, prompt, system=None, temperature=0.7, max_tokens=2000):
        if "replan" in prompt.lower() or "recovery" in prompt.lower():
            return '[{"id": 99, "description": "Recovered step", "agent": "llm", "depends_on": []}]'
        if "behavioral rule" in prompt.lower():
            return "Always verify files exist before claiming they were created."
        if "when should" in prompt.lower():
            return "in 30 minutes"
        if "extract" in prompt.lower():
            return """{"entities": [{"name": "TestProject", "type": "project"}],
                      "relations": [{"from": "TestProject", "relation": "uses", "to": "Python"}]}"""
        return "Mock LLM response"


class MockPlanner:
    def __init__(self):
        self.tasks = []
    def plan(self, goal):
        return []


class MockWorldState:
    def __init__(self):
        self.active_plan = None
        self.action_history = []
    def get_recent_failures(self, n=5):
        return []


class MockOVCLoop:
    pass


class MockJARVISCore:
    def __init__(self):
        self.agents = MockAgents()
        self.memory = MockMemory()

class MockAgents:
    def delegate(self, agent_name, task):
        return {"success": True, "result": f"Mock {agent_name} result"}

class MockMemory:
    def store_fact(self, text, category="other"):
        pass


# ── Replanning Tests ───────────────────────────────────────────────

def test_replanning_analyze_failure():
    print("\n=== Test: Replanning — Failure Analysis ===")
    replanner = ReplanningEngine(MockLLM(), MockPlanner(), MockWorldState(), MockOVCLoop())

    class FakeStep:
        id = 1
        description = "Write file"

    analysis = replanner.analyze_failure(
        FakeStep(),
        {"success": False, "result": "Permission denied"},
        ["Permission denied"]
    )

    assert analysis.category == FailureCategory.PERMISSION_DENIED
    assert analysis.confidence > 0.5
    assert not analysis.can_retry
    print(f"  ✓ Detected: {analysis.category.value} (confidence: {analysis.confidence:.2f})")
    print("✓ Failure analysis: PASS")


def test_replanning_strategy_selection():
    print("\n=== Test: Replanning — Strategy Selection ===")
    replanner = ReplanningEngine(MockLLM(), MockPlanner(), MockWorldState(), MockOVCLoop())

    analysis = type('obj', (object,), {
        'category': FailureCategory.TIMEOUT,
        'is_transient': True,
        'can_retry': True
    })

    strat = replanner.select_recovery_strategy(analysis(), attempt_count=1)
    assert strat == RecoveryStrategy.RETRY

    strat = replanner.select_recovery_strategy(analysis(), attempt_count=2)
    assert strat == RecoveryStrategy.RETRY_WITH_FIX

    analysis_perm = type('obj', (object,), {
        'category': FailureCategory.PERMISSION_DENIED,
        'is_transient': False,
        'can_retry': False
    })
    strat = replanner.select_recovery_strategy(analysis_perm(), attempt_count=1)
    assert strat == RecoveryStrategy.ABORT

    print("  ✓ Retry on first transient failure")
    print("  ✓ Retry_with_fix on second attempt")
    print("  ✓ Abort on permission denied")
    print("✓ Strategy selection: PASS")


def test_replanning_recovery_plan():
    print("\n=== Test: Replanning — Recovery Plan Generation ===")
    replanner = ReplanningEngine(MockLLM(), MockPlanner(), MockWorldState(), MockOVCLoop())

    class FakeStep:
        id = 2
        description = "Build API"
        agent = "coding_agent"
        depends_on = []

    analysis = replanner.analyze_failure(
        FakeStep(), {"success": False}, ["Timeout"]
    )
    plan, _ = replanner.execute_recovery(
        "Build app", FakeStep(), {"success": False}, ["Timeout"],
        [], [], attempt_count=1
    )

    assert plan.strategy in (RecoveryStrategy.RETRY, RecoveryStrategy.RETRY_WITH_FIX)
    assert len(replanner.replan_history) == 1
    print(f"  ✓ Recovery strategy: {plan.strategy.value}")
    print(f"  ✓ History tracked: {len(replanner.replan_history)} entries")
    print("✓ Recovery plan: PASS")


# ── Scheduler Tests ────────────────────────────────────────────────

def test_scheduler_add_job():
    print("\n=== Test: Scheduler — Add Job ===")
    jarvis = MockJARVISCore()
    sched = BackgroundScheduler(jarvis, db_path="/tmp/jarvis_test_scheduler.db")

    jid = sched.add_job(
        name="Test job",
        trigger="delay",
        trigger_args={"seconds": 3600},
        job_type="reminder",
        job_args={"message": "Hello"}
    )
    assert jid.startswith("job_")

    job = sched.get_job(jid)
    assert job is not None
    assert job.name == "Test job"
    assert job.status == "pending"
    print(f"  ✓ Job added: {jid}")
    print("✓ Scheduler add: PASS")

    os.remove("/tmp/jarvis_test_scheduler.db")


def test_scheduler_natural_language():
    print("\n=== Test: Scheduler — Natural Language Parsing ===")
    jarvis = MockJARVISCore()
    sched = BackgroundScheduler(jarvis, db_path="/tmp/jarvis_test_scheduler2.db")

    cases = [
        ("every 5 minutes check email", "interval"),
        ("every Monday at 9am run backup", "cron"),
        ("in 30 minutes remind me", "delay"),
        ("at 2026-09-15 14:00 deploy", "date"),
    ]

    for text, expected_trigger in cases:
        parsed = sched.parse_natural_schedule(text)
        assert parsed is not None, f"Failed to parse: {text}"
        assert parsed["trigger"] == expected_trigger, f"Expected {expected_trigger}, got {parsed['trigger']}"
        print(f"  ✓ '{text[:30]}...' → {parsed['trigger']}")

    print("✓ Natural language parsing: PASS")
    os.remove("/tmp/jarvis_test_scheduler2.db")


def test_scheduler_list_cancel():
    print("\n=== Test: Scheduler — List & Cancel ===")
    jarvis = MockJARVISCore()
    sched = BackgroundScheduler(jarvis, db_path="/tmp/jarvis_test_scheduler3.db")

    jid1 = sched.add_job("Job 1", "delay", {"seconds": 100}, "reminder", {"message": "A"})
    jid2 = sched.add_job("Job 2", "delay", {"seconds": 200}, "reminder", {"message": "B"})

    jobs = sched.list_jobs()
    assert len(jobs) == 2

    sched.cancel_job(jid1)
    jobs = sched.list_jobs(status="pending")
    assert len(jobs) == 1
    assert jobs[0].id == jid2

    print(f"  ✓ Listed {len(jobs)} pending jobs after cancel")
    print("✓ List & cancel: PASS")
    os.remove("/tmp/jarvis_test_scheduler3.db")


# ── Knowledge Graph Tests ──────────────────────────────────────────

def test_kg_add_query():
    print("\n=== Test: Knowledge Graph — Add & Query ===")
    kg = KnowledgeGraph(db_path="/tmp/jarvis_test_kg.db")

    kg.add_entity("JARVIS", "project", {"language": "Python"})
    kg.add_entity("Ollama", "tool", {"type": "LLM runtime"})
    kg.add_relation("JARVIS", "uses", "Ollama")

    results = kg.query(entity_name="JARVIS")
    assert len(results["entities"]) >= 1
    assert len(results["relations"]) >= 1

    related = kg.get_related("JARVIS", direction="outgoing")
    assert any(r["entity_name"] == "Ollama" for r in related)

    print(f"  ✓ Entities: {len(results['entities'])}, Relations: {len(results['relations'])}")
    print("✓ KG add & query: PASS")
    os.remove("/tmp/jarvis_test_kg.db")


def test_kg_pathfinding():
    print("\n=== Test: Knowledge Graph — Path Finding ===")
    kg = KnowledgeGraph(db_path="/tmp/jarvis_test_kg2.db")

    kg.add_entity("User", "person")
    kg.add_entity("JARVIS", "project")
    kg.add_entity("Python", "tool")
    kg.add_entity("FastAPI", "tool")

    kg.add_relation("User", "owns", "JARVIS")
    kg.add_relation("JARVIS", "uses", "Python")
    kg.add_relation("Python", "enables", "FastAPI")

    path = kg.get_path("User", "FastAPI")
    assert path is not None
    assert len(path) > 0
    print(f"  ✓ Path found: User → {' → '.join(p['to_name'] for p in path)}")
    print("✓ KG pathfinding: PASS")
    os.remove("/tmp/jarvis_test_kg2.db")


def test_kg_extraction():
    print("\n=== Test: Knowledge Graph — LLM Extraction ===")
    kg = KnowledgeGraph(db_path="/tmp/jarvis_test_kg3.db")
    llm = MockLLM()

    text = "JARVIS is a project that uses Python and depends on Ollama."
    result = kg.extract_from_text(text, llm)

    assert result["entities_added"] > 0
    print(f"  ✓ Extracted {result['entities_added']} entities, {result['relations_added']} relations")
    print("✓ KG extraction: PASS")
    os.remove("/tmp/jarvis_test_kg3.db")


# ── Temporal Tests ─────────────────────────────────────────────────

def test_temporal_relative():
    print("\n=== Test: Temporal — Relative Parsing ===")
    tr = TemporalReasoner()

    cases = [
        ("in 3 days", "relative"),
        ("tomorrow", "relative"),
        ("in 30 minutes", "relative"),
        ("next week", "relative"),
    ]

    for text, expected_type in cases:
        result = tr.parse(text)
        assert result is not None, f"Failed: {text}"
        assert result.parsed_type == expected_type
        assert result.target_datetime is not None
        print(f"  ✓ '{text}' → {result.description}")

    print("✓ Relative parsing: PASS")


def test_temporal_recurring():
    print("\n=== Test: Temporal — Recurring Parsing ===")
    tr = TemporalReasoner()

    cases = [
        ("every Monday at 9am", "recurring"),
        ("every day at noon", "recurring"),
        ("every 5 minutes", "recurring"),
    ]

    for text, expected_type in cases:
        result = tr.parse(text)
        assert result is not None, f"Failed: {text}"
        assert result.parsed_type == expected_type
        assert result.cron_dict is not None
        print(f"  ✓ '{text}' → {result.description}")

    print("✓ Recurring parsing: PASS")


def test_temporal_deadline():
    print("\n=== Test: Temporal — Deadline Tracking ===")
    tr = TemporalReasoner()

    future = tr.parse("in 5 days")
    status = tr.time_until(future.target_datetime)
    assert not status["overdue"]
    assert "remaining" in status["text"]
    print(f"  ✓ Future deadline: {status['text']}")

    from datetime import datetime, timedelta
    past_dt = datetime.now() - timedelta(days=1)
    assert tr.is_overdue(past_dt)
    status = tr.time_until(past_dt)
    assert status["overdue"]
    print(f"  ✓ Past deadline: {status['text']}")

    print("✓ Deadline tracking: PASS")


def test_temporal_scheduler_bridge():
    print("\n=== Test: Temporal → Scheduler Bridge ===")
    tr = TemporalReasoner()

    expr = tr.parse("every Monday at 9am")
    sched_args = tr.to_scheduler_args(expr)
    assert sched_args["trigger"] == "cron"
    assert sched_args["trigger_args"]["day_of_week"] == "mon"

    expr2 = tr.parse("in 30 minutes")
    sched_args2 = tr.to_scheduler_args(expr2)
    assert sched_args2["trigger"] == "date"

    print(f"  ✓ Cron: {sched_args['trigger_args']}")
    print(f"  ✓ Date: {sched_args2['trigger_args']}")
    print("✓ Scheduler bridge: PASS")


# ── Main ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("JARVIS v0.5 — Tier 2 Intelligence Amplification Test Suite")
    print("=" * 60)

    test_replanning_analyze_failure()
    test_replanning_strategy_selection()
    test_replanning_recovery_plan()

    test_scheduler_add_job()
    test_scheduler_natural_language()
    test_scheduler_list_cancel()

    test_kg_add_query()
    test_kg_pathfinding()
    test_kg_extraction()

    test_temporal_relative()
    test_temporal_recurring()
    test_temporal_deadline()
    test_temporal_scheduler_bridge()

    print("\n" + "=" * 60)
    print("ALL TIER 2 TESTS PASSED")
    print("=" * 60)
    print("\nTier 2 is fully operational.")
    print("JARVIS can now replan, schedule, reason about knowledge, and understand time.")
