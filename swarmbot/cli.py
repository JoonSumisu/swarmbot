from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import os

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


def load_nanobot_config() -> dict:
    cfg = load_config()
    channels_dict = {}
    for name, c_cfg in cfg.channels.items():
        channels_dict[name] = c_cfg.config.copy()
        channels_dict[name]["enabled"] = c_cfg.enabled
    return {"channels": channels_dict}

def save_nanobot_config(config: dict) -> None:
    cfg = load_config()
    
    if "channels" in config:
        for name, c_data in config["channels"].items():
            # Update or create
            enabled = c_data.get("enabled", False)
            conf = {k:v for k,v in c_data.items() if k != "enabled"}
            
            # Update existing or create new
            if name in cfg.channels:
                cfg.channels[name].enabled = enabled
                cfg.channels[name].config.update(conf)
            else:
                from .config_manager import ChannelConfig
                cfg.channels[name] = ChannelConfig(enabled=enabled, config=conf)
    
    save_config(cfg)


def cmd_channels(args: argparse.Namespace, extra_args: list[str]) -> None:
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
        print(f"Unsupported channels action: {action}")

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
    # Show Swarmbot config path now
    print(f"Configuration saved to: {CONFIG_PATH}")
    # Also mirrored to ~/.nanobot/config.json for compatibility
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
    """
    Run the Gateway in native mode.
    This replaces the legacy nanobot CLI wrapper with a direct Python implementation.
    """
    try:
        from swarmbot.gateway.server import run_gateway
        run_gateway()
    except Exception as e:
        print(f"Gateway crashed: {e}")
        import traceback
        traceback.print_exc()

def cmd_heartbeat(args: argparse.Namespace) -> None:
    from .config_manager import WORKSPACE_PATH
    from pathlib import Path

    hb_path = Path(WORKSPACE_PATH) / "HEARTBEAT.md"

    if args.action == "status":
        if not hb_path.exists():
            print("HEARTBEAT.md 不存在。")
            return
        content = hb_path.read_text(encoding="utf-8")
        stripped = "".join(line for line in content.splitlines() if not line.strip().startswith(">")).strip()
        if not stripped:
            print("HEARTBEAT.md 存在但当前没有待办任务。")
        else:
            print("HEARTBEAT.md 存在且包含待办任务。")
    elif args.action == "trigger":
        if not hb_path.exists():
            print("HEARTBEAT.md 不存在，无法触发。")
            return
        print("当前 Heartbeat 任务清单如下（需手动执行）：")
        print(hb_path.read_text(encoding="utf-8"))

def cmd_tool() -> None:
    print("工具管理 CLI 已简化，请在对话中通过 LLM 工具调用使用工具。")

from .loops.overthinking import OverthinkingLoop
import threading


def cmd_cron(args: argparse.Namespace) -> None:
    print("Cron 管理功能当前已禁用（nanobot 依赖已移除）。")

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
    print("Providers:")
    print(json.dumps([p.__dict__ for p in cfg.providers], ensure_ascii=False, indent=2))
    print()
    print("Swarm:")
    print(json.dumps({"swarm": cfg.swarm.__dict__}, ensure_ascii=False, indent=2))
    print()
    print("Overthinking:")
    print(json.dumps({"overthinking": cfg.overthinking.__dict__}, ensure_ascii=False, indent=2))



def cmd_provider_add(args: argparse.Namespace) -> None:
    cfg = load_config()
    from .config_manager import ProviderConfig
    new_provider = ProviderConfig(
        name="primary",
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
        max_tokens=args.max_tokens,
    )
    # Overwrite all providers to avoid conflict as per user instruction
    cfg.providers = [new_provider]
    save_config(cfg)
    print("已更新模型提供方配置（作为唯一 primary provider 生效）。")


def cmd_provider_delete() -> None:
    cfg = load_config()
    cfg.providers = []  # Clear all providers
    save_config(cfg)
    print("已重置模型提供方配置（清空所有 provider）。")


