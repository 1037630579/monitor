"""阿里云治理工具 - ECS 云主机 / OSS 对象存储 / CDN"""

import json
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any

from cloud_monitor.config import AliyunConfig
from cloud_monitor.models.metrics import DataPoint, InstanceInfo, MetricData, MetricInfo

ECS_METRICS = {
    "CPUUtilization": ("CPU使用率", "%"),
    "memory_usedutilization": ("内存使用率", "%"),
    "DiskReadBPS": ("磁盘读速率", "Bytes/s"),
    "DiskWriteBPS": ("磁盘写速率", "Bytes/s"),
    "IntranetInRate": ("内网入带宽", "bits/s"),
    "IntranetOutRate": ("内网出带宽", "bits/s"),
    "InternetInRate": ("公网入带宽", "bits/s"),
    "InternetOutRate": ("公网出带宽", "bits/s"),
}

ALIYUN_COMMON_METRICS = {
    "acs_ecs_dashboard": ECS_METRICS,
}

STAT_MAP = {
    "average": "Average",
    "max": "Maximum",
    "min": "Minimum",
    "sum": "Sum",
}


def _get_cms_client(config: AliyunConfig):
    from alibabacloud_cms20190101.client import Client
    from alibabacloud_tea_openapi.models import Config

    api_config = Config(
        access_key_id=config.access_key_id,
        access_key_secret=config.access_key_secret,
        region_id=config.region_id,
    )
    api_config.endpoint = f"metrics.{config.region_id}.aliyuncs.com"
    return Client(api_config)


# ──────────────── 通用指标查询 ────────────────

def list_metrics_aliyun(config: AliyunConfig, namespace: str = "", metric_name: str = "") -> str:
    """列出阿里云可用的监控指标"""
    try:
        if namespace or metric_name:
            from alibabacloud_cms20190101.models import DescribeMetricMetaListRequest
            client = _get_cms_client(config)
            request = DescribeMetricMetaListRequest(
                namespace=namespace or None,
                metric_name=metric_name or None,
                page_size=100,
            )
            response = client.describe_metric_meta_list(request)
            body = response.body
            resources = body.resources.resource if body.resources and body.resources.resource else []

            results = []
            for r in resources:
                mi = MetricInfo(
                    cloud="阿里云",
                    namespace=r.namespace or "",
                    metric_name=r.metric_name or "",
                    description=r.description or "",
                    unit=r.unit or "",
                )
                results.append(mi.display())
            if not results:
                return "未找到匹配的指标"
            return f"找到 {len(results)} 个指标:\n\n" + "\n\n".join(results)
        else:
            lines = ["阿里云可用监控指标 (ECS):"]
            for ns, metrics in ALIYUN_COMMON_METRICS.items():
                lines.append(f"\n【{ns}】")
                for name, (desc, unit) in metrics.items():
                    lines.append(f"  {name}: {desc} ({unit})")
            return "\n".join(lines)
    except Exception as e:
        return f"阿里云查询指标失败: {e}\n{traceback.format_exc()}"


def get_metric_data_aliyun(
    config: AliyunConfig,
    namespace: str,
    metric_name: str,
    instance_id: str,
    period: int = 300,
    stat: str = "average",
    hours: float = 1,
) -> str:
    """查询阿里云监控指标数据"""
    try:
        from alibabacloud_cms20190101.models import DescribeMetricListRequest
        client = _get_cms_client(config)

        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=hours)

        dimensions = json.dumps([{"instanceId": instance_id}])

        request = DescribeMetricListRequest(
            namespace=namespace,
            metric_name=metric_name,
            dimensions=dimensions,
            period=str(period),
            start_time=start.strftime("%Y-%m-%d %H:%M:%S"),
            end_time=now.strftime("%Y-%m-%d %H:%M:%S"),
        )
        response = client.describe_metric_list(request)
        body = response.body

        desc, unit = "", ""
        if namespace in ALIYUN_COMMON_METRICS:
            if metric_name in ALIYUN_COMMON_METRICS[namespace]:
                desc, unit = ALIYUN_COMMON_METRICS[namespace][metric_name]

        result = MetricData(
            cloud="阿里云",
            namespace=namespace,
            metric_name=f"{metric_name}" + (f" ({desc})" if desc else ""),
            instance_id=instance_id,
            period=period,
            statistics=stat,
        )

        datapoints_str = body.datapoints if body.datapoints else "[]"
        datapoints = json.loads(datapoints_str) if isinstance(datapoints_str, str) else []

        stat_key = STAT_MAP.get(stat, "Average")
        for dp in datapoints:
            val = dp.get(stat_key, dp.get("Average", 0))
            ts = dp.get("timestamp", 0)
            result.data_points.append(
                DataPoint(
                    timestamp=datetime.fromtimestamp(ts / 1000, tz=timezone.utc),
                    value=float(val),
                    unit=unit,
                )
            )

        result.data_points.sort(key=lambda x: x.timestamp)
        return result.display() + "\n\n" + result.summary()
    except Exception as e:
        return f"阿里云查询监控数据失败: {e}\n{traceback.format_exc()}"


