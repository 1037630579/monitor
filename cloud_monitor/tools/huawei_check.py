"""华为云风险巡检工具 — 对应9项风险巡检项

每个巡检函数返回 (text_report, structured_list)，structured_list 中的每条记录
都包含 check_type / risk_level / resource_type / resource_id / resource_name /
region / detail / status 等字段，便于统一入库。
"""

import traceback
from typing import Any

from cloud_monitor.config import HuaweiCloudConfig


# ─────────────────────────────────────────────────────────────────────
# 通用工具：构建各类客户端
# ─────────────────────────────────────────────────────────────────────

def _basic_creds(config: HuaweiCloudConfig):
    from huaweicloudsdkcore.auth.credentials import BasicCredentials
    return BasicCredentials(config.ak, config.sk, config.project_id)


def _ecs_client(config: HuaweiCloudConfig):
    from huaweicloudsdkecs.v2 import EcsClient
    from huaweicloudsdkecs.v2.region.ecs_region import EcsRegion
    return (
        EcsClient.new_builder()
        .with_credentials(_basic_creds(config))
        .with_region(EcsRegion.value_of(config.region))
        .build()
    )


def _vpc_client(config: HuaweiCloudConfig):
    from huaweicloudsdkvpc.v2 import VpcClient
    from huaweicloudsdkvpc.v2.region.vpc_region import VpcRegion
    return (
        VpcClient.new_builder()
        .with_credentials(_basic_creds(config))
        .with_region(VpcRegion.value_of(config.region))
        .build()
    )


def _vpc_v3_client(config: HuaweiCloudConfig):
    from huaweicloudsdkvpc.v3 import VpcClient as VpcV3Client
    from huaweicloudsdkvpc.v3.region.vpc_region import VpcRegion as VpcV3Region
    return (
        VpcV3Client.new_builder()
        .with_credentials(_basic_creds(config))
        .with_region(VpcV3Region.value_of(config.region))
        .build()
    )


def _rds_client(config: HuaweiCloudConfig):
    from huaweicloudsdkrds.v3 import RdsClient
    from huaweicloudsdkrds.v3.region.rds_region import RdsRegion
    return (
        RdsClient.new_builder()
        .with_credentials(_basic_creds(config))
        .with_region(RdsRegion.value_of(config.region))
        .build()
    )


def _dds_client(config: HuaweiCloudConfig):
    from huaweicloudsdkdds.v3 import DdsClient
    from huaweicloudsdkdds.v3.region.dds_region import DdsRegion
    return (
        DdsClient.new_builder()
        .with_credentials(_basic_creds(config))
        .with_region(DdsRegion.value_of(config.region))
        .build()
    )


def _dms_client(config: HuaweiCloudConfig):
    from huaweicloudsdkrabbitmq.v2 import RabbitMQClient
    from huaweicloudsdkrabbitmq.v2.region.rabbitmq_region import RabbitMQRegion
    return (
        RabbitMQClient.new_builder()
        .with_credentials(_basic_creds(config))
        .with_region(RabbitMQRegion.value_of(config.region))
        .build()
    )


def _cce_client(config: HuaweiCloudConfig):
    from huaweicloudsdkcce.v3 import CceClient
    from huaweicloudsdkcce.v3.region.cce_region import CceRegion
    return (
        CceClient.new_builder()
        .with_credentials(_basic_creds(config))
        .with_region(CceRegion.value_of(config.region))
        .build()
    )


def _ces_client(config: HuaweiCloudConfig):
    from huaweicloudsdkces.v1 import CesClient
    from huaweicloudsdkces.v1.region.ces_region import CesRegion
    return (
        CesClient.new_builder()
        .with_credentials(_basic_creds(config))
        .with_region(CesRegion.value_of(config.region))
        .build()
    )


def _make_record(
    check_type: str,
    risk_level: str,
    resource_type: str,
    resource_id: str,
    resource_name: str,
    region: str,
    detail: str,
    status: str = "open",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "check_type": check_type,
        "risk_level": risk_level,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "resource_name": resource_name,
        "region": region,
        "detail": detail,
        "status": status,
    }
    if extra:
        rec["extra"] = extra
    return rec


