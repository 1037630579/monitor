"""AWS CloudWatch 监控工具 - 支持多账户多区域"""

import traceback
from datetime import datetime, timedelta, timezone
from typing import Any

from cloud_monitor.config import AWSAccountConfig
from cloud_monitor.models.metrics import DataPoint, InstanceInfo, MetricData, MetricInfo

# VPN 指标（region: vpn_region）
VPN_METRICS = {
    "TunnelState": ("VPN隧道状态", ""),
    "TunnelDataIn": ("VPN入站流量", "Bytes"),
    "TunnelDataOut": ("VPN出站流量", "Bytes"),
}

# ALB 指标（region: elb_region）
ALB_METRICS = {
    "RequestCount": ("请求数(QPS)", "Count"),
    "ActiveConnectionCount": ("活跃连接数", "Count"),
    "NewConnectionCount": ("新建连接数", "Count"),
    "ConsumedLCUs": ("消耗LCU数", "Count"),
    "ProcessedBytes": ("处理字节数", "Bytes"),
    "TargetResponseTime": ("目标平均响应延迟", "Seconds"),
    "HTTPCode_Target_2XX_Count": ("目标2xx响应", "Count"),
    "HTTPCode_Target_3XX_Count": ("目标3xx响应", "Count"),
    "HTTPCode_Target_4XX_Count": ("目标4xx响应", "Count"),
    "HTTPCode_Target_5XX_Count": ("目标5xx响应", "Count"),
    "HTTPCode_ELB_3XX_Count": ("ELB 3xx响应", "Count"),
    "HTTPCode_ELB_4XX_Count": ("ELB 4xx响应", "Count"),
    "HTTPCode_ELB_5XX_Count": ("ELB 5xx响应", "Count"),
    "HealthyHostCount": ("健康主机数", "Count"),
    "UnHealthyHostCount": ("不健康主机数", "Count"),
}

EC2_METRICS = {
    "CPUUtilization": ("CPU利用率", "Percent"),
    "NetworkIn": ("网络入流量", "Bytes"),
    "NetworkOut": ("网络出流量", "Bytes"),
    "DiskReadBytes": ("磁盘读字节", "Bytes"),
    "DiskWriteBytes": ("磁盘写字节", "Bytes"),
    "StatusCheckFailed": ("状态检查失败", "Count"),
}

S3_METRICS = {
    "BucketSizeBytes": ("存储桶大小", "Bytes"),
    "NumberOfObjects": ("对象数量", "Count"),
}

AWS_COMMON_METRICS = {
    "AWS/VPN": VPN_METRICS,
    "AWS/ApplicationELB": ALB_METRICS,
    "AWS/EC2": EC2_METRICS,
    "AWS/S3": S3_METRICS,
}

STAT_MAP = {
    "average": "Average",
    "max": "Maximum",
    "min": "Minimum",
    "sum": "Sum",
    "count": "SampleCount",
}

VPN_STATE_MAP = {0.0: "DOWN (断开)", 1.0: "UP (正常)"}


def _resolve_region(config: AWSAccountConfig, namespace: str) -> str:
    """根据 namespace 自动解析正确的 AWS 区域"""
    if namespace == "AWS/VPN":
        return config.get_vpn_region()
    if namespace == "AWS/ApplicationELB":
        return config.get_elb_region()
    return config.region


def _get_client(config: AWSAccountConfig, service: str = "cloudwatch", region: str = ""):
    import boto3
    return boto3.client(
        service,
        aws_access_key_id=config.access_key_id,
        aws_secret_access_key=config.secret_access_key,
        region_name=region or config.region,
    )


def _account_label(config: AWSAccountConfig) -> str:
    """生成账户标识前缀"""
    return f"[{config.name}] " if config.name != "default" else ""


# ──────────────── 通用指标查询 ────────────────

