#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Web 库存预检入口：上传原始 CSV -> 出 checked CSV + 操作表 -> 继续出件。"""

from __future__ import annotations

import pandas as pd

from web import storage

CHECK_COLUMNS = [
    "PO Number", "PO Line #", "Record Type", "Qty Ordered", "Vendor Style",
    "Buyers Catalog or Stock Keeping #", "Customer Order #",
]


def write_raw_orders(path, rows=None):
    """1 个全有货 PO + 1 个部分缺货 PO（一个明细无货）。"""
    rows = rows or [
        ["100000001", "", "H", "", "", "", "C1"],
        ["100000001", "1", "D", 2, "STYLE-A", "BUYER-A", "C1"],
        ["100000002", "", "H", "", "", "", "C2"],
        ["100000002", "1", "D", 1, "STYLE-B", "BUYER-B", "C2"],
        ["100000002", "2", "D", 3, "STYLE-C", "BUYER-C", "C2"],
    ]
    pd.DataFrame(rows, columns=CHECK_COLUMNS).to_csv(path, index=False)
    return path


def upload_check(client, path, no_stock="STYLE-B", csrf=None):
    if csrf is None:
        client.get("/checks/new")  # 首次请求才下发 CSRF cookie
        csrf = client.cookies.get("pb_orders_csrf")
    with open(path, "rb") as fh:
        return client.post(
            "/checks/new",
            files={"raw_csv": ("check0stock order x21 20260917_0338_456788.csv", fh, "text/csv")},
            data={"no_stock": no_stock, "actor": "tester", "csrf": csrf or ""},
            follow_redirects=False,
        )


def test_check_page_prefills_no_stock(client):
    resp = client.get("/checks/new")
    assert resp.status_code == 200
    assert "检查 SPS 新订单" in resp.text


def test_upload_runs_check_and_offers_downloads(client, pb_env):
    resp = upload_check(client, write_raw_orders(pb_env.tmp / "raw.csv"))
    assert resp.status_code == 303
    job_id = resp.headers["location"].rsplit("/", 1)[-1]

    page = client.get(f"/jobs/{job_id}")
    assert page.status_code == 200
    assert "库存预检" in page.text
    # 部分缺货 PO 必须有醒目提醒：不要整单取消
    assert "不要整单取消" in page.text
    assert "100000002" in page.text
    # 名字里的 PO 数 = 筛完剩下的（2 个 PO 都保留）
    assert "checked0stock order x2 20260917_0338_456788.csv" in page.text

    artifacts = client.repo.list_artifacts(job_id)
    kinds = {a["kind"] for a in artifacts}
    assert kinds == {"checked_order", "stock_operations"}

    for artifact in artifacts:
        dl = client.get(f"/artifacts/{artifact['id']}/download")
        assert dl.status_code == 200
        assert len(dl.content) > 0


def test_job_page_renders_detail_tables_with_both_skus(client, pb_env):
    """网页上也要有逐行明细表，且每个表都并列对方 SKU 与我方 SKU。"""
    resp = upload_check(client, write_raw_orders(pb_env.tmp / "raw.csv"), no_stock="STYLE-B")
    job_id = resp.headers["location"].rsplit("/", 1)[-1]
    page = client.get(f"/jobs/{job_id}")
    assert page.status_code == 200

    for title in ("ASN 有货明细", "缺货明细", "全部缺货 PO", "部分缺货 PO 逐行操作"):
        assert title in page.text, title

    # 两个 SKU 的列名都出现在页面表格里（对方 BUYER-BUYER + 我方 STYLE-C 各一行）
    assert "Buyers Catalog or Stock Keeping #" in page.text
    assert "Vendor Style" in page.text
    assert "BUYER-C" in page.text
    assert "STYLE-C" in page.text
    assert "STYLE-B" in page.text
    # 数量按整数显示（源里是 1/3，不是 1.0）
    assert ">1.0<" not in page.text and ">3.0<" not in page.text


def test_old_job_without_tables_still_renders(client, pb_env):
    """改版前建的任务 report 里没有 tables，页面不能 500。"""
    import json

    resp = upload_check(client, write_raw_orders(pb_env.tmp / "raw.csv"), no_stock="")
    job_id = resp.headers["location"].rsplit("/", 1)[-1]
    job = client.repo.get_job(job_id)
    report = job["report"]
    report.pop("tables")
    client.repo.update_job(job_id, report_json=json.dumps(report, ensure_ascii=False))

    page = client.get(f"/jobs/{job_id}")
    assert page.status_code == 200
    assert "库存对账" in page.text
    assert "ASN 有货明细" not in page.text