# ──────────────── ECS 云主机（概览 + 已停止详情）────────────────

def list_ecs_instances_aliyun(config: AliyunConfig) -> tuple[str, list[dict]]:
    """列出阿里云 ECS 实例概览：按状态统计，仅输出已停止实例详情。

    返回 (text_report, structured_data)。
    """
    try:
        from alibabacloud_ecs20140526.client import Client as EcsClient
        from alibabacloud_ecs20140526.models import DescribeInstancesRequest
        from alibabacloud_tea_openapi.models import Config

        api_config = Config(
            access_key_id=config.access_key_id,
            access_key_secret=config.access_key_secret,
            region_id=config.region_id,
        )
        api_config.endpoint = f"ecs.{config.region_id}.aliyuncs.com"
        client = EcsClient(api_config)

        all_instances = []
        page = 1
        while True:
            request = DescribeInstancesRequest(region_id=config.region_id, page_size=100, page_number=page)
            response = client.describe_instances(request)
            instances = response.body.instances.instance if response.body.instances else []
            all_instances.extend(instances)
            if len(instances) < 100:
                break
            page += 1

        if not all_instances:
            return f"阿里云区域 {config.region_id} 无 ECS 实例", []

        running_count = 0
        stopped_count = 0
        other_count = 0
        stopped_details = []
        structured: list[dict] = []

        for inst in all_instances:
            status = (inst.status or "").lower()
            if status == "running":
                running_count += 1
            elif status == "stopped":
                stopped_count += 1
                private_ip = ", ".join(inst.vpc_attributes.private_ip_address.ip_address) if inst.vpc_attributes and inst.vpc_attributes.private_ip_address else ""
                public_ip = ", ".join(inst.public_ip_address.ip_address) if inst.public_ip_address and inst.public_ip_address.ip_address else ""

                extra: dict[str, str] = {
                    "区域": config.region_id,
                    "可用区": inst.zone_id or "",
                    "实例类型": inst.instance_type or "",
                    "私有IP": private_ip,
                    "公网IP": public_ip or "无",
                }
                extra_db: dict[str, str] = {}
                if inst.creation_time:
                    extra["创建时间"] = inst.creation_time
                    extra_db["creation_time"] = inst.creation_time
                if inst.expired_time:
                    extra["到期时间"] = inst.expired_time
                    extra_db["expired_time"] = inst.expired_time
                if inst.stopped_mode:
                    extra["停止模式"] = inst.stopped_mode
                    extra_db["stopped_mode"] = inst.stopped_mode

                info = InstanceInfo(
                    cloud="阿里云",
                    instance_id=inst.instance_id or "",
                    instance_name=inst.instance_name or "",
                    instance_type=inst.instance_type or "",
                    status="🔴 Stopped",
                    region=config.region_id,
                    extra=extra,
                )
                stopped_details.append(info.display())
                structured.append({
                    "instance_id": inst.instance_id or "",
                    "instance_name": inst.instance_name or "",
                    "instance_type": inst.instance_type or "",
                    "status": "stopped",
                    "region": config.region_id,
                    "availability_zone": inst.zone_id or "",
                    "private_ip": private_ip,
                    "public_ip": public_ip or None,
                    "avg_cpu": None, "max_cpu": None,
                    "avg_mem": None, "max_mem": None,
                    "tags": {}, "extra": extra_db,
                })
            else:
                other_count += 1

        total = running_count + stopped_count + other_count
        lines = [f"📊 阿里云 ECS 实例概览 [区域: {config.region_id}]"]
        lines.append(f"  总计: {total} 个实例 | 运行中: {running_count} | 已停止: {stopped_count}")

        if stopped_details:
            lines.append(f"\n🔴 已停止实例详情 ({stopped_count} 个):")
            lines.extend(stopped_details)
        else:
            lines.append("\n✅ 无已停止实例")

        return "\n\n".join(lines), structured
    except Exception as e:
        return f"阿里云查询 ECS 实例失败: {e}\n{traceback.format_exc()}", []


# ──────────────── OSS 对象存储 ────────────────