def list_metrics_aws(config: AWSAccountConfig, namespace: str = "", metric_name: str = "") -> str:
    """列出 AWS 可用的监控指标"""
    label = _account_label(config)
    try:
        if namespace or metric_name:
            region = _resolve_region(config, namespace) if namespace else config.region

            client = _get_client(config, region=region)
            params: dict[str, Any] = {}
            if namespace:
                params["Namespace"] = namespace
            if metric_name:
                params["MetricName"] = metric_name

            response = client.list_metrics(**params)
            metrics = response.get("Metrics", [])

            results = []
            for m in metrics:
                dims = {}
                for d in m.get("Dimensions", []):
                    dims[d["Name"]] = d["Value"]
                mi = MetricInfo(
                    cloud="AWS",
                    namespace=m["Namespace"],
                    metric_name=m["MetricName"],
                    dimensions=dims,
                )
                results.append(mi.display())

            if not results:
                return f"{label}在区域 {region} 中未找到匹配的指标"
            return f"{label}在区域 {region} 中找到 {len(results)} 个指标:\n\n" + "\n\n".join(results[:50])
        else:
            lines = [f"{label}AWS 可用监控指标 (EC2 / S3 / VPN / ALB):"]
            for ns, metrics in AWS_COMMON_METRICS.items():
                region = _resolve_region(config, ns)
                lines.append(f"\n【{ns}】(区域: {region})")
                for name, (desc, unit) in metrics.items():
                    lines.append(f"  {name}: {desc}" + (f" ({unit})" if unit else ""))
            lines.append("\n注意: CloudFront 不通过指标查询，直接用 aws_list_cloudfront 查看分发状态")
            return "\n".join(lines)
    except Exception as e:
        return f"{label}AWS 查询指标失败: {e}\n{traceback.format_exc()}"


def get_metric_data_aws(
    config: AWSAccountConfig,
    namespace: str,
    metric_name: str,
    resource_id: str,
    period: int = 60,
    stat: str = "average",
    hours: float = 1,
    dim_name: str = "VpnId",
    region: str = "",
) -> str:
    """查询 AWS CloudWatch 监控指标数据"""
    label = _account_label(config)
    try:
        query_region = region or _resolve_region(config, namespace)
        client = _get_client(config, region=query_region)
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=hours)

        stat_val = STAT_MAP.get(stat, "Average")

        response = client.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric_name,
            Dimensions=[{"Name": dim_name, "Value": resource_id}],
            StartTime=start,
            EndTime=now,
            Period=period,
            Statistics=[stat_val],
        )

        datapoints = response.get("Datapoints", [])

        desc, unit = "", ""
        metric_map = AWS_COMMON_METRICS.get(namespace, {})
        if metric_name in metric_map:
            desc, unit = metric_map[metric_name]

        result = MetricData(
            cloud="AWS",
            namespace=namespace,
            metric_name=f"{metric_name}" + (f" ({desc})" if desc else ""),
            instance_id=f"{label}{resource_id}",
            period=period,
            statistics=stat,
        )

        for dp in datapoints:
            val = dp.get(stat_val, 0)
            result.data_points.append(
                DataPoint(
                    timestamp=dp["Timestamp"].replace(tzinfo=timezone.utc)
                    if dp["Timestamp"].tzinfo is None
                    else dp["Timestamp"],
                    value=float(val),
                    unit=unit or dp.get("Unit", ""),
                )
            )

        result.data_points.sort(key=lambda x: x.timestamp)

        output = result.display() + "\n\n" + result.summary()

        if metric_name == "TunnelState" and result.data_points:
            latest = result.data_points[-1]
            state_text = VPN_STATE_MAP.get(latest.value, f"未知({latest.value})")
            output += f"\n\n🔗 VPN 隧道当前状态: {state_text}"

        return output
    except Exception as e:
        return f"{label}AWS 查询监控数据失败: {e}\n{traceback.format_exc()}"


# ──────────────── VPN 工具 ────────────────

def list_vpn_connections_aws(config: AWSAccountConfig) -> str:
    """列出 AWS VPN 连接，并自动查询每个 VPN 最近1小时每1分钟的带宽数据"""
    label = _account_label(config)
    try:
        region = config.get_vpn_region()
        client = _get_client(config, service="ec2", region=region)
        response = client.describe_vpn_connections()
        vpns = response.get("VpnConnections", [])

        if not vpns:
            return f"{label}AWS 区域 {region} 无 VPN 连接"

        results = []
        for vpn in vpns:
            vpn_id = vpn["VpnConnectionId"]
            detail = get_vpn_status_aws(config, vpn_id=vpn_id, hours=1, period=60)
            results.append(detail)

        return f"{label}在区域 {region} 找到 {len(vpns)} 个 VPN 连接:\n\n" + "\n\n".join(results)
    except Exception as e:
        return f"{label}AWS 查询 VPN 连接失败: {e}\n{traceback.format_exc()}"