def test_newline_separated_no_stock_is_split(client, pb_env):
    """页面写着「逗号或换行分隔」，多行输入必须真的分开 —— 否则缺货行静默漏掉。"""
    resp = upload_check(
        client, write_raw_orders(pb_env.tmp / "raw.csv"), no_stock="STYLE-B\nSTYLE-C\n"
    )
    job_id = resp.headers["location"].rsplit("/", 1)[-1]
    assert client.repo.get_job(job_id)["no_stock_list"] == ["STYLE-B", "STYLE-C"]

    artifact = next(a for a in client.repo.list_artifacts(job_id) if a["kind"] == "checked_order")
    path = storage.resolve_artifact_path(client.settings.artifacts_dir, artifact["rel_path"])
    checked = pd.read_csv(path, dtype=str, keep_default_na=False)
    assert "STYLE-B" not in checked["Vendor Style"].tolist()
    assert "STYLE-C" not in checked["Vendor Style"].tolist()
    # 两条明细都缺货 -> 整个 PO 拿掉，只剩第一个 PO 的 Header + Detail
    assert set(checked["PO Number"]) == {"100000001"}


def test_fulfillment_route_also_splits_newlines(client, pb_env):
    """同一个缺陷在出件入口也存在，一起修掉。"""
    client.get("/jobs/new")
    csrf = client.cookies.get("pb_orders_csrf")
    with open(pb_env.pdf, "rb") as pdf, open(pb_env.csv, "rb") as csv:
        resp = client.post(
            "/jobs/new",
            files={
                "packslip": ("Packslip 美中 x3 20260921.pdf", pdf, "application/pdf"),
                "order_csv": ("checked0stock order x3 20260921.csv", csv, "text/csv"),
            },
            data={"no_stock": "STYLE-A\nSTYLE-B", "actor": "t", "csrf": csrf},
            follow_redirects=False,
        )
    assert resp.status_code == 303
    job_id = resp.headers["location"].rsplit("/", 1)[-1]
    assert client.repo.get_job(job_id)["no_stock_list"] == ["STYLE-A", "STYLE-B"]


def test_checked_csv_keeps_header_and_drops_only_no_stock_detail(client, pb_env):
    resp = upload_check(client, write_raw_orders(pb_env.tmp / "raw.csv"))
    job_id = resp.headers["location"].rsplit("/", 1)[-1]
    artifact = next(a for a in client.repo.list_artifacts(job_id) if a["kind"] == "checked_order")
    path = storage.resolve_artifact_path(client.settings.artifacts_dir, artifact["rel_path"])

    checked = pd.read_csv(path, dtype=str, keep_default_na=False)
    assert list(checked.columns) == CHECK_COLUMNS
    assert checked[["PO Number", "Record Type", "PO Line #"]].values.tolist() == [
        ["100000001", "H", ""],
        ["100000001", "D", "1"],
        ["100000002", "H", ""],   # 部分缺货 PO 的 Header 必须留着
        ["100000002", "D", "2"],  # 只有有货那条明细
    ]


def test_frozen_snapshot_ignores_later_setting_changes(client, pb_env):
    resp = upload_check(client, write_raw_orders(pb_env.tmp / "raw.csv"), no_stock="STYLE-B")
    job_id = resp.headers["location"].rsplit("/", 1)[-1]
    assert client.repo.get_job(job_id)["no_stock_list"] == ["STYLE-B"]

    # 之后再改设置，已出的结果不受影响
    client.get("/settings")
    csrf = client.cookies.get("pb_orders_csrf")
    client.post("/settings/no-stock", data={"no_stock": "STYLE-Z", "csrf": csrf})
    assert client.repo.get_job(job_id)["report"]["no_stock_snapshot"] == ["STYLE-B"]


