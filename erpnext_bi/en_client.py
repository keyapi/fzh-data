# -*- coding: utf-8 -*-
"""EN 生产 BI 看板 — 数据层。

链路: 销售订单(SO) → 工单(WO) → 作业卡(Job Card, 工序: 裁剪/缝制/质检/包装…)
      → 销售出库(Delivery Note, 销售/发货)

聚合口径:
- 按"基础订单号"归并拆分单 (SO-24-00030 / SO-24-00030-1 归并为 SO-24-00030)
- 每个物料 × 每道工序: 数量 = 该物料所有工单该工序作业卡 total_completed_qty 之和,
  完成时间 = 各作业卡最后记录时间 (actual_end_date, 缺失则退用 modified)
- 销售(发货)数量 = SO 回写的 delivered_qty (准);
  销售时间 = 已提交销售出库单 (against_sales_order 关联) 的最后 posting_date

说明:
- 认证沿用 EN_API 惯例: EN_API/.env 的 ERP_API_KEY / ERP_API_SECRET
- 传输层统一用 curl 子进程: requests 在本环境对 EN 生产 API 间歇性触发 nginx 417
- Job Card / Work Order / Delivery Note 支持 limit_page_length=0 一次拉全量
  (34794 张 JC 约 11 秒 / 7.9MB, 可接受; SO 带子表仍分页)
- 带子表字段的列表查询不可用 order_by=modified(触发 EN 服务端 500), 用 order_by=name
"""
from __future__ import annotations

import os
import json
import time
import subprocess
import urllib.parse
from pathlib import Path

# 凭证/URL: 复用 EN_API 模块约定
_ENV_PATH = Path(__file__).resolve().parent.parent / "EN_API" / ".env"
_BASE_URL = "https://erpnext.vilavi.cn"

# 看板固定展示的工序列 (EN 实际工序名 → 展示名)
DISPLAY_OPS = [("裁剪", "裁剪"), ("缝制", "缝制"), ("质检", "检查"), ("包装", "包装")]


def _load_env() -> None:
    if not _ENV_PATH.is_file():
        return
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


_load_env()


