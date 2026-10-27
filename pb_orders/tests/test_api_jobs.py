#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JSON API 任务流：检查 → 出件 → 状态 / 产物 / 下载 / 重试。

队列在 conftest 里被换成同步执行，所以 POST 返回时任务已经跑完，
可以直接断言最终状态与产物字节。
"""

from __future__ import annotations


def _check(api_client, pb_env, no_stock="STYLE-B", name="new orders x3 20260921.csv"):
    return api_client.post(
        "/api/v1/checks",
        files={"raw_csv": (name, pb_env.csv.read_bytes(), "text/csv")},
        data={"no_stock": no_stock},
    )


def _fulfill(api_client, pb_env):
    return api_client.post(
        "/api/v1/jobs",
        files={
            "order_csv": ("checked0stock order x3 20260921.csv", pb_env.csv.read_bytes(), "text/csv"),
            "packslip": ("Packslip 美中 x3 20260921.pdf", pb_env.pdf.read_bytes(), "application/pdf"),
        },
        data={"no_stock": ""},
    )


def test_create_check_returns_202_and_succeeds(api_client, pb_env):
    resp = _check(api_client, pb_env)
    assert resp.status_code == 202
    body = resp.json()
    job_id = body["id"]
    assert resp.headers["location"].endswith(f"/api/v1/jobs/{job_id}")
    assert body["job_type"] == "stock_check"
    assert body["status"] == "succeeded"  # 同步 worker
    kinds = {a["kind"] for a in body["artifacts"]}
    assert {"checked_order", "stock_operations", "input_order"} <= kinds
    assert body["report"]["details"]["out_of_stock"] == 1


def test_get_job_and_download_bytes(api_client, pb_env):
    job_id = _check(api_client, pb_env).json()["id"]
    job = api_client.get(f"/api/v1/jobs/{job_id}").json()
    assert job["status"] == "succeeded"
    assert job["report"]["pipeline_version"] == "test-version"

    art = next(a for a in job["artifacts"] if a["kind"] == "checked_order")
    assert art["download_url"] == f"/api/v1/artifacts/{art['id']}/download"
    dl = api_client.get(art["download_url"])
    assert dl.status_code == 200
    assert len(dl.content) == art["size_bytes"]
    from urllib.parse import unquote

    assert art["download_name"] in unquote(dl.headers["content-disposition"])


def test_list_artifacts_endpoint(api_client, pb_env):
    job_id = _check(api_client, pb_env).json()["id"]
    resp = api_client.get(f"/api/v1/jobs/{job_id}/artifacts")
    assert resp.status_code == 200
    assert resp.json()["job_id"] == job_id
    assert resp.json()["artifacts"]


def test_unknown_job_is_404_json(api_client):
    resp = api_client.get("/api/v1/jobs/job-does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_unknown_artifact_is_404_json(api_client):
    resp = api_client.get("/api/v1/artifacts/art-does-not-exist/download")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_create_fulfillment_job(api_client, pb_env):
    resp = _fulfill(api_client, pb_env)
    assert resp.status_code == 202
    job = resp.json()
    assert job["job_type"] == "fulfillment"
    assert job["status"] == "succeeded"
    kinds = {a["kind"] for a in job["artifacts"]}
    assert {"tongtool", "label", "back_label", "input_packslip", "input_order"} <= kinds
    assert job["report"]["join"]["unmatched"] == 0


def test_fulfillment_from_check(api_client, pb_env):
    check_id = _check(api_client, pb_env, no_stock="").json()["id"]
    resp = api_client.post(
        f"/api/v1/jobs/{check_id}/fulfill",
        files={"packslip": ("Packslip 美中 x3 20260921.pdf", pb_env.pdf.read_bytes(), "application/pdf")},
    )
    assert resp.status_code == 202
    job = resp.json()
    assert job["source_job_id"] == check_id
    assert job["status"] == "succeeded"
    kinds = {a["kind"] for a in job["artifacts"]}
    assert {"tongtool", "label", "back_label"} <= kinds


def test_fulfill_from_check_requires_succeeded_source(api_client, pb_env):
    job_id = _check(api_client, pb_env).json()["id"]
    # 把来源任务改成失败态：接口必须 409，而不是去读一个不存在的 checked CSV
    api_client.repo.mark_failed(job_id, {"code": "x", "message": "boom"})
    resp = api_client.post(
        f"/api/v1/jobs/{job_id}/fulfill",
        files={"packslip": ("p.pdf", pb_env.pdf.read_bytes(), "application/pdf")},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict_state"


def test_retry_creates_new_job(api_client, pb_env):
    job_id = _check(api_client, pb_env).json()["id"]
    resp = api_client.post(f"/api/v1/jobs/{job_id}/retry")
    assert resp.status_code == 202
    body = resp.json()
    assert body["id"] != job_id
    assert body["source_job_id"] == job_id
    assert body["status"] == "succeeded"


def test_invalid_upload_extension_is_422_or_400(api_client, pb_env):
    resp = api_client.post(
        "/api/v1/checks",
        files={"raw_csv": ("payload.pdf", b"%PDF", "application/pdf")},
        data={"no_stock": ""},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_input"


def test_no_stock_settings_roundtrip(api_client):
    resp = api_client.put("/api/v1/settings/no-stock", json={"no_stock": "A-1, B-2, a-1"})
    assert resp.status_code == 200
    assert resp.json()["no_stock"] == "A-1,B-2"
    got = api_client.get("/api/v1/settings/no-stock")
    assert got.status_code == 200
    assert got.json()["no_stock"] == "A-1,B-2"
    assert got.json()["updated_by"] == "test-agent"
