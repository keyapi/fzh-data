from __future__ import annotations

import datetime as _dt
import json

from stock_alert.names import NameCache


class _Api:
    def __init__(self, batch_map=None, list_pages=None):
        self.batch_map = batch_map or {}
        self.list_pages = list(list_pages or [])
        self.calls: list[tuple] = []

    def request(self, path, body):
        self.calls.append((path, body))
        if "skus" in body:
            arr = []
            for sku in body["skus"]:
                name = self.batch_map.get(sku)
                if name:
                    arr.append({"sku": sku, "productName": name, "goodsDetail": [{"goodsSku": sku}]})
            return {"datas": {"array": arr}}
        return {"datas": {"array": self.list_pages.pop(0) if self.list_pages else []}}


def test_extract_variant_to_name():
    m = NameCache._extract([{"sku": "P1", "productName": "靠垫A",
                             "goodsDetail": [{"goodsSku": "V1"}, {"goodsSku": "V2"}]}])
    assert m["V1"] == "靠垫A" and m["V2"] == "靠垫A" and m["P1"] == "靠垫A"


def test_resolve_uses_cache_and_batches_missing(tmp_path):
    p = tmp_path / "n.json"
    p.write_text(json.dumps({"names": {"A": {"name": "甲", "fetched_at": "x"}},
                             "last_full_refresh": "2026-11-17", "schema": 1}), encoding="utf-8")
    api = _Api(batch_map={"B": "乙"})
    nc = NameCache(api, p, today=_dt.date(2026, 11, 17))
    out = nc.resolve(["A", "B", "C"])
    assert out == {"A": "甲", "B": "乙", "C": ""}
    assert any("skus" in b for _, b in api.calls)


def test_full_refresh_when_due(tmp_path):
    p = tmp_path / "n.json"
    p.write_text(json.dumps({"names": {}, "last_full_refresh": "2026-11-01", "schema": 1}), encoding="utf-8")
    api = _Api(list_pages=[[{"sku": "A", "productName": "甲", "goodsDetail": [{"goodsSku": "A"}]}]])
    nc = NameCache(api, p, full_refresh_days=7, today=_dt.date(2026, 11, 17))
    out = nc.resolve(["A"])
    assert out["A"] == "甲"
    saved = json.loads(p.read_text(encoding="utf-8"))
    assert saved["last_full_refresh"] == "2026-11-17"
    assert saved["names"]["A"]["name"] == "甲"
