"""
tests/test_model_router.py

Test the Model Router's classification and routing logic.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.model_router import ModelRouter


class FakeBackend:
    def __init__(self, name):
        self.name = name
    def generate(self, prompt, system=None, temperature=0.7, max_tokens=2000):
        return f"[{self.name}] {prompt[:30]}..."


def test_keyword_classification():
    print("\n=== Test: Keyword Classification ===")
    mr = ModelRouter({"model": "test", "base_url": "http://localhost:11434"})
    
    # Inject fake backends so we don't need Ollama running
    mr.backends = {
        "local_fast": FakeBackend("fast"),
        "local_standard": FakeBackend("std"),
        "local_strong": FakeBackend("strong"),
        "vision": FakeBackend("vision"),
    }

    cases = [
        ("Write a Python function to sort a list", "coding"),
        ("Design a system architecture for my app", "architecture"),
        ("What is the capital of France?", "simple_qa"),
        ("Look at my screen and tell me what you see", "vision"),
        ("Summarize this text for me", "summarization"),
        ("Verify that the file was created", "verification"),
        ("Hello, how are you?", "chat"),
    ]

    for prompt, expected in cases:
        result = mr.classify_task(prompt)
        # Some might fall back to fallback, but coding/arch/vision/simple should be exact
        if expected in ("coding", "architecture", "vision", "simple_qa", "summarization", "verification"):
            assert result == expected, f"Failed for '{prompt}': got {result}, expected {expected}"
            print(f"  ✓ '{prompt[:40]}...' → {result}")

    print("✓ Keyword classification: PASS")


def test_routing_fallback():
    print("\n=== Test: Routing Fallback ===")
    mr = ModelRouter({"model": "test"})
    mr.backends = {
        "local_standard": FakeBackend("std"),
    }

    result = mr.route("Hello world")
    assert result["success"] is True
    assert result["backend_used"] == "local_standard"
    print(f"  ✓ Fallback to local_standard: {result['reason']}")
    print("✓ Routing fallback: PASS")


def test_generate_drop_in():
    print("\n=== Test: Drop-in generate() ===")
    mr = ModelRouter({"model": "test"})
    mr.backends = {"local_standard": FakeBackend("std")}

    # This is exactly how jarvis.py calls it
    text = mr.generate("Hello", system="You are JARVIS")
    assert "[std]" in text
    print(f"  ✓ generate() returned: {text[:40]}...")
    print("✓ Drop-in generate: PASS")


def test_forced_backend():
    print("\n=== Test: Force Backend ===")
    mr = ModelRouter({"model": "test"})
    mr.backends = {
        "local_fast": FakeBackend("fast"),
        "local_strong": FakeBackend("strong"),
    }

    # Force strong model for coding
    result = mr.route("Write code", force_backend="local_strong")
    assert result["backend_used"] == "local_strong"
    print(f"  ✓ Forced backend: {result['backend_used']}")
    print("✓ Force backend: PASS")


def test_stats_tracking():
    print("\n=== Test: Stats Tracking ===")
    mr = ModelRouter({"model": "test"})
    mr.backends = {"local_standard": FakeBackend("std")}

    mr.generate("Test 1")
    mr.generate("Test 2")
    mr.generate("Test 3")

    stats = mr.get_stats()
    assert stats["total_requests"] == 3
    assert "local_standard" in stats["backend_distribution"]
    print(f"  ✓ Stats: {stats}")
    print("✓ Stats tracking: PASS")


if __name__ == "__main__":
    print("=" * 50)
    print("Model Router Test Suite")
    print("=" * 50)

    test_keyword_classification()
    test_routing_fallback()
    test_generate_drop_in()
    test_forced_backend()
    test_stats_tracking()

    print("\n" + "=" * 50)
    print("ALL MODEL ROUTER TESTS PASSED")
    print("=" * 50)
