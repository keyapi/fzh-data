#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PB 订单处理 Web 界面（FastAPI + Jinja）。

只做四件事：接收上传建任务、展示进度与报告、鉴权后下载产物、按相同输入重跑。
真正的处理在 RQ worker（`web/tasks.py`）里，Web 进程不再被 PDF/Excel 占住。

安全边界：
- **钉钉登录闸门**（`web/auth.py`）：配了 `PB_ORDERS_OIDC_ISSUER` 就要求先登录，
  未登录一律挡在登录页；可选用户白名单。
- 不暴露 artifact 目录为静态目录，下载必须走 `/artifacts/{id}/download`；
- 上传物理名由服务器生成，用户文件名只用于显示；
- 下载前复查绝对路径仍在 artifacts 根之下；
- 请求体积在中间件层按 Content-Length 提前拒绝。

部署形态：可以挂在根路径（本机开发），也可以挂在反代前缀下（如公网 `/pb/`）——
所有生成的 URL 都走 `PB_ORDERS_URL_PREFIX`，不在模板里写死根绝对路径。
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from urllib.parse import quote

_PB_DIR = Path(__file__).resolve().parent.parent
if str(_PB_DIR) not in sys.path:
    sys.path.insert(0, str(_PB_DIR))

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.openapi.docs import get_swagger_ui_html  # noqa: E402
from fastapi.responses import (  # noqa: E402
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
)
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.templating import Jinja2Templates  # noqa: E402

from web import api as api_mod  # noqa: E402
from web import api_errors  # noqa: E402
from web import auth as auth_mod  # noqa: E402
from web import csrf as csrf_mod  # noqa: E402
from web import housekeeping  # noqa: E402
from web import jobs_service  # noqa: E402
from web import storage  # noqa: E402
from web.config import get_settings  # noqa: E402
from web.repository import ARTIFACT_LABELS, NO_STOCK_KEY, Repository  # noqa: E402

WEB_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))

log = logging.getLogger("pb_orders.web")

_SKU_SPLIT = re.compile(r"[,，;；\s]+")


def parse_sku_list(raw: str) -> list[str]:
    """把断货 SKU 的输入文本解析成列表。

    逗号（中英文）、分号、空格、换行都算分隔；空项丢掉；
    **按小写去重**（保留第一次出现的写法）—— 匹配本来就是大小写不敏感的，
    所以 `YELLOW-138` 和 `Yellow-138` 是同一条。
    """
    seen: set[str] = set()
    out: list[str] = []
    for part in _SKU_SPLIT.split(raw or ""):
        sku = part.strip()
        if not sku or sku.lower() in seen:
            continue
        seen.add(sku.lower())
        out.append(sku)
    return out


def _human_size(num) -> str:
    try:
        size = float(num)
    except (TypeError, ValueError):
        return "-"
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


templates.env.filters["human_size"] = _human_size
templates.env.globals["ARTIFACT_LABELS"] = ARTIFACT_LABELS

STATUS_LABELS = {
    "uploaded": "已接收",
    "queued": "排队中",
    "running": "处理中",
    "succeeded": "成功",
    "failed": "失败",
}
templates.env.globals["STATUS_LABELS"] = STATUS_LABELS

JOB_TYPE_LABELS = {
    "fulfillment": "出件",
    "stock_check": "库存预检",
}
templates.env.globals["JOB_TYPE_LABELS"] = JOB_TYPE_LABELS


def get_queue(settings):
    from redis import Redis
    from rq import Queue

    conn = Redis.from_url(settings.redis_url, socket_connect_timeout=3)
    return Queue(settings.queue_name, connection=conn)