def list_oss_buckets_aliyun(config: AliyunConfig) -> str:
    """列出阿里云 OSS 存储桶（含区域信息）"""
    try:
        import oss2

        auth = oss2.Auth(config.access_key_id, config.access_key_secret)
        service = oss2.Service(auth, f"https://oss-{config.region_id}.aliyuncs.com")

        results = []
        region_counts: dict[str, int] = {}

        for bucket_info in oss2.BucketIterator(service):
            bucket_region = bucket_info.location.replace("oss-", "") if bucket_info.location else "unknown"
            region_counts[bucket_region] = region_counts.get(bucket_region, 0) + 1

            created = ""
            if bucket_info.creation_date:
                created = bucket_info.creation_date

            info = InstanceInfo(
                cloud="阿里云",
                instance_id=bucket_info.name,
                instance_name=bucket_info.name,
                instance_type="OSS Bucket",
                status="active",
                region=bucket_region,
                extra={"创建时间": str(created)},
            )
            results.append(info.display())

        if not results:
            return "阿里云无 OSS 存储桶"

        summary_parts = [f"{r}: {c}个" for r, c in sorted(region_counts.items())]
        header = f"找到 {len(results)} 个 OSS 存储桶（区域分布: {', '.join(summary_parts)}）"
        return header + ":\n\n" + "\n\n".join(results)
    except Exception as e:
        return f"阿里云查询 OSS 存储桶失败: {e}\n{traceback.format_exc()}"


# ──────────────── CDN（概览 + 禁用详情）────────────────

def list_cdn_domains_aliyun(config: AliyunConfig, status_filter: str = "") -> str:
    """列出阿里云 CDN 加速域名

    Args:
        status_filter: "offline"=仅已停用, "online"=仅启用, ""=全部(含概览)
    """
    try:
        from alibabacloud_cdn20180510.client import Client as CdnClient
        from alibabacloud_cdn20180510.models import DescribeUserDomainsRequest
        from alibabacloud_tea_openapi.models import Config

        api_config = Config(
            access_key_id=config.access_key_id,
            access_key_secret=config.access_key_secret,
            region_id=config.region_id,
        )
        api_config.endpoint = "cdn.aliyuncs.com"
        client = CdnClient(api_config)

        all_domains = []
        page = 1
        while True:
            request = DescribeUserDomainsRequest(page_size=50, page_number=page)
            if status_filter:
                request.domain_status = status_filter
            response = client.describe_user_domains(request)
            domains = response.body.domains.page_data if response.body.domains else []
            all_domains.extend(domains)
            if len(domains) < 50:
                break
            page += 1

        if not all_domains:
            return "阿里云无 CDN 加速域名"

        online_items = [d for d in all_domains if (d.domain_status or "").lower() == "online"]
        offline_items = [d for d in all_domains if (d.domain_status or "").lower() != "online"]

        def _format_cdn(d, detailed: bool = False) -> str:
            extra: dict[str, str] = {
                "域名": d.domain_name or "",
                "CNAME": d.cname or "",
                "状态": d.domain_status or "",
                "CDN类型": d.cdn_type or "",
            }
            if detailed:
                if d.gmt_modified:
                    extra["最后修改"] = d.gmt_modified
                if d.gmt_created:
                    extra["创建时间"] = d.gmt_created
                if d.description:
                    extra["备注"] = d.description
                sources = getattr(d, "sources", None)
                if sources and hasattr(sources, "source"):
                    src_list = sources.source or []
                    src_names = [s.content for s in src_list if s.content]
                    if src_names:
                        extra["源站"] = ", ".join(src_names[:3])

            info = InstanceInfo(
                cloud="阿里云",
                instance_id=d.domain_name or "",
                instance_name=d.domain_name or "",
                instance_type="CDN",
                status=d.domain_status or "",
                region="global",
                extra=extra,
            )
            return info.display()

        if status_filter == "offline":
            if not offline_items:
                return "阿里云无已停用的 CDN 域名"
            results = [_format_cdn(d, detailed=True) for d in offline_items]
            return f"找到 {len(results)} 个已停用的 CDN 域名:\n\n" + "\n\n".join(results)

        if status_filter == "online":
            if not online_items:
                return "阿里云无已启用的 CDN 域名"
            results = [_format_cdn(d) for d in online_items]
            return f"找到 {len(results)} 个已启用的 CDN 域名:\n\n" + "\n\n".join(results)

        lines = [
            "📊 阿里云 CDN 加速域名概览",
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
        return f"阿里云查询 CDN 域名失败: {e}\n{traceback.format_exc()}"
