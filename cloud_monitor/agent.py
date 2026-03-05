"""Claude Agent 集成 - 将云平台监控能力注册为 MCP 工具"""

from typing import Any

from claude_agent_sdk import (
    ClaudeAgentOptions,
    create_sdk_mcp_server,
    tool,
)

from cloud_monitor.config import AppConfig, AWSAccountConfig


def _try_save_db(cloud: str, account: str, structured: list[dict], scan_params: dict | None = None):
    """尝试将结构化数据写入 MongoDB（静默失败）"""
    try:
        from cloud_monitor.db import save_idle_resources, get_db
        if get_db() is not None and structured:
            save_idle_resources(cloud, account, structured, scan_params)
    except Exception:
        pass


def build_tools(config: AppConfig) -> list:
    """根据配置动态构建已启用的云平台工具"""
    tools = []

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
            text, structured = list_ecs_instances_aliyun(ali_config)
            _try_save_db("阿里云", "default", structured)
            return {"content": [{"type": "text", "text": text}]}

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

    # ── 华为云工具 ──
    if config.huawei.enabled:
        from cloud_monitor.tools.huawei_check import run_single_check_all_regions

        hw_cfg = config.huawei

        HUAWEI_RESOURCE_GROUPS: dict[str, list[str]] = {
            "ecs": ["ecs_security_group", "ecs_anti_affinity", "ecs_idle"],
            "rds": ["rds_ha", "rds_network_type", "rds_params_double_one"],
            "cce": ["cce_workload_replica", "cce_node_pods"],
            "dds": ["dds_network_type"],
            "dms": ["dms_rabbitmq_cluster"],
        }

        huawei_task_regions: dict[str, list[str]] = {}
        for gn, task in config.schedule.huawei_checks.items():
            if task.regions:
                huawei_task_regions[gn] = task.regions

        def _run_huawei_group(group_name: str, check_types: list[str]) -> dict[str, Any]:
            task_regions = huawei_task_regions.get(group_name) or None
            all_text: list[str] = []
            for ct in check_types:
                text, data = run_single_check_all_regions(hw_cfg, ct, task_regions=task_regions)
                all_text.append(text)
                try:
                    from cloud_monitor.db import save_check_results, get_db
                    if get_db() is not None and data:
                        save_check_results(ct, data)
                except Exception:
                    pass
            return {"content": [{"type": "text", "text": "\n\n".join(all_text)}]}

        @tool("huawei_ecs", "华为云 ECS 巡检：安全组规则检查 + 反亲和性检查 + 闲置实例检查，一次返回全部结果", {})
        async def huawei_ecs_tool(args: dict[str, Any]) -> dict[str, Any]:
            return _run_huawei_group("ecs", HUAWEI_RESOURCE_GROUPS["ecs"])

        @tool("huawei_rds", "华为云 RDS 巡检：高可用部署检查 + 网络类型检查 + 参数双1检查，一次返回全部结果", {})
        async def huawei_rds_tool(args: dict[str, Any]) -> dict[str, Any]:
            return _run_huawei_group("rds", HUAWEI_RESOURCE_GROUPS["rds"])

        @tool("huawei_cce", "华为云 CCE 巡检：工作负载副本数检查 + 节点 Pod 数量检查，一次返回全部结果", {})
        async def huawei_cce_tool(args: dict[str, Any]) -> dict[str, Any]:
            return _run_huawei_group("cce", HUAWEI_RESOURCE_GROUPS["cce"])

        @tool("huawei_dds", "华为云 DDS (MongoDB) 巡检：网络类型检查", {})
        async def huawei_dds_tool(args: dict[str, Any]) -> dict[str, Any]:
            return _run_huawei_group("dds", HUAWEI_RESOURCE_GROUPS["dds"])

        @tool("huawei_dms", "华为云 DMS 巡检：RabbitMQ 集群部署检查", {})
        async def huawei_dms_tool(args: dict[str, Any]) -> dict[str, Any]:
            return _run_huawei_group("dms", HUAWEI_RESOURCE_GROUPS["dms"])

        @tool("huawei_list_regions", "列出华为云已配置的所有巡检区域及对应的 project_id", {})
        async def huawei_list_regions_tool(args: dict[str, Any]) -> dict[str, Any]:
            regions = hw_cfg.get_regions()
            lines = [f"华为云已配置 {len(regions)} 个区域:"]
            for r in regions:
                pid = hw_cfg.region_projects.get(r, "未知")
                lines.append(f"  {r} → project_id: {pid}")
            return {"content": [{"type": "text", "text": "\n".join(lines)}]}

        tools.extend([
            huawei_ecs_tool, huawei_rds_tool, huawei_cce_tool,
            huawei_dds_tool, huawei_dms_tool, huawei_list_regions_tool,
        ])

    # ── AWS 工具（多账户 / 多区域）──
    if config.aws.enabled:
        from cloud_monitor.tools.aws import (
            get_vpn_status_aws,
            list_ec2_aws,
            list_elb_aws,
            list_cloudfront_distributions_aws,
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
                result = fn(acc, **kwargs)
                if isinstance(result, tuple):
                    text, structured = result
                    parts.append(text)
                    _try_save_db("AWS", acc.name, structured,
                                 {"cpu_threshold": kwargs.get("cpu_threshold"),
                                  "mem_threshold": kwargs.get("mem_threshold"),
                                  "hours": kwargs.get("hours")})
                else:
                    parts.append(result)
            return "\n\n".join(parts)

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
        @tool("aws_list_vpn", "列出 AWS VPN 连接并自动查询每个VPN最近1小时的带宽数据（1分钟粒度表格）。自动扫描所有配置区域。account: 账户名(空=所有账户)。region: 指定区域(空=所有区域)", {"account": str, "region": str})
        async def aws_list_vpn_tool(args: dict[str, Any]) -> dict[str, Any]:
            result = _run_for_accounts(args.get("account", ""), list_vpn_connections_aws,
                                       region=args.get("region", ""))
            return {"content": [{"type": "text", "text": result}]}

        @tool(
            "aws_vpn_status",
            "查询 AWS VPN 带宽使用情况：隧道状态 + 最新采样点 + 每分钟带宽趋势表格(Mbps) + 小结。默认最近1小时、每1分钟一个点(hours=1, period=60)。account: 账户名(空=默认)。vpn_id: 可选指定VPN。region: 指定区域(空=默认)",
            {"account": str, "vpn_id": str, "hours": float, "period": int, "region": str},
        )
        async def aws_vpn_status_tool(args: dict[str, Any]) -> dict[str, Any]:
            acc = aws_cfg.get_account(args.get("account", ""))
            result = get_vpn_status_aws(acc, vpn_id=args.get("vpn_id", ""), hours=args.get("hours", 1), period=args.get("period", 60), region=args.get("region", ""))
            return {"content": [{"type": "text", "text": result}]}

        # ── ALB 负载均衡 ──
        @tool("aws_list_elb", "列出 AWS ALB 负载均衡器。自动扫描所有配置区域。account: 账户名(空=所有账户)。region: 指定区域(空=所有区域)", {"account": str, "region": str})
        async def aws_list_elb_tool(args: dict[str, Any]) -> dict[str, Any]:
            result = _run_for_accounts(args.get("account", ""), list_elb_aws,
                                       region=args.get("region", ""))
            return {"content": [{"type": "text", "text": result}]}

        # ── CloudFront CDN ──
        @tool(
            "aws_list_cloudfront",
            "列出 AWS CloudFront CDN 分发概览（含已启用和已禁用分发详情）。account: 账户名(空=所有账户)。status_filter: 'disabled'=仅禁用, 'enabled'=仅启用, ''=全部",
            {"account": str, "status_filter": str},
        )
        async def aws_list_cloudfront_tool(args: dict[str, Any]) -> dict[str, Any]:
            result = _run_for_accounts(args.get("account", ""), list_cloudfront_distributions_aws,
                                       status_filter=args.get("status_filter", ""))
            return {"content": [{"type": "text", "text": result}]}

        tools.extend([
            aws_ec2_tool,
            aws_list_s3_tool,
            aws_list_vpn_tool,
            aws_vpn_status_tool,
            aws_list_elb_tool,
            aws_list_cloudfront_tool,
        ])

    return tools


def build_allowed_tools(config: AppConfig) -> list[str]:
    """构建允许使用的工具名称列表"""
    allowed = []
    s = "cloud"

    if config.huawei.enabled:
        allowed.extend([f"mcp__{s}__{t}" for t in [
            "huawei_ecs", "huawei_rds", "huawei_cce",
            "huawei_dds", "huawei_dms", "huawei_list_regions",
        ]])

    if config.aliyun.enabled:
        allowed.extend([f"mcp__{s}__{t}" for t in [
            "aliyun_list_metrics", "aliyun_get_metric_data", "aliyun_list_ecs", "aliyun_list_oss", "aliyun_list_cdn",
        ]])

    if config.aws.enabled:
        allowed.extend([f"mcp__{s}__{t}" for t in [
            "aws_ec2", "aws_list_s3",
            "aws_list_vpn", "aws_vpn_status",
            "aws_list_elb", "aws_list_cloudfront",
        ]])

    return allowed


SYSTEM_PROMPT = """\
你是一个多云治理监控专家，帮助用户掌握华为云、阿里云、AWS 云平台的资源使用情况、发现闲置浪费、优化云成本。

# 工具映射

| 资源类型 | 华为云 | 阿里云 | AWS |
|---------|--------|--------|-----|
| ECS 云主机 | huawei_ecs | aliyun_list_ecs | aws_ec2 |
| RDS 数据库 | huawei_rds | - | - |
| CCE 容器 | huawei_cce | - | - |
| DDS 数据库 | huawei_dds | - | - |
| DMS 消息队列 | huawei_dms | - | - |
| 对象存储 | - | aliyun_list_oss | aws_list_s3 |
| CDN | - | aliyun_list_cdn | aws_list_cloudfront |
| 负载均衡 | - | - | aws_list_elb |
| VPN | - | - | aws_list_vpn / aws_vpn_status |
| 区域信息 | huawei_list_regions | - | - |

# 华为云巡检

每个工具一次调用返回该资源的全部巡检结果：
- huawei_ecs: 安全组规则 + 反亲和性 + 闲置实例
- huawei_rds: 高可用部署 + 网络类型 + 参数双1
- huawei_cce: 工作负载副本数 + 节点 Pod 数量
- huawei_dds: 网络类型
- huawei_dms: RabbitMQ 集群部署

# AWS 工具

- aws_ec2: EC2 统一查询（概览 + 已停止 + 低利用率），自动扫描所有区域
- aws_list_s3: S3 存储桶列表，自动扫描所有区域
- aws_list_vpn / aws_vpn_status: VPN 连接和带宽详情，自动扫描所有区域
- aws_list_elb: ALB 负载均衡器列表，自动扫描所有区域
- aws_list_cloudfront: CloudFront CDN 分发概览（全局服务）

# 查询决策

当用户查询"所有云"或未指定平台时，依次调用各启用平台的对应工具。
当用户指定某个平台或服务时，只调用对应工具。

- 华为云 ECS → huawei_ecs
- 华为云 RDS → huawei_rds
- 华为云 CCE → huawei_cce
- 华为云 DDS → huawei_dds
- 华为云 DMS → huawei_dms
- 查 EC2 / 查闲置 → aws_ec2（阿里云用 aliyun_list_ecs）
- 查对象存储 → aliyun_list_oss / aws_list_s3
- 查 CDN → aliyun_list_cdn / aws_list_cloudfront
- 查负载均衡 → aws_list_elb
- 查 VPN → aws_list_vpn 或 aws_vpn_status

# 多账户与多区域

- 每个 AWS 工具都有 account 参数，不传 = 查询所有账户
- AWS 的 EC2、S3、VPN、ELB 都支持 region 参数，不传 = 自动扫描所有配置区域
- 华为云巡检自动遍历配置的所有区域

# 输出规范

1. **必须且只能使用中文回答**，数据必须附带单位
2. 多云结果按平台分段展示，标注平台名称
3. 已停止的实例必须逐条列出完整详情，禁止省略或合并
4. **VPN 带宽数据**：趋势表格必须完整原样输出，禁止省略
5. 主动告警：VPN 隧道 DOWN、安全组高风险规则
6. 查询失败时说明原因并给出排查建议
"""


def create_agent_options(config: AppConfig) -> ClaudeAgentOptions:
    """创建 Claude Agent 配置"""
    if config.mysql.enabled:
        try:
            from cloud_monitor.db import init_db
            init_db(config.mysql)
        except Exception:
            pass

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

    system = SYSTEM_PROMPT + f"\n\n当前已启用的云平台：{enabled_str}"

    options = ClaudeAgentOptions(
        system_prompt=system,
        mcp_servers={"cloud": cloud_server},
        allowed_tools=allowed,
        max_turns=30,
    )

    return options
