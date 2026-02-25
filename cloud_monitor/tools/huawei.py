"""华为云治理工具 - ECS 云主机 / OBS 对象存储 / CDN"""

import traceback
from datetime import datetime, timedelta, timezone
from typing import Any

from cloud_monitor.config import HuaweiCloudConfig
from cloud_monitor.models.metrics import DataPoint, InstanceInfo, MetricData, MetricInfo

ECS_METRICS = {
    "cpu_util": ("CPU使用率", "%"),
    "mem_util": ("内存使用率", "%"),
    "disk_util_inband": ("磁盘使用率", "%"),
    "network_incoming_bytes_rate_inband": ("入方向带宽", "Bytes/s"),
    "network_outgoing_bytes_rate_inband": ("出方向带宽", "Bytes/s"),
    "disk_read_bytes_rate": ("磁盘读速率", "Bytes/s"),
    "disk_write_bytes_rate": ("磁盘写速率", "Bytes/s"),
}

HUAWEI_COMMON_METRICS = {
    "SYS.ECS": ECS_METRICS,
}

STAT_MAP = {
    "average": "average",
    "max": "max",
    "min": "min",
    "sum": "sum",
}


def _get_ces_client(config: HuaweiCloudConfig):
    from huaweicloudsdkces.v1 import CesClient
    from huaweicloudsdkces.v1.region.ces_region import CesRegion
    from huaweicloudsdkcore.auth.credentials import BasicCredentials

    credentials = BasicCredentials(config.ak, config.sk, config.project_id)
    return (
        CesClient.new_builder()
        .with_credentials(credentials)
        .with_region(CesRegion.value_of(config.region))
        .build()
    )


# ──────────────── 通用指标查询 ────────────────

def list_metrics_huawei(config: HuaweiCloudConfig, namespace: str = "", metric_name: str = "") -> str:
    """列出华为云可用的监控指标"""
    try:
        if namespace or metric_name:
            from huaweicloudsdkces.v1.model import ListMetricsRequest
            client = _get_ces_client(config)
            request = ListMetricsRequest()
            if namespace:
                request.namespace = namespace
            if metric_name:
                request.metric_name = metric_name
            request.limit = 100
            response = client.list_metrics(request)
            metrics = response.metrics or []
            results = []
            for m in metrics:
                dims = {}
                if m.dimensions:
                    dims = {d.name: d.value for d in m.dimensions}
                mi = MetricInfo(
                    cloud="华为云",
                    namespace=m.namespace,
                    metric_name=m.metric_name,
                    unit=m.unit or "",
                    dimensions=dims,
                )
                results.append(mi.display())
            if not results:
                return "未找到匹配的指标"
            return f"找到 {len(results)} 个指标:\n\n" + "\n\n".join(results)
        else:
            lines = ["华为云可用监控指标 (ECS):"]
            for ns, metrics in HUAWEI_COMMON_METRICS.items():
                lines.append(f"\n【{ns}】")
                for name, (desc, unit) in metrics.items():
                    lines.append(f"  {name}: {desc} ({unit})")
            return "\n".join(lines)
    except Exception as e:
        return f"华为云查询指标失败: {e}\n{traceback.format_exc()}"


def get_metric_data_huawei(
    config: HuaweiCloudConfig,
    namespace: str,
    metric_name: str,
    instance_id: str,
    period: int = 300,
    stat: str = "average",
    hours: float = 1,
    dim_name: str = "instance_id",
) -> str:
    """查询华为云监控指标数据"""
    try:
        from huaweicloudsdkces.v1.model import ShowMetricDataRequest

        client = _get_ces_client(config)
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=hours)

        request = ShowMetricDataRequest()
        request.namespace = namespace
        request.metric_name = metric_name
        request.dim_0 = f"{dim_name},{instance_id}"
        request.period = period
        request.filter = STAT_MAP.get(stat, "average")
        request.from_ = int(start.timestamp() * 1000)
        request.to = int(now.timestamp() * 1000)

        response = client.show_metric_data(request)
        datapoints = response.datapoints or []

        desc, unit = "", ""
        if namespace in HUAWEI_COMMON_METRICS:
            if metric_name in HUAWEI_COMMON_METRICS[namespace]:
                desc, unit = HUAWEI_COMMON_METRICS[namespace][metric_name]

        result = MetricData(
            cloud="华为云",
            namespace=namespace,
            metric_name=f"{metric_name}" + (f" ({desc})" if desc else ""),
            instance_id=instance_id,
            period=period,
            statistics=stat,
        )

        for dp in datapoints:
            val = getattr(dp, stat, None) or getattr(dp, "average", 0)
            result.data_points.append(
                DataPoint(
                    timestamp=datetime.fromtimestamp(dp.timestamp / 1000, tz=timezone.utc),
                    value=float(val),
                    unit=unit,
                )
            )

        result.data_points.sort(key=lambda x: x.timestamp)
        return result.display() + "\n\n" + result.summary()
    except Exception as e:
        return f"华为云查询监控数据失败: {e}\n{traceback.format_exc()}"


