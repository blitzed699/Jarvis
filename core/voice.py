import os
import tempfile
import subprocess
import re

class VoiceSynthesizer:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.model_path = os.path.expanduser("~/piper-voices/en_GB-alan-medium.onnx")

    def speak(self, text: str):
        if not self.enabled or not text:
            return

        clean = self._clean(text)
        if not clean:
            return

        if os.path.exists(self.model_path):
            self._speak_piper(clean)
        else:
            print("[VOICE] Model not found")
            self._fallback(clean)

    def _clean(self, text):
        text = re.sub(r'```[\s\S]*?```', '', text)
        text = re.sub(r'`[^`]*`', '', text)
        text = re.sub(r'https?://\S+', 'a link', text)
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
        text = re.sub(r'\*(.*?)\*', r'\1', text)
        return re.sub(r'\s+', ' ', text).strip()

    def _speak_piper(self, text):
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav = f.name

            cmd = [
                "piper",
                "--model", self.model_path,
                "--output_file", wav
            ]

            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True
            )
            proc.communicate(input=text)

            # Play audio
            played = False
            for player in ["aplay", "paplay", "ffplay -nodisp -autoexit", "play"]:
                try:
                    subprocess.run(
                        player.split() + [wav],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=True
                    )
                    played = True
                    break
                except:
                    continue

            if not played:
                print("[VOICE] No audio player found (tried aplay, paplay, ffplay)")

            os.remove(wav)

        except Exception as e:
            print("[VOICE ERROR]", e)
            self._fallback(text)

    def _fallback(self, text):
        try:
            subprocess.run(
                ["espeak", "-v", "en-gb", "-s", "140", text],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except:
            print("[VOICE]", text)
