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
            get_metric_data_aws,
            get_vpn_status_aws,
            list_cloudfront_distributions_aws,
            list_ec2_instances_aws,
            list_elb_aws,
            list_idle_ec2_aws,
            list_metrics_aws,
            list_s3_buckets_aws,
            list_vpn_connections_aws,
        )

        aws_cfg = config.aws

        def _get_accounts(account_name: str) -> list[AWSAccountConfig]:
            """根据 account 参数获取账户列表：空=全部，指定名称=单个"""
            if not account_name:
                return aws_cfg.accounts
            return [aws_cfg.get_account(account_name)]

        def _run_for_accounts(account_name: str, fn, **kwargs) -> str:
            """对一个或多个账户执行函数并合并结果"""
            accounts = _get_accounts(account_name)
            parts = []
            for acc in accounts:
                parts.append(fn(acc, **kwargs))
            return "\n\n".join(parts)

        # ── 列出账户 ──
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
                if acc.elb_region:
                    lines.append(f"    ALB区域: {acc.elb_region}")
            return {"content": [{"type": "text", "text": "\n".join(lines)}]}

        # ── 通用指标 ──
        @tool(
            "aws_list_metrics",
            "列出 AWS CloudWatch 可用的监控指标。account: 账户名(空=所有账户)。namespace: AWS/EC2, AWS/S3, AWS/VPN, AWS/ApplicationELB",
            {"account": str, "namespace": str, "metric_name": str},
        )
        async def aws_list_metrics_tool(args: dict[str, Any]) -> dict[str, Any]:
            result = _run_for_accounts(args.get("account", ""), list_metrics_aws,
                                       namespace=args.get("namespace", ""), metric_name=args.get("metric_name", ""))
            return {"content": [{"type": "text", "text": result}]}

        @tool(
            "aws_get_metric_data",
            "查询 AWS CloudWatch 指定资源的监控指标数据。account: 账户名(空=默认账户)。dim_name: EC2用InstanceId, S3用BucketName, VPN用VpnId, ALB用LoadBalancer。period固定60秒。region: 可选指定区域",
            {"account": str, "namespace": str, "metric_name": str, "resource_id": str, "period": int, "stat": str, "hours": float, "dim_name": str, "region": str},
        )
        async def aws_get_metric_data_tool(args: dict[str, Any]) -> dict[str, Any]:
            acc = aws_cfg.get_account(args.get("account", ""))
            result = get_metric_data_aws(
                acc, namespace=args["namespace"], metric_name=args["metric_name"], resource_id=args["resource_id"],
                period=args.get("period", 60), stat=args.get("stat", "average"), hours=args.get("hours", 1),
                dim_name=args.get("dim_name", "InstanceId"), region=args.get("region", ""),
            )
            return {"content": [{"type": "text", "text": result}]}

        # ── EC2 云主机（支持多区域）──
        @tool(
            "aws_list_ec2",
            "列出 AWS EC2 云主机实例。account: 账户名(空=所有账户)。region: 指定单个区域(空=遍历账户配置的所有区域)",
            {"account": str, "region": str},
        )
        async def aws_list_ec2_tool(args: dict[str, Any]) -> dict[str, Any]:
            result = _run_for_accounts(args.get("account", ""), list_ec2_instances_aws,
                                       region=args.get("region", ""))
            return {"content": [{"type": "text", "text": result}]}

        # ── EC2 闲置检测 ──
        @tool(
            "aws_idle_ec2",
            "检测 AWS EC2 闲置实例：列出所有已停止的实例和CPU利用率低于阈值的运行中实例（含详细信息）。account: 账户名(空=所有账户)。cpu_threshold: CPU阈值百分比(默认5)。hours: 检测时间范围(默认24小时)",
            {"account": str, "cpu_threshold": float, "hours": float},
        )
        async def aws_idle_ec2_tool(args: dict[str, Any]) -> dict[str, Any]:
            result = _run_for_accounts(args.get("account", ""), list_idle_ec2_aws,
                                       cpu_threshold=args.get("cpu_threshold", 5.0),
                                       hours=args.get("hours", 24))
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

        # ── CloudFront CDN（全局）──
        @tool(
            "aws_list_cloudfront",
            "列出 AWS CloudFront CDN 分发。account: 账户名(空=所有账户)。status_filter: 'disabled'=仅禁用, 'enabled'=仅启用, ''=全部",
            {"account": str, "status_filter": str},
        )
        async def aws_list_cloudfront_tool(args: dict[str, Any]) -> dict[str, Any]:
            result = _run_for_accounts(args.get("account", ""), list_cloudfront_distributions_aws,
                                       status_filter=args.get("status_filter", ""))
            return {"content": [{"type": "text", "text": result}]}

        # ── VPN ──
        @tool("aws_list_vpn", "列出 AWS VPN 连接列表，包含隧道状态。account: 账户名(空=所有账户)", {"account": str})
        async def aws_list_vpn_tool(args: dict[str, Any]) -> dict[str, Any]:
            result = _run_for_accounts(args.get("account", ""), list_vpn_connections_aws)
            return {"content": [{"type": "text", "text": result}]}

        @tool(
            "aws_vpn_status",
            "查询 AWS VPN 详细状态：隧道UP/DOWN、总流量、平均速率(Mb/s)、峰值速率、趋势。account: 账户名(空=默认)。vpn_id 可选。hours 默认1小时，period 固定60秒",
            {"account": str, "vpn_id": str, "hours": float, "period": int},
        )
        async def aws_vpn_status_tool(args: dict[str, Any]) -> dict[str, Any]:
            acc = aws_cfg.get_account(args.get("account", ""))
            result = get_vpn_status_aws(acc, vpn_id=args.get("vpn_id", ""), hours=args.get("hours", 1), period=args.get("period", 60))
            return {"content": [{"type": "text", "text": result}]}

        # ── ALB ──
        @tool("aws_list_elb", "列出 AWS ALB 负载均衡器列表。account: 账户名(空=所有账户)", {"account": str})
        async def aws_list_elb_tool(args: dict[str, Any]) -> dict[str, Any]:
            result = _run_for_accounts(args.get("account", ""), list_elb_aws)
            return {"content": [{"type": "text", "text": result}]}

        tools.extend([
            aws_list_accounts_tool,
            aws_list_metrics_tool,
            aws_get_metric_data_tool,
            aws_list_ec2_tool,
            aws_idle_ec2_tool,
            aws_list_s3_tool,
            aws_list_cloudfront_tool,
            aws_list_vpn_tool,
            aws_vpn_status_tool,
            aws_list_elb_tool,
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
            "aws_list_metrics", "aws_get_metric_data",
            "aws_list_ec2", "aws_idle_ec2", "aws_list_s3", "aws_list_cloudfront",
            "aws_list_vpn", "aws_vpn_status", "aws_list_elb",
        ]])

    return allowed