def _format_bytes(value: float) -> str:
    """将字节数转为人类可读格式"""
    if value > 1_073_741_824:
        return f"{value / 1_073_741_824:.2f} GB"
    elif value > 1_048_576:
        return f"{value / 1_048_576:.2f} MB"
    elif value > 1024:
        return f"{value / 1024:.2f} KB"
    return f"{value:.0f} Bytes"


def _format_rate(bytes_per_sec: float) -> str:
    """将每秒字节数转为 bps 速率（小b，与网络监控惯例一致）"""
    bits_per_sec = bytes_per_sec * 8
    if bits_per_sec > 1_000_000_000:
        return f"{bits_per_sec / 1_000_000_000:.2f} Gb/s"
    elif bits_per_sec > 1_000_000:
        return f"{bits_per_sec / 1_000_000:.2f} Mb/s"
    elif bits_per_sec > 1_000:
        return f"{bits_per_sec / 1_000:.2f} Kb/s"
    return f"{bits_per_sec:.0f} b/s"


def get_vpn_status_aws(config: AWSAccountConfig, vpn_id: str = "", hours: float = 1, period: int = 60) -> str:
    """查询 AWS VPN 带宽使用情况：最新采样点 + 时间趋势表格 + 小结"""
    label = _account_label(config)
    try:
        region = config.get_vpn_region()
        ec2 = _get_client(config, service="ec2", region=region)
        cw = _get_client(config, region=region)

        params: dict[str, Any] = {}
        if vpn_id:
            params["VpnConnectionIds"] = [vpn_id]

        response = ec2.describe_vpn_connections(**params)
        vpns = response.get("VpnConnections", [])

        if not vpns:
            return f"{label}在区域 {region} 未找到 VPN 连接" + (f" {vpn_id}" if vpn_id else "")

        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=hours)
        time_label = f"{hours:.0f}小时" if hours >= 1 else f"{hours * 60:.0f}分钟"

        display_period = period
        interval_label = f"{display_period // 60} 分钟" if display_period >= 60 else f"{display_period} 秒"

        results = []

        for vpn in vpns:
            vpn_conn_id = vpn["VpnConnectionId"]
            name = ""
            for tag in vpn.get("Tags", []):
                if tag["Key"] == "Name":
                    name = tag["Value"]
                    break

            lines = [f"━━━ {label}VPN: {vpn_conn_id}" + (f" ({name})" if name else "") + f" [区域: {region}] ━━━"]
            lines.append(f"  连接状态: {vpn.get('State', '未知')}")
            lines.append(f"  客户网关: {vpn.get('CustomerGatewayId', '')}")
            lines.append(f"  虚拟专用网关: {vpn.get('VpnGatewayId', '') or vpn.get('TransitGatewayId', '')}")

            for i, tunnel in enumerate(vpn.get("VgwTelemetry", [])):
                status = tunnel.get("Status", "未知")
                status_icon = "🟢" if status == "UP" else "🔴"
                lines.append(f"\n  {status_icon} 隧道 {i+1}: {status}  外部IP: {tunnel.get('OutsideIpAddress', '')}  路由数: {tunnel.get('AcceptedRouteCount', 0)}")

            in_data: list[dict] = []
            out_data: list[dict] = []

            for metric, storage in [("TunnelDataIn", in_data), ("TunnelDataOut", out_data)]:
                try:
                    resp = cw.get_metric_statistics(
                        Namespace="AWS/VPN",
                        MetricName=metric,
                        Dimensions=[{"Name": "VpnId", "Value": vpn_conn_id}],
                        StartTime=start,
                        EndTime=now,
                        Period=display_period,
                        Statistics=["Sum"],
                    )
                    dps = resp.get("Datapoints", [])
                    if dps:
                        sorted_dps = sorted(dps, key=lambda x: x["Timestamp"])
                        for dp in sorted_dps:
                            ts = dp["Timestamp"]
                            if ts.tzinfo is None:
                                ts = ts.replace(tzinfo=timezone.utc)
                            rate_bytes = dp.get("Sum", 0) / display_period
                            rate_mbps = rate_bytes * 8 / 1_000_000
                            storage.append({"ts": ts, "mbps": rate_mbps, "bytes": dp.get("Sum", 0)})
                except Exception:
                    pass

            if in_data or out_data:
                latest_in = in_data[-1]["mbps"] if in_data else 0
                latest_out = out_data[-1]["mbps"] if out_data else 0
                lines.append(f"\n  ## 最新采样点")
                lines.append(f"  | 方向 | 带宽 |")
                lines.append(f"  |------|------|")
                lines.append(f"  | 入方向 (rx) | {latest_in:.1f} Mbps |")
                lines.append(f"  | 出方向 (tx) | {latest_out:.1f} Mbps |")

                ts_set: dict[str, dict] = {}
                for dp in in_data:
                    key = dp["ts"].strftime("%H:%M")
                    ts_set.setdefault(key, {"in": 0, "out": 0})
                    ts_set[key]["in"] = dp["mbps"]
                for dp in out_data:
                    key = dp["ts"].strftime("%H:%M")
                    ts_set.setdefault(key, {"in": 0, "out": 0})
                    ts_set[key]["out"] = dp["mbps"]

                sorted_times = sorted(ts_set.keys())

                lines.append(f"\n  ## 最近 {time_label} 趋势（{interval_label}粒度）")
                lines.append(f"  | 时间 (UTC) | 入方向 (Mbps) | 出方向 (Mbps) |")
                lines.append(f"  |------------|---------------|---------------|")
                for t in sorted_times:
                    v = ts_set[t]
                    lines.append(f"  | {t} | {v['in']:.1f} | {v['out']:.1f} |")

                in_rates = [d["mbps"] for d in in_data] if in_data else [0]
                out_rates = [d["mbps"] for d in out_data] if out_data else [0]
                in_avg = sum(in_rates) / len(in_rates)
                out_avg = sum(out_rates) / len(out_rates)
                in_peak = max(in_rates)
                out_peak = max(out_rates)
                in_min = min(in_rates)
                out_min = min(out_rates)

                total_in_bytes = sum(d["bytes"] for d in in_data)
                total_out_bytes = sum(d["bytes"] for d in out_data)

                lines.append(f"\n  ## 小结")
                lines.append(f"  - 入方向带宽：最近{time_label}在 {in_min:.1f}~{in_peak:.1f} Mbps 之间，平均 {in_avg:.1f} Mbps，总流量 {_format_bytes(total_in_bytes)}")
                lines.append(f"  - 出方向带宽：最近{time_label}在 {out_min:.1f}~{out_peak:.1f} Mbps 之间，平均 {out_avg:.1f} Mbps，总流量 {_format_bytes(total_out_bytes)}")

                if out_avg > in_avg * 1.5:
                    lines.append(f"  - 出方向流量是入方向的 {out_avg / in_avg:.1f} 倍，数据主要从本端向对端传输")
                elif in_avg > out_avg * 1.5:
                    lines.append(f"  - 入方向流量是出方向的 {in_avg / out_avg:.1f} 倍，数据主要从对端向本端传输")
                else:
                    lines.append(f"  - 入出方向流量相对均衡")

                if in_peak > 800 or out_peak > 800:
                    lines.append(f"  - ⚠️ 峰值带宽已超过 800 Mbps，接近 1000M 规格上限，建议关注")
                elif in_peak > 500 or out_peak > 500:
                    lines.append(f"  - 带宽使用率中等，峰值达到网关规格的 {max(in_peak, out_peak) / 10:.0f}%")
            else:
                lines.append(f"\n  📊 最近{time_label}无流量数据")

            results.append("\n".join(lines))

        return "\n\n".join(results)
    except Exception as e:
        return f"{label}AWS 查询 VPN 状态失败: {e}\n{traceback.format_exc()}"


