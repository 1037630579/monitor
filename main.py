#!/usr/bin/env python3
"""多云统一监控应用 - 基于 Claude Agents SDK

通过自然语言查询华为云、阿里云、AWS 三大云平台的监控指标。
"""

import argparse
import asyncio
import sys
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeSDKClient,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from cloud_monitor.agent import create_agent_options
from cloud_monitor.config import load_config
from cloud_monitor.webhook import send_webhook

console = Console()


def print_banner(enabled_clouds: list[str], webhook_enabled: bool = False):
    cloud_names = {"huawei": "华为云", "aliyun": "阿里云", "aws": "AWS"}
    clouds = "、".join(cloud_names.get(c, c) for c in enabled_clouds)

    banner = Text()
    banner.append("☁  多云统一监控助手\n", style="bold cyan")
    banner.append(f"已启用: {clouds}\n", style="green")
    if webhook_enabled:
        banner.append("Webhook 推送: 已开启\n", style="yellow")
    banner.append("输入自然语言查询监控指标，输入 quit 退出", style="dim")

    console.print(Panel(banner, border_style="blue", padding=(1, 2)))


def collect_message(msg, text_parts: list[str]):
    """显示并收集 Agent 消息文本"""
    if isinstance(msg, AssistantMessage):
        for block in msg.content:
            if isinstance(block, TextBlock):
                text_parts.append(block.text)
                try:
                    md = Markdown(block.text)
                    console.print(md)
                except Exception:
                    console.print(block.text)
            elif isinstance(block, ToolUseBlock):
                console.print(
                    f"  [dim]📡 调用工具: {block.name}[/dim]"
                )
                if block.input:
                    params = ", ".join(
                        f"{k}={v}" for k, v in block.input.items()
                        if v is not None and v != ""
                    )
                    if params:
                        console.print(f"  [dim]   参数: {params}[/dim]")
    elif isinstance(msg, ResultMessage):
        if msg.total_cost_usd and msg.total_cost_usd > 0:
            console.print(
                f"\n[dim]💰 本次查询费用: ${msg.total_cost_usd:.6f}[/dim]"
            )


async def interactive_mode(config_path: str | None = None):
    """交互式查询模式"""
    config = load_config(config_path)
    enabled = config.enabled_clouds()

    if not enabled:
        console.print(
            "[red]错误: 没有启用任何云平台。请配置 config.yaml 或设置环境变量。[/red]"
        )
        console.print("[yellow]参考 config.yaml.example 了解配置格式。[/yellow]")
        sys.exit(1)

    options = create_agent_options(config)
    webhook_on = config.webhook.enabled and config.webhook.url
    print_banner(enabled, webhook_enabled=bool(webhook_on))

    async with ClaudeSDKClient(options=options) as client:
        while True:
            console.print()
            try:
                user_input = console.input("[bold green]你> [/bold green]").strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]再见！[/dim]")
                break

            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "q", "退出"):
                console.print("[dim]再见！[/dim]")
                break

            console.print()
            text_parts: list[str] = []

            try:
                await client.query(user_input)
                async for msg in client.receive_response():
                    collect_message(msg, text_parts)
            except Exception as e:
                console.print(f"[red]查询出错: {e}[/red]")

            if webhook_on and text_parts:
                body = f"📋 查询: {user_input}\n\n" + "\n\n".join(text_parts)
                ok = send_webhook(config.webhook.url, body)
                if ok:
                    console.print("[dim]✅ 已推送到 Webhook[/dim]")
                else:
                    console.print("[yellow]⚠️ Webhook 推送失败[/yellow]")


async def single_query_mode(prompt: str, config_path: str | None = None):
    """单次查询模式"""
    config = load_config(config_path)
    enabled = config.enabled_clouds()

    if not enabled:
        console.print(
            "[red]错误: 没有启用任何云平台。请配置 config.yaml 或设置环境变量。[/red]"
        )
        sys.exit(1)

    options = create_agent_options(config)
    webhook_on = config.webhook.enabled and config.webhook.url
    text_parts: list[str] = []

    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)
        async for msg in client.receive_response():
            collect_message(msg, text_parts)

    if webhook_on and text_parts:
        body = f"📋 查询: {prompt}\n\n" + "\n\n".join(text_parts)
        ok = send_webhook(config.webhook.url, body)
        if ok:
            console.print("[dim]✅ 已推送到 Webhook[/dim]")
        else:
            console.print("[yellow]⚠️ Webhook 推送失败[/yellow]")


def main():
    parser = argparse.ArgumentParser(
        description="多云统一监控助手 - 基于 Claude Agents SDK",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
使用示例:
  # 交互式模式
  python main.py

  # 单次查询
  python main.py -q "查看华为云 ECS 实例列表"
  python main.py -q "查询 VPN vpn-xxx 最近1小时流量"

  # 指定配置文件
  python main.py -c /path/to/config.yaml
""",
    )
    parser.add_argument(
        "-q", "--query",
        type=str,
        default=None,
        help="单次查询模式，直接执行指定查询",
    )
    parser.add_argument(
        "-c", "--config",
        type=str,
        default=None,
        help="配置文件路径 (默认: config.yaml)",
    )

    args = parser.parse_args()

    if args.query:
        asyncio.run(single_query_mode(args.query, args.config))
    else:
        asyncio.run(interactive_mode(args.config))


if __name__ == "__main__":
    main()