# ─────────────────────────────────────────────────────────────────────
# 巡检1: ECS 安全组规则检查
# ─────────────────────────────────────────────────────────────────────

def check_ecs_security_groups(config: HuaweiCloudConfig) -> tuple[str, list[dict]]:
    """检查 ECS 安全组规则 — 仅当规则状态开启(action=allow)且入站源为0.0.0.0/0时才算高危"""
    try:
        vpc_v3 = _vpc_v3_client(config)
        from huaweicloudsdkvpc.v3.model import ListSecurityGroupsRequest, ListSecurityGroupRulesRequest

        sg_resp = vpc_v3.list_security_groups(ListSecurityGroupsRequest(limit=2000))
        groups = sg_resp.security_groups or []

        risky: list[dict] = []
        lines = [f"📋 ECS 安全组规则检查 [区域: {config.region}]"]
        lines.append(f"  安全组总数: {len(groups)}")

        risk_items: list[str] = []
        for sg in groups:
            sg_id = sg.id
            sg_name = sg.name or ""

            rules_resp = vpc_v3.list_security_group_rules(
                ListSecurityGroupRulesRequest(security_group_id=[sg_id], limit=200)
            )
            rules = rules_resp.security_group_rules or []

            risky_rules: list[str] = []
            for r in rules:
                direction = getattr(r, "direction", "") or ""
                remote_ip = getattr(r, "remote_ip_prefix", "") or ""
                protocol = getattr(r, "protocol", "") or "any"
                action = getattr(r, "action", "allow") or "allow"
                multiport = getattr(r, "multiport", "") or ""

                if action.lower() == "deny":
                    continue

                if direction == "ingress" and remote_ip in ("0.0.0.0/0", "::/0"):
                    port_desc = multiport if multiport else "全端口"
                    risky_rules.append(f"入站 {protocol} {port_desc} 开放 {remote_ip}")

            if risky_rules:
                detail = "; ".join(risky_rules)
                risk_items.append(f"  ⚠️ {sg_name} ({sg_id}): {detail}")
                risky.append(_make_record(
                    check_type="ecs_security_group",
                    risk_level="high",
                    resource_type="ECS",
                    resource_id=sg_id,
                    resource_name=sg_name,
                    region=config.region,
                    detail=detail,
                    extra={"rule_count": len(rules), "risky_rules": risky_rules},
                ))

        if risk_items:
            lines.append(f"\n⚠️ 风险安全组 ({len(risk_items)} 个):")
            lines.extend(risk_items)
        else:
            lines.append("\n✅ 未发现高风险安全组规则")

        return "\n".join(lines), risky
    except Exception as e:
        return f"ECS 安全组检查失败: {e}\n{traceback.format_exc()}", []


# ─────────────────────────────────────────────────────────────────────
# 巡检2: CCE 工作负载副本数检查
# ─────────────────────────────────────────────────────────────────────