def test_check_rejects_non_csv(client, pb_env):
    client.get("/checks/new")
    csrf = client.cookies.get("pb_orders_csrf")
    resp = client.post(
        "/checks/new",
        files={"raw_csv": ("orders.pdf", b"%PDF-1.4", "application/pdf")},
        data={"no_stock": "", "csrf": csrf},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert ".csv" in resp.text


def test_check_requires_csrf(client, pb_env):
    resp = client.post(
        "/checks/new",
        files={"raw_csv": ("a.csv", b"a,b\n1,2\n", "text/csv")},
        data={"no_stock": "", "csrf": "wrong"},
        follow_redirects=False,
    )
    assert resp.status_code == 403


def test_bad_csv_fails_with_readable_reason(client, pb_env):
    raw = pb_env.tmp / "raw.csv"
    pd.DataFrame([["x", "y"]], columns=["A", "B"]).to_csv(raw, index=False)
    resp = upload_check(client, raw, no_stock="")
    job_id = resp.headers["location"].rsplit("/", 1)[-1]
    page = client.get(f"/jobs/{job_id}")
    assert page.status_code == 200
    assert "缺少必需列" in page.text
    assert client.repo.list_artifacts(job_id) == []


def test_continue_to_fulfillment_reuses_checked_csv(client, pb_env):
    resp = upload_check(client, write_raw_orders(pb_env.tmp / "raw.csv"), no_stock="STYLE-B")
    check_job = resp.headers["location"].rsplit("/", 1)[-1]

    form = client.get(f"/jobs/{check_job}/fulfill")
    assert form.status_code == 200
    assert "继续" in form.text or "生成发货文件" in form.text

    csrf = client.cookies.get("pb_orders_csrf")
    with open(pb_env.pdf, "rb") as fh:
        started = client.post(
            f"/jobs/{check_job}/fulfill",
            files={"packslip": ("Packslip 美中 x3 20260921.pdf", fh, "application/pdf")},
            data={"csrf": csrf, "actor": "tester"},
            follow_redirects=False,
        )
    assert started.status_code == 303
    fulfill_job = started.headers["location"].rsplit("/", 1)[-1]
    assert fulfill_job != check_job

    job = client.repo.get_job(fulfill_job)
    assert job["job_type"] == "fulfillment"
    assert job["source_job_id"] == check_job
    assert job["no_stock"] == ""  # checked CSV 已剔过，不再二次拆分
    assert job["input_order"].startswith("checked0stock")

    # 出件输入里的 order.csv 就是那份 checked CSV（不重传）
    checked = next(a for a in client.repo.list_artifacts(check_job) if a["kind"] == "checked_order")
    checked_path = storage.resolve_artifact_path(client.settings.artifacts_dir, checked["rel_path"])
    copied = client.settings.inputs_dir / fulfill_job / storage.ORDER_NAME
    assert copied.read_bytes() == checked_path.read_bytes()


def test_continue_page_missing_job_is_404(client, pb_env):
    assert client.get("/jobs/does-not-exist/fulfill").status_code == 404


def test_continue_requires_csrf(client, pb_env):
    resp = upload_check(client, write_raw_orders(pb_env.tmp / "raw.csv"), no_stock="")
    check_job = resp.headers["location"].rsplit("/", 1)[-1]
    with open(pb_env.pdf, "rb") as fh:
        started = client.post(
            f"/jobs/{check_job}/fulfill",
            files={"packslip": ("p.pdf", fh, "application/pdf")},
            data={"csrf": "wrong"},
            follow_redirects=False,
        )
    assert started.status_code == 403


def test_direct_fulfillment_still_works(client, pb_env):
    client.get("/jobs/new")
    csrf = client.cookies.get("pb_orders_csrf")
    with open(pb_env.pdf, "rb") as pdf, open(pb_env.csv, "rb") as csv:
        resp = client.post(
            "/jobs/new",
            files={
                "packslip": ("Packslip 美中 x3 20260921.pdf", pdf, "application/pdf"),
                "order_csv": ("checked0stock order x3 20260921.csv", csv, "text/csv"),
            },
            data={"no_stock": "", "actor": "tester", "csrf": csrf},
            follow_redirects=False,
        )
    assert resp.status_code == 303
    job_id = resp.headers["location"].rsplit("/", 1)[-1]
    assert client.repo.get_job(job_id)["job_type"] == "fulfillment"
    assert "通途导入 xlsx" in client.get(f"/jobs/{job_id}").text

    # 通途 xlsx 要用页面上那份 CSV 的名字，而不是磁盘名 order.csv
    # （回归：以前网页产物叫 `PB_0_导入_原始_order_on_…`，看不出是哪一批）
    tongtool = next(a for a in client.repo.list_artifacts(job_id) if a["kind"] == "tongtool")
    assert tongtool["download_name"].startswith(
        "PB_0_导入_原始_checked0stock order x3 20260921_on_"
    )
    assert "_order_on_" not in tongtool["download_name"]
