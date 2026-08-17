"""JARVIS Dashboard Server — lightweight FastAPI wrapper around your existing core."""

import json
import asyncio
from pathlib import Path
from datetime import datetime
from contextlib import asynccontextmanager

try:
    from fastapi import FastAPI, WebSocket, Request
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse, JSONResponse
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

# Path to this file's directory
DASH_DIR = Path(__file__).parent

# Global reference to JARVIS core instance (injected from main.py)
_jarvis_core = None


def set_jarvis_core(core_instance):
    """Called from main.py before server starts."""
    global _jarvis_core
    _jarvis_core = core_instance


def _safe_get(attr_path, default=None):
    """Safely drill into _jarvis_core without crashing if module isn't loaded."""
    if _jarvis_core is None:
        return default
    obj = _jarvis_core
    for part in attr_path.split("."):
        obj = getattr(obj, part, None)
        if obj is None:
            return default
    return obj


# ── Lifespan: broadcast loop ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_broadcast_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="JARVIS Dashboard", version="0.3.2", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=DASH_DIR), name="static")


@app.get("/")
async def serve_dashboard():
    return FileResponse(DASH_DIR / "index.html")


# ── REST API: live data from your core ────────────────────────────────────

@app.get("/api/system")
async def system_stats():
    """Pull from your actual system if available, else mock."""
    # TODO: wire into a real system monitor tool
    import random, psutil
    mem = psutil.virtual_memory()
    return {
        "cpu": psutil.cpu_percent(interval=0.1),
        "gpu": random.randint(30, 60),          # TODO: nvidia-ml-py or gpustat
        "gpu_name": "NVIDIA RTX 4080",
        "ram_used": round(mem.used / 1e9, 1),
        "ram_total": round(mem.total / 1e9, 1),
        "storage_used": 1.2,                    # TODO: psutil.disk_usage
        "storage_total": 2.0,
        "network": 1.3,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/agents")
async def active_agents():
    reg = _safe_get("agent_registry")
    if reg and hasattr(reg, "agents"):
        agents = []
        for name, agent in reg.agents.items():
            agents.append({
                "name": name.upper(),
                "role": getattr(agent, "description", getattr(agent, "role", "Agent")),
                "status": "ONLINE"
            })
        return {"agents": agents}
    # Fallback to hardcoded until wired
    return {"agents": [
        {"name": "SENTINEL", "role": "System Monitor", "status": "ONLINE"},
        {"name": "ARCHER",   "role": "Web & Research", "status": "ONLINE"},
        {"name": "CODEX",    "role": "Code Assistant", "status": "ONLINE"},
        {"name": "PLANNER",  "role": "Task Planner",   "status": "ONLINE"},
        {"name": "CRITIC",   "role": "Review & QA",    "status": "ONLINE"},
        {"name": "MEMORY",   "role": "Recall Engine",  "status": "ONLINE"},
    ]}


@app.get("/api/memory")
async def memory_core():
    mem = _safe_get("memory")
    if mem:
        count = getattr(mem, "count", lambda: 0)()
        last = getattr(mem, "get_last_recall", lambda: None)()
        return {
            "stored": count,
            "last_recall": last.get("content", "Pet grooming project") if last else "—",
            "last_recall_time": "2 min ago"
        }
    return {"stored": 12482, "last_recall": "Pet grooming project", "last_recall_time": "2 min ago"}


@app.get("/api/project")
async def active_project():
    proj = _safe_get("project_manager.active_project")
    if proj:
        return {
            "name": proj.get("name", "PET GROOMING APP"),
            "version": proj.get("version", "v0.3.2"),
            "status": proj.get("status", "DEVELOPMENT"),
            "progress": proj.get("progress", 68),
            "last_updated": proj.get("last_updated", "2 min ago")
        }
    return {
        "name": "PET GROOMING APP",
        "version": "v0.3.2",
        "status": "DEVELOPMENT",
        "progress": 68,
        "last_updated": "2 min ago"
    }


@app.get("/api/events")
async def upcoming_events():
    # TODO: wire into a calendar/goal module
    return {"events": [
        {"date": "15 AUG", "time": "10:00", "title": "Doctor Appointment"},
        {"date": "16 AUG", "time": "14:00", "title": "Grocery Shopping"},
        {"date": "17 AUG", "time": "12:00", "title": "Jacob's Kindergarten"},
        {"date": "17 AUG", "time": "18:00", "title": "Dinner with Taryn"},
    ]}


@app.post("/api/chat")
async def chat(request: Request):
    payload = await request.json()
    user_msg = payload.get("message", "")
    if _jarvis_core and hasattr(_jarvis_core, "process"):
        response = _jarvis_core.process(user_msg)
        return {"response": response, "agent_used": "PLANNER", "processing_time_ms": 0}
    return {"response": f"Echo: {user_msg}", "agent_used": "NONE", "processing_time_ms": 0}


# ── WebSocket: real-time flare control ────────────────────────────────────

_connected_ws = set()


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _connected_ws.add(ws)
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "think":
                # Broadcast flare burst to ALL connected dashboards
                await _broadcast({"type": "flare_burst", "intensity": "high"})
                # TODO: actually run inference via _jarvis_core.process()
                await asyncio.sleep(1.5)
                await _broadcast({"type": "flare_state", "state": "normal"})
            elif msg.get("type") == "ping":
                await ws.send_json({"type": "pong", "time": datetime.now().isoformat()})
    except Exception:
        pass
    finally:
        _connected_ws.discard(ws)


async def _broadcast(msg: dict):
    dead = set()
    for ws in _connected_ws:
        try:
            await ws.send_json(msg)
        except Exception:
            dead.add(ws)
    for ws in dead:
        _connected_ws.discard(ws)


async def _broadcast_loop():
    """Optional: push live system stats every 2s to all dashboards."""
    while True:
        await asyncio.sleep(2)
        if _connected_ws:
            await _broadcast({"type": "heartbeat", "time": datetime.now().isoformat()})


# ── Launcher ──────────────────────────────────────────────────────────────

def start_server(host="0.0.0.0", port=8080):
    if not HAS_FASTAPI:
        print("[DASHBOARD] fastapi / uvicorn not installed. Run: pip install fastapi uvicorn psutil")
        return
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    start_server()