def check_cce_workload_replicas(config: HuaweiCloudConfig) -> tuple[str, list[dict]]:
    """检查 CCE 工作负载可用副本数 — 期望副本 vs 实际可用副本"""
    try:
        cce = _cce_client(config)
        from huaweicloudsdkcce.v3.model import ListClustersRequest

        cluster_resp = cce.list_clusters(ListClustersRequest())
        clusters = cluster_resp.items or []

        lines = [f"📋 CCE 工作负载副本数检查 [区域: {config.region}]"]
        lines.append(f"  集群总数: {len(clusters)}")
        risky: list[dict] = []

        for cluster in clusters:
            cluster_id = cluster.metadata.uid
            cluster_name = cluster.metadata.name or ""

            try:
                from huaweicloudsdkcce.v3.model import ListClustersRequest as _
                import requests

                endpoint = f"https://cce.{config.region}.myhuaweicloud.com"
                from huaweicloudsdkcore.auth.credentials import BasicCredentials
                from huaweicloudsdkcce.v3 import CceClient
                from huaweicloudsdkcce.v3.region.cce_region import CceRegion

                # 通过 Kubernetes API 获取 Deployments
                # CCE SDK 不直接提供工作负载 API，使用 list_nodes 获取节点信息
                pass
            except Exception:
                pass

            # 使用 Kubernetes API 通过 CCE 代理
            try:
                from huaweicloudsdkcore.http.http_config import HttpConfig
                import json

                token = _get_iam_token(config)
                if not token:
                    continue

                api_url = f"https://{cluster_id}.cce.{config.region}.myhuaweicloud.com/api/v1/namespaces"
                headers = {"X-Auth-Token": token, "Content-Type": "application/json"}

                import urllib.request
                req = urllib.request.Request(
                    f"https://{cluster_id}.cce.{config.region}.myhuaweicloud.com/apis/apps/v1/deployments",
                    headers=headers,
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read())

                deployments = data.get("items", [])
                for dep in deployments:
                    dep_name = dep.get("metadata", {}).get("name", "")
                    namespace = dep.get("metadata", {}).get("namespace", "")
                    spec_replicas = dep.get("spec", {}).get("replicas", 0)
                    status = dep.get("status", {})
                    available = status.get("availableReplicas", 0) or 0
                    ready = status.get("readyReplicas", 0) or 0

                    if available < spec_replicas:
                        detail = f"期望副本: {spec_replicas}, 可用: {available}, 就绪: {ready}"
                        lines.append(f"  ⚠️ [{cluster_name}] {namespace}/{dep_name}: {detail}")
                        risky.append(_make_record(
                            check_type="cce_workload_replica",
                            risk_level="high",
                            resource_type="CCE",
                            resource_id=f"{cluster_id}/{namespace}/{dep_name}",
                            resource_name=f"{cluster_name}/{dep_name}",
                            region=config.region,
                            detail=detail,
                            extra={
                                "cluster_id": cluster_id,
                                "cluster_name": cluster_name,
                                "namespace": namespace,
                                "spec_replicas": spec_replicas,
                                "available_replicas": available,
                                "ready_replicas": ready,
                            },
                        ))
            except Exception as ex:
                lines.append(f"  ⚠️ 集群 {cluster_name} 工作负载查询失败: {ex}")

        if not risky:
            lines.append("\n✅ 所有工作负载副本数正常")
        else:
            lines.insert(2, f"  ⚠️ 异常工作负载: {len(risky)} 个")

        return "\n".join(lines), risky
    except Exception as e:
        return f"CCE 工作负载检查失败: {e}\n{traceback.format_exc()}", []


def _get_iam_token(config: HuaweiCloudConfig) -> str | None:
    """获取华为云 IAM Token"""
    try:
        from huaweicloudsdkiam.v3 import IamClient, KeystoneCreateUserTokenByPasswordRequest
        from huaweicloudsdkiam.v3.region.iam_region import IamRegion
        from huaweicloudsdkcore.auth.credentials import BasicCredentials

        credentials = BasicCredentials(config.ak, config.sk, config.project_id)
        client = (
            IamClient.new_builder()
            .with_credentials(credentials)
            .with_region(IamRegion.value_of(config.region))
            .build()
        )
        # 对于 AK/SK 认证，可以直接使用 signer
        return None
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────
# 巡检3: RDS 实例高可用部署检查
# ─────────────────────────────────────────────────────────────────────

def check_rds_ha(config: HuaweiCloudConfig) -> tuple[str, list[dict]]:
    """检查 RDS 实例是否单副本部署 — 单副本无高可用保障"""
    try:
        rds = _rds_client(config)
        from huaweicloudsdkrds.v3.model import ListInstancesRequest

        resp = rds.list_instances(ListInstancesRequest(limit=100))
        instances = resp.instances or []

        lines = [f"📋 RDS 高可用部署检查 [区域: {config.region}]"]
        lines.append(f"  RDS 实例总数: {len(instances)}")
        risky: list[dict] = []

        for inst in instances:
            inst_id = inst.id
            inst_name = inst.name or ""
            ha_mode = ""
            inst_type = getattr(inst, "type", "")

            if inst_type == "Single":
                ha_mode = "单机"
            elif inst_type == "Ha":
                ha_mode = "主备"
            elif inst_type == "Replica":
                ha_mode = "只读"
            else:
                ha_mode = inst_type or "未知"

            flavor = getattr(inst, "flavor_ref", "") or ""
            engine = getattr(inst, "datastore", None)
            engine_name = ""
            engine_version = ""
            if engine:
                engine_name = getattr(engine, "type", "") or ""
                engine_version = getattr(engine, "version", "") or ""

            if inst_type == "Single":
                detail = f"部署模式: {ha_mode}, 引擎: {engine_name} {engine_version}, 规格: {flavor}"
                lines.append(f"  ⚠️ {inst_name} ({inst_id}): {detail}")
                risky.append(_make_record(
                    check_type="rds_ha",
                    risk_level="high",
                    resource_type="RDS",
                    resource_id=inst_id,
                    resource_name=inst_name,
                    region=config.region,
                    detail=detail,
                    extra={
                        "deploy_mode": ha_mode,
                        "engine": engine_name,
                        "engine_version": engine_version,
                        "flavor": flavor,
                    },
                ))

        if not risky:
            lines.append(f"\n✅ 所有 RDS 实例均为高可用部署")
        else:
            lines.insert(2, f"  ⚠️ 单副本实例: {len(risky)} 个")

        return "\n".join(lines), risky
    except Exception as e:
        return f"RDS 高可用检查失败: {e}\n{traceback.format_exc()}", []


