# -*- coding: utf-8 -*-
"""EN（ERPNext）实时供给侧适配器——只读，不下单。

三个契约函数把 EN 的实时事实装成 ``supply_netting`` 已冻结的输入形状：

- ``fetch_stock_snapshot()`` → 库存快照 parquet 契约
  （``snapshot_date / snapshot_at / run_id / warehouse_name / sku /
  available / intransit / waiting_shipment / defects``，``sku`` 仍是通途 SKU）；
- ``fetch_open_so()`` → 未履约 SO CSV 契约
  （``canonical_sku / canonical_warehouse / canonical_uom / quantity``）；
- ``fetch_open_po()`` → 开放采购 TSV 契约
  （``document_key / sku / ordered / open_qty / warehouse``，``sku`` 为 EN 物料码）。

证据链 ``fetch_chain(sku, ...)`` 汇总 SO→WO→DN→Package→PO 节点；关联键缺失的节点
标 ``linked=False``，原因写 ``reason``。Tongtool Package 只按订单号/tracking 精确过滤，
**绝不**全量扫描；没有键时留一条明确的 unlinked 证据而不是去扫 20 万行。

口径纪律：
- 只 GET；凭证只进请求头，不写日志、不进异常文本。
- 未知仓库/单位保留空字符串，不按名字猜；SKU 一对多沿用 ``canonical.py`` 的
  ``ambiguous:`` / ``unmapped:`` 标记。
- 关闭/取消单据排除；行级开放量 = ``qty - delivered_qty`` / ``qty - received_qty``。
"""

from __future__ import annotations

import json
import math
import os
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote
from typing import Any, Iterable, Sequence

import pandas as pd
import requests

from demand_collaboration.so_evidence import branch as branch_of_customer
from self_fulfilled_demand.canonical import (
    SKU_MAP_DEFAULT,
    WAREHOUSE_ALIASES,
    load_sku_map,
    load_warehouse_config,
    resolve_warehouse,
)
from self_fulfilled_demand.en_reader import load_env
from supply_netting.so_backlog import customer_branch

DEFAULT_BASE_URL = "https://erpnext.vilavi.cn"
RETRY_STATUS = frozenset({408, 417, 425, 429, 500, 502, 503, 504})
NOT_RETRY_STATUS = frozenset({400, 401, 403, 404})

RUN_DOCTYPE = "Tongtool Stock Run"
STOCK_DOCTYPE = "Tongtool Stock Latest"
SO_DOCTYPE = "Sales Order"
PO_DOCTYPE = "Purchase Order"
WO_DOCTYPE = "Work Order"
DN_DOCTYPE = "Delivery Note"
PACKAGE_DOCTYPE = "Tongtool Package"

STOCK_COLUMNS = [
    "snapshot_date", "snapshot_at", "run_id", "warehouse_name", "warehouse_id",
    "sku", "available", "intransit", "waiting_shipment", "defects", "stock_key",
]
SO_COLUMNS = [
    "canonical_sku", "canonical_warehouse", "canonical_uom", "quantity",
    "document_key", "item_row", "item_code", "customer_item_code", "customer",
    "branch", "status", "transaction_date", "delivery_date", "line_warehouse",
    "uom", "sku_mapping_status",
]
PO_COLUMNS = [
    "document_key", "sku", "ordered", "open_qty", "warehouse", "eta", "status",
    "supplier", "transaction_date", "schedule_date", "received_qty",
    "sales_order", "item_row",
]
CHAIN_COLUMNS = [
    "node", "document", "doctype", "date", "quantity", "status", "sku",
    "item_code", "warehouse", "branch", "link_key", "link_basis", "linked",
    "reason", "detail",
]

CLOSED_STATUSES = frozenset({"closed", "cancelled"})
SKU_PREFIXES = ("PK#", "ND#", "删除")


class EnLiveError(RuntimeError):
    """EN 实时读取失败；不含凭证。"""

    def __init__(self, message: str, status: int | None = None, url: str | None = None):
        super().__init__(message)
        self.status = status
        self.url = url


