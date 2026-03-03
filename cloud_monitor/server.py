"""FastAPI 服务 — AWS 巡检 + 华为云巡检 API + 前端静态文件托管"""

from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from cloud_monitor.config import load_config
from cloud_monitor.db import (
    get_check_filter_options,
    get_check_summary,
    get_filter_options,
    get_summary,
    init_db,
    query_check_results,
    query_idle_resources,
)

app = FastAPI(title="Cloud Monitor", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    config = load_config()
    if config.mysql.enabled:
        init_db(config.mysql)


# ── AWS 巡检 API ──

@app.get("/api/aws-checks")
def api_aws_checks(
    resource_type: str = Query("", description="资源类型: EC2/ELB/RDS/S3 等"),
    status: str = Query("", description="状态筛选: stopped / low_utilization"),
    region: str = Query("", description="区域筛选"),
    account: str = Query("", description="账户筛选"),
    keyword: str = Query("", description="实例ID/名称模糊搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
):
    return query_idle_resources(
        resource_type=resource_type, status=status, region=region,
        account=account, keyword=keyword,
        page=page, page_size=page_size,
    )


@app.get("/api/aws-checks/summary")
def api_aws_summary():
    return get_summary()


@app.get("/api/aws-checks/filter-options")
def api_aws_filter_options():
    return get_filter_options()


# ── 华为云巡检 API ──

CHECK_TYPE_NAMES = {
    "ecs_security_group": "ECS安全组规则",
    "cce_workload_replica": "CCE工作负载副本数",
    "rds_ha": "RDS高可用部署",
    "dms_rabbitmq_cluster": "DMS RabbitMQ集群",
    "rds_network_type": "RDS网络类型",
    "dds_network_type": "DDS网络类型",
    "rds_params_double_one": "RDS参数配置(双1)",
    "cce_node_pods": "CCE节点Pod数量",
    "ecs_idle": "ECS闲置检查",
}


@app.get("/api/huawei-checks")
def api_huawei_checks(
    check_type: str = Query("", description="巡检类型筛选"),
    resource_type: str = Query("", description="资源类型: ECS/CCE/RDS/DDS/DMS"),
    risk_level: str = Query("", description="风险级别: high/medium/low"),
    region: str = Query("", description="区域筛选"),
    keyword: str = Query("", description="资源ID/名称/详情模糊搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
):
    return query_check_results(
        check_type=check_type, resource_type=resource_type,
        risk_level=risk_level, region=region, keyword=keyword,
        page=page, page_size=page_size,
    )


@app.get("/api/huawei-checks/summary")
def api_huawei_checks_summary():
    summary = get_check_summary()
    summary["check_type_names"] = CHECK_TYPE_NAMES
    return summary


@app.get("/api/huawei-checks/filter-options")
def api_huawei_checks_filter_options():
    opts = get_check_filter_options()
    opts["check_type_names"] = CHECK_TYPE_NAMES
    return opts


WEB_DIST = Path(__file__).parent.parent / "web" / "dist"

if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(WEB_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        file_path = WEB_DIST / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(WEB_DIST / "index.html"))


def run_server(host: str = "0.0.0.0", port: int = 8080):
    import uvicorn
    uvicorn.run(app, host=host, port=port)