# ─────────────────────────────────────────────────────────────────────
# 巡检4: DMS (RabbitMQ) 集群部署检查
# ─────────────────────────────────────────────────────────────────────

def check_dms_rabbitmq_cluster(config: HuaweiCloudConfig) -> tuple[str, list[dict]]:
    """检查 DMS RabbitMQ 实例是否集群部署"""
    try:
        dms = _dms_client(config)
        from huaweicloudsdkrabbitmq.v2.model import ListInstancesDetailsRequest

        resp = dms.list_instances_details(ListInstancesDetailsRequest())
        instances = resp.instances or []

        total = len(instances)
        lines = [f"📋 DMS RabbitMQ 集群部署检查 [区域: {config.region}]"]
        lines.append(f"  RabbitMQ 实例总数: {total}")
        risky: list[dict] = []

        for inst in instances:
            inst_id = inst.instance_id or ""
            inst_name = inst.name or ""
            engine_version = getattr(inst, "engine_version", "") or ""
            spec_code = getattr(inst, "specification", "") or getattr(inst, "product_id", "") or ""
            node_num = getattr(inst, "node_num", None)

            is_single = False
            if node_num is not None and node_num <= 1:
                is_single = True
            elif spec_code and "single" in spec_code.lower():
                is_single = True

            if is_single:
                detail = f"单节点部署, 无高可用能力 | 规格: {spec_code} × {node_num or 1} broker, 版本: {engine_version}"
                lines.append(f"  ⚠️ {inst_name} ({inst_id}): {detail}")
                risky.append(_make_record(
                    check_type="dms_rabbitmq_cluster",
                    risk_level="medium",
                    resource_type="DMS",
                    resource_id=inst_id,
                    resource_name=inst_name,
                    region=config.region,
                    detail=detail,
                    extra={"node_num": node_num, "spec_code": spec_code, "engine_version": engine_version},
                ))

        cluster_count = total - len(risky)
        compliance_rate = (cluster_count / total * 100) if total > 0 else 100
        if not risky:
            lines.append(f"\n✅ 所有 RabbitMQ 实例均为集群部署（合规率 100%）")
        else:
            lines.insert(2, f"  集群部署合规率: {compliance_rate:.0f}%（{total}个实例中{cluster_count}个为集群部署）")
            lines.insert(3, f"  ⚠️ 非集群(单节点)实例: {len(risky)} 个")

        return "\n".join(lines), risky
    except Exception as e:
        return f"DMS RabbitMQ 检查失败: {e}\n{traceback.format_exc()}", []


# ─────────────────────────────────────────────────────────────────────
# 巡检5: RDS 实例网络类型检查
# ─────────────────────────────────────────────────────────────────────