# ──────────────── EC2 云主机（支持多区域）────────────────

def list_ec2_instances_aws(config: AWSAccountConfig, region: str = "") -> str:
    """列出 AWS EC2 实例概览：按区域统计总数和运行/停止数，仅输出已停止实例的详情"""
    label = _account_label(config)
    query_regions = [region] if region else config.get_regions()

    region_stats: dict[str, dict[str, int]] = {}
    stopped_details: list[str] = []
    total = 0

    for r in query_regions:
        stats = {"running": 0, "stopped": 0, "other": 0}
        try:
            client = _get_client(config, service="ec2", region=r)
            response = client.describe_instances()
            for reservation in response.get("Reservations", []):
                for inst in reservation.get("Instances", []):
                    state = inst.get("State", {}).get("Name", "")
                    total += 1

                    if state == "running":
                        stats["running"] += 1
                    elif state == "stopped":
                        stats["stopped"] += 1
                        name = ""
                        tags_list = []
                        for tag in inst.get("Tags", []):
                            if tag["Key"] == "Name":
                                name = tag["Value"]
                            else:
                                tags_list.append(f"{tag['Key']}={tag['Value']}")

                        extra: dict[str, str] = {
                            "区域": r,
                            "可用区": inst.get("Placement", {}).get("AvailabilityZone", ""),
                            "实例类型": inst.get("InstanceType", ""),
                            "私有IP": inst.get("PrivateIpAddress", ""),
                            "公网IP": inst.get("PublicIpAddress", "无"),
                        }

                        launch_time = inst.get("LaunchTime", "")
                        if hasattr(launch_time, "strftime"):
                            extra["最后启动"] = launch_time.strftime("%Y-%m-%d %H:%M")
                            now = datetime.now(timezone.utc)
                            lt = launch_time if launch_time.tzinfo else launch_time.replace(tzinfo=timezone.utc)
                            days = (now - lt).days
                            if days > 365:
                                extra["距今"] = f"{days // 365}年{days % 365}天"
                            else:
                                extra["距今"] = f"{days}天"

                        reason = inst.get("StateTransitionReason", "")
                        if reason:
                            extra["停止原因"] = reason

                        # EBS 卷
                        volumes = inst.get("BlockDeviceMappings", [])
                        if volumes:
                            vol_ids = [v.get("Ebs", {}).get("VolumeId", "") for v in volumes if v.get("Ebs")]
                            extra["EBS卷"] = ", ".join(vol_ids) if vol_ids else "无"
                            extra["EBS卷数"] = str(len(vol_ids))

                        # 安全组
                        sgs = inst.get("SecurityGroups", [])
                        if sgs:
                            extra["安全组"] = ", ".join(f"{sg.get('GroupName', '')}({sg.get('GroupId', '')})" for sg in sgs[:3])

                        # 标签
                        if tags_list:
                            extra["标签"] = ", ".join(tags_list[:5])

                        info = InstanceInfo(
                            cloud="AWS", instance_id=inst["InstanceId"], instance_name=name,
                            instance_type=inst.get("InstanceType", ""),
                            status="🔴 stopped", region=r, extra=extra,
                        )
                        stopped_details.append(info.display())
                    else:
                        stats["other"] += 1
        except Exception as e:
            stopped_details.append(f"区域 {r} 查询失败: {e}")

        region_stats[r] = stats

    region_desc = ", ".join(query_regions)
    if total == 0:
        return f"{label}AWS 区域 [{region_desc}] 无 EC2 实例"

    total_running = sum(s["running"] for s in region_stats.values())
    total_stopped = sum(s["stopped"] for s in region_stats.values())

    lines = [f"{label}📊 EC2 实例概览 [区域: {region_desc}]"]
    lines.append(f"  总计: {total} 个实例 | 运行中: {total_running} | 已停止: {total_stopped}")
    for r, s in region_stats.items():
        r_total = s["running"] + s["stopped"] + s["other"]
        lines.append(f"  {r}: {r_total} 个 (运行: {s['running']}, 停止: {s['stopped']})")

    if stopped_details:
        lines.append(f"\n🔴 已停止实例详情 ({total_stopped} 个):")
        lines.extend(stopped_details)
    else:
        lines.append("\n✅ 无已停止实例")

    return "\n\n".join(lines)