# ──────────────── ECS 云主机（概览 + 已停止详情）────────────────

def list_ecs_instances_huawei(config: HuaweiCloudConfig) -> str:
    """列出华为云 ECS 实例概览：按状态统计，仅输出已停止实例详情"""
    try:
        from huaweicloudsdkecs.v2 import EcsClient, ListServersDetailsRequest
        from huaweicloudsdkecs.v2.region.ecs_region import EcsRegion
        from huaweicloudsdkcore.auth.credentials import BasicCredentials

        credentials = BasicCredentials(config.ak, config.sk, config.project_id)
        client = (
            EcsClient.new_builder()
            .with_credentials(credentials)
            .with_region(EcsRegion.value_of(config.region))
            .build()
        )

        request = ListServersDetailsRequest()
        request.limit = 100
        response = client.list_servers_details(request)
        servers = response.servers or []

        if not servers:
            return f"华为云区域 {config.region} 无 ECS 实例"

        running_count = 0
        stopped_count = 0
        other_count = 0
        stopped_details = []

        for s in servers:
            status = (s.status or "").upper()
            if status == "ACTIVE":
                running_count += 1
            elif status == "SHUTOFF":
                stopped_count += 1
                flavor_id = s.flavor.get("id", "") if isinstance(s.flavor, dict) else str(s.flavor)

                extra: dict[str, str] = {
                    "区域": config.region,
                    "实例类型": flavor_id,
                }
                if hasattr(s, "OS-EXT-AZ:availability_zone"):
                    extra["可用区"] = getattr(s, "OS-EXT-AZ:availability_zone", "")

                addrs = s.addresses or {}
                ips = []
                for net_name, net_addrs in addrs.items():
                    if isinstance(net_addrs, list):
                        for addr in net_addrs:
                            ip = addr.get("addr", "") if isinstance(addr, dict) else str(addr)
                            ip_type = addr.get("OS-EXT-IPS:type", "") if isinstance(addr, dict) else ""
                            if ip:
                                ips.append(f"{ip}({ip_type})" if ip_type else ip)
                if ips:
                    extra["IP地址"] = ", ".join(ips)

                if s.created:
                    extra["创建时间"] = s.created
                if s.updated:
                    extra["最后更新"] = s.updated

                metadata = s.metadata or {}
                if metadata:
                    meta_str = ", ".join(f"{k}={v}" for k, v in list(metadata.items())[:5])
                    extra["元数据"] = meta_str

                info = InstanceInfo(
                    cloud="华为云",
                    instance_id=s.id,
                    instance_name=s.name or "",
                    instance_type=flavor_id,
                    status="🔴 SHUTOFF",
                    region=config.region,
                    extra=extra,
                )
                stopped_details.append(info.display())
            else:
                other_count += 1

        total = running_count + stopped_count + other_count
        lines = [f"📊 华为云 ECS 实例概览 [区域: {config.region}]"]
        lines.append(f"  总计: {total} 个实例 | 运行中: {running_count} | 已停止: {stopped_count}")

        if stopped_details:
            lines.append(f"\n🔴 已停止实例详情 ({stopped_count} 个):")
            lines.extend(stopped_details)
        else:
            lines.append("\n✅ 无已停止实例")

        return "\n\n".join(lines)
    except Exception as e:
        return f"华为云查询 ECS 实例失败: {e}\n{traceback.format_exc()}"


# ──────────────── OBS 对象存储 ────────────────

