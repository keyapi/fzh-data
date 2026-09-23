#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试夹具：用**合成**的小 PDF / CSV / 名称缓存跑真实流程。

不依赖任何客户数据：Packslip PDF 用 reportlab 现画（结构与 SPS 导出一致 ——
`Purchase Order Number <9位>` + `Item Number` 表头 + 下方 7 位数字），
订单 CSV 只有 5 行，名称缓存只有 3 个 SKU。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

PB_DIR = Path(__file__).resolve().parent.parent
if str(PB_DIR) not in sys.path:
    sys.path.insert(0, str(PB_DIR))

# 与真实批次同构：2 个 PO，3 个包裹
PAGES = [
    ("137943090", "1069914"),
    ("137943090", "1069915"),
    ("137943091", "1069916"),
]
SKUS = {"1069914": "STYLE-A", "1069915": "STYLE-B", "1069916": "STYLE-C"}


def write_packslip_pdf(path: Path, pages=PAGES) -> Path:
    """生成结构与 SPS 导出相同的 A4 竖版 PDF。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=A4)
    for po, item in pages:
        c.setFont("Helvetica", 12)
        c.drawString(72, 700, f"Customer Order Number: 362632154021")
        c.drawString(72, 680, f"Purchase Order Number {po}")
        c.drawString(72, 620, "Item Number")
        c.drawString(72, 580, item)
        c.drawString(72, 560, "Component / Item Ratio / Description / Ship Qty / Unit Price")
        c.showPage()
    c.save()
    return path


def write_order_csv(path: Path, rows=None, catalogs=None) -> Path:
    """生成与 SPS `checked0stock order` 同构的 CSV（H 行 + D 行）。"""
    rows = rows or [
        ("137943090", "", "H", "", "", "", "USA", "2026-09-21"),
        ("137943090", "2", "D", 1, "STYLE-A", 10.0, "", ""),
        ("137943090", "1", "D", 1, "STYLE-B", 12.0, "", ""),
        ("137943091", "", "H", "", "", "", "USA", "2026-09-21"),
        ("137943091", "1", "D", 1, "STYLE-C", 9.0, "", ""),
    ]
    df = pd.DataFrame(rows, columns=[
        "PO Number", "PO Line #", "Record Type", "Qty Ordered", "Vendor Style",
        "Unit Price", "Ship To Country", "PO Date",
    ])
    df["Buyers Catalog or Stock Keeping #"] = catalogs if catalogs is not None else [
        "", "1069914", "1069915", "", "1069916",
    ]
    df["Customer Order #"] = "362632154021"
    df.to_csv(path, index=False)
    return path


def write_sku_cache(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"通途SKU": "STYLE-A", "中文名称": "三角灰", "西班牙语名称": "Gris"},
        {"通途SKU": "STYLE-B", "中文名称": "方巾蓝", "西班牙语名称": "Azul"},
        {"通途SKU": "STYLE-C", "中文名称": "枕套白", "西班牙语名称": "Blanco"},
    ]).to_csv(path, index=False)
    return path


@pytest.fixture
def pb_env(tmp_path, monkeypatch):
    """隔离的运行时目录 + 数据集，并把 settings 指向它。"""
    runtime = tmp_path / "runtime"
    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("PB_ORDERS_RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("PB_ORDERS_DATA_DIR", str(data))
    monkeypatch.setenv("PB_ORDERS_PIPELINE_VERSION", "test-version")
    monkeypatch.setenv("PB_ORDERS_REDIS_URL", "redis://127.0.0.1:6399/0")

    from web import config as web_config

    web_config.reset_settings()

    env = type("PBEnv", (), {})()
    env.runtime = runtime
    env.data = data
    env.pdf = write_packslip_pdf(tmp_path / "Packslip 美中 x3 20260921.pdf")
    env.csv = write_order_csv(tmp_path / "checked0stock order x3 20260921.csv")
    env.cache = write_sku_cache(data / "us_sku_name_cache.csv")
    env.tmp = tmp_path
    yield env
    web_config.reset_settings()


class StripPrefix:
    """模拟 NGINX 的 `proxy_pass .../`：把 `/pb/...` 剥成 `/...` 再交给应用。

    生产上应用看到的永远是剥掉前缀的路径，浏览器则按 `/pb/` 作用域带 cookie。
    测试里加这一层，cookie 路径与生成的 URL 才能被真实地验证。
    """

    def __init__(self, app, prefix: str):
        self.app = app
        self.prefix = prefix

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            path = scope.get("path", "")
            if path == self.prefix or path.startswith(self.prefix + "/"):
                # 只改 path，不设 root_path —— 应用本身不依赖 root_path
                # （生成的 URL 走 PB_ORDERS_URL_PREFIX），设了反而会干扰 StaticFiles 匹配
                scope = {**scope, "path": path[len(self.prefix):] or "/"}
        await self.app(scope, receive, send)


@pytest.fixture
def client(pb_env, monkeypatch):
    """带同步队列的测试客户端（闸门用哪套由各测试自己设环境变量决定）。

    队列被替换成同步执行，所以不需要跑 Redis；这样能完整覆盖
    「Web 建任务 + worker 处理 + 页面展示 + 下载」的真实链路。
    """
    import web.app as web_app
    import web.tasks as web_tasks
    from web.config import get_settings
    from web.repository import Repository

    def sync_enqueue(settings, repo, job_id):
        repo.mark_queued(job_id, "test-worker-job")
        web_tasks.run_job(job_id)

    monkeypatch.setattr(web_app, "enqueue_job", sync_enqueue)
    app = web_app.create_app()
    with TestClient(app) as c:
        c.repo = Repository(get_settings().db_path)
        c.settings = get_settings()
        yield c
