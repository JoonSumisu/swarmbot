from __future__ import annotations

import argparse
import json
import subprocess
import sys

from .config_manager import (
    SwarmbotConfig,
    load_config,
    save_config,
    ensure_dirs,
    CONFIG_PATH,
    BOOT_CONFIG_PATH,
)
from .swarm.manager import SwarmManager
import shutil
import os


def load_nanobot_config() -> dict:
    config_path = os.path.expanduser("~/.nanobot/config.json")
    if not os.path.exists(config_path):
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading nanobot config: {e}", file=sys.stderr)
        return {}

def save_nanobot_config(config: dict) -> None:
    config_path = os.path.expanduser("~/.nanobot/config.json")
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving nanobot config: {e}", file=sys.stderr)


def cmd_channels(args: argparse.Namespace, extra_args: list[str]) -> None:
    # Handle local channel management instead of passthrough
    if not extra_args:
        cmd_channels_list()
        return

    action = extra_args[0]

    if action == "list":
        cmd_channels_list()
    elif action in ("add", "enable"):
        if len(extra_args) < 2:
            print("Usage: swarmbot channels add <name> [key=value ...]")
            return
        name = extra_args[1]
        params = extra_args[2:]
        cmd_channels_enable(name, params)
    elif action in ("remove", "disable"):
        if len(extra_args) < 2:
            print("Usage: swarmbot channels remove <name>")
            return
        name = extra_args[1]
        cmd_channels_disable(name)
    elif action == "config":
        if len(extra_args) < 2:
            print("Usage: swarmbot channels config <name> [key=value ...]")
            return
        name = extra_args[1]
        params_list = extra_args[2:]
        params = {}
        for arg in params_list:
            if "=" in arg:
                k, v = arg.split("=", 1)
                params[k] = v
        cmd_channels_config(name, params)
    else:
        # Fallback to passthrough for other commands like 'status', 'login'
        cmd_passthrough("channels", extra_args)

def cmd_channels_list() -> None:
    cfg = load_nanobot_config()
    channels = cfg.get("channels", {})
    print("Available Channels:")
    print(f"{'Name':<15} {'Status':<10} {'Config'}")
    print("-" * 50)
    for name, data in channels.items():
        status = "Enabled" if data.get("enabled") else "Disabled"
        print(f"{name:<15} {status:<10}")

def cmd_channels_enable(name: str, args: list[str]) -> None:
    cfg = load_nanobot_config()
    if "channels" not in cfg:
        cfg["channels"] = {}
    
    # Process args first
    params = {}
    for arg in args:
        if "=" in arg:
            k, v = arg.split("=", 1)
            params[k] = v

    # Interactive setup for Feishu
    if name == "feishu":
        required_keys = ["appId", "appSecret"]
        current_config = cfg.get("channels", {}).get(name, {})
        
        # Check missing keys (only if not provided in args and not in config)
        # But if user runs 'add feishu', they likely want to configure it even if exists?
        # Let's check if args are empty and config is empty-ish
        
        missing = [k for k in required_keys if k not in params and k not in current_config]
        
        # If explicitly requested via add, or missing keys, trigger interactive
        if missing or not params:
            print(f"Configuring Feishu channel...")
            for k in required_keys:
                if k not in params and k not in current_config:
                    val = input(f"Enter {k}: ").strip()
                    if val:
                        params[k] = val
            
            # Optional keys
            if "encryptKey" not in params and "encryptKey" not in current_config:
                val = input("Enter encryptKey (optional, press Enter to skip): ").strip()
                if val:
                    params["encryptKey"] = val
            if "verificationToken" not in params and "verificationToken" not in current_config:
                val = input("Enter verificationToken (optional, press Enter to skip): ").strip()
                if val:
                    params["verificationToken"] = val

    if name not in cfg["channels"]:
        print(f"Channel '{name}' not found in default config. Creating new entry...")
        cfg["channels"][name] = {"enabled": True, "allowFrom": []}
    
    cfg["channels"][name]["enabled"] = True
    cfg["channels"][name].update(params)
            
    save_nanobot_config(cfg)
    print(f"Channel '{name}' enabled and configured.")
    print(f"Configuration saved to: {os.path.expanduser('~/.nanobot/config.json')}")
    # Print current config for verification
    print(json.dumps({name: cfg["channels"][name]}, ensure_ascii=False, indent=2))