def list_obs_buckets_huawei(config: HuaweiCloudConfig) -> str:
    """列出华为云 OBS 存储桶（含区域信息）"""
    try:
        from obs import ObsClient

        obs_client = ObsClient(
            access_key_id=config.ak,
            secret_access_key=config.sk,
            server=f"https://obs.{config.region}.myhuaweicloud.com",
        )

        resp = obs_client.listBuckets()
        if resp.status >= 300:
            return f"华为云 OBS 查询失败: HTTP {resp.status}"

        buckets = resp.body.buckets or []
        if not buckets:
            return "华为云无 OBS 存储桶"

        results = []
        region_counts: dict[str, int] = {}

        for b in buckets:
            bucket_region = b.location or "unknown"
            region_counts[bucket_region] = region_counts.get(bucket_region, 0) + 1

            created = ""
            if b.create_date:
                created = str(b.create_date)

            info = InstanceInfo(
                cloud="华为云",
                instance_id=b.name,
                instance_name=b.name,
                instance_type="OBS Bucket",
                status="active",
                region=bucket_region,
                extra={"创建时间": created},
            )
            results.append(info.display())

        obs_client.close()

        summary_parts = [f"{r}: {c}个" for r, c in sorted(region_counts.items())]
        header = f"找到 {len(results)} 个 OBS 存储桶（区域分布: {', '.join(summary_parts)}）"
        return header + ":\n\n" + "\n\n".join(results)
    except Exception as e:
        return f"华为云查询 OBS 存储桶失败: {e}\n{traceback.format_exc()}"


# ──────────────── CDN（概览 + 停用详情）────────────────

def list_cdn_domains_huawei(config: HuaweiCloudConfig, status_filter: str = "") -> str:
    """列出华为云 CDN 加速域名

    Args:
        status_filter: "offline"=仅已停用, "online"=仅启用, ""=全部(含概览)
    """
    try:
        from huaweicloudsdkcdn.v2 import CdnClient, ListDomainsRequest
        from huaweicloudsdkcdn.v2.region.cdn_region import CdnRegion
        from huaweicloudsdkcore.auth.credentials import GlobalCredentials

        credentials = GlobalCredentials(config.ak, config.sk)
        client = (
            CdnClient.new_builder()
            .with_credentials(credentials)
            .with_region(CdnRegion.value_of("cn-north-1"))
            .build()
        )

        all_domains = []
        page = 1
        while True:
            request = ListDomainsRequest()
            request.page_size = 100
            request.page_number = page
            if status_filter:
                request.domain_status = status_filter
            response = client.list_domains(request)
            domains = response.domains or []
            all_domains.extend(domains)
            if len(domains) < 100:
                break
            page += 1

        if not all_domains:
            return "华为云无 CDN 加速域名"

        online_items = [d for d in all_domains if (d.domain_status or "").lower() == "online"]
        offline_items = [d for d in all_domains if (d.domain_status or "").lower() != "online"]

        def _format_cdn(d, detailed: bool = False) -> str:
            extra: dict[str, str] = {
                "域名": d.domain_name or "",
                "CNAME": d.cname or "",
                "状态": d.domain_status or "",
                "业务类型": d.business_type or "",
            }
            if detailed:
                if d.modify_time:
                    extra["最后修改"] = str(d.modify_time)
                if d.create_time:
                    extra["创建时间"] = str(d.create_time)
                sources = d.sources or []
                if sources:
                    src_names = [s.ip_or_domain for s in sources if s.ip_or_domain]
                    if src_names:
                        extra["源站"] = ", ".join(src_names[:3])

            info = InstanceInfo(
                cloud="华为云",
                instance_id=d.id or d.domain_name or "",
                instance_name=d.domain_name or "",
                instance_type="CDN",
                status=d.domain_status or "",
                region="global",
                extra=extra,
            )
            return info.display()

        if status_filter == "offline":
            if not offline_items:
                return "华为云无已停用的 CDN 域名"
            results = [_format_cdn(d, detailed=True) for d in offline_items]
            return f"找到 {len(results)} 个已停用的 CDN 域名:\n\n" + "\n\n".join(results)

        if status_filter == "online":
            if not online_items:
                return "华为云无已启用的 CDN 域名"
            results = [_format_cdn(d) for d in online_items]
            return f"找到 {len(results)} 个已启用的 CDN 域名:\n\n" + "\n\n".join(results)

        lines = [
            "📊 华为云 CDN 加速域名概览",
            f"  总计: {len(all_domains)} 个域名",
            f"  在线: {len(online_items)} 个",
            f"  离线/停用: {len(offline_items)} 个",
        ]

        if offline_items:
            lines.append(f"\n⚠️ 已停用域名详情 ({len(offline_items)} 个):")
            for d in offline_items:
                lines.append(_format_cdn(d, detailed=True))

        if online_items:
            lines.append(f"\n✅ 在线域名列表 ({len(online_items)} 个):")
            for d in online_items:
                lines.append(_format_cdn(d))

        return "\n\n".join(lines)
    except Exception as e:
        return f"华为云查询 CDN 域名失败: {e}\n{traceback.format_exc()}"