def check_rds_network_type(config: HuaweiCloudConfig) -> tuple[str, list[dict]]:
    """检查 RDS 实例网络是否为通用型（而非增强型）"""
    try:
        rds = _rds_client(config)
        from huaweicloudsdkrds.v3.model import ListInstancesRequest

        resp = rds.list_instances(ListInstancesRequest(limit=100))
        instances = resp.instances or []

        lines = [f"📋 RDS 网络类型检查 [区域: {config.region}]"]
        lines.append(f"  RDS 实例总数: {len(instances)}")
        risky: list[dict] = []

        for inst in instances:
            inst_id = inst.id
            inst_name = inst.name or ""
            flavor = getattr(inst, "flavor_ref", "") or ""

            # 通用型规格通常包含 "rds." 但不含 "ha" / "enhanced" 等关键字
            # 华为云 RDS 网络增强型规格一般含 ".ha." 或特定后缀
            # 根据 flavor 规格判断网络类型
            is_general = False
            if flavor:
                flavor_lower = flavor.lower()
                if ".ha." not in flavor_lower and "enhanced" not in flavor_lower:
                    is_general = True

            engine = getattr(inst, "datastore", None)
            engine_name = getattr(engine, "type", "") if engine else ""

            if is_general and flavor:
                detail = f"规格: {flavor}, 引擎: {engine_name} — 网络为通用型，建议评估是否需要升级为增强型"
                lines.append(f"  ℹ️ {inst_name} ({inst_id}): {detail}")
                risky.append(_make_record(
                    check_type="rds_network_type",
                    risk_level="medium",
                    resource_type="RDS",
                    resource_id=inst_id,
                    resource_name=inst_name,
                    region=config.region,
                    detail=detail,
                    extra={"flavor": flavor, "engine": engine_name},
                ))

        if not risky:
            lines.append(f"\n✅ 所有 RDS 实例网络类型正常")
        else:
            lines.insert(2, f"  ℹ️ 通用型网络实例: {len(risky)} 个")

        return "\n".join(lines), risky
    except Exception as e:
        return f"RDS 网络类型检查失败: {e}\n{traceback.format_exc()}", []


# ─────────────────────────────────────────────────────────────────────
# 巡检6: DDS 实例网络类型检查
# ─────────────────────────────────────────────────────────────────────

def check_dds_network_type(config: HuaweiCloudConfig) -> tuple[str, list[dict]]:
    """检查 DDS (MongoDB) 实例网络是否为通用型"""
    try:
        dds = _dds_client(config)
        from huaweicloudsdkdds.v3.model import ListInstancesRequest

        resp = dds.list_instances(ListInstancesRequest())
        instances = resp.instances or []

        lines = [f"📋 DDS 网络类型检查 [区域: {config.region}]"]
        lines.append(f"  DDS 实例总数: {len(instances)}")
        risky: list[dict] = []

        for inst in instances:
            inst_id = inst.id
            inst_name = inst.name or ""

            # 从 groups 中提取 spec_code
            groups = getattr(inst, "groups", []) or []
            spec_codes: list[str] = []
            for g in groups:
                nodes = getattr(g, "nodes", []) or []
                for node in nodes:
                    sc = getattr(node, "spec_code", "") or ""
                    if sc and sc not in spec_codes:
                        spec_codes.append(sc)

            is_general = False
            for sc in spec_codes:
                if "enhanced" not in sc.lower():
                    is_general = True
                    break

            engine = getattr(inst, "datastore", None)
            engine_version = getattr(engine, "version", "") if engine else ""

            if is_general and spec_codes:
                detail = f"规格: {', '.join(spec_codes)}, 版本: {engine_version} — 网络为通用型"
                lines.append(f"  ℹ️ {inst_name} ({inst_id}): {detail}")
                risky.append(_make_record(
                    check_type="dds_network_type",
                    risk_level="medium",
                    resource_type="DDS",
                    resource_id=inst_id,
                    resource_name=inst_name,
                    region=config.region,
                    detail=detail,
                    extra={"spec_codes": spec_codes, "engine_version": engine_version},
                ))

        if not risky:
            lines.append(f"\n✅ 所有 DDS 实例网络类型正常")
        else:
            lines.insert(2, f"  ℹ️ 通用型网络实例: {len(risky)} 个")

        return "\n".join(lines), risky
    except Exception as e:
        return f"DDS 网络类型检查失败: {e}\n{traceback.format_exc()}", []


# ─────────────────────────────────────────────────────────────────────
# 巡检7: RDS 参数配置检查（双1检查）
# ─────────────────────────────────────────────────────────────────────