SYSTEM_PROMPT = """\
你是一个多云治理监控助手，帮助用户统一掌握阿里云、华为云、AWS 三大云平台的资源使用情况、发现闲置浪费、优化云成本。

# 工具映射

多云监控助手提供的资源查询工具，格式保持一致：

| 资源类型 | 阿里云 | 华为云 | AWS |
|---------|--------|--------|-----|
| 云主机   | aliyun_list_ecs | huawei_list_ecs | aws_list_ec2 |
| 对象存储 | aliyun_list_oss | huawei_list_obs | aws_list_s3 |
| CDN     | aliyun_list_cdn | huawei_list_cdn | aws_list_cloudfront |
| 指标列表 | aliyun_list_metrics | huawei_list_metrics | aws_list_metrics |
| 指标数据 | aliyun_get_metric_data | huawei_get_metric_data | aws_get_metric_data |

AWS 独有工具：aws_list_accounts, aws_idle_ec2, aws_list_vpn, aws_vpn_status, aws_list_elb

# 查询决策

当用户查询"所有云"或未指定平台时，依次调用各启用平台的对应工具。
当用户指定某个平台或服务时，只调用对应工具。

- 查云主机 → 调用 *_list_ecs / aws_list_ec2
- 查对象存储 → 调用 *_list_oss / *_list_obs / aws_list_s3
- 查 CDN → 调用 *_list_cdn / aws_list_cloudfront
- 查闲置资源 → 优先 aws_idle_ec2（自动检测停止+低CPU实例）
- 查 VPN → aws_list_vpn + aws_vpn_status
- 查 ALB → aws_list_elb + aws_get_metric_data

# AWS 多账户与多区域

- 每个 AWS 工具都有 account 参数，不传 = 查询所有账户
- EC2/S3 自动遍历账户配置的所有 regions
- VPN 使用 vpn_region，ALB 使用 elb_region，CloudFront 为全局服务

# AWS CloudWatch 参数

| 服务 | namespace | dim_name | 备注 |
|------|-----------|----------|------|
| EC2 | AWS/EC2 | InstanceId | period=60 |
| S3 | AWS/S3 | BucketName | BucketSizeBytes/NumberOfObjects 需额外维度 StorageType=StandardStorage, period≥86400 |
| VPN | AWS/VPN | VpnId | 查流量用 stat=sum, period=60 |
| ALB | AWS/ApplicationELB | LoadBalancer | 格式 app/lb-name/id, period=60 |
| CloudFront | 不查 CloudWatch | - | 仅通过 aws_list_cloudfront 查看状态 |

# 成本估算（官方按需价格）

对每个查询到的资源，根据实例类型和区域估算月度成本，在输出中标注。月度 = 小时价 × 730h。

## AWS 官方按需价格（us-east-1, Linux）

EC2 实例（小时价 → 月估）：
| 类型 | 配置 | 小时价 | 月估 |
|------|------|--------|------|
| t3.micro | 2vCPU/1GiB | $0.0104/h | $7.59 |
| t3.small | 2vCPU/2GiB | $0.0208/h | $15.18 |
| t3.medium | 2vCPU/4GiB | $0.0416/h | $30.37 |
| t3.large | 2vCPU/8GiB | $0.0832/h | $60.74 |
| t3.xlarge | 4vCPU/16GiB | $0.1664/h | $121.47 |
| t3.2xlarge | 8vCPU/32GiB | $0.3328/h | $242.94 |
| m5.xlarge | 4vCPU/16GiB | $0.192/h | $140.16 |
| m5.2xlarge | 8vCPU/32GiB | $0.384/h | $280.32 |
| c5.xlarge | 4vCPU/8GiB | $0.17/h | $124.10 |
| c5.2xlarge | 8vCPU/16GiB | $0.34/h | $248.20 |
| c5.4xlarge | 16vCPU/32GiB | $0.68/h | $496.40 |
| c5.9xlarge | 36vCPU/72GiB | $1.53/h | $1,116.90 |
| p3dn.24xlarge | 96vCPU/768GiB/8×V100 | $31.212/h | $22,784.76 |

存储与网络：
- EBS gp3：$0.08/GB/月（含 3000 IOPS + 125MB/s）
- S3 标准存储：$0.023/GB/月（前 50TB）、$0.022/GB/月（50-500TB）
- CloudFront 出站流量：$0.085/GB（前 10TB）、$0.060/GB（10-50TB）
- 公网 IPv4 地址（含空闲 EIP）：$0.005/IP/h → $3.65/月/个
- NAT Gateway：$0.045/h → $32.85/月 + $0.045/GB 数据处理费

## 阿里云官方按需价格

ECS 实例（按量付费，小时价 → 月估）：
| 类型 | 配置 | 小时价 | 月估 |
|------|------|--------|------|
| ecs.t6 | 2vCPU/2GiB | ¥0.118/h | ¥86 |
| 通用型 | 2vCPU/4GiB | ¥0.225~0.351/h | ¥164~256 |
| 通用型 | 4vCPU/8GiB | ¥0.45~0.88/h | ¥329~642 |
| 通用型 | 4vCPU/16GiB | ¥0.675~1.05/h | ¥493~767 |
| 通用型 | 8vCPU/32GiB | ¥1.35~2.09/h | ¥986~1,526 |

存储与 CDN：
- OSS 标准存储（单AZ）：¥0.09/GB/月
- OSS 标准存储（多AZ）：¥0.12/GB/月
- OSS 低频存储：¥0.06/GB/月（最少存 30 天）
- CDN 流量（中国大陆）：¥0.24/GB（前 10TB）、¥0.23/GB（10-50TB）

## 华为云官方按需价格

ECS 实例（按需，小时价 → 月估）：
| 类型 | 配置 | 小时价 | 月估 |
|------|------|--------|------|
| s6.small.1 | 1vCPU/1GiB | ¥0.07/h | ¥51 |
| s6.medium.2 | 1vCPU/2GiB | ¥0.17/h | ¥124 |
| c6s.large.2 | 2vCPU/4GiB | ¥0.37/h | ¥270 |
| c6s.xlarge.2 | 4vCPU/8GiB | ¥0.74/h | ¥540 |

存储与 CDN：
- OBS 标准存储（单AZ）：¥0.099/GB/月
- OBS 低频存储：¥0.06/GB/月
- CDN 流量（中国大陆）：¥0.35/GB（标准），超 100TB 降至 ¥0.25/GB

价格说明：以上均为官方公布的按需/按量付费价格，实际费用可能因计费方式（包年包月/RI/Savings Plans）、区域差异和用量折扣而不同。无法精确匹配实例类型时，标注"预估"并给出区间。

# 输出规范

1. 始终用中文回答，数据必须附带单位
2. 多云结果按平台分段展示，标注平台名称
3. 已停止的实例和已禁用/停用的 CDN 必须逐条列出完整详情（ID、名称、类型、区域、停止时长等），禁止省略或合并
4. **成本标注**：对每个资源标注预估月度成本；对已停止但仍产生费用的资源（如 EBS 存储、弹性 IP）单独标注持续费用
5. 主动告警：VPN 隧道 DOWN、ALB 5xx 错误、不健康主机
6. **成本优化建议**：在输出末尾增加「💰 成本优化建议」段落，包含：
   - 已停止实例：列出仍在产生的存储/IP 费用，建议释放或创建快照后删除磁盘
   - 低利用率实例（CPU<5%）：建议缩容到更小规格，估算节省金额
   - 闲置存储桶：建议转为低频/归档存储类型，估算节省比例
   - 禁用 CDN：建议删除无用分发，避免配置残留
   - 未使用的弹性 IP / NAT 网关：建议释放
   - 给出**月度预估可节省总金额**
7. 查询失败时说明原因并给出排查建议
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
