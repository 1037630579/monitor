"""FastAPI 服务 — AWS 巡检 + 华为云巡检 API + 智能对话 + 前端静态文件托管 + 定时巡检"""

import json
import logging
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse

from cloud_monitor.config import AppConfig, load_config
from cloud_monitor.db import (
    get_check_filter_options,
    get_check_summary,
    get_filter_options,
    get_summary,
    init_db,
    query_check_results,
    query_idle_resources,
    save_check_results,
    save_idle_resources,
)

log = logging.getLogger("cloud_monitor.scheduler")

app = FastAPI(title="Cloud Monitor", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_app_config: AppConfig | None = None


def _run_ec2_job():
    """执行 AWS EC2 巡检并写入 MySQL"""
    cfg = _app_config
    if cfg is None or not cfg.aws.enabled:
        return
    try:
        from cloud_monitor.tools.aws import list_ec2_aws
        ec2_cfg = cfg.ec2_check
        scan_params = {
            "cpu_threshold": ec2_cfg.cpu_threshold,
            "mem_threshold": ec2_cfg.mem_threshold,
            "hours": ec2_cfg.hours,
        }
        for acc in cfg.aws.accounts:
            log.info("EC2 巡检开始: 账户=%s", acc.name)
            _, structured = list_ec2_aws(
                acc,
                cpu_threshold=ec2_cfg.cpu_threshold,
                mem_threshold=ec2_cfg.mem_threshold,
                hours=ec2_cfg.hours,
                max_workers=ec2_cfg.max_workers,
            )
            if structured:
                save_idle_resources("AWS", acc.name, structured, scan_params)
                log.info("EC2 巡检完成: 账户=%s, 写入 %d 条", acc.name, len(structured))
            else:
                log.info("EC2 巡检完成: 账户=%s, 无数据写入", acc.name)
    except Exception:
        log.exception("EC2 巡检异常")


def _run_huawei_single(check_type: str, params: dict):
    """执行华为云单项巡检（遍历所有区域）并写入 MySQL"""
    cfg = _app_config
    if cfg is None or not cfg.huawei.enabled:
        return
    try:
        from cloud_monitor.tools.huawei_check import run_single_check_all_regions

        regions = cfg.huawei.get_regions()
        log.info("华为云巡检开始: %s, 区域: %s", check_type, regions)
        _, data = run_single_check_all_regions(cfg.huawei, check_type, params)
        save_check_results(check_type, data)
        log.info("华为云巡检完成: %s, 写入 %d 条", check_type, len(data))
    except Exception:
        log.exception("华为云巡检异常: %s", check_type)


def _bg(fn, *args, name="job"):
    """在后台线程中运行函数"""
    threading.Thread(target=fn, args=args, daemon=True, name=name).start()


@app.on_event("startup")
def startup():
    global _app_config
    config = load_config()
    _app_config = config

    if config.mysql.enabled:
        init_db(config.mysql)

    if not config.schedule.enabled:
        return

    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")

    job_count = 0

    if config.aws.enabled and config.schedule.aws_ec2.enabled:
        t = config.schedule.aws_ec2
        scheduler.add_job(
            lambda: _bg(_run_ec2_job, name="ec2-job"),
            trigger=CronTrigger(day_of_week=t.cron_day_of_week, hour=t.cron_hour),
            id="aws_ec2", name="AWS EC2 巡检",
        )
        log.info("定时任务注册: AWS EC2 巡检, 每周%s %d:00", t.cron_day_of_week, t.cron_hour)
        job_count += 1

    for check_type, task in config.schedule.huawei_checks.items():
        if not task.enabled:
            continue
        if not config.huawei.enabled:
            log.warning("华为云未启用, 跳过巡检: %s", check_type)
            continue
        p = task.params
        scheduler.add_job(
            lambda ct=check_type, pa=p: _bg(_run_huawei_single, ct, pa, name=f"hw-{ct}"),
            trigger=CronTrigger(day_of_week=task.cron_day_of_week, hour=task.cron_hour),
            id=f"huawei_{check_type}", name=f"华为云巡检: {check_type}",
        )
        log.info("定时任务注册: 华为云 %s, 每周%s %d:00", check_type, task.cron_day_of_week, task.cron_hour)
        job_count += 1

    if job_count > 0:
        scheduler.start()
        log.info("定时任务调度器已启动: 共 %d 个任务", job_count)

        if config.schedule.run_on_startup:
            log.info("服务启动: 立即执行首次巡检")
            if config.aws.enabled and config.schedule.aws_ec2.enabled:
                _bg(_run_ec2_job, name="ec2-startup")
            for check_type, task in config.schedule.huawei_checks.items():
                if task.enabled and config.huawei.enabled:
                    _bg(_run_huawei_single, check_type, task.params, name=f"hw-{check_type}-startup")


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


# ── 定时任务状态 API ──

@app.get("/api/schedule/status")
def api_schedule_status():
    cfg = _app_config
    if cfg is None or not cfg.schedule.enabled:
        return {"enabled": False}

    tasks = []
    if cfg.schedule.aws_ec2.enabled:
        tasks.append({
            "id": "aws_ec2", "name": "AWS EC2 巡检",
            "cron_day_of_week": cfg.schedule.aws_ec2.cron_day_of_week,
            "cron_hour": cfg.schedule.aws_ec2.cron_hour,
        })
    for ct, t in cfg.schedule.huawei_checks.items():
        if t.enabled:
            tasks.append({
                "id": f"huawei_{ct}", "name": f"华为云: {ct}",
                "cron_day_of_week": t.cron_day_of_week,
                "cron_hour": t.cron_hour,
                "params": t.params,
            })

    return {
        "enabled": True,
        "run_on_startup": cfg.schedule.run_on_startup,
        "tasks": tasks,
    }


# ── 智能对话 API（SSE 流式返回，不推送 Webhook）──

_chat_sessions: dict[str, object] = {}


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/chat")
async def api_chat(request: Request):
    body = await request.json()
    message = body.get("message", "").strip()
    session_id = body.get("session_id", "")

    if not message:
        return {"error": "message 不能为空"}

    cfg = _app_config
    if cfg is None:
        return {"error": "服务未初始化"}

    if not session_id:
        session_id = str(uuid.uuid4())

    async def event_stream():
        yield _sse_event("session", {"session_id": session_id})

        try:
            from claude_agent_sdk import (
                AssistantMessage,
                ClaudeSDKClient,
                ResultMessage,
                TextBlock,
                ToolUseBlock,
            )
            from cloud_monitor.agent import create_agent_options

            if session_id in _chat_sessions:
                client = _chat_sessions[session_id]
            else:
                options = create_agent_options(cfg)
                client = ClaudeSDKClient(options=options)
                await client.__aenter__()
                _chat_sessions[session_id] = client

            await client.query(message)
            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            yield _sse_event("text", {"text": block.text})
                        elif isinstance(block, ToolUseBlock):
                            params = {k: v for k, v in (block.input or {}).items()
                                      if v is not None and v != ""}
                            yield _sse_event("tool_call", {"name": block.name, "params": params})
                elif isinstance(msg, ResultMessage):
                    if msg.total_cost_usd and msg.total_cost_usd > 0:
                        yield _sse_event("cost", {"cost_usd": msg.total_cost_usd})

            yield _sse_event("done", {})
        except Exception as e:
            log.exception("智能对话异常")
            yield _sse_event("error", {"error": str(e)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/chat/reset")
async def api_chat_reset(request: Request):
    body = await request.json()
    session_id = body.get("session_id", "")
    if session_id and session_id in _chat_sessions:
        client = _chat_sessions.pop(session_id)
        try:
            await client.__aexit__(None, None, None)
        except Exception:
            pass
    return {"ok": True}


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
