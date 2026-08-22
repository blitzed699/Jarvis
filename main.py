import argparse
import threading
from core.jarvis import JARVISCore


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JARVIS v0.4 — Cognitive AI Partner")
    parser.add_argument("--dashboard", action="store_true", help="Launch the web dashboard")
    parser.add_argument("--port", type=int, default=8080, help="Dashboard port (default: 8080)")
    args = parser.parse_args()

    jarvis = JARVISCore()

    if args.dashboard:
        try:
            from dashboard.server import set_jarvis_core, start_server
            set_jarvis_core(jarvis)
            t = threading.Thread(target=start_server, kwargs={"port": args.port}, daemon=True)
            t.start()
            print(f"[JARVIS] Dashboard running at http://localhost:{args.port}")
        except ImportError as e:
            print(f"[JARVIS] Dashboard failed to start: {e}")
            print("[JARVIS] Run: pip install fastapi uvicorn")

    jarvis.chat_loop()