def list_idle_ec2_aws(config: AWSAccountConfig, cpu_threshold: float = 5.0, hours: float = 24) -> str:
    """检测 AWS EC2 闲置实例：已停止的 + CPU利用率低于阈值的运行中实例"""
    label = _account_label(config)
    query_regions = config.get_regions()

    stopped_instances = []
    low_cpu_instances = []
    running_count = 0

    for r in query_regions:
        try:
            ec2 = _get_client(config, service="ec2", region=r)
            cw = _get_client(config, region=r)

            response = ec2.describe_instances()
            for reservation in response.get("Reservations", []):
                for inst in reservation.get("Instances", []):
                    state = inst.get("State", {}).get("Name", "")
                    inst_id = inst["InstanceId"]
                    inst_type = inst.get("InstanceType", "")

                    name = ""
                    for tag in inst.get("Tags", []):
                        if tag["Key"] == "Name":
                            name = tag["Value"]
                            break

                    base_info = {
                        "区域": r,
                        "可用区": inst.get("Placement", {}).get("AvailabilityZone", ""),
                        "实例类型": inst_type,
                        "私有IP": inst.get("PrivateIpAddress", ""),
                        "公网IP": inst.get("PublicIpAddress", "无"),
                    }

                    if state == "stopped":
                        launch_time = inst.get("LaunchTime", "")
                        if hasattr(launch_time, "strftime"):
                            base_info["最后启动"] = launch_time.strftime("%Y-%m-%d %H:%M")
                        reason = inst.get("StateTransitionReason", "")
                        if reason:
                            base_info["停止原因"] = reason
                        info = InstanceInfo(
                            cloud="AWS", instance_id=inst_id, instance_name=name,
                            instance_type=inst_type, status="🔴 stopped", region=r,
                            extra=base_info,
                        )
                        stopped_instances.append(info.display())
                        continue

                    if state != "running":
                        continue

                    running_count += 1

                    try:
                        now = datetime.now(timezone.utc)
                        start = now - timedelta(hours=hours)
                        resp = cw.get_metric_statistics(
                            Namespace="AWS/EC2", MetricName="CPUUtilization",
                            Dimensions=[{"Name": "InstanceId", "Value": inst_id}],
                            StartTime=start, EndTime=now,
                            Period=3600, Statistics=["Average"],
                        )
                        dps = resp.get("Datapoints", [])
                        if dps:
                            avg_cpu = sum(dp.get("Average", 0) for dp in dps) / len(dps)
                            max_cpu = max(dp.get("Average", 0) for dp in dps)

                            if avg_cpu < cpu_threshold:
                                base_info[f"平均CPU({hours:.0f}h)"] = f"{avg_cpu:.2f}%"
                                base_info["最高CPU"] = f"{max_cpu:.2f}%"
                                base_info["数据点数"] = str(len(dps))
                                info = InstanceInfo(
                                    cloud="AWS", instance_id=inst_id, instance_name=name,
                                    instance_type=inst_type, status=f"⚠️ 疑似闲置 (CPU {avg_cpu:.1f}%)", region=r,
                                    extra=base_info,
                                )
                                low_cpu_instances.append(info.display())
                    except Exception:
                        pass

        except Exception as e:
            stopped_instances.append(f"区域 {r} 查询失败: {e}")

    region_desc = ", ".join(query_regions)
    lines = [f"{label}📊 EC2 闲置资源检测 [区域: {region_desc}]"]
    lines.append(f"  检测条件: 已停止 或 CPU < {cpu_threshold}% (最近{hours:.0f}小时)")
    lines.append(f"  运行中实例总数: {running_count}")
    lines.append(f"  已停止实例: {len(stopped_instances)} 个")
    lines.append(f"  低CPU实例: {len(low_cpu_instances)} 个")

    if stopped_instances:
        lines.append(f"\n🔴 已停止的实例 ({len(stopped_instances)} 个):")
        lines.extend(stopped_instances)

    if low_cpu_instances:
        lines.append(f"\n⚠️ 疑似闲置实例 - CPU < {cpu_threshold}% ({len(low_cpu_instances)} 个):")
        lines.extend(low_cpu_instances)

    if not stopped_instances and not low_cpu_instances:
        lines.append("\n✅ 未发现闲置实例")

    return "\n\n".join(lines)


