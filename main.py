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


def _init_db_if_enabled(config):
    """若 MySQL 已启用则初始化连接"""
    if config.mysql.enabled:
        try:
            from cloud_monitor.db import init_db
            init_db(config.mysql)
            return True
        except Exception as e:
            console.print(f"[yellow]⚠️ MySQL 连接失败: {e}，跳过入库[/yellow]")
    return False


def direct_huawei_check(config_path: str | None = None,
                        checks: list[str] | None = None):
    """直接运行华为云风险巡检，跳过 Agent/LLM"""
    import time
    from cloud_monitor.tools.huawei_check import ALL_CHECKS, run_all_checks

    config = load_config(config_path)
    if not config.huawei.enabled:
        console.print("[red]错误: 华为云未启用，请检查 config.yaml[/red]")
        sys.exit(1)

    db_ok = _init_db_if_enabled(config)

    check_names = [name for _, name, _ in ALL_CHECKS]
    if checks:
        check_names = [name for ctype, name, _ in ALL_CHECKS if ctype in checks]

    console.print(Panel(
        f"[bold]华为云风险巡检[/bold]\n"
        f"区域: {config.huawei.region}  |  巡检项: {len(check_names)} 个\n"
        f"[dim]{'、'.join(check_names)}[/dim]\n"
        f"[dim]MySQL: {'已启用' if db_ok else '未启用'}[/dim]",
        border_style="cyan",
    ))

    t0 = time.time()
    full_text, results_data = run_all_checks(config.huawei, checks=checks)
    elapsed = time.time() - t0

    console.print()
    try:
        console.print(Markdown(full_text))
    except Exception:
        console.print(full_text)

    if db_ok:
        from cloud_monitor.db import save_check_results
        total_saved = 0
        for check_type, records in results_data.items():
            save_check_results(check_type, records)
            total_saved += len(records)
        console.print(f"\n[dim]💾 已写入 MySQL: {total_saved} 条巡检记录[/dim]")

    total_issues = sum(len(r) for r in results_data.values())
    console.print(f"[dim]⏱ 总耗时: {elapsed:.1f}s | 发现风险项: {total_issues} 个[/dim]")

    webhook_on = config.webhook.enabled and config.webhook.url
    if webhook_on:
        body = f"📋 华为云风险巡检报告\n\n{full_text}"
        ok = send_webhook(config.webhook.url, body)
        if ok:
            console.print("[dim]✅ 已推送到 Webhook[/dim]")
        else:
            console.print("[yellow]⚠️ Webhook 推送失败[/yellow]")


def direct_ec2_check(config_path: str | None = None,
                     cpu_override: float | None = None,
                     mem_override: float | None = None,
                     hours_override: float | None = None):
    """直接调用 EC2 闲置检测，跳过 Agent/LLM，无需对话。
    参数优先级：命令行 > config.yaml > 代码默认值"""
    import time
    from cloud_monitor.tools.aws import list_ec2_aws

    config = load_config(config_path)
    if not config.aws.enabled:
        console.print("[red]错误: AWS 未启用，请检查 config.yaml[/red]")
        sys.exit(1)

    db_ok = _init_db_if_enabled(config)

    ec2_cfg = config.ec2_check
    cpu_threshold = cpu_override if cpu_override is not None else ec2_cfg.cpu_threshold
    mem_threshold = mem_override if mem_override is not None else ec2_cfg.mem_threshold
    hours = hours_override if hours_override is not None else ec2_cfg.hours

    days = hours / 24
    time_desc = f"{days:.0f}天" if hours >= 48 else f"{hours:.0f}小时"
    console.print(Panel(
        f"[bold]AWS EC2 闲置检测[/bold]\n"
        f"CPU 阈值: {cpu_threshold}%  |  内存阈值: {mem_threshold}%  |  时间窗口: {time_desc}\n"
        f"并发线程: {ec2_cfg.max_workers}  |  账户数: {len(config.aws.accounts)}\n"
        f"[dim]参数来源: config.yaml → ec2_check | MySQL: {'已启用' if db_ok else '未启用'}[/dim]",
        border_style="cyan",
    ))

    webhook_on = config.webhook.enabled and config.webhook.url
    all_results: list[str] = []
    scan_params = {"cpu_threshold": cpu_threshold, "mem_threshold": mem_threshold, "hours": hours}

    for acc in config.aws.accounts:
        regions = acc.get_regions()
        console.print(f"\n[cyan]▶ 账户 [{acc.name}]  区域: {', '.join(regions)}[/cyan]")
        t0 = time.time()

        text, structured = list_ec2_aws(
            acc,
            cpu_threshold=cpu_threshold,
            mem_threshold=mem_threshold,
            hours=hours,
            max_workers=ec2_cfg.max_workers,
        )
        elapsed = time.time() - t0
        all_results.append(text)

        if db_ok and structured:
            from cloud_monitor.db import save_idle_resources
            save_idle_resources("AWS", acc.name, structured, scan_params)
            console.print(f"[dim]  💾 已写入 MySQL: {len(structured)} 条[/dim]")

        console.print()
        try:
            console.print(Markdown(text))
        except Exception:
            console.print(text)
        console.print(f"[dim]  ⏱ 耗时: {elapsed:.1f}s[/dim]")

    if webhook_on and all_results:
        body = "📋 AWS EC2 闲置检测报告\n\n" + "\n\n".join(all_results)
        ok = send_webhook(config.webhook.url, body)
        if ok:
            console.print("\n[dim]✅ 已推送到 Webhook[/dim]")
        else:
            console.print("\n[yellow]⚠️ Webhook 推送失败[/yellow]")


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

  # EC2 闲置检测
  python main.py --ec2

  # 启动 Web 服务（API + 前端）
  python main.py --server
  python main.py --server --port 3000

  # 指定配置文件
  python main.py -c /path/to/config.yaml