class EnClient:
    def __init__(self, base_url: str | None = None,
                 api_key: str | None = None, api_secret: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("ERP_URL") or _BASE_URL).rstrip("/")
        self.api_key = api_key or os.getenv("ERP_API_KEY") or ""
        self.api_secret = api_secret or os.getenv("ERP_API_SECRET") or ""

    def _get(self, doctype: str, params: dict) -> list[dict]:
        """用 curl 取数 (requests 在本环境间歇性 417, curl 稳定)。"""
        url = f"{self.base_url}/api/resource/{urllib.parse.quote(doctype)}"
        qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
        full = url + "?" + qs
        auth = f"token {self.api_key}:{self.api_secret}"
        cmd = ["curl", "-s", "-f", "-H", f"Authorization: {auth}", full]
        last: Exception | None = None
        for attempt in range(4):
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
                if r.returncode != 0:
                    raise RuntimeError(f"curl exit {r.returncode}: {r.stderr[:200]}")
                return json.loads(r.stdout).get("data", [])
            except Exception as e:
                last = e
                time.sleep(1 + attempt)
        raise last or RuntimeError("EN API 请求失败")

    # ── 拉数 ──────────────────────────────────────────────

    def fetch_so_item_rows(self, page_size: int = 500) -> list[dict]:
        """所有已提交(docstatus=1)销售订单的物料行(拍平)。"""
        fields = json.dumps([
            "name", "status", "customer", "delivery_status", "transaction_date",
            "items.item_code", "items.item_name",
            "items.qty", "items.produced_qty", "items.delivered_qty",
        ])
        rows: list[dict] = []
        start = 0
        while True:
            params = {
                "fields": fields,
                "filters": json.dumps([["docstatus", "=", 1]]),
                "limit_page_length": page_size,
                "limit_start": start,
                "order_by": "name",
            }
            chunk = self._get("Sales Order", params)
            if not chunk:
                break
            rows.extend(chunk)
            if len(chunk) < page_size:
                break
            start += page_size
        return rows

    def fetch_work_orders(self) -> list[dict]:
        """所有已提交工单: 工单号 / 关联 SO / 生产物料。"""
        return self._get("Work Order", {
            "fields": json.dumps([
                "name", "sales_order", "production_item", "item_name",
                "qty", "produced_qty", "status",
            ]),
            "filters": json.dumps([["docstatus", "=", 1]]),
            "limit_page_length": 0,
        })

    def fetch_job_cards(self) -> list[dict]:
        """全量作业卡: 工序 / 完成数量 / 最后记录时间。约 3.5 万张, ~11s。"""
        return self._get("Job Card", {
            "fields": json.dumps([
                "name", "operation", "work_order",
                "total_completed_qty", "actual_end_date", "modified", "docstatus",
            ]),
            "limit_page_length": 0,
        })

    def fetch_dn_item_rows(self) -> list[dict]:
        """所有已提交销售出库单物料行(拍平), 含关联 SO 与出库日期。"""
        return self._get("Delivery Note", {
            "fields": json.dumps([
                "name", "posting_date",
                "items.item_code", "items.qty", "items.against_sales_order",
            ]),
            "filters": json.dumps([["docstatus", "=", 1]]),
            "limit_page_length": 0,
            "order_by": "name",
        })

    # ── 聚合 ──────────────────────────────────────────────

    @staticmethod
    def _base_so(so: str) -> str:
        """剥离拆分单尾缀: SO-24-00030-1 -> SO-24-00030。"""
        parts = so.split("-")
        if len(parts) > 3:
            return "-".join(parts[:-1])
        return so

    @staticmethod
    def _fmt_ts(ts: str | None) -> str:
        """'2024-11-26 16:49:11.672132' -> '2024-11-26 16:49'。"""
        if not ts:
            return ""
        return ts[:16]

    @classmethod
    def aggregate(cls, so_rows: list[dict], wo_rows: list[dict],
                  jc_rows: list[dict], dn_rows: list[dict]) -> list[dict]:
        """按基础订单号归并, 输出每个物料的下单/各工序(数量+最后时间)/销售。"""
        # 1) 作业卡按 (工单, 工序) 汇总: 数量求和, 时间取最后
        jc_map: dict[tuple[str, str], dict] = {}
        for jc in jc_rows:
            if jc.get("docstatus") == 2:  # 已取消
                continue
            wo = jc.get("work_order")
            op = jc.get("operation")
            qty = float(jc.get("total_completed_qty") or 0)
            if not wo or not op:
                continue
            slot = jc_map.setdefault((wo, op), {"qty": 0.0, "t": ""})
            slot["qty"] += qty
            if qty > 0:
                t = jc.get("actual_end_date") or jc.get("modified") or ""
                if t > slot["t"]:
                    slot["t"] = t

        # 2) 工单按 SO 索引
        wo_by_so: dict[str, list[dict]] = {}
        for wo in wo_rows:
            so = wo.get("sales_order")
            if so:
                wo_by_so.setdefault(so, []).append(wo)

        # 3) 出库行按 (基础SO, 物料) 汇总最后出库日期; 数量以 SO 回写 delivered_qty 为准
        dn_map: dict[tuple[str, str], str] = {}
        dn_so_map: dict[str, str] = {}
        for dn in dn_rows:
            so = dn.get("against_sales_order")
            if not so:
                continue
            base = cls._base_so(so)
            d = dn.get("posting_date") or ""
            code = dn.get("item_code") or ""
            k = (base, code)
            if d > dn_map.get(k, ""):
                dn_map[k] = d
            if d > dn_so_map.get(base, ""):
                dn_so_map[base] = d

        # 4) 主聚合: SO 物料行 → 订单/物料
        orders: dict[str, dict] = {}
        for row in so_rows:
            so = row.get("name")
            if not so:
                continue
            if row.get("status") in ("Cancelled", "Completed"):
                continue
            base = cls._base_so(so)
            o = orders.setdefault(base, {
                "base_so": base, "splits": set(), "customer": "",
                "statuses": set(), "delivery_statuses": set(), "items": {},
                "order_date": "", "ordered": 0.0, "delivered": 0.0,
            })
            o["splits"].add(so)
            o["statuses"].add(row.get("status"))
            if row.get("delivery_status"):
                o["delivery_statuses"].add(row.get("delivery_status"))
            if not o["order_date"] and row.get("transaction_date"):
                o["order_date"] = row.get("transaction_date")
            if not o["customer"] and row.get("customer"):
                o["customer"] = row.get("customer")
            code = row.get("item_code")
            if not code:
                continue
            it = o["items"].setdefault(code, {
                "item_code": code, "item_name": row.get("item_name") or "",
                "ordered": 0.0, "delivered": 0.0, "ops": {},
            })
            it["ordered"] += float(row.get("qty") or 0)
            it["delivered"] += float(row.get("delivered_qty") or 0)
            o["ordered"] += float(row.get("qty") or 0)
            o["delivered"] += float(row.get("delivered_qty") or 0)

        # 5) 工序数据挂到物料上 (经 拆分SO → WO → JC, jc 先按工单索引避免全表扫描)
        jc_by_wo: dict[str, dict[str, dict]] = {}
        for (wo_name, op), slot in jc_map.items():
            jc_by_wo.setdefault(wo_name, {})[op] = slot
        for base, o in orders.items():
            for so in o["splits"]:
                for wo in wo_by_so.get(so, []):
                    code = wo.get("production_item")
                    it = o["items"].get(code)
                    if it is None:
                        # 工单生产的物料不在 SO 行 (如 BOM 半成品), 也单列出来
                        it = o["items"].setdefault(code, {
                            "item_code": code,
                            "item_name": wo.get("item_name") or "",
                            "ordered": 0.0, "delivered": 0.0, "ops": {},
                        })
                    for op_key, slot in jc_by_wo.get(wo.get("name"), {}).items():
                        s = it["ops"].setdefault(op_key, {"qty": 0.0, "t": ""})
                        s["qty"] += slot["qty"]
                        if slot["t"] > s["t"]:
                            s["t"] = slot["t"]

        # 6) 输出
        result = []
        for base, o in orders.items():
            items = sorted(o["items"].values(), key=lambda x: x["item_code"] or "")
            order_ops: dict[str, dict] = {}
            for it in items:
                # 销售时间: 物料级出库日期, 退化到订单级
                it["sold_qty"] = it.pop("delivered")
                if it["sold_qty"] > 0:
                    it["sold_t"] = dn_map.get((base, it["item_code"]), "") or dn_so_map.get(base, "")
                else:
                    it["sold_t"] = ""
                # 时间格式化
                for op, s in it["ops"].items():
                    s["t"] = cls._fmt_ts(s["t"])
                    os_ = order_ops.setdefault(op, {"qty": 0.0, "t": ""})
                    os_["qty"] += s["qty"]
                    if s["t"] > os_["t"]:
                        os_["t"] = s["t"]
            sold_t = dn_so_map.get(base, "") if o["delivered"] > 0 else ""
            result.append({
                "base_so": base,
                "splits": sorted(o["splits"]),
                "customer": o["customer"],
                "statuses": sorted(o["statuses"]),
                "delivery_statuses": sorted(o["delivery_statuses"]),
                "order_date": o["order_date"],
                "ordered": o["ordered"],
                "sold_qty": o["delivered"],
                "sold_t": sold_t,
                "ops": order_ops,
                "items": items,
            })
        result.sort(key=lambda x: x["base_so"])
        return result

    def fetch_all(self) -> dict:
        """一次拉全 4 类单据并聚合。全量约 20s。"""
        so_rows = self.fetch_so_item_rows()
        wo_rows = self.fetch_work_orders()
        jc_rows = self.fetch_job_cards()
        dn_rows = self.fetch_dn_item_rows()
        orders = self.aggregate(so_rows, wo_rows, jc_rows, dn_rows)
        return {
            "orders": orders,
            "counts": {
                "so_rows": len(so_rows), "work_orders": len(wo_rows),
                "job_cards": len(jc_rows), "dn_rows": len(dn_rows),
            },
        }