# ──────────────── S3 对象存储 ────────────────

def list_s3_buckets_aws(config: AWSAccountConfig, region: str = "") -> str:
    """列出 AWS S3 存储桶，自动获取每个桶的区域。可按 region 过滤"""
    label = _account_label(config)
    try:
        client = _get_client(config, service="s3")
        response = client.list_buckets()
        buckets = response.get("Buckets", [])

        if not buckets:
            return f"{label}AWS 无 S3 存储桶"

        results = []
        region_counts: dict[str, int] = {}

        for b in buckets:
            bucket_name = b["Name"]
            bucket_region = "us-east-1"
            try:
                loc = client.get_bucket_location(Bucket=bucket_name)
                loc_constraint = loc.get("LocationConstraint")
                if loc_constraint:
                    bucket_region = loc_constraint
            except Exception:
                bucket_region = "unknown"

            if region and bucket_region != region:
                continue

            region_counts[bucket_region] = region_counts.get(bucket_region, 0) + 1

            created = b.get("CreationDate", "")
            if hasattr(created, "strftime"):
                created = created.strftime("%Y-%m-%d %H:%M")
            info = InstanceInfo(
                cloud="AWS", instance_id=bucket_name, instance_name=bucket_name,
                instance_type="S3 Bucket", status="active", region=bucket_region,
                extra={"创建时间": str(created)},
            )
            results.append(info.display())

        if not results:
            return f"{label}AWS 无 S3 存储桶" + (f"（区域 {region}）" if region else "")

        summary_parts = [f"{r}: {c}个" for r, c in sorted(region_counts.items())]
        header = f"{label}找到 {len(results)} 个 S3 存储桶"
        if region:
            header += f"（区域: {region}）"
        else:
            header += f"（区域分布: {', '.join(summary_parts)}）"

        return header + ":\n\n" + "\n\n".join(results)
    except Exception as e:
        return f"{label}AWS 查询 S3 存储桶失败: {e}\n{traceback.format_exc()}"


