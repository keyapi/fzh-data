#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Web 层：上传→入队→详情→下载 全流程，以及体积/扩展名/路径越界的拒绝。

队列在测试里被替换成同步执行，所以不需要跑 Redis；这样可以完整验证
「Web 建任务 + worker 处理 + 页面展示 + 下载」的真实链路。
"""

from __future__ import annotations

from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

import web.app as web_app


def _csrf(client) -> str:
    page = client.get("/jobs/new")
    assert page.status_code == 200
    token = client.cookies.get("pb_orders_csrf")
    assert token
    return token


def _upload(client, **overrides):
    files = {
        "packslip": ("Packslip 美中 x3 20260921.pdf", open(overrides["pdf"], "rb"), "application/pdf"),
        "order_csv": ("checked0stock order x3 20260921.csv", open(overrides["csv"], "rb"), "text/csv"),
    }
    data = {
        "actor": overrides.get("actor", "tester"),
        "no_stock": overrides.get("no_stock", ""),
        "no_stock_note": overrides.get("no_stock_note", ""),
        "validate_only": "1" if overrides.get("validate_only") else "",
        "allow_unmatched": "1" if overrides.get("allow_unmatched") else "",
        "csrf": overrides.get("csrf", _csrf(client)),
    }
    return client.post("/jobs/new", files=files, data=data, follow_redirects=False)


def test_index_and_form_render(client):
    assert client.get("/").status_code == 200
    form = client.get("/jobs/new")
    assert form.status_code == 200
    assert "Packslip PDF" in form.text


def test_full_flow_upload_process_download(client, pb_env):
    resp = _upload(client, pdf=pb_env.pdf, csv=pb_env.csv)
    assert resp.status_code == 303
    job_id = resp.headers["location"].rsplit("/", 1)[-1]

    page = client.get(f"/jobs/{job_id}")
    assert page.status_code == 200
    assert "成功" in page.text
    assert "背贴 PDF" in page.text

    job = client.repo.get_job(job_id)
    assert job["status"] == "succeeded"
    # 落库的是用户原始文件名（展示用）；磁盘上一律是固定物理名
    assert job["input_packslip"] == "Packslip 美中 x3 20260921.pdf"
    assert job["input_order"] == "checked0stock order x3 20260921.csv"
    assert "Packslip 美中 x3 20260921.pdf" in page.text
    assert (pb_env.runtime / "inputs" / job_id / "packslip.pdf").is_file()
    assert (pb_env.runtime / "inputs" / job_id / "order.csv").is_file()
    assert job["report"]["pdf"]["pages"] == 3

    arts = client.repo.list_artifacts(job_id)
    assert {a["kind"] for a in arts} == {
        "input_packslip", "input_order", "tongtool", "label", "back_label",
    }

    for art in arts:
        dl = client.get(f"/artifacts/{art['id']}/download")
        assert dl.status_code == 200
        assert len(dl.content) == art["size_bytes"]
        assert art["content_hash"], "产物必须登记内容哈希"


def test_download_sets_download_name(client, pb_env):
    _upload(client, pdf=pb_env.pdf, csv=pb_env.csv)
    art = next(a for a in client.repo.list_artifacts(client.repo.list_jobs()[0]["id"]) if a["kind"] == "back_label")
    dl = client.get(f"/artifacts/{art['id']}/download")
    assert dl.status_code == 200
    disposition = unquote(dl.headers.get("content-disposition", ""))
    assert "背贴" in disposition
    assert art["download_name"] in disposition


def test_validate_only_job_has_no_outputs_but_inputs_are_downloadable(client, pb_env):
    """仅校验 = 不出产物；但上传的输入仍可下载核对。"""
    resp = _upload(client, pdf=pb_env.pdf, csv=pb_env.csv, validate_only=True)
    job_id = resp.headers["location"].rsplit("/", 1)[-1]
    assert client.repo.get_job(job_id)["status"] == "succeeded"
    kinds = {a["kind"] for a in client.repo.list_artifacts(job_id)}
    assert kinds == {"input_packslip", "input_order"}
    assert "仅校验" in client.get(f"/jobs/{job_id}").text


def test_status_fragment_polls(client, pb_env):
    resp = _upload(client, pdf=pb_env.pdf, csv=pb_env.csv)
    job_id = resp.headers["location"].rsplit("/", 1)[-1]
    frag = client.get(f"/jobs/{job_id}/status")
    assert frag.status_code == 200
    assert "数量对账" in frag.text


def test_failed_job_shows_reason_and_retry_creates_new_job(client, pb_env):
    from conftest import write_packslip_pdf

    extra = write_packslip_pdf(
        pb_env.tmp / "Packslip extra.pdf",
        [("137943090", "1069914"), ("137943090", "1069915"),
         ("137943091", "1069916"), ("137943099", "1069917")],
    )
    resp = _upload(client, pdf=extra, csv=pb_env.csv)
    job_id = resp.headers["location"].rsplit("/", 1)[-1]

    page = client.get(f"/jobs/{job_id}")
    assert "1:1 校验失败" in page.text
    assert "Qty per Carton" in page.text
    assert "Traceback" not in page.text
    assert str(pb_env.tmp) not in page.text  # 不泄露服务器路径

    retry = client.post(
        f"/jobs/{job_id}/retry", data={"csrf": _csrf(client)}, follow_redirects=False
    )
    assert retry.status_code == 303
    new_id = retry.headers["location"].rsplit("/", 1)[-1]
    assert new_id != job_id
    assert client.repo.get_job(new_id)["source_job_id"] == job_id


def _post_new(client, files):
    return client.post(
        "/jobs/new",
        files=files,
        data={
            "actor": "t", "no_stock": "", "no_stock_note": "",
            "validate_only": "", "allow_unmatched": "", "csrf": _csrf(client),
        },
    )


def test_rejects_wrong_extension(client, pb_env):
    files = {
        "packslip": ("payload.exe", b"MZ", "application/octet-stream"),
        "order_csv": ("order.csv", b"PO Number\n1\n", "text/csv"),
    }
    resp = _post_new(client, files)
    assert resp.status_code == 400
    assert "只接受" in resp.text


def test_rejects_swapped_suffixes(client):
    files = {
        "packslip": ("notes.csv", b"a,b\n", "text/csv"),
        "order_csv": ("slip.pdf", b"%PDF", "application/pdf"),
    }
    resp = _post_new(client, files)
    assert resp.status_code == 400
    assert "只接受 .pdf" in resp.text


def test_post_without_csrf_is_rejected(client, pb_env):
    files = {
        "packslip": ("a.pdf", open(pb_env.pdf, "rb"), "application/pdf"),
        "order_csv": ("a.csv", open(pb_env.csv, "rb"), "text/csv"),
    }
    resp = client.post(
        "/jobs/new",
        files=files,
        data={"actor": "t", "no_stock": "", "no_stock_note": "",
              "validate_only": "", "allow_unmatched": ""},
    )
    assert resp.status_code == 403
    assert "刷新" in resp.text


def test_rejects_oversize_upload(pb_env, monkeypatch):
    monkeypatch.setattr(web_app, "enqueue_job", lambda *a, **k: None)
    import web.config as web_config

    web_config.reset_settings()
    settings = web_config.get_settings()
    object.__setattr__(settings, "max_upload_mb", 1)

    app = web_app.create_app()
    with TestClient(app) as c:
        files = {
            "packslip": ("big.pdf", b"%PDF" + b"x" * (2 * 1024 * 1024), "application/pdf"),
            "order_csv": ("o.csv", b"a", "text/csv"),
        }
        token = c.get("/jobs/new").cookies.get("pb_orders_csrf") or c.cookies.get("pb_orders_csrf")
        resp = c.post("/jobs/new", files=files, data={"actor": "t", "no_stock": "",
                                                      "no_stock_note": "", "validate_only": "",
                                                      "allow_unmatched": "", "csrf": token})
    assert resp.status_code == 413


def test_download_rejects_unknown_and_traversal_artifact(client, pb_env):
    assert client.get("/artifacts/art-nope/download").status_code == 404

    job_id = _upload(client, pdf=pb_env.pdf, csv=pb_env.csv).headers["location"].rsplit("/", 1)[-1]
    art_id = client.repo.add_artifact(
        job_id, "label", "x.pdf", "x.pdf", "../../escape.pdf", "h", 1, "application/pdf"
    )
    assert client.get(f"/artifacts/{art_id}/download").status_code == 404


def test_unknown_job_returns_404(client):
    assert client.get("/jobs/job-nope").status_code == 404
    assert client.get("/jobs/job-nope/status").status_code == 404


def test_healthz_reports_db_up(client):
    resp = client.get("/healthz")
    # 测试环境没有 Redis，所以整体是 degraded，但 DB 检查必须为真
    assert resp.status_code in (200, 503)
    assert resp.json()["checks"]["db"] is True


def test_cache_missing_surfaces_friendly_error(client, pb_env):
    pb_env.cache.unlink()
    resp = _upload(client, pdf=pb_env.pdf, csv=pb_env.csv)
    job_id = resp.headers["location"].rsplit("/", 1)[-1]
    job = client.repo.get_job(job_id)
    assert job["status"] == "failed"
    assert job["error"]["code"] == "cache_missing"
    assert "缓存" in job["error"]["hint"]
    assert "Traceback" not in client.get(f"/jobs/{job_id}").text
