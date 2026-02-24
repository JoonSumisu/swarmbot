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


def _perform_backup_if_changed(state: dict) -> dict:
    os.makedirs(BACKUP_ROOT, exist_ok=True)
    last_config_hash = state.get("last_config_hash", "")
    last_boot_hash = state.get("last_boot_hash", "")
    config_hash = _hash_file(CONFIG_PATH)
    boot_hash = _hash_boot_dir()
    if not config_hash and not boot_hash:
        return state
    if config_hash == last_config_hash and boot_hash == last_boot_hash:
        return state
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
    return state


def _check_llm_health() -> str:
    try:
        from .config_manager import load_config

        cfg = load_config()
        # Use primary provider
        primary = cfg.providers[0] if cfg.providers else None
        base = primary.base_url if primary else None
        if not base:
            return "unknown"
        import urllib.request

        req = urllib.request.Request(base, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            code = resp.getcode()
        if 200 <= code < 500:
            return "healthy"
        return f"http_status_{code}"
    except Exception as e:
        return f"error:{e.__class__.__name__}"


def _check_channel_health(services: dict) -> dict:
    status: dict = {}
    try:
        from .config_manager import load_config

        cfg = load_config()
        gw_running = (
            "gateway" in services
            and services["gateway"].get("proc") is not None
            and services["gateway"]["proc"].poll() is None
        )
        feishu = cfg.channels.get("feishu")
        if not feishu or not feishu.enabled:
            status["feishu"] = "disabled"
        else:
            ok = bool(feishu.app_id and feishu.app_secret)
            if ok and gw_running:
                status["feishu"] = "healthy"
            elif ok:
                status["feishu"] = "gateway_not_running"
            else:
                status["feishu"] = "misconfigured"
    except Exception as e:
        status["error"] = f"{e.__class__.__name__}"
    return status


def _ensure_service(
    name: str,
    services: dict,
    enabled: bool,
    cmd: list,
    restart_delay: int,
) -> None:
    now = time.time()
    svc = services.get(name)
    if not enabled:
        if svc:
            proc = svc.get("proc")
            if proc is not None and proc.poll() is None:
                # Do not forcibly terminate here; shutdown logic will handle it.
                pass
        return
    if svc is None:
        svc = {"proc": None, "last_start": 0.0}
        services[name] = svc
    proc = svc.get("proc")
    if proc is not None and proc.poll() is None:
        return
    last_start = float(svc.get("last_start", 0.0))
    if now - last_start < max(restart_delay, 1):
        return
    try:
        os.makedirs(os.path.join(CONFIG_HOME, "logs"), exist_ok=True)
        log_path = os.path.join(CONFIG_HOME, "logs", f"daemon_{name}.log")
        with open(log_path, "a") as f:
            p = __import__("subprocess").Popen(
                cmd,
                stdout=f,
                stderr=__import__("subprocess").STDOUT,
                start_new_session=True,
            )
        svc["proc"] = p
        svc["last_start"] = now
    except Exception:
        svc["last_start"] = now


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
    state = _load_state()
    backup_interval = int(cfg.get("backup_interval_seconds", 60))
    if backup_interval <= 0:
        backup_interval = 60
    health_interval = int(cfg.get("health_check_interval_seconds", 3600))
    if health_interval <= 0:
        health_interval = 60
    manage_gateway = bool(cfg.get("manage_gateway", False))
    manage_overthinking = bool(cfg.get("manage_overthinking", False))
    services: dict = {}
    last_backup = 0.0
    last_health = 0.0
    while not _shutdown:
        now = time.time()
        try:
            _ensure_service(
                "gateway",
                services,
                manage_gateway,
                [sys.executable, "-m", "swarmbot.gateway_wrapper", "gateway"],
                int(cfg.get("gateway_restart_delay_seconds", 10)),
            )
            _ensure_service(
                "overthinking",
                services,
                manage_overthinking,
                [sys.executable, "-m", "swarmbot.cli", "overthinking", "start"],
                int(cfg.get("overthinking_restart_delay_seconds", 10)),
            )
            if now - last_backup >= backup_interval:
                state = _perform_backup_if_changed(state)
                last_backup = now
            if now - last_health >= health_interval:
                state["llm_health"] = _check_llm_health()
                state["channels"] = _check_channel_health(services)
                last_health = now
            state["services"] = {
                name: {
                    "pid": svc.get("proc").pid if svc.get("proc") is not None and svc.get("proc").poll() is None else None,
                    "last_start": svc.get("last_start", 0.0),
                }
                for name, svc in services.items()
            }
            _save_state(state)
        except Exception:
            pass
        for _ in range(5):
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