# ──────────────── CloudFront CDN（全局服务）────────────────

def _format_cf_item(d: dict, detailed: bool = False) -> str:
    """格式化单个 CloudFront 分发条目"""
    aliases = d.get("Aliases", {}).get("Items", [])
    origins = [o.get("DomainName", "") for o in d.get("Origins", {}).get("Items", [])]
    extra: dict[str, str] = {
        "域名": d.get("DomainName", ""),
        "别名": ", ".join(aliases) if aliases else "无",
        "源站": ", ".join(origins[:3]),
        "启用": "是" if d.get("Enabled") else "否",
    }
    if detailed:
        last_modified = d.get("LastModifiedTime", "")
        if hasattr(last_modified, "strftime"):
            last_modified = last_modified.strftime("%Y-%m-%d %H:%M")
        comment = d.get("Comment", "")
        extra["最后修改"] = str(last_modified) if last_modified else "未知"
        extra["价格等级"] = d.get("PriceClass", "").replace("PriceClass_", "")
        extra["HTTP版本"] = d.get("HttpVersion", "")
        extra["IPv6"] = "是" if d.get("IsIPV6Enabled") else "否"
        waf = d.get("WebACLId", "")
        extra["WAF"] = waf.split("/")[-1] if waf else "无"
        if comment:
            extra["备注"] = comment
        cert = d.get("ViewerCertificate", {})
        cert_source = cert.get("CertificateSource", "")
        if cert_source == "acm":
            extra["证书"] = "ACM"
        elif cert_source == "iam":
            extra["证书"] = "IAM"
        else:
            extra["证书"] = "CloudFront默认"
    info = InstanceInfo(
        cloud="AWS", instance_id=d["Id"],
        instance_name=", ".join(aliases) if aliases else d.get("DomainName", ""),
        instance_type="CloudFront", status=d.get("Status", ""), region="global",
        extra=extra,
    )
    return info.display()


