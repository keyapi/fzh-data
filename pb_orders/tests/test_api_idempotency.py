#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""幂等与去重：Idempotency-Key 重放 / 冲突，以及同输入短窗口去重。"""

from __future__ import annotations


def _post_check(api_client, pb_env, data=None, key=None, csv_extra=b""):
    headers = {"Idempotency-Key": key} if key else {}
    return api_client.post(
        "/api/v1/checks",
        files={"raw_csv": ("new orders x3 20260921.csv", pb_env.csv.read_bytes() + csv_extra, "text/csv")},
        data=data or {"no_stock": "STYLE-B"},
        headers=headers,
    )


def test_same_key_same_input_replays(api_client, pb_env):
    first = _post_check(api_client, pb_env, key="k-1")
    assert first.status_code == 202
    second = _post_check(api_client, pb_env, key="k-1")
    assert second.status_code == 200
    assert second.headers.get("idempotent-replayed") == "true"
    assert second.json()["id"] == first.json()["id"]


def test_same_key_different_input_conflicts(api_client, pb_env):
    assert _post_check(api_client, pb_env, key="k-2").status_code == 202
    resp = _post_check(api_client, pb_env, key="k-2", csv_extra=b"\n")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "idempotency_conflict"


def test_different_keys_deduplicate_by_input(api_client, pb_env):
    first = _post_check(api_client, pb_env, key="k-3")
    second = _post_check(api_client, pb_env, key="k-4")
    assert second.status_code == 200
    assert second.json()["deduplicated"] is True
    assert second.json()["id"] == first.json()["id"]


def test_no_key_same_input_deduplicates(api_client, pb_env):
    first = _post_check(api_client, pb_env)
    second = _post_check(api_client, pb_env)
    assert first.status_code == 202
    assert second.status_code == 200
    assert second.json()["deduplicated"] is True
    assert second.json()["id"] == first.json()["id"]


def test_different_no_stock_is_not_deduplicated(api_client, pb_env):
    first = _post_check(api_client, pb_env, data={"no_stock": "STYLE-B"})
    second = _post_check(api_client, pb_env, data={"no_stock": "STYLE-C"})
    assert second.status_code == 202
    assert second.json()["id"] != first.json()["id"]


def test_failed_job_is_not_reused(api_client, pb_env):
    first = _post_check(api_client, pb_env)
    job_id = first.json()["id"]
    api_client.repo.mark_failed(job_id, {"code": "x", "message": "boom"})
    second = _post_check(api_client, pb_env)
    assert second.status_code == 202
    assert second.json()["id"] != job_id


def test_idempotency_is_scoped_per_key(client, pb_env):
    k1 = client.repo.create_api_key("k1", "check", "pytest")
    k2 = client.repo.create_api_key("k2", "check", "pytest")
    files = {"raw_csv": ("n.csv", pb_env.csv.read_bytes(), "text/csv")}
    r1 = client.post(
        "/api/v1/checks", files=files, data={"no_stock": ""},
        headers={"Authorization": f"Bearer {k1['key']}", "Idempotency-Key": "shared"},
    )
    # 同一把 Key 的幂等重放
    r2 = client.post(
        "/api/v1/checks",
        files={"raw_csv": ("n.csv", pb_env.csv.read_bytes(), "text/csv")},
        data={"no_stock": ""},
        headers={"Authorization": f"Bearer {k1['key']}", "Idempotency-Key": "shared"},
    )
    assert r2.status_code == 200 and r2.json()["id"] == r1.json()["id"]
    # 另一把 Key 用同一个 Idempotency-Key：不共享（但同输入会走去重）
    r3 = client.post(
        "/api/v1/checks",
        files={"raw_csv": ("n.csv", pb_env.csv.read_bytes(), "text/csv")},
        data={"no_stock": ""},
        headers={"Authorization": f"Bearer {k2['key']}", "Idempotency-Key": "shared"},
    )
    assert r3.status_code == 200
    assert r3.json()["deduplicated"] is True
    assert r3.json()["id"] == r1.json()["id"]


def test_expired_idempotency_rows_are_purged(client):
    client.repo.store_idempotency(
        "api-key:x", "checks", "old", "fp", "job-x", "{}", ttl_minutes=-1
    )
    assert (client.repo.lookup_idempotency("api-key:x", "checks", "old")) is None
    assert client.repo.purge_expired_idempotency() >= 1
