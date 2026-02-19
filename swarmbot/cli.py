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
)
from .swarm.manager import SwarmManager


def cmd_onboard() -> None:
    ensure_dirs()
    cfg = load_config()
    save_config(cfg)
    try:
        subprocess.run(["nanobot", "onboard"], check=False)
    except FileNotFoundError:
        pass
    print(f"Swarmbot 已完成初始化，配置文件位于: {CONFIG_PATH}")


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


def cmd_gateway() -> None:
    # 直接透传 nanobot gateway 命令
    try:
        subprocess.run(["nanobot", "gateway"], check=True)
    except FileNotFoundError:
        print("未找到 nanobot 命令，请先安装 nanobot-ai。", file=sys.stderr)

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

def cmd_status() -> None:
    cfg = load_config()
    print("Swarmbot 状态:")
    print()
    print("Provider:")
    print(json.dumps({"provider": cfg.provider.__dict__}, ensure_ascii=False, indent=2))
    print()
    print("Swarm:")
    print(json.dumps({"swarm": cfg.swarm.__dict__}, ensure_ascii=False, indent=2))


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

    args, _ = parser.parse_known_args()

    if args.command == "onboard":
        cmd_onboard()
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
        cmd_passthrough("channels", sys.argv[2:])
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