""",
    )
    parser.add_argument(
        "-q", "--query",
        type=str,
        default=None,
        help="单次查询模式，通过 Agent 执行指定查询",
    )
    parser.add_argument(
        "--ec2",
        action="store_true",
        help="直接运行 AWS EC2 闲置检测（跳过 Agent，参数从 config.yaml 的 ec2_check 段读取）",
    )
    parser.add_argument(
        "--huawei-check",
        action="store_true",
        help="直接运行华为云风险巡检（ECS安全组/CCE副本/RDS高可用/DMS集群/RDS网络/DDS网络/RDS参数/CCE Pod/ECS闲置）",
    )
    parser.add_argument(
        "--checks",
        type=str,
        default=None,
        help="指定巡检项（逗号分隔），如: rds_ha,rds_params_double_one,ecs_security_group",
    )
    parser.add_argument(
        "--server",
        action="store_true",
        help="启动 Web 服务（FastAPI API + Vue 前端）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Web 服务端口 (默认: 8080)",
    )
    parser.add_argument(
        "--cpu",
        type=float,
        default=None,
        help="覆盖 CPU 利用率阈值%%（不传则使用 config.yaml 中的值）",
    )
    parser.add_argument(
        "--mem",
        type=float,
        default=None,
        help="覆盖内存利用率阈值%%（不传则使用 config.yaml 中的值）",
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=None,
        help="覆盖检测时间窗口/小时（不传则使用 config.yaml 中的值）",
    )
    parser.add_argument(
        "-c", "--config",
        type=str,
        default=None,
        help="配置文件路径 (默认: config.yaml)",
    )

    args = parser.parse_args()

    if args.server:
        from cloud_monitor.server import run_server
        console.print(Panel(
            f"[bold]多云闲置资源管理[/bold]\n"
            f"API 地址: http://0.0.0.0:{args.port}/api\n"
            f"前端地址: http://0.0.0.0:{args.port}\n"
            f"[dim]需要先构建前端: cd web && npm run build[/dim]",
            border_style="cyan",
        ))
        run_server(port=args.port)
    elif args.huawei_check:
        check_list = None
        if args.checks:
            check_list = [c.strip() for c in args.checks.split(",") if c.strip()]
        direct_huawei_check(args.config, checks=check_list)
    elif args.ec2:
        direct_ec2_check(args.config, args.cpu, args.mem, args.hours)
    elif args.query:
        asyncio.run(single_query_mode(args.query, args.config))
    else:
        asyncio.run(interactive_mode(args.config))


if __name__ == "__main__":
    main()
