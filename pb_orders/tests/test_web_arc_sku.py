#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Web 层：弧形颈枕旧->新 SKU 的常驻提示与自动转换。"""

from __future__ import annotations

import pandas as pd

from conftest import write_packslip_pdf

COLUMNS = [
    "PO Number",
    "PO Line #",
    "Record Type",
    "Qty Ordered",
    "Vendor Style",
    "Buyers Catalog or Stock Keeping #",
    "Ship To Country",
    "Unit Price",
]


def _csrf(client) -> str:
    page = client.get("/jobs/new")
    assert page.status_code == 200
    token = client.cookies.get("pb_orders_csrf")
    assert token
    return token


def _upload(client, pdf, csv_path):
    files = {
        "packslip": ("Packslip 美中 x2 arc.pdf", open(pdf, "rb"), "application/pdf"),
        "order_csv": ("checked0stock arc.csv", open(csv_path, "rb"), "text/csv"),
    }
    data = {
        "actor": "tester",
        "no_stock": "",
        "no_stock_note": "",
        "validate_only": "",
        "allow_unmatched": "",
        "csrf": _csrf(client),
    }
    return client.post("/jobs/new", files=files, data=data, follow_redirects=False)


def _write_cache(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"通途SKU": "TT0312672K0064328", "中文名称": "弧形颈枕灰", "西班牙语名称": "Gris"},
        {"通途SKU": "TT0312673K0064329", "中文名称": "弧形颈枕象牙白", "西班牙语名称": "Marfil"},
    ]).to_csv(path, index=False)
    return path


def _write_arc_csv(path):
    df = pd.DataFrame(
        [
            ["137943090", "", "H", "", "", "", "USA", ""],
            ["137943090", "1", "D", 1, "TT0031058K0062965", "5938375", "USA", "10"],
            ["137943090", "2", "D", 1, "TT0031059K0062966", "4020032", "USA", "10"],
        ],
        columns=COLUMNS,
    )
    df.to_csv(path, index=False)
    return path


def test_notice_is_visible_on_index_and_forms(client):
    for path in ("/", "/jobs/new", "/checks/new"):
        page = client.get(path)
        assert page.status_code == 200
        assert "弧形海绵颈枕 SKU 切换已开启" in page.text


def test_web_job_auto_converts_and_shows_report(client, pb_env, tmp_path):
    _write_cache(pb_env.cache)
    pdf = write_packslip_pdf(
        tmp_path / "Packslip 美中 x2 arc.pdf",
        pages=[("137943090", "5938375"), ("137943090", "4020032")],
    )
    csv_path = _write_arc_csv(tmp_path / "checked0stock arc.csv")

    resp = _upload(client, pdf, csv_path)
    assert resp.status_code == 303
    job_id = resp.headers["location"].rsplit("/", 1)[-1]

    page = client.get(f"/jobs/{job_id}")
    assert page.status_code == 200
    assert "成功" in page.text
    assert "SKU 自动转换" in page.text
    assert "TT0031058K0062965" in page.text and "TT0312672K0064328" in page.text
    assert "转换后订单 CSV（新 SKU）" in page.text

    job = client.repo.get_job(job_id)
    assert job["report"]["sku_migration"]["applied"] is True
