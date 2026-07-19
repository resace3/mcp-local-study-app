import json

from local_study_app import process


def test_stale_state_is_cleaned(monkeypatch, tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"pid": 999999, "port": 65500}), encoding="utf-8")
    monkeypatch.setattr(process, "STATE", state_path)
    result = process.status()
    assert result["success"] and not result["data"]["running"]
    assert not state_path.exists()


def test_start_is_idempotent_when_health_is_ready(monkeypatch):
    monkeypatch.setattr(process, "_read_state", lambda: {"pid": 12, "port": 8080, "instance_token": "owned"})
    monkeypatch.setattr(process, "_alive", lambda pid: True)
    monkeypatch.setattr(process, "_health", lambda port, timeout=0.8: (True, {"status": "ok", "pid": 12, "instance_token": "owned"}))
    first = process.start()
    second = process.start()
    assert first["success"] and second["success"]
    assert first["data"]["url"] == second["data"]["url"]


def test_status_rejects_unowned_healthy_process(monkeypatch, tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"pid": 12, "port": 8080, "instance_token": "ours"}), encoding="utf-8")
    monkeypatch.setattr(process, "STATE", state_path)
    monkeypatch.setattr(process, "_alive", lambda pid: True)
    monkeypatch.setattr(process, "_health", lambda port, timeout=0.8: (True, {"status": "ok", "pid": 12, "instance_token": "theirs"}))
    result = process.status()
    assert result["success"] and not result["data"]["running"]
    assert not state_path.exists()


def test_stop_never_signals_unowned_process(monkeypatch, tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"pid": 12, "port": 8080, "instance_token": "ours"}), encoding="utf-8")
    monkeypatch.setattr(process, "STATE", state_path)
    monkeypatch.setattr(process, "_alive", lambda pid: True)
    monkeypatch.setattr(process, "_health", lambda port, timeout=0.8: (True, {"status": "ok", "pid": 44, "instance_token": "other"}))
    signaled = []
    monkeypatch.setattr(process.os, "kill", lambda *args: signaled.append(args))
    result = process.stop()
    assert result["success"] and not result["data"]["stopped"]
    assert signaled == []