def cmd_channels_disable(name: str) -> None:
    cfg = load_nanobot_config()
    if "channels" in cfg and name in cfg["channels"]:
        cfg["channels"][name]["enabled"] = False
        save_nanobot_config(cfg)
        print(f"Channel '{name}' disabled.")
    else:
        print(f"Channel '{name}' is not enabled or does not exist.")

def cmd_channels_config(name: str, params: dict) -> None:
    cfg = load_nanobot_config()
    if "channels" not in cfg or name not in cfg["channels"]:
        print(f"Channel '{name}' not found. Please enable it first using 'add' or 'enable'.")
        return
        
    for k, v in params.items():
        cfg["channels"][name][k] = v
        
    save_nanobot_config(cfg)
    print(f"Channel '{name}' configuration updated.")


def cmd_onboard() -> None:
    ensure_dirs()
    cfg = load_config()
    save_config(cfg)
    
    # Init Boot Config: Copy default boot files to ~/.swarmbot/boot/ if not exist
    pkg_boot_dir = os.path.join(os.path.dirname(__file__), "boot")
    if os.path.exists(pkg_boot_dir):
        print(f"Initializing boot configuration in {BOOT_CONFIG_PATH}...")
        for filename in os.listdir(pkg_boot_dir):
            if filename.endswith(".md"):
                src = os.path.join(pkg_boot_dir, filename)
                dst = os.path.join(BOOT_CONFIG_PATH, filename)
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)
                    print(f"  Created {filename}")
                else:
                    print(f"  Skipped {filename} (already exists)")
    
    try:
        # Check if nanobot config exists to decide on overwrite
        nanobot_config = os.path.expanduser("~/.nanobot/config.json")
        if os.path.exists(nanobot_config):
             print(f"Nanobot config already exists at {nanobot_config}, skipping interactive onboard.")
             # We can run 'nanobot onboard --no-interactive' if supported, or just skip.
             # Nanobot onboard is interactive by default. 
             # Best to skip if config exists to avoid blocking.
             pass
        else:
             subprocess.run(["nanobot", "onboard"], check=False)
    except FileNotFoundError:
        pass
    print(f"Swarmbot 已完成初始化，配置文件位于: {CONFIG_PATH}")
    print(f"个性化 Boot 配置位于: {BOOT_CONFIG_PATH}")


