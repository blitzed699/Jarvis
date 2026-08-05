import os
import base64
import subprocess
from typing import Dict, Any
from .base import BaseTool


class VisionTool(BaseTool):
    name = "vision"
    description = "Capture and analyze the screen or an image. Params: mode (str 'screen' or 'file'), path (str, optional), query (str, default 'Describe what you see.')"

    def __init__(self):
        self.vision_model = "llava"

    def run(self, mode: str = "screen", path: str = "", query: str = "Describe what you see.") -> Dict[str, Any]:
        try:
            if mode == "screen":
                img_path = self._capture_screen()
            else:
                img_path = path

            if not img_path or not os.path.exists(img_path):
                return {"success": False, "result": "Could not capture or find image."}

            analysis = self._analyze_image(img_path, query)

            if mode == "screen" and img_path.startswith("/tmp/"):
                os.unlink(img_path)

            return {"success": True, "result": analysis}
        except Exception as e:
            return {"success": False, "result": str(e)}

    def _capture_screen(self) -> str:
        tmp = f"/tmp/jarvis_vision_{os.urandom(4).hex()}.png"
        try:
            subprocess.run(["gnome-screenshot", "-f", tmp], check=True, timeout=10)
            return tmp
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass
        try:
            subprocess.run(["scrot", tmp], check=True, timeout=10)
            return tmp
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            img.save(tmp)
            return tmp
        except ImportError:
            raise RuntimeError("No screenshot tool found. Install gnome-screenshot, scrot, or Pillow.")

    def _analyze_image(self, img_path: str, prompt: str) -> str:
        import requests
        with open(img_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        payload = {
            "model": self.vision_model,
            "prompt": prompt,
            "images": [b64],
            "stream": False
        }
        try:
            resp = requests.post("http://localhost:11434/api/generate", json=payload, timeout=60)
            resp.raise_for_status()
            return resp.json().get("response", "").strip()
        except requests.exceptions.ConnectionError:
            return "[ERROR] Ollama not running. Pull a vision model: ollama pull llava"
        except Exception as e:
            return f"[ERROR] Vision analysis failed: {str(e)}"