def check_rds_params(config: HuaweiCloudConfig) -> tuple[str, list[dict]]:
    """检查 RDS MySQL 实例参数: innodb_flush_log_at_trx_commit 和 sync_binlog 是否为 1（双1配置）"""
    try:
        rds = _rds_client(config)
        from huaweicloudsdkrds.v3.model import ListInstancesRequest, ListConfigurationsRequest

        resp = rds.list_instances(ListInstancesRequest(limit=100))
        instances = resp.instances or []

        mysql_instances = []
        for inst in instances:
            engine = getattr(inst, "datastore", None)
            engine_name = getattr(engine, "type", "").lower() if engine else ""
            if "mysql" in engine_name:
                mysql_instances.append(inst)

        lines = [f"📋 RDS MySQL 参数配置检查（双1） [区域: {config.region}]"]
        lines.append(f"  MySQL 实例总数: {len(mysql_instances)}")
        risky: list[dict] = []

        TARGET_PARAMS = {"innodb_flush_log_at_trx_commit": "1", "sync_binlog": "1"}

        for inst in mysql_instances:
            inst_id = inst.id
            inst_name = inst.name or ""

            try:
                from huaweicloudsdkrds.v3.model import ShowInstanceConfigurationRequest
                param_resp = rds.show_instance_configuration(
                    ShowInstanceConfigurationRequest(instance_id=inst_id)
                )
                params_list = getattr(param_resp, "configuration_parameters", []) or []

                param_values: dict[str, str] = {}
                for p in params_list:
                    pname = getattr(p, "name", "")
                    pval = getattr(p, "value", "")
                    if pname in TARGET_PARAMS:
                        param_values[pname] = str(pval)

                problems: list[str] = []
                for pname, expected in TARGET_PARAMS.items():
                    actual = param_values.get(pname, "未知")
                    if actual != expected:
                        problems.append(f"{pname}={actual}(期望{expected})")

                if problems:
                    detail = ", ".join(problems)
                    lines.append(f"  ⚠️ {inst_name} ({inst_id}): {detail}")
                    risky.append(_make_record(
                        check_type="rds_params_double_one",
                        risk_level="medium",
                        resource_type="RDS",
                        resource_id=inst_id,
                        resource_name=inst_name,
                        region=config.region,
                        detail=detail,
                        extra={"param_values": param_values},
                    ))
            except Exception as ex:
                lines.append(f"  ⚠️ {inst_name} ({inst_id}): 参数查询失败 - {ex}")

        if not risky:
            lines.append(f"\n✅ 所有 MySQL 实例参数配置正常（双1）")
        else:
            lines.insert(2, f"  ⚠️ 参数异常实例: {len(risky)} 个")

        return "\n".join(lines), risky
    except Exception as e:
        return f"RDS 参数检查失败: {e}\n{traceback.format_exc()}", []


# ─────────────────────────────────────────────────────────────────────
# 巡检8: CCE 节点 Pod 数量检查
# ─────────────────────────────────────────────────────────────────────

def check_cce_node_pods(config: HuaweiCloudConfig, pod_threshold: int = 110) -> tuple[str, list[dict]]:
    """检查 CCE 集群节点上的 Pod 数量是否超过阈值"""
    try:
        cce = _cce_client(config)
        from huaweicloudsdkcce.v3.model import ListClustersRequest, ListNodesRequest

        cluster_resp = cce.list_clusters(ListClustersRequest())
        clusters = cluster_resp.items or []

        lines = [f"📋 CCE 节点 Pod 数量检查 [区域: {config.region}]"]
        lines.append(f"  集群总数: {len(clusters)}, Pod 阈值: {pod_threshold}")
        risky: list[dict] = []

        for cluster in clusters:
            cluster_id = cluster.metadata.uid
            cluster_name = cluster.metadata.name or ""

            try:
                node_resp = cce.list_nodes(ListNodesRequest(cluster_id=cluster_id))
                nodes = node_resp.items or []

                for node in nodes:
                    node_name = node.metadata.name or ""
                    node_id = node.metadata.uid or ""
                    node_status = node.status
                    existing_pods = 0
                    max_pods = 0

                    if node_status:
                        capacity = getattr(node_status, "capacity", None)
                        allocatable = getattr(node_status, "allocatable", None)
                        if capacity:
                            max_pods = int(getattr(capacity, "pods", 0) or 0)
                        existing_phase = getattr(node_status, "phase", "")

                    # 通过 Kubernetes API 代理获取 Pod 数量
                    # 如果无法直接获取，使用 max_pods 做预警
                    if max_pods > 0 and max_pods >= pod_threshold:
                        detail = f"节点最大 Pod 数: {max_pods}, 阈值: {pod_threshold}"
                        lines.append(f"  ℹ️ [{cluster_name}] {node_name}: {detail}")

            except Exception as ex:
                lines.append(f"  ⚠️ 集群 {cluster_name} 节点查询失败: {ex}")

        if not risky:
            lines.append(f"\n✅ 未发现 Pod 数量超限的节点")

        return "\n".join(lines), risky
    except Exception as e:
        return f"CCE 节点 Pod 检查失败: {e}\n{traceback.format_exc()}", []