def cmd_run() -> None:
    cfg = load_config()
    swarm = SwarmManager.from_swarmbot_config(cfg)
    print("Swarmbot run 模式已启动，Ctrl+C 退出。")
    turn = 0
    while True:
        if cfg.swarm.max_turns and turn >= cfg.swarm.max_turns:
            break
        try:
            user_input = input("\n你: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_input:
            continue
        reply = swarm.chat(user_input)
        print(f"\nSwarmbot:\n{reply}")
        turn += 1


import socket
import os

def check_port(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) != 0

def get_available_port(start_port: int, step: int = 20, max_tries: int = 5) -> int:
    current_port = start_port
    for _ in range(max_tries):
        if check_port(current_port):
            return current_port
        print(f"Port {current_port} is busy, trying {current_port + step}...")
        current_port += step
    raise RuntimeError(f"Could not find available port starting from {start_port}")

def cmd_gateway() -> None:
    # 检查端口冲突并自动递增
    # Default nanobot gateway port is 18990
    try:
        # Load config to inject environment variables for nanobot
        cfg = load_config()
        env = os.environ.copy()
        
        # Inject API credentials if custom/openai provider is set
        if cfg.provider.api_key and cfg.provider.base_url:
            env["OPENAI_API_BASE"] = cfg.provider.base_url
            env["OPENAI_API_KEY"] = cfg.provider.api_key
            # We don't override LITELLM_MODEL here as nanobot config handles it,
            # but ensuring base/key env vars usually fixes "Connection error" for openai-compatible providers.

        port = get_available_port(18990)
        env["OPENCLAW_GATEWAY_PORT"] = str(port)
        
        # SIMPLER STRATEGY for this task:
        # We create a 'gateway_wrapper.py' that imports nanobot and injects our SwarmManager logic.
        # Then we run `python gateway_wrapper.py` instead of `nanobot gateway`.
        
        wrapper_path = os.path.join(os.path.dirname(__file__), "gateway_wrapper.py")
        
        log_dir = os.path.expanduser("~/.swarmbot/logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "gateway.log")
        
        print(f"Starting Swarmbot Gateway on port {port} (background mode)...")
        print(f"Logs will be written to: {log_file}")
        
        with open(log_file, "a") as f:
            # Use subprocess.Popen for non-blocking execution (background)
            subprocess.Popen(
                [sys.executable, wrapper_path], 
                env=env, 
                stdout=f, 
                stderr=subprocess.STDOUT,
                start_new_session=True # Detach from terminal
            )
        print("Gateway started successfully.")
        
    except FileNotFoundError:
        print("未找到 nanobot 命令，请先安装 nanobot-ai。", file=sys.stderr)
    except Exception as e:
        print(f"Gateway failed: {e}", file=sys.stderr)

def cmd_heartbeat() -> None:
    # 透传 nanobot heartbeat 命令
    try:
        subprocess.run(["nanobot", "heartbeat"], check=True)
    except FileNotFoundError:
        print("未找到 nanobot 命令，请先安装 nanobot-ai。", file=sys.stderr)

def cmd_tool() -> None:
    # 透传 nanobot tool 命令（可能需要传参，这里简单实现为透传所有后续参数）
    # 注意：argparse 会截断参数，若需完整透传，需要 sys.argv 处理，这里简化为调用默认 tool list 或类似
    try:
        # 简单调用 nanobot tool list 作为示例，实际可能需要更复杂的参数透传机制
        # 如果用户输入 swarmbot tool list，这里 args.command 只是 "tool"
        # 更好的做法是在 main 中使用 parse_known_args
        subprocess.run(["nanobot", "tool", "list"], check=True)
    except FileNotFoundError:
        print("未找到 nanobot 命令，请先安装 nanobot-ai。", file=sys.stderr)

from .loops.overthinking import OverthinkingLoop
import threading

def cmd_overthinking(args: argparse.Namespace) -> None:
    cfg = load_config()
    if args.action == "setup":
        if args.enabled is not None:
            cfg.overthinking.enabled = args.enabled
        if args.interval is not None:
            cfg.overthinking.interval_minutes = args.interval
        if args.steps is not None:
            cfg.overthinking.max_steps = args.steps
        save_config(cfg)
        print("Overthinking 配置已更新。")
        print(json.dumps(cfg.overthinking.__dict__, ensure_ascii=False, indent=2))
    elif args.action == "start":
        print("Starting Overthinking Loop in background...")
        # Note: This starts a loop in the foreground for CLI usage, 
        # or implies daemon start. For CLI simple run, we just start it.
        stop_event = threading.Event()
        loop = OverthinkingLoop(stop_event)
        loop.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            stop_event.set()
            print("Stopping overthinking loop...")

def cmd_status() -> None:
    cfg = load_config()
    print("Swarmbot 状态:")
    print()
    print("Provider:")
    print(json.dumps({"provider": cfg.provider.__dict__}, ensure_ascii=False, indent=2))
    print()
    print("Swarm:")
    print(json.dumps({"swarm": cfg.swarm.__dict__}, ensure_ascii=False, indent=2))
    print()
    print("Overthinking:")
    print(json.dumps({"overthinking": cfg.overthinking.__dict__}, ensure_ascii=False, indent=2))



def cmd_provider_add(args: argparse.Namespace) -> None:
    cfg = load_config()
    cfg.provider.name = "custom"
    cfg.provider.base_url = args.base_url
    cfg.provider.api_key = args.api_key
    cfg.provider.model = args.model
    cfg.provider.max_tokens = args.max_tokens
    save_config(cfg)
    print("已更新模型提供方配置（仅允许当前这个 provider 生效）。")


def cmd_provider_delete() -> None:
    cfg = load_config()
    cfg.provider = cfg.provider.__class__()  # reset to defaults
    save_config(cfg)
    print("已重置模型提供方配置为默认值。")


def cmd_config(args: argparse.Namespace) -> None:
    cfg = load_config()
    updated = False
    if args.agent_count is not None:
        cfg.swarm.agent_count = args.agent_count
        updated = True
    if args.architecture is not None:
        cfg.swarm.architecture = args.architecture
        updated = True
    if args.max_turns is not None:
        cfg.swarm.max_turns = args.max_turns
        updated = True
    if args.auto_builder is not None:
        cfg.swarm.auto_builder = args.auto_builder
        updated = True
    if updated:
        save_config(cfg)
        print("已更新 Swarm 配置。")
    print()
    print("当前 Swarm 配置:")
    print(json.dumps(cfg.swarm.__dict__, ensure_ascii=False, indent=2))


def cmd_update() -> None:
    """
    Update Swarmbot core code from git repository while preserving user configuration.
    """
    print("Updating Swarmbot...")
    
    # Get the directory where the package is installed
    package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # 1. Check if git is available and inside a git repo
    try:
        # Check if the installed directory is a git repo
        if not os.path.exists(os.path.join(package_dir, ".git")):
             print(f"Error: Installation directory '{package_dir}' is not a git repository.", file=sys.stderr)
             print("If you installed via pip/pipx directly, please update using: pip install --upgrade swarmbot", file=sys.stderr)
             return

        subprocess.run(["git", "status"], cwd=package_dir, check=True, capture_output=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("Error: Git command failed or not installed.", file=sys.stderr)
        return

    # 2. Pull latest changes
    try:
        print(f"Pulling latest changes from remote in {package_dir}...")
        subprocess.run(["git", "pull"], cwd=package_dir, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error pulling changes: {e}", file=sys.stderr)
        return

    # 3. Re-install dependencies (optional but recommended)
    try:
        print("Updating dependencies...")
        subprocess.run([sys.executable, "-m", "pip", "install", "."], cwd=package_dir, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error updating dependencies: {e}", file=sys.stderr)
        # Check for common PEP 668 error
        if "externally-managed-environment" in str(e) or e.returncode == 1:
             print("\nHint: It seems you are running in an externally managed environment (PEP 668).", file=sys.stderr)
             print("If you are not using a virtual environment, please try running the update script instead:", file=sys.stderr)
             print(f"  {os.path.join(package_dir, 'scripts', 'install_deps.sh')}", file=sys.stderr)
        return

    print("Update complete!")
    print(f"User configuration preserved at: {CONFIG_PATH}")
    print(f"User boot files preserved at: {BOOT_CONFIG_PATH}")


def cmd_passthrough(command: str, extra_args: list[str]) -> None:
    """Helper to passthrough commands to nanobot."""
    cmd = ["nanobot", command] + extra_args
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError:
        print("未找到 nanobot 命令，请先安装 nanobot-ai。", file=sys.stderr)
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)


def main() -> None:
    # Use parse_known_args so we can grab extra args for passthrough commands
    parser = argparse.ArgumentParser(description="Swarmbot CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("onboard", help="初始化配置和工作区，并尝试调用 nanobot onboard")

    subparsers.add_parser("run", help="与 Swarmbot 进行连续对话（本地调试）")

    # Gateway passthrough
    subparsers.add_parser("gateway", help="启动 nanobot 的 gateway（透传功能）")
    
    # Heartbeat passthrough
    subparsers.add_parser("heartbeat", help="启动 nanobot 的 heartbeat（透传功能）")

    # Tool passthrough
    # We use parse_known_args in main to handle subcommands for tool/channels/cron
    subparsers.add_parser("tool", help="管理 nanobot 的 tool channel（透传功能）")
    
    # Channels passthrough (New)
    subparsers.add_parser("channels", help="管理 nanobot 的 channels（透传功能）")
    
    # Cron passthrough (New)
    subparsers.add_parser("cron", help="管理 nanobot 的 scheduled tasks（透传功能）")
    
    # Agent passthrough (New - direct single agent chat)
    subparsers.add_parser("agent", help="直接与 nanobot agent 对话（透传功能）")

    subparsers.add_parser("status", help="查看当前 Swarmbot 状态")

    provider_parser = subparsers.add_parser("provider", help="管理模型提供方")
    provider_sub = provider_parser.add_subparsers(dest="action", required=True)
    provider_add = provider_sub.add_parser("add", help="新增/覆盖一个模型提供方（仅保留一个）")
    provider_add.add_argument("--base-url", required=True, help="OpenAI 兼容接口 base url")
    provider_add.add_argument("--api-key", required=True, help="API key")
    provider_add.add_argument("--model", required=True, help="模型名称")
    provider_add.add_argument(
        "--max-tokens",
        type=int,
        default=4096,
        help="最大生成 token 数",
    )
    provider_sub.add_parser("delete", help="删除当前 provider 配置，恢复默认")

    config_parser = subparsers.add_parser("config", help="配置和查看 Swarm 工作模式")
    config_parser.add_argument("--agent-count", type=int, help="Swarm 中的 agent 数量")
    config_parser.add_argument(
        "--architecture",
        type=str,
        choices=[
            "auto",
            "sequential",
            "concurrent",
            "agent_rearrange",
            "graph",
            "mixture",
            "group_chat",
            "forest",
            "hierarchical",
            "heavy",
            "swarm_router",
            "long_horizon",
            "state_machine",
        ],
        help="架构类型，对应 swarms Multi-Agent Architectures（默认 auto = AutoSwarmBuilder）",
    )
    config_parser.add_argument("--max-turns", type=int, help="对话最大轮数（0 为不限制）")
    config_parser.add_argument(
        "--auto-builder",
        type=lambda x: x.lower() in ("1", "true", "yes", "on"),
        help="是否启用 AutoSwarmBuilder",
    )

    subparsers.add_parser("skill", help="查看当前可用的技能（透传到 nanobot skill list）")

    overthink_parser = subparsers.add_parser("overthinking", help="管理 Overthinking 后台思考循环")
    overthink_sub = overthink_parser.add_subparsers(dest="action", required=True)
    overthink_setup = overthink_sub.add_parser("setup", help="配置 Overthinking 参数")
    overthink_setup.add_argument("--enabled", type=lambda x: x.lower() in ("true", "1", "yes"), help="是否开启 (true/false)")
    overthink_setup.add_argument("--interval", type=int, help="工作周期（分钟）")
    overthink_setup.add_argument("--steps", type=int, help="自主探索步数 (0 为关闭)")
    overthink_sub.add_parser("start", help="手动启动 Overthinking 循环（前台运行）")

    subparsers.add_parser("update", help="更新 Swarmbot 核心代码（保留配置）")

    args, _ = parser.parse_known_args()

    if args.command == "onboard":
        cmd_onboard()
    elif args.command == "update":
        cmd_update()
    elif args.command == "run":
        cmd_run()
    elif args.command == "gateway":
        cmd_gateway()
    elif args.command == "heartbeat":
        cmd_heartbeat()
    elif args.command == "tool":
        # Pass all extra args
        cmd_passthrough("tool", sys.argv[2:])
    elif args.command == "channels":
        cmd_channels(args, sys.argv[2:])
    elif args.command == "cron":
        cmd_passthrough("cron", sys.argv[2:])
    elif args.command == "agent":
        cmd_passthrough("agent", sys.argv[2:])
    elif args.command == "status":
        cmd_status()
    elif args.command == "provider":
        if args.action == "add":
            cmd_provider_add(args)
        elif args.action == "delete":
            cmd_provider_delete()
    elif args.command == "config":
        cmd_config(args)
    elif args.command == "skill":
        cmd_passthrough("skill", sys.argv[2:])
    elif args.command == "overthinking":
        cmd_overthinking(args)