def cmd_config(args: argparse.Namespace) -> None:
    cfg = load_config()
    updated = False
    if args.max_agents is not None:
        cfg.swarm.max_agents = args.max_agents
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
    Update Swarmbot core code.
    """
    print("自动更新功能目前已禁用。")
    print("请手动进入 Swarmbot 源码目录进行更新：")
    print("")
    print("  cd /path/to/swarmbot")
    print("  git pull")
    print("  ./scripts/install_deps.sh")
    print("")
    print("如果您是通过 pip 安装的，请使用 pip install --upgrade swarmbot")


def cmd_daemon(args: argparse.Namespace) -> None:
    from .config_manager import CONFIG_HOME
    pid_file = os.path.join(CONFIG_HOME, "daemon.pid")
    if args.action == "start":
        if os.path.exists(pid_file):
            try:
                with open(pid_file, "r", encoding="utf-8") as f:
                    pid = int(f.read().strip() or "0")
                if pid > 0:
                    os.kill(pid, 0)
                    print(f"Swarmbot daemon 已在运行，PID={pid}")
                    return
            except Exception:
                try:
                    os.remove(pid_file)
                except Exception:
                    pass
        cmd = [sys.executable, "-m", "swarmbot.daemon"]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            with open(pid_file, "w", encoding="utf-8") as f:
                f.write(str(proc.pid))
        except Exception:
            pass
        print(f"Swarmbot daemon 已启动，PID={proc.pid}")
    elif args.action == "shutdown":
        if not os.path.exists(pid_file):
            print("Swarmbot daemon 未在运行。")
            return
        try:
            with open(pid_file, "r", encoding="utf-8") as f:
                pid = int(f.read().strip() or "0")
        except Exception:
            pid = 0
        if pid <= 0:
            try:
                os.remove(pid_file)
            except Exception:
                pass
            print("Swarmbot daemon PID 文件无效，已清理。")
            return
        try:
            import signal

            os.kill(pid, signal.SIGTERM)
            print(f"已发送 shutdown 信号到 Swarmbot daemon (PID={pid})")
        except ProcessLookupError:
            print("Swarmbot daemon 进程不存在，清理 PID 文件。")
        except Exception as e:
            print(f"无法发送 shutdown 信号: {e}")
        try:
            os.remove(pid_file)
        except Exception:
            pass


def main() -> None:
    # Use parse_known_args so we can grab extra args for passthrough commands
    parser = argparse.ArgumentParser(description="Swarmbot CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("onboard", help="初始化配置和工作区")

    subparsers.add_parser("run", help="与 Swarmbot 进行连续对话（本地调试）")

    # Gateway passthrough
    subparsers.add_parser("gateway", help="启动 Swarmbot Gateway")
    
    heartbeat_parser = subparsers.add_parser("heartbeat", help="管理 Swarmbot 的 heartbeat")
    heartbeat_sub = heartbeat_parser.add_subparsers(dest="action", required=True)
    heartbeat_sub.add_parser("status", help="查看 heartbeat 状态")
    heartbeat_sub.add_parser("trigger", help="立即执行一次 heartbeat 检查")

    subparsers.add_parser("tool", help="查看和使用 Swarmbot 暴露的工具（简化模式）")
    subparsers.add_parser("channels", help="管理 Swarmbot 的消息通道配置")
    
    cron_parser = subparsers.add_parser("cron", help="管理 Swarmbot 的定时任务")
    cron_sub = cron_parser.add_subparsers(dest="action", required=True)
    cron_sub.add_parser("list", help="列出所有定时任务")
    cron_add = cron_sub.add_parser("add", help="添加一个新的定时任务")
    cron_add.add_argument("--name", required=True, help="任务名称")
    cron_add.add_argument("--message", required=True, help="发送给 Agent 的消息")
    cron_add.add_argument("--every-minutes", type=int, required=True, help="执行间隔（分钟）")
    cron_add.add_argument("--deliver", action="store_true", help="是否将结果发送到指定渠道")
    cron_add.add_argument("--channel", type=str, help="渠道名称，如 feishu")
    cron_add.add_argument("--to", type=str, help="接收者标识")
    cron_remove = cron_sub.add_parser("remove", help="删除定时任务")
    cron_remove.add_argument("--id", required=True, help="任务 ID")
    cron_enable = cron_sub.add_parser("enable", help="启用定时任务")
    cron_enable.add_argument("--id", required=True, help="任务 ID")
    cron_disable = cron_sub.add_parser("disable", help="禁用定时任务")
    cron_disable.add_argument("--id", required=True, help="任务 ID")
    
    subparsers.add_parser("agent", help="保留占位符（原 nanobot agent 透传已禁用）")

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
    config_parser.add_argument("--max-agents", type=int, help="Swarm 中的 agent 最大数量")
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

    subparsers.add_parser("skill", help="查看当前可用的技能（内部通过 ToolAdapter 实现）")

    daemon_parser = subparsers.add_parser("daemon", help="管理 Swarmbot 守护进程")
    daemon_sub = daemon_parser.add_subparsers(dest="action", required=True)
    daemon_sub.add_parser("start", help="启动守护进程")
    daemon_sub.add_parser("shutdown", help="关闭守护进程")

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
        cmd_heartbeat(args)
    elif args.command == "tool":
        cmd_tool()
    elif args.command == "channels":
        cmd_channels(args, sys.argv[2:])
    elif args.command == "cron":
        cmd_cron(args)
    elif args.command == "agent":
        print("直接与底层 nanobot agent 对话的功能已禁用。")
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
        print("技能管理请通过对话中的 skill_summary / skill_load 工具完成。")
    elif args.command == "overthinking":
        cmd_overthinking(args)
    elif args.command == "daemon":
        cmd_daemon(args)

if __name__ == "__main__":
    from nanobot.cli.commands import app
    # Add our commands if not present? 
    # Actually, swarmbot cli uses argparse, nanobot uses typer.
    # The swarmbot/cli.py uses argparse.
    # We should just run main().
    main()