def enqueue_job(settings, repo: Repository, job_id: str) -> None:
    """把任务投进 RQ。Redis 不可用时给用户可读提示而不是 500 堆栈。

    提到模块级是为了测试能替换成同步执行，不必在测试里跑一个 Redis。
    """
    try:
        rq_job = get_queue(settings).enqueue(
            "web.tasks.run_job", job_id, job_timeout=settings.job_timeout
        )
    except Exception as exc:  # noqa: BLE001 - Redis 不可用要给用户可读提示
        raise HTTPException(
            status_code=503,
            detail=f"任务队列不可用（{type(exc).__name__}）。请确认 Redis 已启动。",
        ) from exc
    repo.mark_queued(job_id, rq_job.id)


def create_app() -> FastAPI:
    settings = get_settings()
    settings.ensure_dirs()
    repo = Repository(settings.db_path)
    try:
        housekeeping.purge_expired(settings, repo)
    except Exception:  # noqa: BLE001 - 清理失败不应挡住服务启动
        log.exception("过期任务清理失败")

    prefix = settings.url_prefix
    templates.env.globals["prefix"] = prefix

    def url(path: str) -> str:
        return f"{prefix}{path}"

    def enqueue_or_fail(job_id: str) -> None:
        """投队列；Redis 不可用时把任务落成失败，页面才看得到原因。"""
        try:
            enqueue_job(settings, repo, job_id)
        except HTTPException as exc:
            repo.mark_failed(
                job_id,
                {"code": "queue_unavailable", "message": exc.detail, "hint": "确认 Redis 后重新提交。"},
            )

    def current_no_stock() -> str:
        """当前生效的断货 SKU 列表（逗号分隔）。

        页面里设过就用页面那份（存在 `app_settings`），从没设过才回落到
        `.env` 的 `PB_ORDERS_DEFAULT_NO_STOCK` —— 也就是「初始值」。
        """
        stored = repo.get_setting(NO_STOCK_KEY)
        if stored is not None:
            return stored["value"]
        return ",".join(settings.default_no_stock)

    app = FastAPI(title="PB 订单处理", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

    if prefix:
        # 应用看到的路径没有前缀（反代剥掉了），但对外文档必须指到 /pb/api/v1，
        # 否则 Swagger 里点 “Try it out” 会打到域名根上的别的服务。
        _app_openapi = app.openapi

        def _openapi_with_prefix():
            schema = _app_openapi()
            schema.setdefault("servers", []).insert(0, {"url": prefix})
            return schema

        app.openapi = _openapi_with_prefix

    @app.exception_handler(api_errors.ApiError)
    async def _api_error_handler(request: Request, exc: api_errors.ApiError):
        return JSONResponse(
            api_errors.error_body(exc.code, exc.message, exc.hint, exc.details),
            status_code=exc.status_code,
            headers={"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None,
        )

    ctx = auth_mod.AuthContext(settings=settings)
    states = auth_mod.StateStore(settings.redis_url)
    app.include_router(auth_mod.build_router(ctx, states, templates))
    app.include_router(api_mod.build_api_router(settings, repo, enqueue_or_fail, url))

    @app.get("/api/openapi.json", include_in_schema=False)
    async def api_openapi():
        return JSONResponse(app.openapi())

    @app.get("/api/docs", include_in_schema=False)
    async def api_docs():
        return get_swagger_ui_html(
            openapi_url=url("/api/openapi.json"),
            title="PB 订单处理 API",
        )

    if settings.auth_enabled:
        allow = "、".join(settings.allowed_users) if settings.allowed_users else "（未设白名单，按桥的判定 = 本公司钉钉员工）"
        log.info("认证：开启（钉钉 OIDC %s）；允许用户：%s", settings.oidc_issuer, allow)
        if not settings.allowed_users:
            log.info(
                "PB_ORDERS_ALLOWED_USERS 未设 —— 登录范围由桥把关（2026-09-23 起桥按组织成员"
                "判定，只有本公司钉钉员工能进）。需要再窄一层时再填这个白名单。"
            )
    else:
        log.info("认证：关闭（仅限本机/内网使用）")
    log.info("URL 前缀：%s", prefix or "（根路径）")

    def render(request: Request, name: str, ctx_extra: dict | None = None, status_code: int = 200):
        base = {
            "user": getattr(request.state, "user", None) or auth_mod.current_user(request, settings),
            "auth_enabled": settings.auth_enabled,
            "csrf": getattr(request.state, "csrf", ""),
        }
        base.update(ctx_extra or {})
        return templates.TemplateResponse(request, name, base, status_code=status_code)

    @app.middleware("http")
    async def limit_body(request: Request, call_next):
        if request.method == "POST":
            raw = request.headers.get("content-length")
            limit = settings.max_upload_bytes * 2 + 1024 * 1024
            if raw and raw.isdigit() and int(raw) > limit:
                if request.url.path.startswith("/api/"):
                    return JSONResponse(
                        api_errors.error_body(
                            "payload_too_large",
                            f"上传体积超过上限（单文件 {settings.max_upload_mb} MB）",
                        ),
                        status_code=413,
                    )
                return render(
                    request,
                    "error.html",
                    {"message": f"上传体积超过上限（单文件 {settings.max_upload_mb} MB）"},
                    status_code=413,
                )
        return await call_next(request)

    @app.middleware("http")
    async def oidc_gate(request: Request, call_next):
        """认证闸门。CSRF 中间件在它外面，先把令牌放进 request.state。

        页面被拦 -> 302 去登录并记住原地址；页面里的轮询/下载请求被拦 -> 401，
        避免把登录页 HTML 塞进轮询片段里。
        """
        if not settings.auth_enabled:
            request.state.user = auth_mod.current_user(request, settings)
            return await call_next(request)

        path = request.url.path
        # JSON API 自己用 Bearer 鉴权；不套 cookie 会话，也不跳登录页。
        if path.startswith("/api/"):
            return await call_next(request)
        if path in auth_mod.PUBLIC_PATHS or path.startswith("/static/"):
            return await call_next(request)

        user = auth_mod.current_user(request, settings)
        if user is None:
            if request.headers.get("x-requested-with") == "fetch":
                return JSONResponse({"detail": "登录已失效"}, status_code=401)
            # return_to 必须是**浏览器看到的**地址（带前缀）。
            # request.url.path 是反代剥掉前缀后的应用侧路径（如 "/"），
            # 直接用它会让登录后跳到域名根路径 —— 而根路径是别的服务。
            return RedirectResponse(
                url(f"/oidc-login?return_to={quote(url(path), safe='')}"),
                status_code=303,  # 303 才会把 POST 变成 GET，307 会让浏览器继续 POST
            )

        if not auth_mod.is_allowed(user, settings):
            return render(
                request,
                "error.html",
                {"message": f"账号「{user.get('display_name')}」不在允许名单内。"},
                status_code=403,
            )

        request.state.user = user
        return await call_next(request)

    @app.middleware("http")
    async def issue_csrf(request: Request, call_next):
        """最外层：先发 CSRF cookie，后面的页面（含闸门返回的错误页）都能带上令牌。"""
        token, fresh = csrf_mod.current_or_new(request)
        request.state.csrf = token
        response = await call_next(request)
        if fresh:
            response.set_cookie(
                csrf_mod.COOKIE_NAME,
                token,
                max_age=8 * 3600,
                httponly=True,
                samesite="lax",
                path=ctx.cookie_path,
                secure=csrf_mod.cookie_is_secure(request),
            )
        return response

    @app.get("/healthz")
    async def healthz():
        checks = {"db": False, "redis": False}
        try:
            repo.list_jobs(limit=1)
            checks["db"] = True
        except Exception:  # noqa: BLE001
            pass
        try:
            from redis import Redis

            checks["redis"] = bool(Redis.from_url(settings.redis_url, socket_connect_timeout=2).ping())
        except Exception:  # noqa: BLE001
            pass
        ok = all(checks.values())
        return JSONResponse(
            {"status": "ok" if ok else "degraded", "checks": checks},
            status_code=200 if ok else 503,
        )

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request, status: str = ""):
        jobs = repo.list_jobs(status=status or None, limit=200)
        return render(request, "index.html", {"jobs": jobs, "status": status, "settings": settings})

    @app.get("/jobs/new", response_class=HTMLResponse)
    async def new_job_form(request: Request):
        return render(
            request,
            "new_job.html",
            {
                "settings": settings,
                "cache_ready": settings.sku_cache_path.is_file(),
                "default_no_stock": current_no_stock(),
            },
        )

    # ---------- 库存预检（SPS New 订单原始 CSV -> checked CSV + 操作表）----------

    @app.get("/checks/new", response_class=HTMLResponse)
    async def new_check_form(request: Request):
        return render(
            request,
            "new_check.html",
            {"settings": settings, "default_no_stock": current_no_stock()},
        )

    @app.post("/checks/new")
    async def create_check(
        request: Request,
        raw_csv: UploadFile,
        actor: str = Form(""),
        no_stock: str = Form(""),
        csrf: str = Form(""),
    ):
        if not csrf_mod.accepted(request, csrf):
            return render(request, "error.html", {"message": "页面已过期，请刷新后重试"}, status_code=403)
        user = getattr(request.state, "user", None) or {}
        default_actor = user.get("display_name") if settings.auth_enabled else ""
        try:
            job_id = jobs_service.create_stock_check_job(
                settings, repo, raw_csv, (actor.strip() or default_actor or "web-user"),
                no_stock, enqueue_or_fail,
            )
        except jobs_service.JobServiceError as exc:
            return render(request, "error.html", {"message": exc.message}, status_code=exc.status_code)
        return RedirectResponse(url(f"/jobs/{job_id}"), status_code=303)

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(request: Request, saved: str = ""):
        stored = repo.get_setting(NO_STOCK_KEY)
        return render(
            request,
            "settings.html",
            {
                "settings": settings,
                "no_stock": current_no_stock(),
                "updated_at": (stored or {}).get("updated_at", ""),
                "updated_by": (stored or {}).get("updated_by", ""),
                "env_default": ",".join(settings.default_no_stock),
                "saved": bool(saved),
            },
        )

    @app.post("/settings/no-stock")
    async def save_no_stock(request: Request, no_stock: str = Form(""), csrf: str = Form("")):
        if not csrf_mod.accepted(request, csrf):
            return render(request, "error.html", {"message": "页面已过期，请刷新后重试"}, status_code=403)
        user = getattr(request.state, "user", None) or auth_mod.current_user(request, settings) or {}
        repo.set_setting(
            NO_STOCK_KEY,
            ",".join(parse_sku_list(no_stock)),
            (user.get("display_name") or user.get("identity") or "web-user"),
        )
        return RedirectResponse(url("/settings?saved=1"), status_code=303)

    @app.post("/jobs/new")
    async def create_job(
        request: Request,
        packslip: UploadFile,
        order_csv: UploadFile,
        actor: str = Form(""),
        no_stock: str = Form(""),
        no_stock_note: str = Form(""),
        reorder: str = Form(""),
        validate_only: str = Form(""),
        allow_unmatched: str = Form(""),
        csrf: str = Form(""),
    ):
        if not csrf_mod.accepted(request, csrf):
            return render(request, "error.html", {"message": "页面已过期，请刷新后重试"}, status_code=403)
        user = getattr(request.state, "user", None) or {}
        default_actor = user.get("display_name") if settings.auth_enabled else ""
        try:
            job_id, _ = jobs_service.create_fulfillment_job(
                settings, repo, order_csv, packslip,
                (actor.strip() or default_actor or "web-user"),
                no_stock, no_stock_note, bool(validate_only), bool(allow_unmatched),
                reorder, {}, enqueue_or_fail,
            )
        except jobs_service.JobServiceError as exc:
            return render(request, "error.html", {"message": exc.message}, status_code=exc.status_code)
        return RedirectResponse(url(f"/jobs/{job_id}"), status_code=303)

    # ---------- 从库存预检继续出件（不再传 checked CSV）----------

    def checked_artifact(job_id: str) -> dict | None:
        return next(
            (a for a in repo.list_artifacts(job_id) if a["kind"] == "checked_order"), None
        )

    @app.get("/jobs/{job_id}/fulfill", response_class=HTMLResponse)
    async def fulfill_form(request: Request, job_id: str):
        job = repo.get_job(job_id)
        if job is None or job["job_type"] != "stock_check":
            return render(request, "error.html", {"message": "这不是一个库存预检任务"}, status_code=404)
        checked = checked_artifact(job_id)
        error = ""
        if job["status"] != "succeeded":
            error = "库存预检还没成功完成，先等它跑完再继续。"
        elif checked is None:
            error = "这个任务没有 checked CSV 产物，无法继续出件。"
        return render(
            request,
            "check_fulfill.html",
            {
                "settings": settings,
                "check_job": job,
                "checked_name": checked["download_name"] if checked else "",
                "cache_ready": settings.sku_cache_path.is_file(),
                "error": error,
            },
        )

    @app.post("/jobs/{job_id}/fulfill")
    async def start_fulfillment(
        request: Request,
        job_id: str,
        packslip: UploadFile,
        actor: str = Form(""),
        reorder: str = Form(""),
        csrf: str = Form(""),
    ):
        if not csrf_mod.accepted(request, csrf):
            return render(request, "error.html", {"message": "页面已过期，请刷新后重试"}, status_code=403)
        user = getattr(request.state, "user", None) or {}
        default_actor = user.get("display_name") if settings.auth_enabled else ""
        try:
            new_job_id, _ = jobs_service.create_fulfillment_from_check(
                settings, repo, job_id, packslip,
                (actor.strip() or default_actor or "web-user"), reorder, {}, enqueue_or_fail,
            )
        except jobs_service.JobServiceError as exc:
            return render(request, "error.html", {"message": exc.message}, status_code=exc.status_code)
        return RedirectResponse(url(f"/jobs/{new_job_id}"), status_code=303)

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    async def job_detail(request: Request, job_id: str):
        job = repo.get_job(job_id)
        if job is None:
            return render(request, "error.html", {"message": "任务不存在"}, status_code=404)
        return render(
            request,
            "job_detail.html",
            {"job": job, "artifacts": repo.list_artifacts(job_id), "settings": settings},
        )

    @app.get("/jobs/{job_id}/status", response_class=HTMLResponse)
    async def job_status(request: Request, job_id: str):
        job = repo.get_job(job_id)
        if job is None:
            return HTMLResponse("任务不存在", status_code=404)
        return render(
            request,
            "_status.html",
            {"job": job, "artifacts": repo.list_artifacts(job_id)},
        )

    @app.post("/jobs/{job_id}/retry")
    async def retry_job(request: Request, job_id: str, csrf: str = Form("")):
        if not csrf_mod.accepted(request, csrf):
            return render(request, "error.html", {"message": "页面已过期，请刷新后重试"}, status_code=403)
        try:
            new_job_id = jobs_service.retry_job(settings, repo, job_id, enqueue_or_fail)
        except jobs_service.JobServiceError as exc:
            return render(request, "error.html", {"message": exc.message}, status_code=exc.status_code)
        return RedirectResponse(url(f"/jobs/{new_job_id}"), status_code=303)

    @app.get("/artifacts/{artifact_id}/download")
    async def download(artifact_id: str):
        art = repo.get_artifact(artifact_id)
        if art is None:
            raise HTTPException(status_code=404, detail="产物不存在")
        try:
            path = storage.resolve_artifact_path(settings.artifacts_dir, art["rel_path"])
        except storage.StoredPathError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return FileResponse(path, media_type=art["mime_type"], filename=art["download_name"])

    return app


app = create_app()
