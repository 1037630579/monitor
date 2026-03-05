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

logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("apscheduler").setLevel(logging.WARNING)
log = logging.getLogger("cloud_monitor")

app = FastAPI(title="Cloud Monitor", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_app_config: AppConfig | None = None


def _run_aws_single(check_type: str, params: dict, task_regions: list[str] | None = None):
    """执行 AWS 单项巡检（遍历指定区域）并写入 MySQL"""
    import time
    cfg = _app_config
    if cfg is None or not cfg.aws.enabled:
        return
    try:
        from cloud_monitor.tools.aws import run_single_aws_check, AWS_CHECK_NAMES

        for acc in cfg.aws.accounts:
            regions = task_regions if task_regions else acc.get_regions()
            t0 = time.time()
            log.info("[AWS巡检] 开始 | %s, 账户=%s, 区域(%d): %s",
                     check_type, acc.name, len(regions), regions)
            _, data = run_single_aws_check(acc, check_type, params, task_regions=task_regions)
            elapsed = time.time() - t0
            if check_type == "ec2" and data:
                scan_params = {
                    "cpu_threshold": params.get("cpu_threshold", 10.0),
                    "mem_threshold": params.get("mem_threshold", 10.0),
                    "hours": params.get("hours", 360),
                }
                save_idle_resources("AWS", acc.name, data, scan_params)
            log.info("[AWS巡检] 完成 | %s, 账户=%s, 数据 %d 条, 耗时 %.1fs",
                     check_type, acc.name, len(data), elapsed)
    except Exception:
        log.exception("[AWS巡检] 异常 | %s", check_type)


def _run_huawei_group(group_name: str, check_types: list[str], params: dict, task_regions: list[str] | None = None):
    """执行华为云资源组巡检（同一资源的多个巡检项顺序执行）"""
    import time
    cfg = _app_config
    if cfg is None or not cfg.huawei.enabled:
        return
    from cloud_monitor.tools.huawei_check import run_single_check_all_regions

    regions = task_regions if task_regions else cfg.huawei.get_regions()
    t0 = time.time()
    log.info("[华为云巡检] 开始 | %s (%s), 区域(%d): %s",
             group_name, ", ".join(check_types), len(regions), regions)
    total_records = 0
    for ct in check_types:
        try:
            _, data = run_single_check_all_regions(cfg.huawei, ct, params, task_regions=task_regions)
            save_check_results(ct, data)
            total_records += len(data)
            log.info("[华为云巡检]   %s → %d 条", ct, len(data))
        except Exception:
            log.exception("[华为云巡检] 异常 | %s", ct)
    elapsed = time.time() - t0
    log.info("[华为云巡检] 完成 | %s, 共 %d 条, 耗时 %.1fs", group_name, total_records, elapsed)


def _bg(fn, *args, name="job"):
    """在后台线程中运行函数"""
    threading.Thread(target=fn, args=args, daemon=True, name=name).start()


def _run_all_checks_sequential():
    """按顺序执行所有已启用的巡检任务（AWS → 华为云）"""
    import time
    cfg = _app_config
    if cfg is None:
        return
    t_total = time.time()
    log.info("=" * 60)
    log.info("[定时巡检] 开始顺序执行所有巡检任务")
    log.info("=" * 60)

    task_idx = 0
    for check_type, task in cfg.schedule.aws_checks.items():
        if not task.enabled or not cfg.aws.enabled:
            continue
        task_idx += 1
        log.info("[定时巡检] (%d) AWS %s 开始", task_idx, check_type)
        _run_aws_single(check_type, task.params, task.regions or None)
        log.info("[定时巡检] (%d) AWS %s 完成", task_idx, check_type)

    for group_name, task in cfg.schedule.huawei_checks.items():
        if not task.enabled or not cfg.huawei.enabled:
            continue
        task_idx += 1
        cts = task.check_types if task.check_types else [group_name]
        log.info("[定时巡检] (%d) 华为云 %s 开始", task_idx, group_name)
        _run_huawei_group(group_name, cts, task.params, task.regions or None)
        log.info("[定时巡检] (%d) 华为云 %s 完成", task_idx, group_name)

    elapsed = time.time() - t_total
    log.info("=" * 60)
    log.info("[定时巡检] 全部完成 | 共 %d 项, 总耗时 %.1fs", task_idx, elapsed)
    log.info("=" * 60)


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

    aws_tasks: list[tuple[str, dict, list[str] | None]] = []
    huawei_tasks: list[tuple[str, list[str], dict, list[str] | None]] = []

    for check_type, task in config.schedule.aws_checks.items():
        if not task.enabled:
            continue
        if not config.aws.enabled:
            log.warning("AWS 未启用, 跳过巡检: %s", check_type)
            continue
        aws_tasks.append((check_type, task.params, task.regions or None))

    for group_name, task in config.schedule.huawei_checks.items():
        if not task.enabled:
            continue
        if not config.huawei.enabled:
            log.warning("华为云未启用, 跳过巡检: %s", group_name)
            continue
        cts = task.check_types if task.check_types else [group_name]
        huawei_tasks.append((group_name, cts, task.params, task.regions or None))

    job_count = len(aws_tasks) + len(huawei_tasks)

    if job_count > 0:
        all_tasks = list(config.schedule.aws_checks.values()) + list(config.schedule.huawei_checks.values())
        first_enabled = next((t for t in all_tasks if t.enabled), None)
        cron_dow = first_enabled.cron_day_of_week if first_enabled else "*"
        cron_h = first_enabled.cron_hour if first_enabled else 2
        cron_m = first_enabled.cron_minute if first_enabled else 0

        scheduler.add_job(
            lambda: _bg(_run_all_checks_sequential, name="all-checks"),
            trigger=CronTrigger(day_of_week=cron_dow, hour=cron_h, minute=cron_m),
            id="all_checks", name="全部巡检（顺序执行）",
        )
        scheduler.start()

        job = scheduler.get_job("all_checks")
        next_run = job.next_run_time.strftime("%Y-%m-%d %H:%M:%S %Z") if job and job.next_run_time else "未知"

        log.info("=" * 60)
        log.info("定时任务调度器已启动 (时区: Asia/Shanghai)")
        log.info("执行模式: 顺序执行 | 下次执行: %s", next_run)
        log.info("共 %d 个巡检任务:", job_count)

        default_aws_regions = config.aws.accounts[0].get_regions() if config.aws.accounts else []
        idx = 0
        for ct, t in config.schedule.aws_checks.items():
            if t.enabled and config.aws.enabled:
                idx += 1
                effective = t.regions if t.regions else default_aws_regions
                log.info("  %d. [aws_%s] AWS巡检: %s | 区域(%d): %s", idx, ct, ct, len(effective), effective)
        for gn, t in config.schedule.huawei_checks.items():
            if t.enabled and config.huawei.enabled:
                idx += 1
                effective = t.regions if t.regions else config.huawei.get_regions()
                cts = t.check_types if t.check_types else [gn]
                label = f"{gn} ({', '.join(cts)})" if len(cts) > 1 else gn
                log.info("  %d. [huawei_%s] 华为云巡检: %s | 区域(%d): %s", idx, gn, label, len(effective), effective)
        log.info("=" * 60)

        if config.schedule.run_on_startup:
            log.info("服务启动: 立即顺序执行首次巡检")
            _bg(_run_all_checks_sequential, name="all-checks-startup")


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
    default_aws_regions = cfg.aws.accounts[0].get_regions() if cfg.aws.accounts else []
    for ct, t in cfg.schedule.aws_checks.items():
        if t.enabled:
            effective_regions = t.regions if t.regions else default_aws_regions
            tasks.append({
                "id": f"aws_{ct}", "name": f"AWS: {ct}",
                "cron_day_of_week": t.cron_day_of_week,
                "cron_hour": t.cron_hour,
                "params": t.params,
                "regions": effective_regions,
            })
    for gn, t in cfg.schedule.huawei_checks.items():
        if t.enabled:
            effective_regions = t.regions if t.regions else cfg.huawei.get_regions()
            cts = t.check_types if t.check_types else [gn]
            tasks.append({
                "id": f"huawei_{gn}", "name": f"华为云: {gn}",
                "check_types": cts,
                "cron_day_of_week": t.cron_day_of_week,
                "cron_hour": t.cron_hour,
                "params": t.params,
                "regions": effective_regions,
            })

    return {
        "enabled": True,
        "run_on_startup": cfg.schedule.run_on_startup,
        "tasks": tasks,
    }


# ── 智能对话 API（SSE 流式返回，不推送 Webhook）──


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

    import asyncio

    async def event_stream():
        yield _sse_event("session", {"session_id": session_id})

        client = None
        try:
            from claude_agent_sdk import (
                AssistantMessage,
                ClaudeSDKClient,
                ResultMessage,
                TextBlock,
                ToolUseBlock,
            )
            from cloud_monitor.agent import create_agent_options

            options = create_agent_options(cfg)
            client = ClaudeSDKClient(options=options)
            await client.__aenter__()

            await client.query(message, session_id=session_id)

            async for msg in client.receive_response():
                if await request.is_disconnected():
                    log.info("客户端已断开, 终止对话")
                    await client.interrupt()
                    break

                if isinstance(msg, AssistantMessage):
                    has_tool_use = any(
                        isinstance(b, ToolUseBlock) for b in msg.content
                    )
                    for block in msg.content:
                        if isinstance(block, ToolUseBlock):
                            params = {k: v for k, v in (block.input or {}).items()
                                      if v is not None and v != ""}
                            yield _sse_event("tool_call", {"name": block.name, "params": params})
                        elif isinstance(block, TextBlock):
                            if has_tool_use:
                                continue
                            yield _sse_event("text", {"text": block.text})
                elif isinstance(msg, ResultMessage):
                    if msg.total_cost_usd and msg.total_cost_usd > 0:
                        yield _sse_event("cost", {"cost_usd": msg.total_cost_usd})

            yield _sse_event("done", {})
        except asyncio.CancelledError:
            log.info("对话请求被取消")
        except Exception as e:
            log.exception("Chat SSE error")
            yield _sse_event("error", {"error": str(e)})
        finally:
            if client:
                try:
                    await client.interrupt()
                except Exception:
                    pass
                try:
                    await client.__aexit__(None, None, None)
                except Exception:
                    pass

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/chat/reset")
async def api_chat_reset(request: Request):
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