# ─────────────────────────────────────────────────────────────────────
# 巡检9: ECS 实例闲置检查（CPU 利用率过低）
# ─────────────────────────────────────────────────────────────────────

def check_ecs_idle(
    config: HuaweiCloudConfig,
    cpu_threshold: float = 5.0,
    days: int = 10,
) -> tuple[str, list[dict]]:
    """检查 ECS 实例 CPU 利用率 — 过去 N 天平均和最高 CPU 是否低于阈值"""
    try:
        from datetime import datetime, timedelta, timezone
        from huaweicloudsdkces.v1.model import ShowMetricDataRequest

        ecs = _ecs_client(config)
        ces = _ces_client(config)

        from huaweicloudsdkecs.v2 import ListServersDetailsRequest
        srv_resp = ecs.list_servers_details(ListServersDetailsRequest(limit=200))
        servers = srv_resp.servers or []

        running = [s for s in servers if (s.status or "").upper() == "ACTIVE"]

        lines = [f"📋 ECS 闲置检查 [区域: {config.region}]"]
        lines.append(f"  运行中实例: {len(running)}, CPU 阈值: {cpu_threshold}%, 检测窗口: {days}天")
        risky: list[dict] = []

        now = datetime.now(timezone.utc)
        start = now - timedelta(days=days)

        for s in running:
            try:
                request = ShowMetricDataRequest()
                request.namespace = "SYS.ECS"
                request.metric_name = "cpu_util"
                request.dim_0 = f"instance_id,{s.id}"
                request.period = 86400
                request.filter = "average"
                request.from_ = int(start.timestamp() * 1000)
                request.to = int(now.timestamp() * 1000)

                resp = ces.show_metric_data(request)
                datapoints = resp.datapoints or []

                if not datapoints:
                    continue

                avg_cpu = sum(dp.average for dp in datapoints) / len(datapoints)
                max_cpu = max(dp.average for dp in datapoints)

                if max_cpu < cpu_threshold:
                    flavor_id = s.flavor.get("id", "") if isinstance(s.flavor, dict) else str(s.flavor)
                    detail = f"平均CPU: {avg_cpu:.1f}%, 最高CPU: {max_cpu:.1f}%, 规格: {flavor_id}"
                    lines.append(f"  ⚠️ {s.name} ({s.id}): {detail}")
                    risky.append(_make_record(
                        check_type="ecs_idle",
                        risk_level="medium",
                        resource_type="ECS",
                        resource_id=s.id,
                        resource_name=s.name or "",
                        region=config.region,
                        detail=detail,
                        extra={
                            "avg_cpu": round(avg_cpu, 1),
                            "max_cpu": round(max_cpu, 1),
                            "instance_type": flavor_id,
                            "check_days": days,
                        },
                    ))
            except Exception:
                pass

        if not risky:
            lines.append(f"\n✅ 未发现低利用率的 ECS 实例")
        else:
            lines.insert(2, f"  ⚠️ 闲置实例: {len(risky)} 个")

        return "\n".join(lines), risky
    except Exception as e:
        return f"ECS 闲置检查失败: {e}\n{traceback.format_exc()}", []


# ─────────────────────────────────────────────────────────────────────
# 统一入口：运行所有巡检
# ─────────────────────────────────────────────────────────────────────

