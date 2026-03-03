"""MySQL 存储层 — AWS 巡检 & 华为云巡检结果的持久化与查询"""

import json
from datetime import datetime, timezone
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

from cloud_monitor.config import MySQLConfig

_pool_cfg: dict | None = None


def init_db(config: MySQLConfig):
    """保存 MySQL 连接参数，后续按需创建连接"""
    global _pool_cfg
    if not config.enabled:
        return
    _pool_cfg = {
        "host": config.host,
        "port": config.port,
        "user": config.user,
        "password": config.password,
        "database": config.db_name,
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
    }


def _conn() -> pymysql.Connection | None:
    if _pool_cfg is None:
        return None
    return pymysql.connect(**_pool_cfg)


def get_db():
    return _pool_cfg


# ─────────────────────────────────────────────────────────────────────
# AWS 巡检（idle_resources 表）
# ─────────────────────────────────────────────────────────────────────

def save_idle_resources(
    cloud: str,
    account: str,
    instances: list[dict[str, Any]],
    scan_params: dict[str, Any] | None = None,
):
    conn = _conn()
    if conn is None:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM idle_resources WHERE cloud=%s AND account=%s",
                (cloud, account),
            )
            if not instances:
                conn.commit()
                return

            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            sql = (
                "INSERT INTO idle_resources "
                "(cloud,account,resource_type,instance_id,instance_name,instance_type,"
                "status,region,availability_zone,private_ip,public_ip,"
                "avg_cpu,max_cpu,avg_mem,max_mem,tags,extra,scan_params,scan_time) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
            )
            rows = []
            for inst in instances:
                rows.append((
                    cloud, account,
                    inst.get("resource_type", ""),
                    inst.get("instance_id", ""),
                    inst.get("instance_name", ""),
                    inst.get("instance_type", ""),
                    inst.get("status", ""),
                    inst.get("region", ""),
                    inst.get("availability_zone", ""),
                    inst.get("private_ip", ""),
                    inst.get("public_ip"),
                    _to_str(inst.get("avg_cpu")),
                    _to_str(inst.get("max_cpu")),
                    _to_str(inst.get("avg_mem")),
                    _to_str(inst.get("max_mem")),
                    json.dumps(inst.get("tags") or {}, ensure_ascii=False),
                    json.dumps(inst.get("extra") or {}, ensure_ascii=False),
                    json.dumps(scan_params or {}, ensure_ascii=False),
                    now,
                ))
            cur.executemany(sql, rows)
        conn.commit()
    finally:
        conn.close()


