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
from fastapi.responses import (  # noqa: E402
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
)
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.templating import Jinja2Templates  # noqa: E402

from web import auth as auth_mod  # noqa: E402
from web import csrf as csrf_mod  # noqa: E402
from web import housekeeping  # noqa: E402
from web import storage  # noqa: E402
from web.config import get_settings  # noqa: E402
from web.repository import ARTIFACT_LABELS, NO_STOCK_KEY, Repository, new_id  # noqa: E402

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

    def receive_upload(upload: UploadFile, label: str, suffix: str, dest: Path) -> str:
        """校验扩展名 + 分块落盘到固定物理名，返回用户原始文件名（仅供展示）。

        抛 `ValueError`（扩展名不对，页面按 400 处理）或
        `storage.UploadTooLarge`（超限，页面按 413 处理）。
        """
        display = storage.validate_upload_name(upload.filename, label, suffix)
        storage.save_upload_stream(upload.file, dest, settings.max_upload_bytes)
        return display

    def enqueue_or_fail(job_id: str) -> None:
        """投队列；Redis 不可用时把任务落成失败，页面才看得到原因。"""
        try:
            enqueue_job(settings, repo, job_id)
        except HTTPException as exc:
            repo.mark_failed(
                job_id,
                {"code": "queue_unavailable", "message": exc.detail, "hint": "确认 Redis 后重新提交。"},
            )

    # 上传槽位 -> (产物类型, 展示用类型名, MIME)。类型名与 database 的 ARTIFACT_LABELS 一致。
    _INPUT_SLOTS = (
        (storage.PACKSLIP_NAME, "input_packslip", "Packslip PDF", "application/pdf"),
        (storage.ORDER_NAME, "input_order", "SPS 订单 CSV", "text/csv"),
    )

    def register_inputs(job_id: str, displays: dict[str, str]) -> None:
        """把上传的输入也登记成可下载产物 —— 使用者要能核对「我到底传了什么」。

        用 `publish_input_copy`（硬链接/复制），**不移动** inputs/ 里的原文件：
        那份还要给 worker 用、还要供「用相同输入重新处理」。
        登记失败不能连累建任务（没登记上也还能出件，只是少一个下载口），所以吞掉异常并记日志。
        """
        for slot, kind, label, mime in _INPUT_SLOTS:
            path = settings.inputs_dir / job_id / slot
            if not path.is_file():
                continue
            try:
                rel_path, size, digest = storage.publish_input_copy(path, settings.artifacts_dir)
                repo.add_artifact(
                    job_id=job_id, kind=kind, original_name=slot,
                    download_name=displays.get(slot) or slot, rel_path=rel_path,
                    content_hash=digest, size_bytes=size, mime_type=mime,
                )
            except Exception:  # noqa: BLE001 - 登记失败不该挡住任务
                log.exception("登记输入产物失败 job=%s slot=%s", job_id, slot)

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

    ctx = auth_mod.AuthContext(settings=settings)
    states = auth_mod.StateStore(settings.redis_url)
    app.include_router(auth_mod.build_router(ctx, states, templates))

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
            if raw and raw.isdigit() and int(raw) > settings.max_upload_bytes * 2:
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
        job_id = new_id("job")
        job_dir = settings.inputs_dir / job_id
        try:
            order_display = receive_upload(
                raw_csv, "原始订单 CSV", storage.ORDER_SUFFIX, job_dir / storage.ORDER_NAME
            )
        except ValueError as exc:
            return render(request, "error.html", {"message": str(exc)}, status_code=400)
        except storage.UploadTooLarge as exc:
            storage.remove_job_dirs(settings.inputs_dir, settings.work_dir, job_id)
            return render(request, "error.html", {"message": str(exc)}, status_code=413)

        user = getattr(request.state, "user", None) or {}
        default_actor = user.get("display_name") if settings.auth_enabled else ""
        repo.create_job(
            job_id=job_id,
            job_type="stock_check",
            created_by=(actor.strip() or default_actor or "web-user"),
            # 提交即冻结：这份快照写进任务，之后改设置不影响已出的结果。
            # 用 parse_sku_list 而不是 split(",")：页面写着「逗号或换行分隔」，
            # 只按逗号切会把多行输入当成一个 SKU，缺货行就静默漏掉了。
            no_stock=",".join(parse_sku_list(no_stock)),
            no_stock_note=None,
            validate_only=False,
            allow_unmatched=False,
            input_packslip="",
            input_order=order_display,
            pipeline_version=settings.pipeline_version,
        )
        register_inputs(job_id, {storage.ORDER_NAME: order_display})
        enqueue_or_fail(job_id)
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
        validate_only: str = Form(""),
        allow_unmatched: str = Form(""),
        csrf: str = Form(""),
    ):
        if not csrf_mod.accepted(request, csrf):
            return render(request, "error.html", {"message": "页面已过期，请刷新后重试"}, status_code=403)
        job_id = new_id("job")
        job_dir = settings.inputs_dir / job_id
        try:
            # 返回值是用户原始文件名，只落库供页面展示；
            # 磁盘上一律用 storage 的固定名，避免用用户文件名做路径。
            packslip_display = storage.validate_upload_name(
                packslip.filename, "Packslip PDF", storage.PACKSLIP_SUFFIX
            )
            order_display = storage.validate_upload_name(
                order_csv.filename, "订单 CSV", storage.ORDER_SUFFIX
            )
        except ValueError as exc:
            return render(request, "error.html", {"message": str(exc)}, status_code=400)

        try:
            receive_upload(packslip, "Packslip PDF", storage.PACKSLIP_SUFFIX, job_dir / storage.PACKSLIP_NAME)
            receive_upload(order_csv, "订单 CSV", storage.ORDER_SUFFIX, job_dir / storage.ORDER_NAME)
        except storage.UploadTooLarge as exc:
            storage.remove_job_dirs(settings.inputs_dir, settings.work_dir, job_id)
            return render(request, "error.html", {"message": str(exc)}, status_code=413)

        user = getattr(request.state, "user", None) or {}
        default_actor = user.get("display_name") if settings.auth_enabled else ""
        repo.create_job(
            job_id=job_id,
            job_type="fulfillment",
            created_by=(actor.strip() or default_actor or "web-user"),
            # 同 /checks/new：页面写的是「逗号或换行分隔」，多行输入要能分开
            no_stock=",".join(parse_sku_list(no_stock)),
            no_stock_note=no_stock_note.strip() or None,
            validate_only=bool(validate_only),
            allow_unmatched=bool(allow_unmatched),
            input_packslip=packslip_display,
            input_order=order_display,
            pipeline_version=settings.pipeline_version,
        )
        register_inputs(
            job_id,
            {storage.PACKSLIP_NAME: packslip_display, storage.ORDER_NAME: order_display},
        )
        enqueue_or_fail(job_id)
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
        csrf: str = Form(""),
    ):
        if not csrf_mod.accepted(request, csrf):
            return render(request, "error.html", {"message": "页面已过期，请刷新后重试"}, status_code=403)
        source = repo.get_job(job_id)
        if source is None or source["job_type"] != "stock_check":
            return render(request, "error.html", {"message": "这不是一个库存预检任务"}, status_code=404)

        checked = checked_artifact(job_id) if source["status"] == "succeeded" else None
        if checked is None:
            return render(
                request,
                "error.html",
                {"message": "来源任务的 checked CSV 不可用（任务未成功或已被清理），请先重新跑一次库存预检。"},
                status_code=409,
            )
        try:
            checked_path = storage.resolve_artifact_path(settings.artifacts_dir, checked["rel_path"])
        except storage.StoredPathError as exc:
            return render(request, "error.html", {"message": str(exc)}, status_code=409)

        new_job_id = new_id("job")
        new_dir = settings.inputs_dir / new_job_id
        try:
            packslip_display = receive_upload(
                packslip, "Packslip PDF", storage.PACKSLIP_SUFFIX, new_dir / storage.PACKSLIP_NAME
            )
        except ValueError as exc:
            return render(request, "error.html", {"message": str(exc)}, status_code=400)
        except storage.UploadTooLarge as exc:
            storage.remove_job_dirs(settings.inputs_dir, settings.work_dir, new_job_id)
            return render(request, "error.html", {"message": str(exc)}, status_code=413)

        # 把上一次生成的 checked CSV 直接落成这次出件的 order.csv：
        # 出件范围与预检结果严格一致，人也少传一遍文件。
        storage.link_or_copy(checked_path, new_dir / storage.ORDER_NAME)

        user = getattr(request.state, "user", None) or {}
        default_actor = user.get("display_name") if settings.auth_enabled else ""
        repo.create_job(
            job_id=new_job_id,
            job_type="fulfillment",
            created_by=(actor.strip() or default_actor or "web-user"),
            # checked CSV 已经剔过缺货明细，这里不再做无货拆分（留空）
            no_stock="",
            no_stock_note=None,
            validate_only=False,
            allow_unmatched=False,
            input_packslip=packslip_display,
            input_order=checked["download_name"],
            pipeline_version=settings.pipeline_version,
            source_job_id=job_id,
        )
        register_inputs(
            new_job_id,
            {storage.PACKSLIP_NAME: packslip_display, storage.ORDER_NAME: checked["download_name"]},
        )
        enqueue_or_fail(new_job_id)
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
        old = repo.get_job(job_id)
        if old is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        src_dir = settings.inputs_dir / job_id
        if not src_dir.is_dir():
            return render(
                request,
                "error.html",
                {"message": "原任务的输入文件已被清理，请重新上传。"},
                status_code=409,
            )

        new_job_id = new_id("job")
        storage.clone_inputs(src_dir, settings.inputs_dir / new_job_id)
        repo.create_job(
            job_id=new_job_id,
            job_type=old["job_type"] or "fulfillment",
            created_by=old["created_by"],
            no_stock=old["no_stock"],
            no_stock_note=old["no_stock_note"],
            validate_only=old["validate_only"],
            allow_unmatched=old["allow_unmatched"],
            input_packslip=old["input_packslip"],
            input_order=old["input_order"],
            pipeline_version=settings.pipeline_version,
            source_job_id=job_id,
        )
        register_inputs(
            new_job_id,
            {storage.PACKSLIP_NAME: old["input_packslip"], storage.ORDER_NAME: old["input_order"]},
        )
        enqueue_or_fail(new_job_id)
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