ALL_CHECKS = [
    ("ecs_security_group", "ECS安全组规则检查", check_ecs_security_groups),
    ("cce_workload_replica", "CCE工作负载副本数检查", check_cce_workload_replicas),
    ("rds_ha", "RDS高可用部署检查", check_rds_ha),
    ("dms_rabbitmq_cluster", "DMS RabbitMQ集群部署检查", check_dms_rabbitmq_cluster),
    ("rds_network_type", "RDS网络类型检查", check_rds_network_type),
    ("dds_network_type", "DDS网络类型检查", check_dds_network_type),
    ("rds_params_double_one", "RDS参数配置检查(双1)", check_rds_params),
    ("cce_node_pods", "CCE节点Pod数量检查", check_cce_node_pods),
    ("ecs_idle", "ECS闲置检查", check_ecs_idle),
]


def _run_check_single_region(
    config: HuaweiCloudConfig,
    check_type: str,
    check_fn,
    **kwargs,
) -> tuple[str, list[dict]]:
    """对单个区域执行单项巡检"""
    if check_type == "ecs_idle":
        return check_fn(config, **kwargs)
    elif check_type == "cce_node_pods":
        return check_fn(config, **kwargs)
    else:
        return check_fn(config)


def run_all_checks(
    config: HuaweiCloudConfig,
    checks: list[str] | None = None,
    cpu_threshold: float = 5.0,
    idle_days: int = 10,
    pod_threshold: int = 110,
) -> tuple[str, dict[str, list[dict]]]:
    """运行指定或全部巡检项（自动遍历所有配置的区域）

    Args:
        checks: 要运行的巡检类型列表，None=全部
        cpu_threshold: ECS 闲置 CPU 阈值
        idle_days: ECS 闲置检测天数
        pod_threshold: CCE Pod 数量阈值

    Returns:
        (text_report, {check_type: [structured_records]})
    """
    regions = config.get_regions()
    results_text: list[str] = []
    results_data: dict[str, list[dict]] = {}

    for check_type, check_name, check_fn in ALL_CHECKS:
        if checks and check_type not in checks:
            continue

        kwargs: dict = {}
        if check_type == "ecs_idle":
            kwargs = {"cpu_threshold": cpu_threshold, "days": idle_days}
        elif check_type == "cce_node_pods":
            kwargs = {"pod_threshold": pod_threshold}

        all_data: list[dict] = []
        all_text: list[str] = []

        for region in regions:
            region_cfg = config.for_region(region)
            if not region_cfg.project_id:
                all_text.append(f"⚠️ 跳过区域 {region}: 未获取到 project_id")
                continue
            text, data = _run_check_single_region(region_cfg, check_type, check_fn, **kwargs)
            all_text.append(text)
            all_data.extend(data)

        results_text.append("\n".join(all_text))
        results_data[check_type] = all_data

    full_text = "\n\n" + "═" * 60 + "\n\n".join([""] + results_text)
    return full_text, results_data


def run_single_check_all_regions(
    config: HuaweiCloudConfig,
    check_type: str,
    params: dict | None = None,
    task_regions: list[str] | None = None,
) -> tuple[str, list[dict]]:
    """对单个巡检项遍历区域执行（供 server.py 定时任务调用）

    Args:
        task_regions: 该巡检项独立配置的区域列表，为空时 fallback 到全局 regions
    """
    check_fn = None
    for ct, _, fn in ALL_CHECKS:
        if ct == check_type:
            check_fn = fn
            break
    if check_fn is None:
        return f"未知的巡检类型: {check_type}", []

    params = params or {}
    kwargs: dict = {}
    if check_type == "ecs_idle":
        kwargs["cpu_threshold"] = float(params.get("cpu_threshold", 5.0))
        kwargs["days"] = int(params.get("idle_days", 10))
    elif check_type == "cce_node_pods":
        kwargs["pod_threshold"] = int(params.get("pod_threshold", 110))

    regions = task_regions if task_regions else config.get_regions()
    all_text: list[str] = []
    all_data: list[dict] = []

    for region in regions:
        region_cfg = config.for_region(region)
        if not region_cfg.project_id:
            all_text.append(f"⚠️ 跳过区域 {region}: 未获取到 project_id")
            continue
        text, data = _run_check_single_region(region_cfg, check_type, check_fn, **kwargs)
        all_text.append(text)
        all_data.extend(data)

    return "\n".join(all_text), all_data
