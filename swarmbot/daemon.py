import os
import sys
import time
import json
import shutil
import hashlib
import signal

from .config_manager import CONFIG_HOME, CONFIG_PATH, BOOT_CONFIG_PATH


PID_FILE = os.path.join(CONFIG_HOME, "daemon.pid")
STATE_FILE = os.path.join(CONFIG_HOME, "daemon_state.json")
BACKUP_ROOT = os.path.join(CONFIG_HOME, "backups")


def _load_daemon_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    return data.get("daemon", {})


def _load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    os.makedirs(CONFIG_HOME, exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)


def _hash_file(path: str) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
    except Exception:
        return ""
    return h.hexdigest()


def _hash_boot_dir() -> str:
    if not os.path.isdir(BOOT_CONFIG_PATH):
        return ""
    h = hashlib.sha256()
    try:
        for root, _, files in os.walk(BOOT_CONFIG_PATH):
            for name in sorted(files):
                if not name.endswith(".md"):
                    continue
                full = os.path.join(root, name)
                rel = os.path.relpath(full, BOOT_CONFIG_PATH)
                h.update(rel.encode("utf-8", errors="ignore"))
                try:
                    with open(full, "rb") as f:
                        for chunk in iter(lambda: f.read(8192), b""):
                            h.update(chunk)
                except Exception:
                    continue
    except Exception:
        return ""
    return h.hexdigest()


def _copy_tree(src: str, dst: str) -> None:
    if not os.path.exists(src):
        return
    if os.path.exists(dst):
        shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst)


def _perform_backup_if_changed(config_interval: int) -> None:
    os.makedirs(BACKUP_ROOT, exist_ok=True)
    state = _load_state()
    last_config_hash = state.get("last_config_hash", "")
    last_boot_hash = state.get("last_boot_hash", "")
    config_hash = _hash_file(CONFIG_PATH)
    boot_hash = _hash_boot_dir()
    if not config_hash and not boot_hash:
        return
    if config_hash == last_config_hash and boot_hash == last_boot_hash:
        return
    ts = time.strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(BACKUP_ROOT, f"backup_{ts}")
    os.makedirs(backup_dir, exist_ok=True)
    if os.path.exists(CONFIG_PATH):
        shutil.copy2(CONFIG_PATH, os.path.join(backup_dir, "config.json"))
    if os.path.isdir(BOOT_CONFIG_PATH):
        _copy_tree(BOOT_CONFIG_PATH, os.path.join(backup_dir, "boot"))
    cfg = _load_daemon_config()
    remote_path = cfg.get("backup_remote_path") or ""
    if remote_path:
        try:
            remote_root = os.path.join(remote_path, "swarmbot_backups")
            os.makedirs(remote_root, exist_ok=True)
            remote_dir = os.path.join(remote_root, f"backup_{ts}")
            _copy_tree(backup_dir, remote_dir)
        except Exception:
            pass
    state["last_config_hash"] = config_hash
    state["last_boot_hash"] = boot_hash
    state["last_backup_ts"] = ts
    _save_state(state)


_shutdown = False


def _signal_handler(signum, frame) -> None:
    global _shutdown
    _shutdown = True


def main() -> None:
    os.makedirs(CONFIG_HOME, exist_ok=True)
    try:
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    cfg = _load_daemon_config()
    interval = int(cfg.get("backup_interval_seconds", 60))
    if interval <= 0:
        interval = 60
    while not _shutdown:
        try:
            _perform_backup_if_changed(interval)
        except Exception:
            pass
        for _ in range(interval):
            if _shutdown:
                break
            time.sleep(1)
    try:
        if os.path.exists(PID_FILE):
            with open(PID_FILE, "r", encoding="utf-8") as f:
                pid = int(f.read().strip() or "0")
            if pid == os.getpid():
                os.remove(PID_FILE)
    except Exception:
        pass


if __name__ == "__main__":
    main()