# --------------------------------------------------------------------------- 低层客户端
class EnLiveClient:
    """最小只读客户端：GET / 分页 / 超时 / 429&5xx 重试。"""

    def __init__(self, base_url: str | None = None, env_file: str | Path | None = None,
                 timeout: float = 60.0, min_interval: float = 0.05,
                 max_retries: int = 4, api_key: str | None = None,
                 api_secret: str | None = None):
        env = {} if (api_key and api_secret) else load_env(
            [Path(env_file)] if env_file else None)
        self.base_url = (base_url or env.get("ERP_BASE_URL")
                         or os.environ.get("ERP_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        key = api_key or env.get("ERP_API_KEY")
        secret = api_secret or env.get("ERP_API_SECRET")
        if not key or not secret:
            raise EnLiveError("缺少 ERP_API_KEY / ERP_API_SECRET（检查 EN_API/.env 或进程环境变量）")
        self._headers = {
            "Authorization": f"token {key}:{secret}",
            "Accept": "application/json",
        }
        self.timeout = float(timeout)
        self.min_interval = float(min_interval)
        self.max_retries = int(max_retries)
        self._last_call = 0.0
        self.request_count = 0
        self._session = requests.Session()

    def _throttle(self) -> None:
        wait = self.min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def _get(self, doctype: str, params: dict[str, Any]) -> list[dict]:
        url = f"{self.base_url}/api/resource/{quote(doctype, safe='')}"
        last: EnLiveError | None = None
        for attempt in range(self.max_retries):
            self._throttle()
            try:
                response = self._session.request(
                    "GET", url, headers=self._headers, params=params,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:  # 网络层：可重试
                last = EnLiveError(f"GET {doctype} 网络错误：{type(exc).__name__}", None, url)
                if attempt < self.max_retries - 1:
                    time.sleep(min(2 ** attempt, 8))
                    continue
                raise last from None
            self.request_count += 1
            status = response.status_code
            if status == 200:
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise EnLiveError(f"GET {doctype} 返回非 JSON", status, url) from exc
                data = payload.get("data") if isinstance(payload, dict) else None
                if not isinstance(data, list):
                    raise EnLiveError(f"GET {doctype} 返回缺少 data 列表", status, url)
                return data
            if status in NOT_RETRY_STATUS:
                raise EnLiveError(f"GET {doctype} 被拒绝：HTTP {status}", status, url)
            if status in RETRY_STATUS and attempt < self.max_retries - 1:
                last = EnLiveError(f"GET {doctype} 暂时失败：HTTP {status}", status, url)
                time.sleep(min(2 ** attempt, 8))
                continue
            raise EnLiveError(f"GET {doctype} 失败：HTTP {status}", status, url)
        raise last or EnLiveError(f"GET {doctype} 失败", None, url)

    def list_page(self, doctype: str, fields: Sequence[str],
                  filters: Sequence | None = None, order_by: str | None = None,
                  limit_start: int = 0, limit_page_length: int = 1) -> list[dict]:
        params: dict[str, Any] = {
            "fields": json.dumps(list(fields), ensure_ascii=False),
            "limit_start": int(limit_start),
            "limit_page_length": int(limit_page_length),
        }
        if filters:
            params["filters"] = json.dumps(list(filters), ensure_ascii=False)
        if order_by:
            params["order_by"] = order_by
        return self._get(doctype, params)

    def fetch_all(self, doctype: str, fields: Sequence[str],
                  filters: Sequence | None = None, order_by: str | None = None,
                  page_size: int = 500, max_pages: int = 400) -> list[dict]:
        """offset 分页取尽；预算耗尽必须报错，不能静默截断。"""
        rows: list[dict] = []
        start = 0
        for page in range(max_pages):
            batch = self.list_page(doctype, fields, filters=filters, order_by=order_by,
                                   limit_start=start, limit_page_length=page_size)
            rows.extend(batch)
            if len(batch) < page_size:
                return rows
            start += page_size
        raise EnLiveError(f"{doctype} 分页超过 {max_pages} 页仍未取尽，拒绝截断")


def client(env_file: str | Path | None = None, base_url: str | None = None,
           timeout: float = 60.0, max_retries: int = 4) -> EnLiveClient:
    """按 EN_API/.env 或进程环境变量建只读客户端。"""
    return EnLiveClient(base_url=base_url, env_file=env_file, timeout=timeout,
                        max_retries=max_retries)


def _c(_client: EnLiveClient | None) -> EnLiveClient:
    return _client if _client is not None else client()


# --------------------------------------------------------------------------- 通用小工具
def _text(value) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).strip()


def _number(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _frame(records: list[dict], columns: Sequence[str]) -> pd.DataFrame:
    return pd.DataFrame(records, columns=list(columns))


def _empty(columns: Sequence[str]) -> pd.DataFrame:
    return _frame([], columns)


def _sku_mapping(path: str | Path | None = SKU_MAP_DEFAULT) -> pd.DataFrame | None:
    """加载 tongtool_sku → item_codes 映射；文件不存在时返回 None（不猜）。"""
    if path is None:
        return None
    p = Path(path)
    if not p.exists():
        return None
    return load_sku_map(p)


def _warehouse_config(path: str | Path | None = WAREHOUSE_ALIASES) -> dict:
    return load_warehouse_config(path or WAREHOUSE_ALIASES)


def _lookup_sku_map(sku_map: pd.DataFrame | None, tongtool_sku: str) -> tuple[str, str]:
    """返回 (canonical_sku, mapping_status)；与 ``canonical.py`` 的标记保持一致。"""
    if not tongtool_sku or sku_map is None or sku_map.empty:
        return "", "no_sku_map"
    found = sku_map.loc[sku_map["tongtool_sku"] == tongtool_sku]
    if found.empty:
        return f"unmapped:{tongtool_sku}", "unmapped"
    codes = found.iloc[0]["item_codes"]
    if not isinstance(codes, tuple) or len(codes) != 1:
        return f"ambiguous:{tongtool_sku}", "ambiguous"
    return str(codes[0]), "mapped"


def _canonical_sku(item_code: str, customer_item_code: str,
                   sku_map: pd.DataFrame | None) -> tuple[str, str]:
    """SO 行的规范 SKU：优先客户物料码的登记映射，其次 EN 行物料码。"""
    if customer_item_code:
        canonical, status = _lookup_sku_map(sku_map, customer_item_code)
        if status != "no_sku_map":
            return canonical, status
    if item_code:
        return item_code, "item_code"
    return "", "missing"


def _canonical_warehouse(customer: str, cfg: dict) -> str:
    """SO 客户 → 分公司目的仓；非分公司客户/未知仓保留空。"""
    destination, _role = customer_branch(customer)
    if not destination:
        return ""
    resolved = resolve_warehouse(destination, cfg)
    if resolved["warehouse_status"] == "unknown":
        return ""
    return str(resolved["canonical_warehouse"])


def _branch_of_warehouse(warehouse: str, cfg: dict) -> str:
    resolved = resolve_warehouse(warehouse, cfg)
    canonical = str(resolved.get("canonical_warehouse") or "")
    if "美东" in canonical or "CENTRADE" in canonical.upper():
        return "USNJ"
    if "美中" in canonical or "DANEEY" in canonical.upper():
        return "USTX"
    if "波兰" in canonical:
        return "PL"
    return ""


def _chunks(values: Iterable[str], size: int = 40) -> list[list[str]]:
    items = [v for v in dict.fromkeys(values) if v]
    return [items[i:i + size] for i in range(0, len(items), size)]


def _in_filter(field: str, values: Sequence[str], table: str | None = None) -> list:
    return [table or field, field, "in", list(values)]


def _open_quantity(qty: float | None, done: float | None) -> float | None:
    if qty is None:
        return None
    return qty - (done or 0.0)


def _progress(value) -> float | None:
    """已交付/已收货量：ERP 单据缺省即 0；有值但不可解析则返回 None（不猜）。"""
    if value is None or value == "" or (isinstance(value, float) and math.isnan(value)):
        return 0.0
    return _number(value)


# --------------------------------------------------------------------------- 库存快照
def _latest_stock_run(c: EnLiveClient) -> dict:
    rows = c.list_page(
        RUN_DOCTYPE, ["*"],
        filters=[["job", "=", "stock_snapshot"], ["status", "=", "Success"],
                 ["complete", "=", 1]],
        order_by="snapshot_at desc", limit_page_length=1,
    )
    if not rows:
        raise EnLiveError("EN 没有可用的库存快照 run（job=stock_snapshot/status=Success/complete=1）")
    run = rows[0]
    if not run.get("run_id") or not run.get("snapshot_at") or not run.get("snapshot_date"):
        raise EnLiveError("EN 库存快照 run 缺少 run_id/snapshot_at/snapshot_date")
    return run


def fetch_stock_snapshot(_client: EnLiveClient | None = None, *,
                         page_size: int = 500) -> tuple[pd.DataFrame, dict]:
    """最新成功 run 的全量库存行 → ``load_stock`` parquet 契约。"""
    c = _c(_client)
    run = _latest_stock_run(c)
    run_id = str(run["run_id"])
    raw = c.fetch_all(
        STOCK_DOCTYPE,
        ["stock_key", "warehouse", "warehouse_id", "sku", "available", "intransit",
         "waiting_shipment", "defects", "snapshot_at", "run_id"],
        filters=[["run_id", "=", run_id]],
        order_by="name asc",
        page_size=page_size,
    )
    expected = run.get("row_count")
    if expected is not None and int(expected) >= 0 and len(raw) != int(expected):
        raise EnLiveError(
            f"库存快照行数不一致：run.row_count={expected}，实际取回 {len(raw)}（拒绝残缺快照）")
    if not raw:
        frame = _empty(STOCK_COLUMNS)
        return frame, dict(source="en_tongtool_stock_latest", run_id=run_id,
                           snapshot_date=str(run["snapshot_date"]),
                           snapshot_at=str(run["snapshot_at"]), rows=0,
                           warehouses=[], run_row_count=expected)

    records: list[dict] = []
    seen: set[str] = set()
    for row in raw:
        key = _text(row.get("stock_key"))
        if key and key in seen:
            raise EnLiveError(f"库存快照出现重复 stock_key：{key}")
        if key:
            seen.add(key)
        sku = _text(row.get("sku"))
        warehouse = _text(row.get("warehouse"))
        if not sku or not warehouse:
            raise EnLiveError("库存快照行缺少 sku/warehouse")
        quantities: dict[str, float] = {}
        for column in ("available", "intransit", "waiting_shipment", "defects"):
            value = _number(row.get(column))
            if value is None:
                raise EnLiveError(f"库存快照行数量不可解析：{column}={row.get(column)!r}")
            quantities[column] = value
        records.append(dict(
            snapshot_date=str(run["snapshot_date"]),
            snapshot_at=str(row.get("snapshot_at") or run.get("snapshot_at")),
            run_id=run_id,
            warehouse_name=warehouse,
            warehouse_id=_text(row.get("warehouse_id")),
            sku=sku,
            stock_key=key,
            **quantities,
        ))
    frame = _frame(records, STOCK_COLUMNS)
    meta = dict(
        source="en_tongtool_stock_latest",
        run_id=run_id,
        snapshot_date=str(run["snapshot_date"]),
        snapshot_at=str(run["snapshot_at"]),
        rows=int(len(frame)),
        warehouses=sorted(frame["warehouse_name"].astype(str).unique().tolist()),
        run_row_count=expected,
        warehouse_count=run.get("warehouse_count"),
    )
    return frame, meta


# --------------------------------------------------------------------------- 开放 SO
SO_FIELDS = [
    "name", "status", "docstatus", "customer", "customer_name",
    "transaction_date", "delivery_date", "set_warehouse",
    "items.name as item_row", "items.item_code", "items.customer_item_code",
    "items.qty", "items.delivered_qty", "items.stock_uom", "items.uom",
    "items.warehouse", "items.delivery_date",
]


def fetch_open_so(branch: str | None = None, _client: EnLiveClient | None = None, *,
                  sku_map: pd.DataFrame | None = None,
                  warehouse_cfg: dict | None = None,
                  page_size: int = 500) -> tuple[pd.DataFrame, dict]:
    """已提交、未关闭 SO 的行级未发量 → 未履约 backlog 契约。

    ``canonical_sku`` 优先走客户物料码的登记映射（与需求侧同一口径）；
    ``canonical_warehouse`` 取客户所属分公司目的仓（SO 行仓是工厂仓，不是需求侧仓）；
    仓不明/UOM 不明保留空；``branch`` 过滤按客户名判定。
    """
    c = _c(_client)
    sku_map = _sku_mapping() if sku_map is None else sku_map
    cfg = _warehouse_config() if warehouse_cfg is None else warehouse_cfg
    wanted_branch = _text(branch).upper() or None
    if wanted_branch not in (None, "USNJ", "USTX", "PL"):
        raise ValueError(f"未知分公司编码：{branch}（只支持 USNJ/USTX/PL）")
    target_branch = wanted_branch

    raw = c.fetch_all(
        SO_DOCTYPE, SO_FIELDS,
        filters=[["docstatus", "=", 1],
                 ["status", "not in", ["Closed", "Cancelled"]]],
        order_by="`tabSales Order`.name asc",
        page_size=page_size,
    )
    skipped = dict(status_closed=0, zero_open=0, missing_quantity=0, branch_mismatch=0)
    records: list[dict] = []
    for row in raw:
        status = _text(row.get("status"))
        if status.lower() in CLOSED_STATUSES:
            skipped["status_closed"] += 1
            continue
        qty = _number(row.get("qty"))
        delivered = _progress(row.get("delivered_qty"))
        open_qty = _open_quantity(qty, delivered)
        if qty is None or delivered is None:
            skipped["missing_quantity"] += 1
            continue
        if open_qty is None or open_qty <= 0:
            skipped["zero_open"] += 1
            continue
        customer = _text(row.get("customer"))
        row_branch = branch_of_customer(customer) or ""
        if target_branch and row_branch != target_branch:
            skipped["branch_mismatch"] += 1
            continue
        item_code = _text(row.get("item_code"))
        customer_item_code = _text(row.get("customer_item_code"))
        canonical_sku, mapping_status = _canonical_sku(item_code, customer_item_code, sku_map)
        canonical_warehouse = _canonical_warehouse(customer, cfg)
        canonical_uom = _text(row.get("stock_uom")) or _text(row.get("uom"))
        records.append(dict(
            canonical_sku=canonical_sku,
            canonical_warehouse=canonical_warehouse,
            canonical_uom=canonical_uom,
            quantity=float(open_qty),
            document_key=_text(row.get("name")),
            item_row=_text(row.get("item_row")),
            item_code=item_code,
            customer_item_code=customer_item_code,
            customer=customer,
            branch=row_branch,
            status=status,
            transaction_date=_text(row.get("transaction_date")),
            delivery_date=_text(row.get("items.delivery_date") or row.get("delivery_date")),
            line_warehouse=_text(row.get("warehouse")),
            uom=canonical_uom,
            sku_mapping_status=mapping_status,
        ))
    frame = _frame(records, SO_COLUMNS)
    meta = dict(
        source="en_sales_order",
        branch=target_branch,
        rows=int(len(frame)),
        quantity=float(frame["quantity"].sum()) if len(frame) else 0.0,
        customers=sorted({r["customer"] for r in records}),
        branches=sorted({r["branch"] for r in records if r["branch"]}),
        statuses_fetched=sorted({_text(r.get("status")) for r in raw}),
        skipped=skipped,
        empty_warehouse=int((frame["canonical_warehouse"] == "").sum()) if len(frame) else 0,
        empty_uom=int((frame["canonical_uom"] == "").sum()) if len(frame) else 0,
        unmapped_sku=int(frame["sku_mapping_status"].isin(["unmapped", "ambiguous"]).sum())
        if len(frame) else 0,
    )
    return frame, meta


# --------------------------------------------------------------------------- 开放 PO
PO_FIELDS = [
    "name", "status", "docstatus", "supplier", "transaction_date", "schedule_date",
    "set_warehouse",
    "items.name as item_row", "items.item_code", "items.qty", "items.received_qty",
    "items.stock_uom", "items.uom", "items.warehouse", "items.schedule_date",
    "items.expected_delivery_date", "items.sales_order",
]


def fetch_open_po(_client: EnLiveClient | None = None, *,
                  page_size: int = 500) -> tuple[pd.DataFrame, dict]:
    """已提交、未关闭 PO 的开放行 → ``po_open`` 契约。

    ``sku`` 是 EN ``Item.item_code``（不是通途 goods_sku）；仓/ETA 缺失保留空。
    """
    c = _c(_client)
    raw = c.fetch_all(
        PO_DOCTYPE, PO_FIELDS,
        filters=[["docstatus", "=", 1],
                 ["status", "not in", ["Closed", "Cancelled"]]],
        order_by="`tabPurchase Order`.name asc",
        page_size=page_size,
    )
    skipped = dict(status_closed=0, zero_open=0, missing_quantity=0)
    records: list[dict] = []
    for row in raw:
        status = _text(row.get("status"))
        if status.lower() in CLOSED_STATUSES:
            skipped["status_closed"] += 1
            continue
        qty = _number(row.get("qty"))
        received = _progress(row.get("received_qty"))
        open_qty = _open_quantity(qty, received)
        if qty is None or received is None:
            skipped["missing_quantity"] += 1
            continue
        if open_qty is None or open_qty <= 0:
            skipped["zero_open"] += 1
            continue
        warehouse = _text(row.get("warehouse")) or _text(row.get("set_warehouse"))
        eta = _text(row.get("items.expected_delivery_date"))
        records.append(dict(
            document_key=_text(row.get("name")),
            sku=_text(row.get("item_code")),
            ordered=float(qty),
            open_qty=float(open_qty),
            warehouse=warehouse,
            eta=eta,
            status=status,
            supplier=_text(row.get("supplier")),
            transaction_date=_text(row.get("transaction_date")),
            schedule_date=_text(row.get("items.schedule_date") or row.get("schedule_date")),
            received_qty=float(received or 0.0),
            sales_order=_text(row.get("items.sales_order")),
            item_row=_text(row.get("item_row")),
        ))
    frame = _frame(records, PO_COLUMNS)
    meta = dict(
        source="en_purchase_order",
        rows=int(len(frame)),
        quantity=float(frame["open_qty"].sum()) if len(frame) else 0.0,
        suppliers=sorted({r["supplier"] for r in records if r["supplier"]}),
        statuses_fetched=sorted({_text(r.get("status")) for r in raw}),
        skipped=skipped,
        empty_warehouse=int((frame["warehouse"] == "").sum()) if len(frame) else 0,
        empty_eta=int((frame["eta"] == "").sum()) if len(frame) else 0,
    )
    return frame, meta


# --------------------------------------------------------------------------- 证据链
def _sku_variants(codes: Sequence[str]) -> list[str]:
    out: set[str] = set()
    for code in codes:
        text = _text(code)
        if not text:
            continue
        out.add(text)
        for prefix in SKU_PREFIXES:
            if text.startswith(prefix):
                out.add(text[len(prefix):])
            else:
                out.add(prefix + text)
    return sorted(v for v in out if v)


def _match_item(item_code: str, codes: Sequence[str]) -> str | None:
    text = _text(item_code)
    if not text:
        return None
    if text in codes:
        return "exact"
    for prefix in SKU_PREFIXES:
        if text.startswith(prefix) and text[len(prefix):] in codes:
            return f"{prefix}-stripped (conversion_assumed)"
        if any(prefix + code == text for code in codes):
            return f"{prefix}-prefixed"
    return None


def _fetch_by_keys(c: EnLiveClient, doctype: str, fields: Sequence[str],
                   key_field: str, values: Sequence[str], base_filters: Sequence | None = None,
                   table: str | None = None, order_by: str | None = None) -> list[dict]:
    rows: list[dict] = []
    for chunk in _chunks(values):
        filters = list(base_filters or [])
        if table:
            filters.append([table, key_field, "in", chunk])
        else:
            # 父单字段必须用三元组；四元组会被 Frappe 当成 (doctype, field, op, value)
            filters.append([key_field, "in", chunk])
        rows.extend(c.fetch_all(doctype, fields, filters=filters, order_by=order_by))
    return rows


def fetch_chain(sku: str, branch: str | None = None, since_days: int = 180,
                _client: EnLiveClient | None = None, *,
                order_numbers: Sequence[str] | None = None,
                tracking_numbers: Sequence[str] | None = None,
                sku_map: pd.DataFrame | None = None,
                warehouse_cfg: dict | None = None) -> pd.DataFrame:
    """某 SKU 的 SO→WO→DN→Package→PO 节点证据（只读）。

    - SO 按窗口内全部已提交单据取回后本地匹配（共约 301 张，非全表扫描）；
    - WO/DN/PO 用关联键或物料码的 ``in`` 过滤分批查询；
    - Package 只接受调用方订单号/tracking 或 DN ``lr_no`` 的精确过滤；
      没有键时留一条 ``linked=False / reason=no_order_or_tracking_key`` 证据，
      **不**拉全量包裹。
    """
    c = _c(_client)
    sku_text = _text(sku)
    if not sku_text:
        raise ValueError("fetch_chain 需要非空 sku")
    sku_map = _sku_mapping() if sku_map is None else sku_map
    cfg = _warehouse_config() if warehouse_cfg is None else warehouse_cfg
    wanted_branch = _text(branch).upper() or None
    if wanted_branch not in (None, "USNJ", "USTX", "PL"):
        raise ValueError(f"未知分公司编码：{branch}（只支持 USNJ/USTX/PL）")

    codes, mapping_status = _sku_lookup(sku_text, sku_map)
    identity = list(dict.fromkeys([sku_text, *codes]))
    variants = _sku_variants(identity)
    since = (date.today() - timedelta(days=max(int(since_days), 0))).isoformat()

    records: list[dict] = []
    so_rows = _match_sales_orders(c, identity, since)
    so_branch: dict[str, str] = {}
    so_names: list[str] = []
    for row in so_rows:
        customer = _text(row.get("customer"))
        row_branch = branch_of_customer(customer) or ""
        if wanted_branch and row_branch != wanted_branch:
            continue
        name = _text(row.get("name"))
        if name and name not in so_names:
            so_names.append(name)
            so_branch[name] = row_branch
        basis = _match_item(_text(row.get("item_code")), identity) or "customer_item_code"
        records.append(_node(
            node="SO", document=name, doctype=SO_DOCTYPE,
            date=_text(row.get("transaction_date")),
            quantity=_open_quantity(_number(row.get("qty")), _progress(row.get("delivered_qty"))),
            status=_text(row.get("status")), sku=sku_text,
            item_code=_text(row.get("item_code")),
            warehouse=_text(row.get("warehouse")),
            branch=row_branch, link_key=_text(row.get("item_row")),
            link_basis=f"root ({basis})", linked=True, reason="",
            detail=f"customer={customer}; delivery_date={_text(row.get('items.delivery_date') or row.get('delivery_date'))}",
        ))

    wo_rows = _fetch_by_keys(c, WO_DOCTYPE, WO_FIELDS, "sales_order", so_names,
                             base_filters=[["docstatus", "=", 1]],
                             order_by="`tabWork Order`.name asc")
    wo_rows += _fetch_by_keys(c, WO_DOCTYPE, WO_FIELDS, "production_item", variants,
                              base_filters=[["docstatus", "=", 1]],
                              order_by="`tabWork Order`.name asc")
    seen_wo: set[str] = set()
    for row in wo_rows:
        name = _text(row.get("name"))
        if name in seen_wo:
            continue
        seen_wo.add(name)
        if not _match_item(_text(row.get("production_item")), identity):
            continue
        key = _text(row.get("sales_order"))
        row_branch = so_branch.get(key, "")
        if wanted_branch and row_branch != wanted_branch:
            continue
        records.append(_node(
            node="WO", document=name, doctype=WO_DOCTYPE,
            date=_text(row.get("actual_end_date") or row.get("planned_start_date")),
            quantity=_number(row.get("qty")), status=_text(row.get("status")),
            sku=sku_text, item_code=_text(row.get("production_item")),
            warehouse=_text(row.get("fg_warehouse")), branch=row_branch,
            link_key=key, link_basis="wo.sales_order",
            linked=bool(key and key in so_branch),
            reason="" if key else "missing_sales_order",
            detail=f"produced_qty={_text(row.get('produced_qty'))}",
        ))

    dn_rows = _fetch_by_keys(c, DN_DOCTYPE, DN_FIELDS, "against_sales_order", so_names,
                             base_filters=[["docstatus", "=", 1]],
                             table="Delivery Note Item",
                             order_by="`tabDelivery Note`.name asc")
    dn_rows += _fetch_by_keys(c, DN_DOCTYPE, DN_FIELDS, "item_code", variants,
                              base_filters=[["docstatus", "=", 1]],
                              table="Delivery Note Item",
                              order_by="`tabDelivery Note`.name asc")
    seen_dn: set[tuple[str, str]] = set()
    dn_tracking: dict[str, str] = {}
    for row in dn_rows:
        name = _text(row.get("name"))
        item_row = _text(row.get("item_row"))
        key_tuple = (name, item_row)
        if key_tuple in seen_dn:
            continue
        seen_dn.add(key_tuple)
        if not _match_item(_text(row.get("item_code")), identity):
            continue
        so_key = _text(row.get("against_sales_order"))
        row_branch = so_branch.get(so_key) or branch_of_customer(row.get("customer")) or ""
        if wanted_branch and row_branch != wanted_branch:
            continue
        tracking = _text(row.get("lr_no"))
        if tracking:
            dn_tracking[tracking] = name
        records.append(_node(
            node="DN", document=name, doctype=DN_DOCTYPE,
            date=_text(row.get("posting_date")), quantity=_number(row.get("qty")),
            status=_text(row.get("status")), sku=sku_text,
            item_code=_text(row.get("item_code")), warehouse=_text(row.get("warehouse")),
            branch=row_branch, link_key=so_key, link_basis="dn_item.against_sales_order",
            linked=bool(so_key and so_key in so_branch),
            reason="" if so_key else "missing_sales_order",
            detail=f"customer={_text(row.get('customer'))}; tracking={tracking}",
        ))

    po_rows = _fetch_by_keys(c, PO_DOCTYPE, PO_FIELDS, "sales_order", so_names,
                             base_filters=[["docstatus", "=", 1]],
                             table="Purchase Order Item",
                             order_by="`tabPurchase Order`.name asc")
    po_rows += _fetch_by_keys(c, PO_DOCTYPE, PO_FIELDS, "item_code", variants,
                              base_filters=[["docstatus", "=", 1]],
                              table="Purchase Order Item",
                              order_by="`tabPurchase Order`.name asc")
    seen_po: set[tuple[str, str]] = set()
    for row in po_rows:
        name = _text(row.get("name"))
        item_row = _text(row.get("item_row"))
        key_tuple = (name, item_row)
        if key_tuple in seen_po:
            continue
        seen_po.add(key_tuple)
        if not _match_item(_text(row.get("item_code")), identity):
            continue
        so_key = _text(row.get("items.sales_order"))
        row_branch = so_branch.get(so_key, "")
        if wanted_branch and row_branch != wanted_branch:
            continue
        records.append(_node(
            node="PO", document=name, doctype=PO_DOCTYPE,
            date=_text(row.get("items.expected_delivery_date") or row.get("transaction_date")),
            quantity=_open_quantity(_number(row.get("qty")), _progress(row.get("received_qty"))),
            status=_text(row.get("status")), sku=sku_text,
            item_code=_text(row.get("item_code")), warehouse=_text(row.get("warehouse")),
            branch=row_branch, link_key=so_key, link_basis="po_item.sales_order",
            linked=bool(so_key and so_key in so_branch),
            reason="" if so_key else "missing_sales_order",
            detail=f"supplier={_text(row.get('supplier'))}",
        ))

    package_keys = list(tracking_numbers or []) + list(dn_tracking)
    package_orders = list(order_numbers or [])
    package_rows = _fetch_packages(c, package_orders, package_keys)
    if package_rows:
        for row in package_rows:
            order_id = _text(row.get("order_id"))
            tracking = _text(row.get("tracking_number"))
            matched_tracking = tracking if tracking in dn_tracking else ""
            warehouse = _text(row.get("warehouse"))
            row_branch = _branch_of_warehouse(warehouse, cfg) if warehouse else ""
            if wanted_branch and row_branch not in ("", wanted_branch):
                continue
            records.append(_node(
                node="PACKAGE", document=_text(row.get("name")), doctype=PACKAGE_DOCTYPE,
                date=_text(row.get("despatch_time") or row.get("updated_date")),
                quantity=None, status=_text(row.get("status")), sku=sku_text,
                item_code="", warehouse=warehouse, branch=row_branch,
                link_key=_text(tracking or order_id),
                link_basis="dn.lr_no=tracking" if matched_tracking else "order_number/tracking",
                linked=bool(matched_tracking or order_id),
                reason="" if (matched_tracking or order_id) else "missing_order_key",
                detail=f"order_id={order_id}; tracking={tracking}",
            ))
    else:
        records.append(_node(
            node="PACKAGE", document="", doctype=PACKAGE_DOCTYPE, date="",
            quantity=None, status="", sku=sku_text, item_code="", warehouse="",
            branch="", link_key="", link_basis="package_requires_order_or_tracking",
            linked=False, reason="no_order_or_tracking_key",
            detail="未提供订单号/tracking；按约束不拉全量 Tongtool Package",
        ))

    frame = _frame(records, CHAIN_COLUMNS)
    meta = dict(source="en_chain", sku=sku_text, canonical_codes=list(codes),
                mapping_status=mapping_status, variants=variants,
                branch=wanted_branch, since=since,
                so_documents=len(so_names), rows=int(len(frame)),
                linked=int(frame["linked"].sum()) if len(frame) else 0,
                unlinked=int((~frame["linked"].astype(bool)).sum()) if len(frame) else 0)
    frame.attrs["meta"] = meta
    return frame


WO_FIELDS = [
    "name", "status", "docstatus", "production_item", "qty", "produced_qty",
    "sales_order", "sales_order_item", "fg_warehouse", "planned_start_date",
    "planned_end_date", "actual_start_date", "actual_end_date",
    "expected_delivery_date", "stock_uom",
]
DN_FIELDS = [
    "name", "status", "docstatus", "customer", "posting_date", "lr_no",
    "items.name as item_row", "items.item_code", "items.qty", "items.warehouse",
    "items.against_sales_order", "items.so_detail", "items.stock_uom",
]
PACKAGE_FIELDS = [
    "name", "package_id", "tracking_number", "status", "warehouse",
    "despatch_time", "updated_date", "order_links.order_id",
    "order_links.erp_order",
]


def _sku_lookup(sku: str, sku_map: pd.DataFrame | None) -> tuple[list[str], str]:
    if sku_map is not None and not sku_map.empty:
        found = sku_map.loc[sku_map["tongtool_sku"] == sku]
        if not found.empty:
            value = found.iloc[0]["item_codes"]
            if isinstance(value, tuple) and value:
                return [str(v) for v in value], str(found.iloc[0]["mapping_status"])
    return [sku], "item_code"


def _match_sales_orders(c: EnLiveClient, codes: Sequence[str], since: str) -> list[dict]:
    accepted = set(codes)
    raw = c.fetch_all(
        SO_DOCTYPE, SO_FIELDS,
        filters=[["docstatus", "=", 1], ["transaction_date", ">=", since]],
        order_by="`tabSales Order`.name asc",
    )
    matched = []
    for row in raw:
        customer_code = _text(row.get("customer_item_code"))
        if (customer_code and customer_code in accepted) or _match_item(
                _text(row.get("item_code")), codes):
            matched.append(row)
    return matched


def _fetch_packages(c: EnLiveClient, order_numbers: Sequence[str],
                    tracking_numbers: Sequence[str]) -> list[dict]:
    """仅按订单号/tracking 精确过滤；没有键就返回空，绝不全量扫描。"""
    rows: list[dict] = []
    for chunk in _chunks(order_numbers):
        rows.extend(c.fetch_all(
            PACKAGE_DOCTYPE, PACKAGE_FIELDS,
            filters=[["Tongtool Package Order", "order_id", "in", chunk]],
            order_by="`tabTongtool Package`.name asc"))
    for chunk in _chunks(tracking_numbers):
        rows.extend(c.fetch_all(
            PACKAGE_DOCTYPE, PACKAGE_FIELDS,
            filters=[["tracking_number", "in", chunk]],
            order_by="`tabTongtool Package`.name asc"))
    return rows


def _node(**fields) -> dict:
    return {column: fields.get(column) for column in CHAIN_COLUMNS}
