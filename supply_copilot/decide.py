# -*- coding: utf-8 -*-
"""当天补货决策编排器（只读，不下单）。

数据来源分工（2026-11-23 优先级）：

- **需求**：默认取 D6 包 q95（``supply_copilot.recommend`` 回放读取）。
  若给了 ``forecast_root``，优先用 ``en-demand-forecast-v1`` 的刷新预测
  （同一 SKU×仓×UOM 的 p90，约 90% 情形）替换 D6 需求；预测不可用只警告，不阻塞。
- **供给**：现场读取 live 库存快照（stock parquet/csv）、未履约 SO
  （backlog csv/parquet）、开放 PO（tsv 或 ``purchaseOrderQuery`` JSONL），
  以及库存快照里的 ``WayfairCG-*`` 仓作为 CG 抵扣。
- **回退**：没有可用 live 库存时，退回现有 D6 包 replay（``mode=replay_fallback``）。

为什么是薄封装（任务允许）：
``supply_netting.engine`` / ``supply`` / ``forecast`` 在本分支依赖
``supply_chain_visibility.supply_row`` / ``receipt_buckets``，这两个上游模块
只存在于未合并的分支，直接 import 会 ``ModuleNotFoundError``。所以本模块：

1. 复用 ``supply_netting.demand.load_backlog``（可导入）与
   ``self_fulfilled_demand.canonical`` 的身份/仓库/UOM 口径；
2. 自己按 ``supply_netting`` 的输入文件契约读 stock / PO / backlog；
3. 未来上游模块合回 main 后，可把 ``_supply_facts`` 换成
   ``supply_netting.supply.build_supply_facts``，输出列不变。

**未接入**（必须在报告里明示，不许当作 0）：
- 分桶净额引擎 ``net_all``、批次去重 / 跨阶段同批只计一次、FBA 分配排除、
  退货仓角色排除等 ``supply_netting`` gate —— 本模块只按仓库前缀取本分公司
  可用库存，不做批次级对账；
- 预测窗口的逐桶摊派：本模块只取窗口 p50 合计作为当期需求；
- 提前期 / 需要日重算：需要日、下单日沿用 D6 包计划，标注 ``date_source=d6_pack``；
- 催已有量：沿用 D6 包 ``催已有量``，不按 live 供给重算。

数量语义：未知一律 ``None``（``qty_status`` 记录原因），绝不写 0。
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from pathlib import Path

import pandas as pd

from .paths import load_manifest
from .recommend import recommend
from .live_rules import recalc_dates

BRANCH_POOL = {"USNJ": "美东USNJ", "USTX": "美中USTX", "PL": "波兰"}
POOL_WAREHOUSE = {"美东USNJ": "美东-CENTRADE",
                  "美中USTX": "美中-FZH-DANEEY",
                  "波兰": "波兰-FZHPoland-covers"}
POOL_PREFIX = {"美东USNJ": "美东-", "美中USTX": "美中-", "波兰": "波兰-"}
# live SO 导出（en_sales_orders/so_backlog_all_open_rows.csv）用客户名区分分公司；
# 无法归到本分公司的行保留在证据计数里，不摊派、不写 0。
SO_CUSTOMER_POOL = {"CENTRADE": "美东USNJ", "DANEEY": "美中USTX", "波兰公司": "波兰"}
CG_WAREHOUSE_PREFIX = "WayfairCG"
FORECAST_SCHEMA = "en-demand-forecast-v1"
FORECAST_LEAD_DAYS = 90          # 预测 run 实测只有 60/90/120 三档

D6_REQUIRED = ["product_id", "池", "形态", "UOM", "q95", "C可发供给",
               "en_stock在途+待发", "PO追加(去重)", "SO已下", "CG可调拨抵扣",
               "净需求95", "建议动作", "新补数量", "催已有量", "建议数量",
               "需要日", "下单日", "路线状态"]

COLUMNS = [
    "branch", "sku", "warehouse", "uom", "pool", "physical_form",
    "action", "new_qty", "new_qty_if_conditional_late", "expedite_qty",
    "need_date", "order_date", "date_source",
    "need_date_status", "order_date_status",
    "demand_qty", "d6_q95", "demand_source", "demand_evidence",
    "supply_opening", "supply_intransit", "supply_po", "supply_cg",
    "supply_so", "supply_expected", "supply_independent", "supply_proven",
    "new_qty_if_independent",
    "qty_status", "reason", "warnings",
    "stock_snapshot_at", "stock_sha256", "stock_snapshot_date",
    "forecast_run_id", "forecast_as_of",
    "so_sha256", "po_sha256", "cg_source", "source", "mode",
]


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #
def _num(value):
    """任何未知/非数值 → None；已知的 0 保留为 0。"""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sha(path) -> str:
    if not path:
        return ""
    p = Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else ""


def _file_meta(path) -> dict:
    if not path:
        return dict(path=None, exists=False, sha256="")
    p = Path(path)
    return dict(path=str(p), exists=p.exists(), sha256=_sha(p) if p.exists() else "")


def _read_table(path):
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(p, encoding="utf-8-sig")
    if suffix == ".tsv":
        return pd.read_csv(p, sep="\t", encoding="utf-8-sig")
    if suffix in (".parquet", ".pq"):
        return pd.read_parquet(p)
    raise ValueError(f"不支持的表格格式：{p}")


def parse_as_of(text: str) -> datetime:
    try:
        value = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"as_of 需要 ISO 时间：{exc}") from exc
    if value.tzinfo is None:
        raise ValueError("as_of 必须带时区，例如 2026-11-23T10:47:42+08:00")
    return value


def normalize_branch(branch: str) -> str:
    aliases = {"USNJ": "美东USNJ", "美东": "美东USNJ", "美东USNJ": "美东USNJ",
               "USTX": "美中USTX", "美中": "美中USTX", "美中USTX": "美中USTX",
               "PL": "波兰", "波兰": "波兰"}
    raw = str(branch).strip()
    if raw not in aliases:
        raise ValueError(f"未知分公司：{branch}（可用：USNJ / USTX / PL）")
    return aliases[raw]


def _find(root: Path, *names):
    for name in names:
        for candidate in (root / name, root / "data" / name):
            if candidate.exists():
                return candidate
    return None


def _load_pack_manifest(pack_manifest):
    if isinstance(pack_manifest, dict):
        return pack_manifest
    try:
        return load_manifest(pack_manifest)
    except (SystemExit, OSError, json.JSONDecodeError):
        return {}


# --------------------------------------------------------------------------- #
# live 供给：库存 / PO / SO / CG
# --------------------------------------------------------------------------- #
def _load_stock(path, snapshot_date=None):
    """读取 live 库存快照；列契约与 ``en_stock.parquet`` 一致，额外接受 csv。"""
    frame = _read_table(path)
    required = {"sku", "warehouse_name", "available"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"库存快照缺列：{missing}（文件 {path}）")
    if "snapshot_date" in frame.columns:
        dates = sorted(pd.to_datetime(frame["snapshot_date"]).dt.date.unique())
        chosen = (pd.Timestamp(snapshot_date).date() if snapshot_date else dates[-1])
        if chosen not in dates:
            raise ValueError(f"库存快照没有 {chosen}；可用：{[str(d) for d in dates]}")
        frame = frame[pd.to_datetime(frame["snapshot_date"]).dt.date == chosen].copy()
        snapshot_day = str(chosen)
    else:
        snapshot_day = None
    snapshot_at = None
    if "snapshot_at" in frame.columns and len(frame):
        snapshot_at = str(pd.to_datetime(frame["snapshot_at"]).max())
    elif snapshot_day:
        snapshot_at = snapshot_day
    meta = dict(path=str(path), sha256=_sha(path), rows=int(len(frame)),
                snapshot_date=snapshot_day, snapshot_at=snapshot_at)
    return frame, meta


def _sku_lookup(sku_map: pd.DataFrame) -> dict:
    lookup = {}
    for row in sku_map.itertuples(index=False):
        codes = tuple(row.item_codes)
        if row.mapping_status == "mapped" and len(codes) == 1:
            lookup[str(row.tongtool_sku).strip()] = codes[0]
    return lookup


def _service_policy_uoms(path) -> dict:
    if not path:
        return {}
    frame = pd.read_csv(path, encoding="utf-8-sig")
    if "sku" not in frame.columns or "canonical_uom" not in frame.columns:
        return {}
    return {str(sku).strip(): str(uom).strip()
            for sku, uom in zip(frame["sku"], frame["canonical_uom"])
            if str(sku).strip() and str(uom).strip() and str(uom) != "nan"}


def _supply_facts(stock_df, *, lookup, uom_by_item, warehouse_cfg, branch_wh,
                  branch_prefix):
    """把 live 库存拍平成 ``(sku, 仓, uom)`` 的可用/在途，以及 CG 抵扣。

    返回 (supply_by_key, cg_by_sku, evidence)。未知身份/单位/仓只计数，
    不猜、不并入任何数量。
    """
    from self_fulfilled_demand.canonical import resolve_warehouse_role

    supply = {}
    cg = {}
    evidence = dict(stock_rows=0, identity_missing=0, uom_missing=0,
                    warehouse_out_of_branch=0, return_warehouse_excluded=0)

    def add(store, key, amount):
        store[key] = store.get(key, 0.0) + float(amount)

    for row in stock_df.itertuples(index=False):
        evidence["stock_rows"] += 1
        raw_sku = str(row.sku).strip()
        item = lookup.get(raw_sku)
        if not item:
            evidence["identity_missing"] += 1
            continue
        available = _num(getattr(row, "available", None))
        intransit = _num(getattr(row, "intransit", None))
        raw_wh = str(row.warehouse_name)
        if raw_wh.startswith(CG_WAREHOUSE_PREFIX):
            # CG 可调拨：按 SKU 汇总，跨分公司可调；
            # 是否真的抵到本分公司由 D6 口径决定，这里只提供上界证据。
            if available is not None:
                add(cg, item, available)
            continue
        profile = resolve_warehouse_role(raw_wh, warehouse_cfg)
        if not profile.get("counts_as_available", True):
            evidence["return_warehouse_excluded"] += 1
            continue
        canonical = str(profile["canonical_warehouse"])
        if not (canonical == branch_wh or canonical.startswith(branch_prefix)):
            evidence["warehouse_out_of_branch"] += 1
            continue
        uom = uom_by_item.get(item)
        if not uom:
            evidence["uom_missing"] += 1
            continue
        key = (item, canonical, uom)
        if available is not None:
            add(supply, key + ("opening",), available)
        if intransit is not None:
            add(supply, key + ("intransit",), intransit)
    return supply, cg, evidence


def _po_facts(po_path, po_tongtool_path, *, lookup, uom_by_item, warehouse_cfg,
              branch_wh, branch_prefix):
    """开放 PO（tsv 或 JSONL）→ ``(sku, 仓, uom, on_time?)`` 数量。"""
    from self_fulfilled_demand.canonical import resolve_warehouse_role

    po = {}
    evidence = dict(source=None, rows=0, identity_missing=0, uom_missing=0,
                    warehouse_out_of_branch=0, with_eta=0)
    if not po_path and not po_tongtool_path:
        return po, evidence

    def add(raw_sku, raw_wh, qty, eta):
        evidence["rows"] += 1
        raw_sku = str(raw_sku).strip()
        item = lookup.get(raw_sku) or (raw_sku if raw_sku in uom_by_item else None)
        if not item:
            evidence["identity_missing"] += 1
            return
        uom = uom_by_item.get(item)
        if not uom:
            evidence["uom_missing"] += 1
            return
        profile = resolve_warehouse_role(raw_wh, warehouse_cfg)
        canonical = str(profile["canonical_warehouse"])
        if not (canonical == branch_wh or canonical.startswith(branch_prefix)):
            evidence["warehouse_out_of_branch"] += 1
            return
        if eta:
            evidence["with_eta"] += 1
        key = (item, canonical, uom)
        po[key + ("po",)] = po.get(key + ("po",), 0.0) + float(qty)
        po.setdefault(key + ("detail",), []).append((float(qty), str(eta or "")))

    if po_path:
        path = Path(po_path)
        evidence["source"] = str(path)
        if not path.exists():
            evidence["exists"] = False
        else:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) < 4:
                    continue
                raw_sku, open_qty = parts[1], parts[3]
                warehouse = parts[4] if len(parts) > 4 else ""
                eta = parts[5] if len(parts) > 5 else ""
                try:
                    qty = float(open_qty)
                except ValueError:
                    continue
                if qty > 0:
                    add(raw_sku, warehouse, qty, eta=eta)

    if po_tongtool_path:
        path = Path(po_tongtool_path)
        evidence["source"] = str(path)
        if not path.exists():
            evidence["exists"] = False
            return po, evidence
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            status = str(record.get("status"))
            if status == "4":
                continue
            if status not in ("0", "1", "2"):
                continue
            qty = float(record.get("quantity") or 0) - float(record.get("in_quantity") or 0)
            if qty <= 0:
                continue
            eta = record.get("willArriveDate") or record.get("purchaseArrivalDate")
            add(record.get("goods_sku") or "", record.get("warehouseName") or "", qty, eta=bool(eta))
    return po, evidence


def _so_facts(path, branch):
    """未履约 SO 余额 → ``{(sku, 仓, uom): qty}`` + 逐行交付日明细。"""
    if not path:
        return None, dict(source="none", rows=0, quantity=None)
    if not Path(path).exists():
        return None, dict(source=str(path), exists=False, rows=0, quantity=None)

    frame = _read_table(path)
    branch_wh = POOL_WAREHOUSE[branch]
    result = {}
    evidence = dict(source=str(path), sha256=_sha(path), rows=int(len(frame)))

    def add(key, qty, delivery_date=None):
        result[key] = result.get(key, 0.0) + float(qty)
        result.setdefault(key + ("detail",), []).append(
            (float(qty), str(delivery_date or "")))

    canonical_cols = {"canonical_sku", "canonical_warehouse", "canonical_uom", "quantity"}
    if canonical_cols.issubset(set(frame.columns)):
        for row in frame.itertuples(index=False):
            key = (str(row.canonical_sku), str(row.canonical_warehouse),
                   str(row.canonical_uom))
            qty = _num(getattr(row, "quantity", None))
            if qty is None or qty <= 0:
                continue
            if not (key[1] == branch_wh or key[1].startswith(POOL_PREFIX[branch])):
                continue
            add(key, qty, getattr(row, "delivery_date", ""))
        evidence.update(rows=int(len(frame)), quantity=float(sum(
            v for k, v in result.items() if not isinstance(k, tuple) or k[-1] != "detail")),
            format="canonical", with_delivery_date="delivery_date" in frame.columns)
        return result, evidence

    if {"item_code", "open_qty", "customer"}.issubset(set(frame.columns)):
        unmapped = 0
        for row in frame.itertuples(index=False):
            if SO_CUSTOMER_POOL.get(str(row.customer).strip()) != branch:
                unmapped += 1
                continue
            qty = _num(getattr(row, "open_qty", None))
            uom = str(getattr(row, "uom", "") or "").strip()
            if qty is None or not uom:
                unmapped += 1
                continue
            add((str(row.item_code).strip(), branch_wh, uom), qty,
                getattr(row, "delivery_date", ""))
        evidence.update(rows=int(len(frame)), quantity=float(sum(
            v for k, v in result.items() if not isinstance(k, tuple) or k[-1] != "detail")),
            format="en_sales_orders", excluded_rows=unmapped,
            with_delivery_date="delivery_date" in frame.columns)
        return result, evidence

    raise ValueError(f"SO 文件 {path} 既不是 canonical 四列，也不是 EN 开放 SO 导出")


# --------------------------------------------------------------------------- #
# live 需求：D6 q95 / 刷新预测
# --------------------------------------------------------------------------- #
def _forecast_demand(forecast_root, *, lead_days, lookup, branch_prefix):
    """读取 ``en-demand-forecast-v1`` 窗口 p50，按 SKU×仓×UOM 合计。

    只校验 manifest/schema/窗口哈希，不消费逐桶摊派引擎（未接入）。
    任何契约问题返回 ``(None, warning)``，不阻塞 D6 需求路径。
    """
    if not forecast_root:
        return None, None
    root = Path(forecast_root)
    current = root / "CURRENT"
    if not current.exists():
        return None, f"预测 CURRENT 不存在：{current}"
    try:
        run_id = current.read_text(encoding="utf-8").strip()
        run_dir = root / run_id
        manifest = json.loads((run_dir / "forecast_manifest.json").read_text(encoding="utf-8"))
        windows_path = run_dir / "forecast_sku_warehouse_windows.parquet"
        if manifest.get("schema_version") != FORECAST_SCHEMA:
            raise ValueError(f"预测 schema 不符：{manifest.get('schema_version')}")
        if manifest.get("run_id") != run_id:
            raise ValueError("预测 manifest.run_id 与 CURRENT 不一致")
        declared = [item for item in (manifest.get("outputs") or [])
                    if isinstance(item, dict) and item.get("file") == windows_path.name]
        if len(declared) != 1:
            raise ValueError("预测 manifest 未唯一声明窗口文件")
        actual = _sha(windows_path)
        expected = str(declared[0].get("sha256") or "").lower()
        if not expected or actual.lower() != expected:
            raise ValueError("预测窗口文件哈希与 manifest 不符")
        frame = pd.read_parquet(windows_path)
        if "lead_days" not in frame.columns:
            raise ValueError("预测窗口表缺 lead_days")
        frame = frame[frame["lead_days"] == lead_days]
        if frame.empty:
            raise ValueError(f"预测窗口没有 lead_days={lead_days} 的行")
        required = {"tongtool_sku", "canonical_warehouse", "canonical_uom", "p50",
                    "netting_eligible", "window_start", "window_end"}
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"预测窗口表缺列：{missing}")
    except Exception as exc:                       # 预测不可用绝不阻塞
        return None, f"预测未接入（{exc}）；需求回退 D6 包 q95"

    demand = {}
    p90_rows = 0
    excluded = dict(ineligible=0, identity=0, uom=0, quantity=0, out_of_branch=0)
    for row in frame.itertuples(index=False):
        if not _truthy(row.netting_eligible):
            excluded["ineligible"] += 1
            continue
        item = lookup.get(str(row.tongtool_sku).strip())
        if not item:
            excluded["identity"] += 1
            continue
        uom = str(row.canonical_uom or "").strip()
        if not uom or uom == "unknown":
            excluded["uom"] += 1
            continue
        canonical = str(row.canonical_warehouse)
        if not canonical.startswith(branch_prefix):
            excluded["out_of_branch"] += 1
            continue
        qty = _num(row.p50)
        p90 = _num(getattr(row, "p90", None))
        if p90 is not None and (qty is None or p90 >= qty):
            # 业务默认用 90% 服务档（经验分位，未做覆盖率回测）；不再派生 q95
            qty = p90
            p90_rows += 1
        if qty is None or qty < 0:
            excluded["quantity"] += 1
            continue
        key = (item, canonical, uom)
        demand[key] = demand.get(key, 0.0) + qty

    meta = dict(run_id=run_id, as_of=(manifest.get("run") or {}).get("decision_date"),
                generated_at=manifest.get("generated_at"),
                data_cutoff=(manifest.get("run") or {}).get("data_cutoff"),
                lead_days=lead_days, windows_sha256=actual,
                window_start=str(frame["window_start"].min()),
                window_end=str(frame["window_end"].max()),
                rows_in=int(len(frame)), keys=int(len(demand)), excluded=excluded,
                quantile=("p90_service90" if p90_rows else "p50_fallback"),
                quantile_rows=p90_rows,
                allocation="窗口 p90（约90%情形）合计；p90 为经验分位，未做覆盖率回测")
    return demand, meta


def _truthy(value) -> bool:
    if value is None:
        return False
    if isinstance(value, float) and value != value:
        return False
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1")
    return bool(value) is True


# --------------------------------------------------------------------------- #
# 决策
# --------------------------------------------------------------------------- #
def _decide_live(d6_rows, demand_map, demand_source, supply, cg, so, po,
                 so_known, po_known, *, branch, stock_meta, forecast_meta,
                 file_meta, as_of_dt, lead_by_sku=None):
    wh = POOL_WAREHOUSE[branch]
    as_of_date = as_of_dt.date()
    lead_by_sku = lead_by_sku or {}
    rows = []
    for record in d6_rows.to_dict("records"):
        sku = str(record["product_id"])
        uom = str(record["UOM"]).strip()
        key = (sku, wh, uom)
        needs_date = _date_str(record.get("需要日"))
        order_date = _date_str(record.get("下单日"))
        need_status = _date_status(needs_date, as_of_date)
        order_status = _date_status(order_date, as_of_date)
        date_source = "d6_pack"
        lead_days = lead_by_sku.get(sku)
        if lead_days and needs_date and need_status != "past_due":
            calc = recalc_dates(needs_date, as_of_date, lead_days)
            if calc.get("order_date"):
                order_date = calc["order_date"]
                order_status = calc["status"]
                date_source = "d6_need_minus_d6_lead"
        q95 = _num(record.get("q95"))
        forecast_qty = demand_map.get(key) if demand_map is not None else None
        if demand_source == "forecast_refresh":
            demand_qty = forecast_qty
            if demand_qty is None:
                demand_qty = q95          # 预测未覆盖该键：退回 D6 q95 并标注
        else:
            demand_qty = q95

        opening = supply.get(key + ("opening",))
        intransit = supply.get(key + ("intransit",))
        # SO/PO 源存在时，「该键没有行」是实测 0；源缺失才是未知。
        so_detail = list(so.get(key + ("detail",), [])) if so is not None else []
        po_detail = list(po.get(key + ("detail",), [])) if po is not None else []
        so_qty = sum(q for q, _ in so_detail) if so is not None else None
        po_qty = sum(q for q, _ in po_detail) if po is not None else None
        d6_cg = _num(record.get("CG可调拨抵扣"))
        live_cg = cg.get(sku)
        if live_cg is not None and d6_cg is not None:
            cg_qty = min(live_cg, d6_cg)
            cg_source = "live_capped_by_d6"
        elif live_cg is not None:
            cg_qty = 0.0
            cg_source = "live_no_policy"
        else:
            cg_qty = d6_cg
            cg_source = "d6_pack"

        need_dt = None
        if needs_date:
            try:
                need_dt = datetime.fromisoformat(str(needs_date)[:10]).date()
            except ValueError:
                need_dt = None
        def _on_time(detail):
            total = 0.0
            for qty, eta in detail:
                if not eta or need_dt is None:
                    continue
                try:
                    if datetime.fromisoformat(str(eta)[:10]).date() <= need_dt:
                        total += float(qty)
                except ValueError:
                    continue
            return total

        po_on_time = _on_time(po_detail)
        so_on_time = _on_time(so_detail)

        reasons, warnings = [], []
        missing = []
        if demand_qty is None:
            missing.append("demand")
            reasons.append("需求未知")
        if opening is None:
            missing.append("opening")
            reasons.append("库存快照无该 SKU×仓基准（不写 0）")
        if not so_known:
            missing.append("so")
            reasons.append("SO 未接入")
        if not po_known:
            missing.append("po")
            reasons.append("PO 未接入")

        supply_expected = supply_proven = supply_independent = None
        new_qty = lower = new_qty_if_independent = None
        if not missing:
            total_demand = demand_qty
            # 分公司 SO 是上游生产/交付单，不是终端需求；无批次键时按最大单阶段避免同批重复。
            # 在途/按时 PO 可计入；分公司 SO 无可靠到货日时只作条件，不抵扣主建议
            incoming = max(float(intransit or 0.0), float(po_on_time or 0.0),
                           float(so_on_time or 0.0))
            supply_independent = (opening + (intransit or 0.0) + (po_on_time or 0.0)
                                  + (so_on_time or 0.0) + (cg_qty or 0.0))
            supply_expected = opening + incoming + (cg_qty or 0.0)
            supply_proven = opening + (po_on_time or 0.0) + (so_on_time or 0.0) + (cg_qty or 0.0)
            new_qty_if_independent = max(0, int(math.ceil(total_demand - supply_independent)))
            new_qty = max(0, int(math.ceil(total_demand - supply_expected)))
            lower = max(0, int(math.ceil(total_demand - supply_proven)))
            if new_qty > 0:
                reasons.append(f"需求 {total_demand:g} > 已知供给 {supply_expected:g}")
            else:
                reasons.append(f"已知供给 {supply_expected:g} 覆盖需求 {total_demand:g}")
            if lower > new_qty:
                reasons.append(f"若在途/未确认 SO/迟到 PO 不到，最坏需 {lower}")
            if po_qty and po_qty > po_on_time:
                warnings.append(f"PO {po_qty:g} 中 {po_qty - po_on_time:g} 未证按时（ETA 缺失或晚于需要日）")
            if so_qty:
                warnings.append(f"分公司 SO {so_qty:g} 未加进需求，也不抵扣主建议（无可靠到货日）；若按时到可少补 {so_qty:g}")

        if missing:
            action = "待核"
            qty_status = "unknown_" + "_".join(missing)
        elif new_qty and new_qty > 0:
            action = "补"
            qty_status = "measured"
        else:
            action = "不补"
            qty_status = "measured"

        if demand_source == "forecast_refresh" and forecast_qty is None:
            warnings.append("预测未覆盖该键，需求退回 D6 q95")
        if cg_source == "d6_pack":
            warnings.append("CG 用 D6 包值，不是 live WayfairCG 仓重算")
        if need_status == "past_due":
            warnings.append(f"需要日 {needs_date} 已过（D6 包计划），需按路线交期重排")
        if order_status == "past_due":
            warnings.append(f"下单日 {order_date} 已过（D6 包计划），不可直接执行；需重排")
        if intransit or po_qty:
            warnings.append("在途/PO 未证明按时；最坏情况见 new_qty_if_conditional_late")

        rows.append(dict(
            branch=branch, sku=sku, warehouse=wh, uom=record["UOM"],
            pool=record.get("池"), physical_form=record.get("形态"),
            action=action, new_qty=new_qty, new_qty_if_conditional_late=lower,
            expedite_qty=_num(record.get("催已有量")),
            need_date=needs_date, order_date=order_date, date_source=date_source,
            need_date_status=need_status, order_date_status=order_status,
            demand_qty=None if demand_qty is None else float(demand_qty),
            d6_q95=q95, demand_source=demand_source,
            demand_evidence=("D6 q95" if demand_source == "d6_pack_q95"
                             else "forecast window p90 (~90% service)"),
            supply_opening=_num(opening), supply_intransit=_num(intransit),
            supply_po=_num(po_qty), supply_cg=_num(cg_qty),
            supply_so=_num(so_qty), supply_expected=_num(supply_expected),
            supply_independent=_num(supply_independent),
            supply_proven=_num(supply_proven),
            new_qty_if_independent=new_qty_if_independent,
            qty_status=qty_status,
            reason="；".join(reasons) if reasons else None,
            warnings="；".join(warnings) if warnings else None,
            stock_snapshot_at=stock_meta.get("snapshot_at"),
            stock_snapshot_date=stock_meta.get("snapshot_date"),
            stock_sha256=stock_meta.get("sha256"),
            forecast_run_id=(forecast_meta or {}).get("run_id"),
            forecast_as_of=(forecast_meta or {}).get("as_of"),
            so_sha256=file_meta["so"]["sha256"],
            po_sha256=file_meta["po"]["sha256"],
            cg_source=cg_source,
            source=f"live:{file_meta['stock']['path']}" if file_meta["stock"]["path"]
                   else "live",
            mode="live",
        ))
    return pd.DataFrame(rows, columns=COLUMNS)


def _decide_fallback(frame, *, branch):
    rows = []
    for record in frame.to_dict("records"):
        qty = _num(record.get("新补数量"))
        action = str(record.get("建议动作") or "")
        rows.append(dict(
            branch=branch, sku=str(record["product_id"]), warehouse=POOL_WAREHOUSE[branch],
            uom=record.get("UOM"), pool=record.get("池"), physical_form=record.get("形态"),
            action=action, new_qty=qty, new_qty_if_conditional_late=None,
            expedite_qty=_num(record.get("催已有量")),
            need_date=_date_str(record.get("需要日")),
            order_date=_date_str(record.get("下单日")), date_source="d6_pack",
            demand_qty=_num(record.get("q95")), d6_q95=_num(record.get("q95")),
            demand_source="d6_pack_q95", demand_evidence="D6 q95（回放）",
            supply_opening=_num(record.get("C可发供给")),
            supply_intransit=_num(record.get("en_stock在途+待发")),
            supply_po=_num(record.get("PO追加(去重)")),
            supply_cg=_num(record.get("CG可调拨抵扣")),
            supply_so=_num(record.get("SO已下")),
            supply_expected=None, supply_proven=None,
            qty_status="replay",
            reason=str(record.get("动作原因") or "D6 包回放"),
            warnings="D6 历史回放，未用 live 供给重算",
            stock_snapshot_at=None, stock_snapshot_date=None, stock_sha256="",
            forecast_run_id=None, forecast_as_of=None, so_sha256="", po_sha256="",
            cg_source="d6_pack", source="d6_pack", mode="replay_fallback",
        ))
    return pd.DataFrame(rows, columns=COLUMNS)


def _date_str(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.date().isoformat()
    text = str(value).strip()
    if not text or text.lower() in ("nan", "nat"):
        return None
    # Excel 读入有时变成 "2027-02-16 00:00:00"
    if len(text) >= 19 and text[10] == " " and text[13:19] == "00:00:00":
        return text[:10]
    return text


def _date_status(value, as_of_date):
    """D6 包日期相对决策日：future / past_due / None。"""
    text = _date_str(value)
    if not text:
        return None
    try:
        return "past_due" if datetime.fromisoformat(text).date() < as_of_date else "future"
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #
def run(data_root, branch, as_of, *, stock_path=None, backlog_path=None,
        po_path=None, po_tongtool_path=None, forecast_root=None,
        demand_netting=None, snapshot_date=None, forecast_lead_days=FORECAST_LEAD_DAYS,
        pack_manifest=None):
    """产出 ``(DataFrame, meta)``。只读；无 live 库存时回退 D6 包 replay。"""
    as_of_dt = parse_as_of(as_of)
    pool = normalize_branch(branch)
    root = Path(data_root)

    manifest = _load_pack_manifest(pack_manifest)
    pack_meta = dict(version=manifest.get("version"), as_of=manifest.get("as_of"))

    try:
        d6_rows = recommend(root, pool)
    except SystemExit as exc:                 # recommend 用 SystemExit 报错，这里转成 ValueError
        raise ValueError(str(exc)) from exc
    if d6_rows.empty:
        raise ValueError(f"D6 包没有 {pool} 的行")
    for column in D6_REQUIRED:
        if column not in d6_rows.columns:
            raise ValueError(f"D6 包缺列：{column}")

    stock_meta = dict(path=None, exists=False, sha256="", snapshot_at=None,
                      snapshot_date=None)
    file_meta = dict(stock=_file_meta(stock_path), so=_file_meta(backlog_path),
                     po=_file_meta(po_path or po_tongtool_path))

    live = bool(stock_path) and Path(stock_path).exists()
    if not live:
        frame = _decide_fallback(d6_rows, branch=pool)
        warnings = ["live 库存不可用，退回 D6 包 replay；不是今天的执行建议"]
        meta = dict(mode="replay_fallback", branch=pool, as_of=as_of_dt.isoformat(),
                    pack=pack_meta, stock=stock_meta, forecast=None,
                    so=file_meta["so"], po=file_meta["po"],
                    demand_netting=_file_meta(demand_netting),
                    cg=dict(source="d6_pack"),
                    demand_source="d6_pack_q95", warnings=warnings,
                    executable=False, executable_reasons=["live 库存不可用，仅回放"],
                    totals=dict(rows=int(len(frame)), suggest=int((frame["action"] == "补").sum())),
                    limits=["历史回放，未用 live 库存/SO/PO/CG 重算",
                            "未知数量保持 null，不写 0"])
        return frame, meta

    # ---- live 身份/单位/仓库口径 ----
    from self_fulfilled_demand.canonical import load_sku_map, load_warehouse_config

    sku_map_path = _find(root, "sku_map.tsv")
    if not sku_map_path:
        raise ValueError(f"live 模式需要 sku_map.tsv：{root}")
    sku_map = load_sku_map(sku_map_path)
    lookup = _sku_lookup(sku_map)
    policy_path = _find(root, "service_policy.csv")
    uom_by_item = _service_policy_uoms(policy_path)
    # D6 行的 UOM 是需求口径，补进单位映射（service_policy 缺号时兜底）
    for record in d6_rows.to_dict("records"):
        item = str(record["product_id"])
        uom_by_item.setdefault(item, str(record.get("UOM") or "").strip())
    warehouse_cfg = load_warehouse_config()

    # ---- live 供给 ----
    stock_df, stock_meta = _load_stock(stock_path, snapshot_date)
    stock_meta["sha256"] = file_meta["stock"]["sha256"]
    branch_wh = POOL_WAREHOUSE[pool]
    branch_prefix = POOL_PREFIX[pool]
    supply, cg, supply_evidence = _supply_facts(
        stock_df, lookup=lookup, uom_by_item=uom_by_item,
        warehouse_cfg=warehouse_cfg, branch_wh=branch_wh, branch_prefix=branch_prefix)
    po, po_evidence = _po_facts(po_path, po_tongtool_path, lookup=lookup,
                                uom_by_item=uom_by_item, warehouse_cfg=warehouse_cfg,
                                branch_wh=branch_wh, branch_prefix=branch_prefix)
    po_known = bool((po_path and Path(po_path).exists())
                    or (po_tongtool_path and Path(po_tongtool_path).exists()))
    so, so_evidence = _so_facts(backlog_path, pool)
    so_known = bool(backlog_path and Path(backlog_path).exists())
    if backlog_path and not so_known:
        so_evidence["exists"] = False

    # ---- live 需求：预测优先，D6 q95 兜底 ----
    demand_map, forecast_meta = _forecast_demand(
        forecast_root, lead_days=forecast_lead_days, lookup=lookup,
        branch_prefix=branch_prefix)
    if forecast_meta is None or isinstance(forecast_meta, str):
        forecast_warning = forecast_meta if isinstance(forecast_meta, str) else None
        forecast_meta = None
        demand_source = "d6_pack_q95"
    else:
        forecast_warning = None
        demand_source = "forecast_refresh"

    lead_by_sku = {}
    for rec in d6_rows.to_dict("records"):
        need = _date_str(rec.get("需要日"))
        order = _date_str(rec.get("下单日"))
        if not need or not order:
            continue
        try:
            days = (datetime.fromisoformat(need).date()
                    - datetime.fromisoformat(order).date()).days
        except ValueError:
            continue
        if 0 < days < 400:
            lead_by_sku[str(rec["product_id"])] = days

    frame = _decide_live(
        d6_rows, demand_map, demand_source, supply, cg, so, po,
        so_known, po_known, branch=pool, stock_meta=stock_meta,
        forecast_meta=forecast_meta, file_meta=file_meta, as_of_dt=as_of_dt,
        lead_by_sku=lead_by_sku)

    warnings = []
    if demand_source == "d6_pack_q95":
        warnings.append(forecast_warning or
                        "预测未接入；需求来自 D6 包 q95（as_of "
                        f"{pack_meta.get('as_of')}）")
    if not so_known:
        warnings.append("SO 未接入：相关行 new_qty 为 null（不写 0）")
    if not po_known:
        warnings.append("PO 未接入：相关行 new_qty 为 null（不写 0）")
    elif po_evidence.get("rows") and (
            po_evidence.get("identity_missing", 0)
            + po_evidence.get("uom_missing", 0)
            + po_evidence.get("warehouse_out_of_branch", 0)
            == po_evidence["rows"]):
        warnings.append("PO 文件行没有落到本分公司仓（多为物料仓/未映射 SKU），"
                        "PO 供给按 0 计；请改用通途 purchaseOrderQuery JSONL")
    if policy_path is None:
        warnings.append("service_policy.csv 缺失：单位取自 D6 行，供给单位证据偏弱")
    warnings.append("未接入 supply_netting 的批次去重/跨阶段同批/FBA 分配等 gate；"
                    "库存按分公司仓前缀汇总，可用供给可能与净额引擎有差")
    warnings.append("部分需要日/下单日沿用 D6 包；有交期可算的已按 D6 计划交期倒排（非实际路线交期）")

    stock_age_hours = None
    if stock_meta.get("snapshot_at"):
        try:
            snap = datetime.fromisoformat(str(stock_meta["snapshot_at"]).replace("Z", "+00:00"))
            if snap.tzinfo is not None:
                delta = as_of_dt - snap
            else:
                delta = as_of_dt.replace(tzinfo=None) - snap
            stock_age_hours = round(delta.total_seconds() / 3600, 1)
        except ValueError:
            stock_age_hours = None
    if stock_age_hours is not None and stock_age_hours > 12:
        warnings.append(f"库存快照已过去 {stock_age_hours} 小时，可能不是最新")

    executable_reasons = []
    if stock_age_hours is not None and stock_age_hours > 12:
        executable_reasons.append(f"库存快照超过 12 小时（{stock_age_hours}h）")
    fallback_rows = int(frame["warnings"].fillna("").str.contains("预测未覆盖").sum())
    if fallback_rows:
        executable_reasons.append(f"{fallback_rows} 行预测未覆盖，退回 D6 q95")
    if demand_source != "forecast_refresh":
        executable_reasons.append("需求未刷新：仍为 D6 包 q95（历史时点）")
    if not so_known:
        executable_reasons.append("SO 未接入")
    if not po_known or (po_evidence.get("rows") and
                        po_evidence.get("identity_missing", 0)
                        + po_evidence.get("uom_missing", 0)
                        + po_evidence.get("warehouse_out_of_branch", 0)
                        == po_evidence["rows"]):
        executable_reasons.append("PO 未映射到本分公司仓")
    if (frame["order_date_status"] == "past_due").any():
        executable_reasons.append("存在已过下单日")
    if (frame["cg_source"].isin(["d6_pack", "live_no_policy"])).any():
        executable_reasons.append("CG 抵扣规则未确认（仅 D6 上限/实时封顶）")

    meta = dict(
        mode="live", branch=pool, as_of=as_of_dt.isoformat(),
        demand_source=demand_source, pack=pack_meta,
        stock=stock_meta, forecast=forecast_meta,
        so=so_evidence, po=po_evidence,
        demand_netting=_file_meta(demand_netting),
        cg=dict(source=("live_stock.cg" if cg else "d6_pack"),
                items=int(len(cg)), quantity=round(float(sum(cg.values())), 6)),
        supply_evidence=supply_evidence,
        executable=not executable_reasons,
        executable_reasons=executable_reasons,
        stock_age_hours=stock_age_hours,
        totals=dict(rows=int(len(frame)),
                    suggest=int((frame["action"] == "补").sum()),
                    unknown=int((frame["qty_status"] != "measured").sum()),
                    past_due=int((frame["order_date_status"] == "past_due").sum())),
        warnings=warnings,
        limits=["缺口是 D6 q95/预测窗口总量口径，不是某一天的精确缺货日",
                "在途与无 ETA 的 PO 计入 expected；最坏情况见 "
                "new_qty_if_conditional_late",
                "未履约 SO 按未完成量计入需求；SO 文件缺失时数量保持 null",
                "CG 未提供 live 源时使用 D6 包值（cg_source 标注）",
                "demand_netting 只登记哈希；薄封装未接入其逐桶分摊与资格对账",
                "未知数量/日期保持 null，不写 0"],
    )
    return frame, meta


def to_report(frame, meta, limit=None) -> str:
    """结论 → 为什么 → 证据 → 时点 → 限制。"""
    shown = frame if limit is None else frame.head(limit)
    mode = meta.get("mode")
    lines = [f"# 补货决策 — {meta.get('branch')}", "",
             f"- 模式：**{mode}**；as_of：{meta.get('as_of')}",
             f"- 需求来源：**{meta.get('demand_source')}**"
             + (f"（D6 包 as_of {meta.get('pack', {}).get('as_of')}）"
                if meta.get("demand_source") == "d6_pack_q95" else ""),
             f"- 显示 {len(shown)} / {len(frame)} 行；未静默截断", ""]
    executable = bool(meta.get("executable"))
    reasons = "；".join(meta.get("executable_reasons") or [])
    lines.append(f"- 可执行性：**{'是' if executable else '否'}**"
                 + (f"（{reasons}）" if not executable and reasons else ""))
    stock = meta.get("stock") or {}
    if stock.get("path"):
        lines.append(f"- 供给来源：库存 {stock.get('path')}（snapshot_at "
                     f"{stock.get('snapshot_at') or '未知'}，sha256 "
                     f"{(stock.get('sha256') or '')[:12]}…）")
        so = meta.get("so") or {}
        po = meta.get("po") or {}
        lines.append(f"  - SO：{so.get('source') or '未接入'}（sha256 "
                     f"{(so.get('sha256') or '')[:12] or '—'}）")
        lines.append(f"  - PO：{po.get('source') or '未接入'}；CG："
                     f"{(meta.get('cg') or {}).get('source')}")
    forecast = meta.get("forecast") or {}
    if forecast:
        lines.append(f"- 预测：{forecast.get('run_id')}（as_of {forecast.get('as_of')}，"
                     f"lead {forecast.get('lead_days')}d，sha256 "
                     f"{(forecast.get('windows_sha256') or '')[:12]}…）")
    for warning in meta.get("warnings") or []:
        lines.append(f"- ⚠️ {warning}")
    lines.append("")

    for _, row in shown.iterrows():
        lines += [f"## {row['sku']} · {row['warehouse']} · {row['uom']}", "",
                  f"**结论：{row['action']}**" +
                  (f"；新补 {row['new_qty']}" if row.get("new_qty") is not None else
                   "；数量待核（未知不写 0）") +
                  (f"；催已有 {row['expedite_qty']}"
                   if row.get("expedite_qty") not in (None, 0) else ""), "",
                  f"- 为什么：{row.get('reason') or '—'}",
                  f"- 需求：{row.get('demand_evidence')} = "
                  f"{_fmt(row.get('demand_qty'))}；D6 q95 {_fmt(row.get('d6_q95'))}",
                  f"- 供给：期初 {_fmt(row.get('supply_opening'))}；在途 "
                  f"{_fmt(row.get('supply_intransit'))}；PO {_fmt(row.get('supply_po'))}；"
                  f"SO {_fmt(row.get('supply_so'))}；CG {_fmt(row.get('supply_cg'))}",
                  f"- 最坏（在途/无 ETA PO 迟到）：{_fmt(row.get('new_qty_if_conditional_late'))}",
                  f"- 需要日 {row.get('need_date') or '未知'}；下单日 "
                  f"{row.get('order_date') or '未知'}（{row.get('date_source')}）",
                  f"- 时点：库存快照 {row.get('stock_snapshot_at') or '未知'}；预测 "
                  f"{row.get('forecast_run_id') or '未接入'}", ""]
    if meta.get("limits"):
        lines += ["---", "", "## 限制", ""] + [f"- {item}" for item in meta["limits"]]
    return "\n".join(lines)


def _fmt(value):
    if value is None:
        return "未知"
    try:
        if pd.isna(value):
            return "未知"
    except (TypeError, ValueError):
        pass
    return f"{float(value):g}"
