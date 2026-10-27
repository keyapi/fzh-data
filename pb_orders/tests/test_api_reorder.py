#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重复建单后缀：order_number_usage 预留 + 显式/自动后缀 + 冲突。

通途不允许重复订单号（workflow.md §10）。API 建任务时就要把号定下来：
自动分配在服务端原子完成，失败保留预留（号跳过但不重复）。
"""

from __future__ import annotations

import pandas as pd
import pytest

from web.repository import OrderNumberConflict
from web import storage


def test_auto_suffix_increments(client):
    repo = client.repo
    assert repo.reserve_order_numbers(["137943090"], "j1") == {"137943090": "-2"}
    assert repo.reserve_order_numbers(["137943090"], "j2") == {"137943090": "-3"}


def test_bare_number_counts_as_used(client):
    repo = client.repo
    repo.record_full_numbers(["137943091"], "j0")
    assert repo.reserve_order_numbers(["137943091"], "j1") == {"137943091": "-2"}


def test_explicit_suffix_is_trusted(client):
    repo = client.repo
    assert repo.reserve_order_numbers(["137943090"], "j1", {"137943090": "-7"}) == {
        "137943090": "-7"
    }
    # 不带 - 也归一成 -N
    assert repo.reserve_order_numbers(["137943091"], "j2", {"137943091": "3"}) == {
        "137943091": "-3"
    }


def test_duplicate_reservation_conflicts(client):
    repo = client.repo
    repo.reserve_order_numbers(["137999999"], "j1", {"137999999": "-2"})
    with pytest.raises(OrderNumberConflict):
        repo.reserve_order_numbers(["137999999"], "j2", {"137999999": "-2"})


def test_api_applies_auto_suffix_to_xlsx(api_client, pb_env):
    resp = api_client.post(
        "/api/v1/jobs",
        files={
            "order_csv": ("checked0stock order x3 20260921.csv", pb_env.csv.read_bytes(), "text/csv"),
            "packslip": ("Packslip 美中 x3 20260921.pdf", pb_env.pdf.read_bytes(), "application/pdf"),
        },
        data={"no_stock": "", "reorder": "137943090"},
    )
    assert resp.status_code == 202
    job = resp.json()
    assert job["reorder"] == ["137943090=-2"]
    assert job["report"]["reorder"]["applied"] == {"137943090": "-2"}

    art = next(a for a in job["artifacts"] if a["kind"] == "tongtool")
    stored = api_client.repo.get_artifact(art["id"])
    path = storage.resolve_artifact_path(api_client.settings.artifacts_dir, stored["rel_path"])
    df = pd.read_excel(path, dtype=str)
    numbers = set(df["PO Number"].astype(str))
    assert "137943090-2" in numbers
    assert "137943091" in numbers  # 没点名的 PO 不动
    # 完整订单号也登记了，下一次自动分配会跳过 -2
    with api_client.repo.connect() as conn:
        used = {
            r[0] for r in conn.execute(
                "SELECT full_number FROM order_number_usage WHERE po_base = '137943090'"
            )
        }
    assert "137943090-2" in used
    # 裸号也登记（查全表，不限 po_base）
    with api_client.repo.connect() as conn:
        all_used = {r[0] for r in conn.execute("SELECT full_number FROM order_number_usage")}
    assert "137943091" in all_used


def test_api_explicit_reorder_map(api_client, pb_env):
    resp = api_client.post(
        "/api/v1/jobs",
        files={
            "order_csv": ("checked0stock order x3 20260921.csv", pb_env.csv.read_bytes(), "text/csv"),
            "packslip": ("Packslip 美中 x3 20260921.pdf", pb_env.pdf.read_bytes(), "application/pdf"),
        },
        data={"no_stock": "", "reorder_map": '{"137943090": "-5"}'},
    )
    assert resp.status_code == 202
    assert resp.json()["report"]["reorder"]["applied"] == {"137943090": "-5"}


def test_api_reorder_conflict_returns_409(api_client, pb_env):
    api_client.repo.reserve_order_numbers(["137943090"], "someone-else", {"137943090": "-2"})
    resp = api_client.post(
        "/api/v1/jobs",
        files={
            "order_csv": ("checked0stock order x3 20260921.csv", pb_env.csv.read_bytes(), "text/csv"),
            "packslip": ("Packslip 美中 x3 20260921.pdf", pb_env.pdf.read_bytes(), "application/pdf"),
        },
        data={"no_stock": "", "reorder_map": '{"137943090": "-2"}'},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "reorder_conflict"


def test_api_rejects_bad_reorder_map_json(api_client):
    resp = api_client.post(
        "/api/v1/jobs",
        files={
            "order_csv": ("a.csv", b"x", "text/csv"),
            "packslip": ("a.pdf", b"%PDF", "application/pdf"),
        },
        data={"no_stock": "", "reorder_map": "not-json"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_input"


def test_backfill_reads_existing_tongtool_artifacts(client, pb_env):
    """新库上线时从历史 xlsx 回填，下一次自动分配才会跳过已用过的 -2。"""
    from web import backfill_order_numbers as backfill

    client.repo.create_job(
        job_id="job-old", created_by="tester", no_stock="", no_stock_note=None,
        validate_only=False, allow_unmatched=False, input_packslip="",
        input_order="old.csv", pipeline_version="test-version",
    )
    xlsx = pb_env.tmp / "PB_0_导入_原始_old.xlsx"
    pd.DataFrame({
        "PO Number": ["137943090", "137943090-2"],
        "PO Number-Line": ["137943090-1", "137943090-2-1"],
    }).to_excel(xlsx, index=False)
    rel, size, digest = storage.publish_artifact(xlsx, client.settings.artifacts_dir, xlsx.name)
    client.repo.add_artifact(
        job_id="job-old", kind="tongtool", original_name=xlsx.name,
        download_name=xlsx.name, rel_path=rel, content_hash=digest, size_bytes=size,
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    found, warnings = backfill.collect_numbers(client.settings, client.repo)
    assert warnings == []
    assert found == {"137943090": "job-old", "137943090-2": "job-old"}

    client.repo.record_full_numbers(list(found), "job-old", source="backfill")
    assert client.repo.reserve_order_numbers(["137943090"], "job-new") == {
        "137943090": "-3"
    }
