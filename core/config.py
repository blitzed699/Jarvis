import os
import yaml
from typing import Dict, Any


DEFAULT_CONFIG = {
    "model": "llama3.1",
    "base_url": "http://localhost:11434",
    "voice_enabled": False,
    "auto_approve_readonly": True,
    "memory_db": "memory/jarvis_memory.db",
    "chroma_path": "memory/chroma_db",
    "max_tokens": 2000,
    "temperature": 0.7,
    "working_memory_recent": 10,
    "working_memory_relevant": 5,
}


class Config:
    def __init__(self, path: str = "config.yaml"):
        self.path = path
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r') as f:
                    return {**DEFAULT_CONFIG, **yaml.safe_load(f)}
            except Exception:
                pass
        return DEFAULT_CONFIG.copy()

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value: Any):
        self.data[key] = value
        self.save()

    def save(self):
        with open(self.path, 'w') as f:
            yaml.dump(self.data, f, default_flow_style=False)
