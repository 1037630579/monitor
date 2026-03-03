"""Claude Agent 集成 - 将云平台监控能力注册为 MCP 工具"""

from typing import Any

from claude_agent_sdk import (
    ClaudeAgentOptions,
    create_sdk_mcp_server,
    tool,
)

from cloud_monitor.config import AppConfig, AWSAccountConfig


def build_tools(config: AppConfig) -> list:
    """根据配置动态构建已启用的云平台工具"""
    tools = []

    # ── 华为云工具 ──
    if config.huawei.enabled:
        from cloud_monitor.tools.huawei import (
            get_metric_data_huawei,
            list_cdn_domains_huawei,
            list_ecs_instances_huawei,
            list_metrics_huawei,
            list_obs_buckets_huawei,
        )

        hw_config = config.huawei

        @tool(
            "huawei_list_metrics",
            "列出华为云可用的监控指标(ECS)。不传参数返回常用指标，可通过 namespace 和 metric_name 过滤",
            {"namespace": str, "metric_name": str},
        )
        async def huawei_list_metrics_tool(args: dict[str, Any]) -> dict[str, Any]:
            result = list_metrics_huawei(hw_config, namespace=args.get("namespace", ""), metric_name=args.get("metric_name", ""))
            return {"content": [{"type": "text", "text": result}]}

        @tool(
            "huawei_get_metric_data",
            "查询华为云指定实例的监控指标数据。需提供 namespace、metric_name、instance_id",
            {"namespace": str, "metric_name": str, "instance_id": str, "period": int, "stat": str, "hours": float, "dim_name": str},
        )
        async def huawei_get_metric_data_tool(args: dict[str, Any]) -> dict[str, Any]:
            result = get_metric_data_huawei(
                hw_config, namespace=args["namespace"], metric_name=args["metric_name"], instance_id=args["instance_id"],
                period=args.get("period", 300), stat=args.get("stat", "average"), hours=args.get("hours", 1), dim_name=args.get("dim_name", "instance_id"),
            )
            return {"content": [{"type": "text", "text": result}]}

        @tool("huawei_list_ecs", "列出华为云 ECS 云主机实例（概览+已停止实例详情），与 AWS EC2 输出格式一致", {})
        async def huawei_list_ecs_tool(args: dict[str, Any]) -> dict[str, Any]:
            return {"content": [{"type": "text", "text": list_ecs_instances_huawei(hw_config)}]}

        @tool("huawei_list_obs", "列出华为云 OBS 对象存储桶（含区域信息和区域分布统计），与 AWS S3 输出格式一致", {})
        async def huawei_list_obs_tool(args: dict[str, Any]) -> dict[str, Any]:
            return {"content": [{"type": "text", "text": list_obs_buckets_huawei(hw_config)}]}

        @tool(
            "huawei_list_cdn",
            "列出华为云 CDN 加速域名（概览+已停用域名详情），与 AWS CloudFront 输出格式一致。status_filter: 'offline'=仅停用, 'online'=仅启用, ''=全部",
            {"status_filter": str},
        )
        async def huawei_list_cdn_tool(args: dict[str, Any]) -> dict[str, Any]:
            return {"content": [{"type": "text", "text": list_cdn_domains_huawei(hw_config, status_filter=args.get("status_filter", ""))}]}

        tools.extend([huawei_list_metrics_tool, huawei_get_metric_data_tool, huawei_list_ecs_tool, huawei_list_obs_tool, huawei_list_cdn_tool])

    # ── 阿里云工具 ──
    if config.aliyun.enabled:
        from cloud_monitor.tools.aliyun import (
            get_metric_data_aliyun,
            list_cdn_domains_aliyun,
            list_ecs_instances_aliyun,
            list_metrics_aliyun,
            list_oss_buckets_aliyun,
        )

        ali_config = config.aliyun

        @tool(
            "aliyun_list_metrics",
            "列出阿里云可用的监控指标(ECS)。不传参数返回常用指标，可通过 namespace 和 metric_name 过滤",
            {"namespace": str, "metric_name": str},
        )
        async def aliyun_list_metrics_tool(args: dict[str, Any]) -> dict[str, Any]:
            result = list_metrics_aliyun(ali_config, namespace=args.get("namespace", ""), metric_name=args.get("metric_name", ""))
            return {"content": [{"type": "text", "text": result}]}

        @tool(
            "aliyun_get_metric_data",
            "查询阿里云指定实例的监控指标数据。需提供 namespace、metric_name、instance_id",
            {"namespace": str, "metric_name": str, "instance_id": str, "period": int, "stat": str, "hours": float},
        )
        async def aliyun_get_metric_data_tool(args: dict[str, Any]) -> dict[str, Any]:
            result = get_metric_data_aliyun(
                ali_config, namespace=args["namespace"], metric_name=args["metric_name"], instance_id=args["instance_id"],
                period=args.get("period", 300), stat=args.get("stat", "average"), hours=args.get("hours", 1),
            )
            return {"content": [{"type": "text", "text": result}]}

        @tool("aliyun_list_ecs", "列出阿里云 ECS 云主机实例（概览+已停止实例详情），与 AWS EC2 输出格式一致", {})
        async def aliyun_list_ecs_tool(args: dict[str, Any]) -> dict[str, Any]:
            return {"content": [{"type": "text", "text": list_ecs_instances_aliyun(ali_config)}]}

        @tool("aliyun_list_oss", "列出阿里云 OSS 对象存储桶（含区域信息和区域分布统计），与 AWS S3 输出格式一致", {})
        async def aliyun_list_oss_tool(args: dict[str, Any]) -> dict[str, Any]:
            return {"content": [{"type": "text", "text": list_oss_buckets_aliyun(ali_config)}]}

        @tool(
            "aliyun_list_cdn",
            "列出阿里云 CDN 加速域名（概览+已停用域名详情），与 AWS CloudFront 输出格式一致。status_filter: 'offline'=仅停用, 'online'=仅启用, ''=全部",
            {"status_filter": str},
        )
        async def aliyun_list_cdn_tool(args: dict[str, Any]) -> dict[str, Any]:
            return {"content": [{"type": "text", "text": list_cdn_domains_aliyun(ali_config, status_filter=args.get("status_filter", ""))}]}

        tools.extend([aliyun_list_metrics_tool, aliyun_get_metric_data_tool, aliyun_list_ecs_tool, aliyun_list_oss_tool, aliyun_list_cdn_tool])

    # ── AWS 工具（多账户 / 多区域）──
    if config.aws.enabled:
        from cloud_monitor.tools.aws import (
            get_vpn_status_aws,
            list_ec2_aws,
            list_s3_buckets_aws,
            list_vpn_connections_aws,
        )

        aws_cfg = config.aws
        ec2_cfg = config.ec2_check

        def _get_accounts(account_name: str) -> list[AWSAccountConfig]:
            if not account_name:
                return aws_cfg.accounts
            return [aws_cfg.get_account(account_name)]

        def _run_for_accounts(account_name: str, fn, **kwargs) -> str:
            accounts = _get_accounts(account_name)
            parts = []
            for acc in accounts:
                parts.append(fn(acc, **kwargs))
            return "\n\n".join(parts)

        @tool("aws_list_accounts", "列出所有已配置的 AWS 账户及其区域信息", {})
        async def aws_list_accounts_tool(args: dict[str, Any]) -> dict[str, Any]:
            lines = [f"已配置 {len(aws_cfg.accounts)} 个 AWS 账户:"]
            for acc in aws_cfg.accounts:
                lines.append(f"\n  账户: {acc.name}")
                lines.append(f"    默认区域: {acc.region}")
                if acc.regions:
                    lines.append(f"    多区域: {', '.join(acc.regions)}")
                if acc.vpn_region:
                    lines.append(f"    VPN区域: {acc.vpn_region}")
            return {"content": [{"type": "text", "text": "\n".join(lines)}]}

        ec2_days = ec2_cfg.hours / 24
        ec2_time_desc = f"{ec2_days:.0f}天" if ec2_cfg.hours >= 48 else f"{ec2_cfg.hours:.0f}小时"

        @tool(
            "aws_ec2",
            f"AWS EC2 统一查询：一次返回实例概览 + 已停止实例详情 + 全部低利用率实例（紧凑表格）。"
            f"默认检测条件: CPU<{ec2_cfg.cpu_threshold}% 或 内存<{ec2_cfg.mem_threshold}%（最近{ec2_time_desc}）。"
            f"account: 账户名(空=所有账户)。region: 指定区域(空=所有区域)。"
            f"首次调用会扫描 CloudWatch（耗时约1-2分钟），结果自动缓存，后续调用瞬间返回。",
            {"account": str, "region": str, "cpu_threshold": float, "mem_threshold": float,
             "hours": float},
        )
        async def aws_ec2_tool(args: dict[str, Any]) -> dict[str, Any]:
            result = _run_for_accounts(
                args.get("account", ""), list_ec2_aws,
                region=args.get("region", ""),
                cpu_threshold=args.get("cpu_threshold", ec2_cfg.cpu_threshold),
                mem_threshold=args.get("mem_threshold", ec2_cfg.mem_threshold),
                hours=args.get("hours", ec2_cfg.hours),
                max_workers=ec2_cfg.max_workers,
            )
            return {"content": [{"type": "text", "text": result}]}

        # ── S3 对象存储 ──
        @tool(
            "aws_list_s3",
            "列出 AWS S3 存储桶（含每个桶的区域信息和区域分布统计）。account: 账户名(空=所有账户)。region: 过滤特定区域的桶(空=全部)",
            {"account": str, "region": str},
        )
        async def aws_list_s3_tool(args: dict[str, Any]) -> dict[str, Any]:
            result = _run_for_accounts(args.get("account", ""), list_s3_buckets_aws,
                                       region=args.get("region", ""))
            return {"content": [{"type": "text", "text": result}]}

        # ── VPN ──
        @tool("aws_list_vpn", "列出 AWS VPN 连接并自动查询每个VPN最近1小时的带宽数据（1分钟粒度表格）。account: 账户名(空=所有账户)", {"account": str})
        async def aws_list_vpn_tool(args: dict[str, Any]) -> dict[str, Any]:
            result = _run_for_accounts(args.get("account", ""), list_vpn_connections_aws)
            return {"content": [{"type": "text", "text": result}]}

        @tool(
            "aws_vpn_status",
            "查询 AWS VPN 带宽使用情况：隧道状态 + 最新采样点 + 每分钟带宽趋势表格(Mbps) + 小结。默认最近1小时、每1分钟一个点(hours=1, period=60)。account: 账户名(空=默认)。vpn_id: 可选指定VPN",
            {"account": str, "vpn_id": str, "hours": float, "period": int},
        )
        async def aws_vpn_status_tool(args: dict[str, Any]) -> dict[str, Any]:
            acc = aws_cfg.get_account(args.get("account", ""))
            result = get_vpn_status_aws(acc, vpn_id=args.get("vpn_id", ""), hours=args.get("hours", 1), period=args.get("period", 60))
            return {"content": [{"type": "text", "text": result}]}

        tools.extend([
            aws_list_accounts_tool,
            aws_ec2_tool,
            aws_list_s3_tool,
            aws_list_vpn_tool,
            aws_vpn_status_tool,
        ])

    return tools