def _to_str(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return f"{v:.1f}%"
    return str(v)


def query_idle_resources(
    cloud: str = "",
    resource_type: str = "",
    status: str = "",
    region: str = "",
    account: str = "",
    keyword: str = "",
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    conn = _conn()
    if conn is None:
        return {"total": 0, "items": [], "page": page, "page_size": page_size}

    try:
        wheres, params = _build_idle_where(cloud, resource_type, status, region, account, keyword)
        where_sql = ("WHERE " + " AND ".join(wheres)) if wheres else ""

        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS cnt FROM idle_resources {where_sql}", params)
            total = cur.fetchone()["cnt"]

            offset = (page - 1) * page_size
            cur.execute(
                f"SELECT * FROM idle_resources {where_sql} ORDER BY scan_time DESC LIMIT %s OFFSET %s",
                params + [page_size, offset],
            )
            rows = cur.fetchall()

        items = [_row_to_item(r) for r in rows]
        return {"total": total, "items": items, "page": page, "page_size": page_size}
    finally:
        conn.close()


def _build_idle_where(cloud, resource_type, status, region, account, keyword):
    wheres = []
    params = []
    if cloud:
        wheres.append("cloud=%s"); params.append(cloud)
    if resource_type:
        wheres.append("resource_type=%s"); params.append(resource_type)
    if status:
        wheres.append("status=%s"); params.append(status)
    if region:
        wheres.append("region=%s"); params.append(region)
    if account:
        wheres.append("account=%s"); params.append(account)
    if keyword:
        wheres.append("(instance_id LIKE %s OR instance_name LIKE %s)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    return wheres, params


def _row_to_item(row: dict) -> dict:
    item = dict(row)
    item.pop("id", None)
    for k in ("tags", "extra", "scan_params"):
        if k in item and isinstance(item[k], str):
            try:
                item[k] = json.loads(item[k])
            except (json.JSONDecodeError, TypeError):
                pass
    if "scan_time" in item and isinstance(item["scan_time"], datetime):
        item["scan_time"] = item["scan_time"].isoformat()
    return item


def get_summary() -> dict[str, Any]:
    conn = _conn()
    if conn is None:
        return {"total": 0, "by_resource_type": {}, "by_status": {}, "by_region": {}, "scan_time": None}

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM idle_resources")
            total = cur.fetchone()["cnt"]

            by_resource_type = _group_count(cur, "idle_resources", "resource_type")
            by_status = _group_count(cur, "idle_resources", "status")
            by_region = _group_count(cur, "idle_resources", "region")

            cur.execute("SELECT scan_time FROM idle_resources ORDER BY scan_time DESC LIMIT 1")
            row = cur.fetchone()
            scan_time = None
            if row and row["scan_time"]:
                scan_time = row["scan_time"].isoformat() if isinstance(row["scan_time"], datetime) else str(row["scan_time"])

        return {
            "total": total,
            "by_resource_type": by_resource_type,
            "by_status": by_status,
            "by_region": by_region,
            "scan_time": scan_time,
        }
    finally:
        conn.close()


def get_filter_options() -> dict[str, list[str]]:
    conn = _conn()
    if conn is None:
        return {"resource_types": [], "statuses": [], "regions": [], "accounts": []}

    try:
        with conn.cursor() as cur:
            return {
                "resource_types": _distinct(cur, "idle_resources", "resource_type"),
                "statuses": _distinct(cur, "idle_resources", "status"),
                "regions": _distinct(cur, "idle_resources", "region"),
                "accounts": _distinct(cur, "idle_resources", "account"),
            }
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────
# 华为云巡检结果（huawei_checks 表）
# ─────────────────────────────────────────────────────────────────────

def save_check_results(
    check_type: str,
    records: list[dict[str, Any]],
):
    conn = _conn()
    if conn is None:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM huawei_checks WHERE check_type=%s", (check_type,))
            if not records:
                conn.commit()
                return

            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            sql = (
                "INSERT INTO huawei_checks "
                "(check_type,resource_type,risk_level,resource_id,resource_name,"
                "region,detail,extra,scan_time) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
            )
            rows = []
            for rec in records:
                extra = {k: v for k, v in rec.items()
                         if k not in ("check_type", "resource_type", "risk_level",
                                      "resource_id", "resource_name", "region", "detail")}
                rows.append((
                    rec.get("check_type", check_type),
                    rec.get("resource_type", ""),
                    rec.get("risk_level", ""),
                    rec.get("resource_id", ""),
                    rec.get("resource_name", ""),
                    rec.get("region", ""),
                    rec.get("detail", ""),
                    json.dumps(extra, ensure_ascii=False),
                    now,
                ))
            cur.executemany(sql, rows)
        conn.commit()
    finally:
        conn.close()


def query_check_results(
    check_type: str = "",
    resource_type: str = "",
    risk_level: str = "",
    region: str = "",
    keyword: str = "",
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    conn = _conn()
    if conn is None:
        return {"total": 0, "items": [], "page": page, "page_size": page_size}

    try:
        wheres, params = [], []
        if check_type:
            wheres.append("check_type=%s"); params.append(check_type)
        if resource_type:
            wheres.append("resource_type=%s"); params.append(resource_type)
        if risk_level:
            wheres.append("risk_level=%s"); params.append(risk_level)
        if region:
            wheres.append("region=%s"); params.append(region)
        if keyword:
            wheres.append("(resource_id LIKE %s OR resource_name LIKE %s OR detail LIKE %s)")
            params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])

        where_sql = ("WHERE " + " AND ".join(wheres)) if wheres else ""

        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS cnt FROM huawei_checks {where_sql}", params)
            total = cur.fetchone()["cnt"]

            offset = (page - 1) * page_size
            cur.execute(
                f"SELECT * FROM huawei_checks {where_sql} ORDER BY scan_time DESC LIMIT %s OFFSET %s",
                params + [page_size, offset],
            )
            rows = cur.fetchall()

        items = [_check_row_to_item(r) for r in rows]
        return {"total": total, "items": items, "page": page, "page_size": page_size}
    finally:
        conn.close()


def _check_row_to_item(row: dict) -> dict:
    item = dict(row)
    item.pop("id", None)
    if "extra" in item and isinstance(item["extra"], str):
        try:
            item["extra"] = json.loads(item["extra"])
        except (json.JSONDecodeError, TypeError):
            pass
    if "scan_time" in item and isinstance(item["scan_time"], datetime):
        item["scan_time"] = item["scan_time"].isoformat()
    return item


def get_check_summary() -> dict[str, Any]:
    conn = _conn()
    if conn is None:
        return {"total": 0, "by_check_type": {}, "by_risk_level": {}, "by_resource_type": {}, "scan_time": None}

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM huawei_checks")
            total = cur.fetchone()["cnt"]

            by_check_type = _group_count(cur, "huawei_checks", "check_type")
            by_risk_level = _group_count(cur, "huawei_checks", "risk_level")
            by_resource_type = _group_count(cur, "huawei_checks", "resource_type")

            cur.execute("SELECT scan_time FROM huawei_checks ORDER BY scan_time DESC LIMIT 1")
            row = cur.fetchone()
            scan_time = None
            if row and row["scan_time"]:
                scan_time = row["scan_time"].isoformat() if isinstance(row["scan_time"], datetime) else str(row["scan_time"])

        return {
            "total": total,
            "by_check_type": by_check_type,
            "by_risk_level": by_risk_level,
            "by_resource_type": by_resource_type,
            "scan_time": scan_time,
        }
    finally:
        conn.close()


def get_check_filter_options() -> dict[str, list[str]]:
    conn = _conn()
    if conn is None:
        return {"check_types": [], "risk_levels": [], "resource_types": [], "regions": []}

    try:
        with conn.cursor() as cur:
            return {
                "check_types": _distinct(cur, "huawei_checks", "check_type"),
                "risk_levels": _distinct(cur, "huawei_checks", "risk_level"),
                "resource_types": _distinct(cur, "huawei_checks", "resource_type"),
                "regions": _distinct(cur, "huawei_checks", "region"),
            }
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────────────────

def _group_count(cur, table: str, column: str) -> dict[str, int]:
    cur.execute(f"SELECT `{column}` AS k, COUNT(*) AS cnt FROM `{table}` WHERE `{column}` != '' GROUP BY `{column}`")
    return {row["k"]: row["cnt"] for row in cur.fetchall()}


def _distinct(cur, table: str, column: str) -> list[str]:
    cur.execute(f"SELECT DISTINCT `{column}` FROM `{table}` WHERE `{column}` != '' ORDER BY `{column}`")
    return [row[column] for row in cur.fetchall()]
