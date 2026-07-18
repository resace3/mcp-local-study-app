"""Safe, project-scoped web process lifecycle management."""
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
import urllib.request

from .db import DB, LOGS, STATE

HOST = "127.0.0.1"


def _read_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_state(value):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(STATE)


def _alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        except (AttributeError, OSError):
            return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, SystemError):
        return False


def _health(port, timeout=0.8):
    try:
        with urllib.request.urlopen("http://%s:%d/api/health" % (HOST, port), timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
            return response.status == 200 and body.get("status") == "ok", body
    except Exception:
        return False, None


def _free_port(preferred=8080):
    for port in range(preferred, preferred + 25):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind((HOST, port))
                return port
            except OSError:
                healthy, _ = _health(port)
                if healthy:
                    return port
    raise RuntimeError("No free localhost port was found between %d and %d" % (preferred, preferred + 24))


def status():
    state = _read_state()
    pid = state.get("pid")
    port = int(state.get("port", 8080))
    healthy, health = _health(port)
    token = state.get("instance_token")
    owned = bool(
        healthy
        and token
        and health
        and health.get("instance_token") == token
        and health.get("pid") == pid
    )
    running = bool(owned and _alive(pid))
    if state and not running and STATE.exists():
        try:
            STATE.unlink()
        except OSError:
            pass
    return {"success": True, "data": {"running": running, "healthy": healthy, "url": "http://%s:%d" % (HOST, port), "host": HOST, "port": port, "pid": pid if running else None, "database_path": str(DB), "health": health}, "summary": "Study app is running" if running else "Study app is stopped", "error": None}


def start(wait_seconds=12):
    current = status()
    if current["data"]["running"]:
        current["summary"] = "Study app was already running"
        return current
    port = _free_port(8080)
    LOGS.mkdir(parents=True, exist_ok=True)
    log_path = LOGS / "server.log"
    if log_path.exists() and log_path.stat().st_size > 1024 * 1024:
        previous = LOGS / "server.previous.log"
        if previous.exists():
            previous.unlink()
        log_path.replace(previous)
    log_handle = open(str(log_path), "a", encoding="utf-8")
    env = dict(os.environ)
    instance_token = secrets.token_urlsafe(24)
    env["STUDY_PORT"] = str(port)
    env["STUDY_INSTANCE_TOKEN"] = instance_token
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen([sys.executable, "-m", "local_study_app.server"], stdin=subprocess.DEVNULL, stdout=log_handle, stderr=log_handle, env=env, creationflags=flags)
    log_handle.close()
    _write_state({"pid": process.pid, "port": port, "instance_token": instance_token, "command": [sys.executable, "-m", "local_study_app.server"], "started_at": time.time()})
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        healthy, health = _health(port)
        if healthy and health and health.get("instance_token") == instance_token and health.get("pid") == process.pid:
            return {"success": True, "data": {"running": True, "healthy": True, "url": "http://%s:%d" % (HOST, port), "port": port, "pid": process.pid, "database_path": str(DB), "health": health}, "summary": "Study app started", "error": None}
        if process.poll() is not None:
            break
        time.sleep(0.15)
    return {"success": False, "data": None, "summary": "Study app failed to start", "error": {"code": "start_failed", "message": "The health endpoint did not become ready", "details": {"log_path": str(log_path)}}}


def stop(wait_seconds=6):
    state = _read_state()
    pid = state.get("pid")
    port = int(state.get("port", 8080))
    token = state.get("instance_token")
    healthy, health = _health(port)
    owned = bool(healthy and token and health and health.get("instance_token") == token and health.get("pid") == pid)
    if not owned or not _alive(pid):
        if STATE.exists():
            STATE.unlink()
        return {"success": True, "data": {"stopped": False, "pid": None}, "summary": "Study app was already stopped", "error": None}
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        return {"success": False, "data": None, "summary": "Study app could not be stopped", "error": {"code": "stop_failed", "message": str(exc), "details": {"pid": pid}}}
    deadline = time.time() + wait_seconds
    stopped = False
    while time.time() < deadline:
        healthy, health = _health(port, timeout=0.2)
        still_owned = bool(healthy and health and health.get("instance_token") == token and health.get("pid") == pid)
        if not still_owned:
            stopped = True
            break
        time.sleep(0.1)
    if not stopped:
        return {"success": False, "data": None, "summary": "Study app did not stop cleanly", "error": {"code": "stop_timeout", "message": "The recorded project process is still running", "details": {"pid": pid}}}
    if STATE.exists():
        STATE.unlink()
    return {"success": True, "data": {"stopped": True, "pid": pid}, "summary": "Study app stopped", "error": None}
