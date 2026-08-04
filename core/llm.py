import requests
import json
from typing import Iterator, Optional


class OllamaClient:
    """Simple client for local Ollama API."""
    
    def __init__(self, model: str = "llama3.1", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.generate_url = f"{self.base_url}/api/generate"
    
    def generate(self, prompt: str, system: Optional[str] = None, 
                 temperature: float = 0.7, max_tokens: int = 2000) -> str:
        """Send a prompt to Ollama and return the response text."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            }
        }
        if system:
            payload["system"] = system
        
        try:
            response = requests.post(self.generate_url, json=payload, timeout=120)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "").strip()
        except requests.exceptions.ConnectionError:
            return "[ERROR] Cannot connect to Ollama. Is it running? (ollama serve)"
        except Exception as e:
            return f"[ERROR] {str(e)}"
    
    def generate_stream(self, prompt: str, system: Optional[str] = None,
                        temperature: float = 0.7) -> Iterator[str]:
        """Stream response tokens from Ollama."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "options": {"temperature": temperature}
        }
        if system:
            payload["system"] = system
        
        try:
            response = requests.post(self.generate_url, json=payload, stream=True, timeout=120)
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    data = json.loads(line)
                    token = data.get("response", "")
                    if token:
                        yield token
        except Exception as e:
            yield f"[ERROR] {str(e)}"
