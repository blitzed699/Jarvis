import os
import tempfile
import subprocess
from typing import Optional


class VoiceSynthesizer:
    """JARVIS voice output. Deep, calm, composed."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.engine = None
        self._init_engine()

    def _init_engine(self):
        if not self.enabled:
            return
        try:
            import pyttsx3
            self.engine = pyttsx3.init()
            # JARVIS voice profile: slower, deeper
            self.engine.setProperty('rate', 150)  # Default ~200
            self.engine.setProperty('volume', 0.9)
        except ImportError:
            self.engine = None

    def speak(self, text: str):
        """Speak text aloud."""
        if not self.enabled:
            return
        
        # Strip markdown and JSON for cleaner speech
        clean = self._clean_text(text)
        
        if self.engine:
            self.engine.say(clean)
            self.engine.runAndWait()
        else:
            # Fallback: use espeak or print
            self._fallback_speak(clean)

    def _clean_text(self, text: str) -> str:
        """Remove code blocks, JSON, markdown for voice."""
        import re
        # Remove code blocks
        text = re.sub(r'```[\s\S]*?```', '', text)
        # Remove inline code
        text = re.sub(r'`[^`]*`', '', text)
        # Remove URLs
        text = re.sub(r'https?://\S+', 'link', text)
        # Remove JSON objects
        text = re.sub(r'\{[^{}]*\}', '', text)
        return text.strip()

    def _fallback_speak(self, text: str):
        """Use system TTS if pyttsx3 unavailable."""
        try:
            # Try espeak (Linux)
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(text)
                tmp = f.name
            subprocess.run(['espeak', '-s', '150', '-v', 'en-us', '-f', tmp], 
                        capture_output=True, timeout=30)
            os.unlink(tmp)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # Last resort: just print
            print(f"[VOICE] {text}")

    def save_to_file(self, text: str, path: str):
        """Save speech to audio file."""
        if not self.engine:
            return False
        try:
            self.engine.save_to_file(text, path)
            self.engine.runAndWait()
            return True
        except Exception:
            return False