def list_cloudfront_distributions_aws(config: AWSAccountConfig, status_filter: str = "") -> str:
    """列出 AWS CloudFront CDN 分发

    Args:
        status_filter: 过滤条件 - "disabled" 仅禁用, "enabled" 仅启用, 空字符串返回全部(含概览)
    """
    label = _account_label(config)
    try:
        client = _get_client(config, service="cloudfront", region="us-east-1")
        response = client.list_distributions()
        dist_list = response.get("DistributionList", {})
        all_items = dist_list.get("Items", [])

        if not all_items:
            return f"{label}AWS 无 CloudFront 分发"

        enabled_items = [d for d in all_items if d.get("Enabled")]
        disabled_items = [d for d in all_items if not d.get("Enabled")]

        if status_filter == "disabled":
            if not disabled_items:
                return f"{label}AWS 无已禁用的 CloudFront 分发"
            results = [_format_cf_item(d, detailed=True) for d in disabled_items]
            return f"{label}找到 {len(results)} 个已禁用的 CloudFront 分发:\n\n" + "\n\n".join(results)

        if status_filter == "enabled":
            if not enabled_items:
                return f"{label}AWS 无已启用的 CloudFront 分发"
            results = [_format_cf_item(d) for d in enabled_items]
            return f"{label}找到 {len(results)} 个已启用的 CloudFront 分发:\n\n" + "\n\n".join(results)

        lines = [
            f"{label}📊 CloudFront CDN 分发概览",
            f"  总计: {len(all_items)} 个分发",
            f"  已启用: {len(enabled_items)} 个",
            f"  已禁用: {len(disabled_items)} 个",
        ]

        if disabled_items:
            lines.append(f"\n⚠️ 已禁用的分发详情 ({len(disabled_items)} 个):")
            for d in disabled_items:
                lines.append(_format_cf_item(d, detailed=True))

        if enabled_items:
            lines.append(f"\n✅ 已启用的分发列表 ({len(enabled_items)} 个):")
            for d in enabled_items:
                lines.append(_format_cf_item(d))

        return "\n\n".join(lines)
    except Exception as e:
        return f"{label}AWS 查询 CloudFront 分发失败: {e}\n{traceback.format_exc()}"


# ──────────────── ALB ────────────────

def list_elb_aws(config: AWSAccountConfig) -> str:
    """列出 AWS ALB 负载均衡器"""
    label = _account_label(config)
    try:
        region = config.get_elb_region()
        results = []
        try:
            elbv2_client = _get_client(config, service="elbv2", region=region)
            resp = elbv2_client.describe_load_balancers()

            alb_list = [lb for lb in resp.get("LoadBalancers", []) if lb.get("Type") == "application"]

            tags_map: dict[str, list] = {}
            if alb_list:
                lb_arns = [lb["LoadBalancerArn"] for lb in alb_list]
                for i in range(0, len(lb_arns), 20):
                    batch = lb_arns[i:i+20]
                    try:
                        tags_resp = elbv2_client.describe_tags(ResourceArns=batch)
                        for td in tags_resp.get("TagDescriptions", []):
                            tags_map[td["ResourceArn"]] = td.get("Tags", [])
                    except Exception:
                        pass

            for lb in alb_list:
                arn = lb.get("LoadBalancerArn", "")
                lb_dim = "/".join(arn.split("/")[-3:]) if arn.count("/") >= 3 else lb.get("LoadBalancerName", "")

                name = lb.get("LoadBalancerName", "")
                tags = tags_map.get(arn, [])
                for tag in tags:
                    if tag.get("Key") == "Name":
                        name = tag["Value"]
                        break

                info = InstanceInfo(
                    cloud="AWS",
                    instance_id=lb_dim,
                    instance_name=lb.get("LoadBalancerName", ""),
                    instance_type="ALB",
                    status=lb.get("State", {}).get("Code", ""),
                    region=region,
                    extra={
                        "DNS": lb.get("DNSName", ""),
                        "ARN": arn,
                        "Scheme": lb.get("Scheme", ""),
                    },
                )
                results.append(info.display())
        except Exception:
            pass

        if not results:
            return f"{label}AWS 区域 {region} 无负载均衡器"

        return f"{label}在区域 {region} 找到 {len(results)} 个负载均衡器:\n\n" + "\n\n".join(results)
    except Exception as e:
        return f"{label}AWS 查询负载均衡器失败: {e}\n{traceback.format_exc()}"
