"""
core/model_router.py

Model Router — Tier 2 Intelligence Amplification.
Routes every LLM request to the most appropriate backend.

Drop-in replacement for OllamaClient. All existing self.llm.generate() calls
work unchanged — but now get intelligently routed.
"""

import os
import time
import requests
from typing import Dict, Any, Optional, List


class ModelRouter:
    """
    Intelligent LLM router. Acts like OllamaClient but routes by task type.
    """

    DEFAULT_ROUTES = {
        "simple_qa":      ("local_fast",     "llama3.2:1b",        "Simple question, fast model"),
        "routing":        ("local_fast",     "llama3.2:1b",        "Routing decision"),
        "classification": ("local_fast",     "llama3.2:1b",        "Classification task"),
        "chat":           ("local_standard", "llama3.1",           "General conversation"),
        "summarization":  ("local_standard", "llama3.1",           "Text processing"),
        "coding":         ("local_strong",   "qwen2.5-coder:14b",  "Code generation"),
        "architecture":   ("local_strong",   "qwen2.5-coder:14b",  "Design reasoning"),
        "debugging":      ("local_strong",   "qwen2.5-coder:14b",  "Debugging"),
        "verification":   ("local_strong",   "qwen2.5-coder:14b",  "Verification"),
        "vision":         ("vision",         "llava",              "Vision task"),
        "fallback":       ("local_standard", "llama3.1",           "Default fallback"),
    }

    COST_TABLE = {
        "local_fast": 0.1,
        "local_standard": 0.3,
        "local_strong": 0.8,
        "cloud": 1.0,
        "vision": 0.5,
    }

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.routes = self.config.get("model_routes", self.DEFAULT_ROUTES.copy())
        self.backends = self._init_backends()
        self.request_log: List[Dict] = []

    def _init_backends(self) -> Dict[str, Any]:
        from core.llm import OllamaClient

        backends = {}
        base_url = self.config.get("base_url", "http://localhost:11434")

        fast_model = self.config.get("fast_model", "llama3.2:1b")
        if self._model_available(fast_model):
            backends["local_fast"] = OllamaClient(model=fast_model, base_url=base_url)

        std_model = self.config.get("model", "llama3.1")
        if self._model_available(std_model):
            backends["local_standard"] = OllamaClient(model=std_model, base_url=base_url)

        strong_model = self.config.get("strong_model", "qwen2.5-coder:14b")
        if self._model_available(strong_model):
            backends["local_strong"] = OllamaClient(model=strong_model, base_url=base_url)

        vision_model = self.config.get("vision_model", "llava")
        if self._model_available(vision_model):
            backends["vision"] = OllamaClient(model=vision_model, base_url=base_url)

        if self.config.get("openai_api_key"):
            backends["cloud"] = CloudBackend(
                self.config["openai_api_key"],
                self.config.get("cloud_model", "gpt-4o-mini")
            )

        return backends

    def _model_available(self, model_name: str) -> bool:
        try:
            resp = requests.get("http://localhost:11434/api/tags", timeout=2)
            if resp.status_code == 200:
                models = [m["name"] for m in resp.json().get("models", [])]
                return any(model_name in m for m in models)
        except Exception:
            pass
        return True

    def classify_task(self, prompt: str) -> str:
        """Fast keyword-based classification. No LLM call needed for common cases."""
        p = prompt.lower()

        # Coding keywords
        if any(k in p for k in ["def ", "class ", "import ", "function", "code:", "```python",
                                  "javascript", "script", "program", "debug", "error in",
                                  "write a python", "build an app", "create a script"]):
            return "coding"

        # Architecture/planning keywords
        if any(k in p for k in ["plan", "subtask", "architecture", "design", "structure",
                                  "break into steps", "system design", "how should i"]):
            return "architecture"

        # Vision keywords
        if any(k in p for k in ["look at", "screen", "image", "photo", "vision",
                                  "see this", "what do you see", "describe this"]):
            return "vision"

        # Verification keywords
        if any(k in p for k in ["verify", "check if", "test", "did it work",
                                  "confirm", "validate"]):
            return "verification"

        # Simple Q&A
        if any(k in p for k in ["what is", "who is", "when", "where", "how many",
                                  "define", "explain", "tell me about"]):
            return "simple_qa"

        # Summarization
        if any(k in p for k in ["summarize", "summary", "tl;dr", "condense", "key points"]):
            return "summarization"

        # Fallback to LLM classifier for ambiguous cases
        classifier = self.backends.get("local_fast") or self.backends.get("local_standard")
        if not classifier:
            return "fallback"

        try:
            cp = f"""Classify this task into ONE category: simple_qa, chat, coding, architecture, debugging, verification, summarization, vision, fallback.
Task: {prompt[:400]}
Category:"""
            result = classifier.generate(cp, max_tokens=15, temperature=0.1)
            cat = result.strip().lower().split()[0]
            if cat in self.routes:
                return cat
        except Exception:
            pass

        return "fallback"

    def route(self, prompt: str, system: str = None, task_type: str = None,
              force_backend: str = None, **kwargs) -> Dict[str, Any]:
        start = time.time()

        if force_backend:
            backend_name = force_backend
            _, model_name, reason = self.routes.get(task_type or "fallback", self.routes["fallback"])
            reason = f"Forced to {force_backend}"
        elif task_type and task_type in self.routes:
            backend_name, model_name, reason = self.routes[task_type]
        else:
            detected = self.classify_task(prompt)
            backend_name, model_name, reason = self.routes.get(detected, self.routes["fallback"])

        backend = self.backends.get(backend_name)
        if not backend:
            for fb in ["local_standard", "local_strong", "local_fast"]:
                backend = self.backends.get(fb)
                if backend:
                    backend_name = fb
                    break

        if not backend:
            return {
                "result": "[ERROR] No LLM backend available",
                "backend_used": "none",
                "latency_ms": 0,
                "cost": 0.0,
                "success": False
            }

        try:
            result = backend.generate(prompt, system=system, **kwargs)
            latency = int((time.time() - start) * 1000)
            cost = self.COST_TABLE.get(backend_name, 0.3) * (len(prompt) + len(result)) / 2000

            self.request_log.append({
                "backend": backend_name,
                "task_type": task_type or "auto",
                "latency": latency,
                "cost": cost,
                "timestamp": time.time()
            })

            return {
                "result": result,
                "backend_used": backend_name,
                "model": model_name,
                "latency_ms": latency,
                "cost": round(cost, 4),
                "reason": reason,
                "success": True
            }

        except Exception as e:
            latency = int((time.time() - start) * 1000)
            return {
                "result": f"[ERROR] {e}",
                "backend_used": backend_name,
                "latency_ms": latency,
                "cost": 0.0,
                "success": False
            }

    def generate(self, prompt: str, system: Optional[str] = None,
                 temperature: float = 0.7, max_tokens: int = 2000,
                 task_type: str = None, force_backend: str = None) -> str:
        """
        Drop-in replacement for OllamaClient.generate().
        All existing self.llm.generate() calls work unchanged.
        """
        result = self.route(
            prompt, system=system, temperature=temperature,
            max_tokens=max_tokens, task_type=task_type,
            force_backend=force_backend
        )
        return result["result"]

    def get_stats(self) -> Dict[str, Any]:
        if not self.request_log:
            return {"total_requests": 0, "backends_available": list(self.backends.keys())}

        total = len(self.request_log)
        bc = {}
        tc = 0.0
        tl = 0
        for r in self.request_log:
            b = r["backend"]
            bc[b] = bc.get(b, 0) + 1
            tc += r["cost"]
            tl += r["latency"]

        return {
            "total_requests": total,
            "backend_distribution": bc,
            "avg_latency_ms": round(tl / total, 1),
            "total_cost": round(tc, 4),
            "backends_available": list(self.backends.keys())
        }


class CloudBackend:
    """Optional OpenAI cloud fallback."""
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model

    def generate(self, prompt: str, system: str = None, temperature: float = 0.7,
                 max_tokens: int = 2000) -> str:
        try:
            import openai
            client = openai.OpenAI(api_key=self.api_key)
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            resp = client.chat.completions.create(
                model=self.model, messages=messages,
                temperature=temperature, max_tokens=max_tokens
            )
            return resp.choices[0].message.content
        except Exception as e:
            return f"[Cloud error: {e}]"
