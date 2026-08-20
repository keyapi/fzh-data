"""Tests for sync-combos cache/checkpoint helpers (Issue #188)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "SELLFOX_API"))

from combo_ops_context import ComboOpsCache, checkpoint_path, write_checkpoint  # noqa: E402
from sellfox_combo_ops import cmd_create, find_category, resolve_child_skus  # noqa: E402


def test_combo_ops_cache_reuses_category_lookup():
    calls: list[str] = []

    def fetch() -> dict:
        calls.append("fetch")
        return {"fullCid": "428697-", "id": "1"}

    cache = ComboOpsCache()
    assert cache.get_category("428697-", fetch) == {"fullCid": "428697-", "id": "1"}
    assert cache.get_category("428697-", fetch) == {"fullCid": "428697-", "id": "1"}
    assert calls == ["fetch"]
    assert cache.category_fetch_calls == 1
    assert cache.category_cache_hits == 1


def test_resolve_child_skus_uses_bottom_cache_without_refetch():
    class FailClient:
        def signed_post(self, *_args, **_kwargs):
            raise AssertionError("should not query bottoms when cache provided")

    bottom_cache = {
        "KS1": {"id": "101", "sku": "KS1"},
        "KS2": {"id": "102", "sku": "KS2"},
    }
    result = resolve_child_skus(
        FailClient(),
        [("KS1", 2), ("KS2", 1)],
        bottom_cache=bottom_cache,
    )
    assert result == [
        {"childId": "101", "sku": "KS1", "num": "2"},
        {"childId": "102", "sku": "KS2", "num": "1"},
    ]


def test_cmd_create_reuses_category_cache_and_bottom_cache():
    category_calls: list[str] = []
    page_calls: list[dict] = []

    class FakeClient:
        def signed_post(self, url, payload):
            if url == "/api/category/getList.json":
                category_calls.append("category")
                return [{"fullCid": "428697-", "id": "1", "childVo": []}]
            if url == "/api/commodity/pageList.json":
                page_calls.append(payload)
                if len(page_calls) == 1:
                    return {"rows": []}
                return {
                    "rows": [
                        {
                            "sku": "TJ#TEST-001",
                            "name": "测试组合-001",
                            "isGroup": "1",
                            "fullCid": "428697-",
                            "childSkus": [{"sku": "KS1", "num": "2", "childId": "101"}],
                        }
                    ]
                }
            if url == "/api/commodity/create.json":
                return {"id": "999"}
            raise AssertionError(url)

    cache = ComboOpsCache()
    cache.set_bottom_rows({"KS1": {"id": "101", "sku": "KS1"}})
    args = argparse.Namespace(
        sku="TJ#TEST-001",
        name="测试组合-001",
        child=["KS1:2"],
        full_cid="428697-",
        auto_calc_weight="true",
        apply=True,
        ops_cache=cache,
        bottom_cache=cache.bottom_rows,
    )
    assert cmd_create(FakeClient(), args) == 0
    assert category_calls == ["category"]
    assert len(page_calls) == 2
    assert all(payload.get("skus") == ["TJ#TEST-001"] for payload in page_calls)


def test_find_category_with_cache(monkeypatch):
    calls: list[str] = []

    class FakeClient:
        def signed_post(self, url, payload):
            calls.append(url)
            return [{"fullCid": "428697-", "id": "1", "childVo": []}]

    cache = ComboOpsCache()
    assert find_category(FakeClient(), "428697-", cache=cache) is not None
    assert find_category(FakeClient(), "428697-", cache=cache) is not None
    assert calls == ["/api/category/getList.json"]


def test_checkpoint_written_incrementally(tmp_path: Path):
    ckpt = checkpoint_path(str(tmp_path / "sync_report.json"))
    assert ckpt == tmp_path / "sync_report.checkpoint.json"
    write_checkpoint(
        ckpt,
        {"applied": [{"sku": "A", "action": "create"}], "pending": ["B"], "counts": {"pending": 1}},
    )
    payload = json.loads(ckpt.read_text(encoding="utf-8"))
    assert payload["pending"] == ["B"]
    assert payload["counts"]["pending"] == 1