def build_allowed_tools(config: AppConfig) -> list[str]:
    """构建允许使用的工具名称列表"""
    allowed = []
    s = "cloud"

    if config.huawei.enabled:
        allowed.extend([f"mcp__{s}__{t}" for t in [
            "huawei_list_metrics", "huawei_get_metric_data", "huawei_list_ecs", "huawei_list_obs", "huawei_list_cdn",
        ]])

    if config.aliyun.enabled:
        allowed.extend([f"mcp__{s}__{t}" for t in [
            "aliyun_list_metrics", "aliyun_get_metric_data", "aliyun_list_ecs", "aliyun_list_oss", "aliyun_list_cdn",
        ]])

    if config.aws.enabled:
        allowed.extend([f"mcp__{s}__{t}" for t in [
            "aws_list_accounts",
            "aws_ec2", "aws_list_s3",
            "aws_list_vpn", "aws_vpn_status",
        ]])

    return allowed


SYSTEM_PROMPT = """\
你是一个多云治理监控助手，帮助用户统一掌握阿里云、华为云、AWS 三大云平台的资源使用情况、发现闲置浪费、优化云成本。

# 工具映射

多云监控助手提供的资源查询工具，格式保持一致：

| 资源类型 | 阿里云 | 华为云 | AWS |
|---------|--------|--------|-----|
| 云主机   | aliyun_list_ecs | huawei_list_ecs | aws_ec2 |
| 对象存储 | aliyun_list_oss | huawei_list_obs | aws_list_s3 |
| CDN     | aliyun_list_cdn | huawei_list_cdn | - |
| 指标列表 | aliyun_list_metrics | huawei_list_metrics | - |
| 指标数据 | aliyun_get_metric_data | huawei_get_metric_data | - |

AWS 独有工具：aws_list_accounts, aws_list_vpn, aws_vpn_status

aws_ec2 是统一的 EC2 工具，一次调用返回全部结果：实例概览 + 已停止实例详情 + 低利用率实例表格。
低利用率实例使用紧凑表格格式（一行一条），即使数量较多也不会导致上下文溢出。
调用 aws_ec2 时**不需要传参数**，默认值已从配置文件加载。首次调用会扫描 CloudWatch（约1-2分钟），结果自动缓存。

# 查询决策

当用户查询"所有云"或未指定平台时，依次调用各启用平台的对应工具。
当用户指定某个平台或服务时，只调用对应工具。

- 查云主机 / 查闲置资源 / 查 EC2 → 调用 aws_ec2（不传参数即可），一次返回全部结果。低利用率实例已使用紧凑表格格式，直接完整输出给用户。阿里云用 aliyun_list_ecs，华为云用 huawei_list_ecs
- 查对象存储 → 调用 *_list_oss / *_list_obs / aws_list_s3
- 查 CDN → 调用 aliyun_list_cdn / huawei_list_cdn（AWS 暂不支持 CDN 查询）
- 查 VPN → 调用 aws_list_vpn（自动列出所有VPN并查询每个VPN最近1小时每1分钟的带宽表格）。查特定VPN或自定义时间范围时用 aws_vpn_status

# AWS 多账户与多区域

- 每个 AWS 工具都有 account 参数，不传 = 查询所有账户
- EC2/S3 自动遍历账户配置的所有 regions
- VPN 使用 vpn_region


# 输出规范

1. **必须且只能使用中文回答**，包括标题、表格、建议、小结等所有内容，严禁使用英文。数据必须附带单位
2. 多云结果按平台分段展示，标注平台名称
3. 已停止的实例和已禁用/停用的 CDN 必须逐条列出完整详情（ID、名称、类型、区域、停止时长等），禁止省略或合并
4. **VPN 带宽数据**：工具返回的带宽趋势表格（每分钟一行）必须完整原样输出，禁止省略、合并或只输出小结。对有流量的 VPN，输出顺序为：最新采样点表格 → 每分钟趋势表格（全部行） → 小结。对无流量的 VPN（所有隧道 DOWN），只需简要说明即可
5. 主动告警：VPN 隧道 DOWN
6. 查询失败时说明原因并给出排查建议
"""


def create_agent_options(config: AppConfig) -> ClaudeAgentOptions:
    """创建 Claude Agent 配置"""
    all_tools = build_tools(config)

    if not all_tools:
        raise ValueError("没有启用任何云平台，请检查 config.yaml 配置")

    cloud_server = create_sdk_mcp_server(
        name="cloud-monitor",
        version="1.0.0",
        tools=all_tools,
    )

    allowed = build_allowed_tools(config)

    enabled = config.enabled_clouds()
    cloud_names = {"huawei": "华为云", "aliyun": "阿里云", "aws": "AWS"}
    enabled_str = "、".join(cloud_names.get(c, c) for c in enabled)

    extra_info = ""
    if config.aws.enabled and config.aws.accounts:
        names = config.aws.list_account_names()
        extra_info = f"\nAWS 已配置账户: {', '.join(names)}"

    system = SYSTEM_PROMPT + f"\n\n当前已启用的云平台：{enabled_str}{extra_info}"

    options = ClaudeAgentOptions(
        system_prompt=system,
        mcp_servers={"cloud": cloud_server},
        allowed_tools=allowed,
        max_turns=30,
    )

    return options
