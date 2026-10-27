# -*- coding: utf-8 -*-
"""刷新预测（en-demand-forecast-v1）的唯一入口。

只认 ``forecast/CURRENT`` 指向的那个 run，并校验 run_id 与 manifest：
- **预测资格**用预测自己的 ``netting_eligible`` / ``netting_block_reason``；
  它与 ``demand_netting.netting_allowed`` 是两套字段，绝不互相替代。
- 预测按 ``tongtool_sku × canonical_warehouse`` 给出窗口 p50；本层只把它换算成
  桶需求（窗口内按天均摊），不改预测、不跨仓摊派、不给未知单位编单位。
- 不满足资格、缺数量、缺单位、身份一对多的行一律留证据，不写 0。

历史需求仍来自 ``demand_netting``；两边在日期上不得重叠。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import pandas as pd

from .engine import day_instant

SCHEMA_VERSION = "en-demand-forecast-v1"
REQUIRED_COLUMNS = ["tongtool_sku", "canonical_warehouse", "canonical_uom", "lead_days",
                    "window_start", "window_end", "p50", "netting_eligible",
                    "netting_block_reason"]

EVIDENCE_REASON = {
    "ineligible": "forecast_netting_ineligible",
    "quantity": "forecast_quantity_unproven",
    "identity": "forecast_identity_unproven",
    "uom": "forecast_uom_unproven",
    "window": "forecast_window_unproven",
    "overlap": "forecast_overlap_with_actuals",
}


class ForecastContractError(ValueError):
    """预测入口不满足版本/字段契约时抛出，不降级。"""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


@dataclass
class ForecastInput:
    root: Path
    run_id: str
    run_dir: Path
    manifest: dict
    manifest_sha256: str
    windows_path: Path
    windows_sha256: str
    decision_date: str | None
    data_cutoff: str | None
    lead_days: int
    window_start: str | None = None
    window_end: str | None = None
    rows: pd.DataFrame = field(default_factory=pd.DataFrame)


def load_forecast(root: str | Path, *, expected_run_id: str | None = None,
                  lead_days: int = 60) -> ForecastInput:
    root = Path(root)
    current = root / "CURRENT"
    if not current.exists():
        raise ForecastContractError(f"预测 CURRENT 不存在：{current}")
    run_id = current.read_text(encoding="utf-8").strip()
    if not run_id:
        raise ForecastContractError("预测 CURRENT 为空")
    if expected_run_id and run_id != expected_run_id:
        raise ForecastContractError(
            f"预测版本不符：CURRENT={run_id}，要求 {expected_run_id}；拒绝静默换版本")
    run_dir = root / run_id
    manifest_path = run_dir / "forecast_manifest.json"
    windows_path = run_dir / "forecast_sku_warehouse_windows.parquet"
    for path in (manifest_path, windows_path):
        if not path.exists():
            raise ForecastContractError(f"预测产物缺失：{path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ForecastContractError(f"预测 schema 不符：{manifest.get('schema_version')}")
    if manifest.get("run_id") != run_id:
        raise ForecastContractError(
            f"预测 manifest.run_id={manifest.get('run_id')} 与 CURRENT={run_id} 不一致")

    frame = pd.read_parquet(windows_path)
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ForecastContractError(f"预测窗口表缺列：{missing}")
    frame = frame[frame["lead_days"] == lead_days].copy()
    if frame.empty:
        raise ForecastContractError(f"预测窗口表没有 lead_days={lead_days} 的行")

    run_meta = manifest.get("run", {})
    return ForecastInput(
        root=root, run_id=run_id, run_dir=run_dir, manifest=manifest,
        manifest_sha256=_sha256(manifest_path), windows_path=windows_path,
        windows_sha256=_sha256(windows_path),
        decision_date=run_meta.get("decision_date"),
        data_cutoff=run_meta.get("data_cutoff"),
        lead_days=lead_days,
        window_start=str(frame["window_start"].min()),
        window_end=str(frame["window_end"].max()),
        rows=frame,
    )


def _evidence(reason: str, row, detail: str = "", qty=None) -> dict:
    return dict(
        event_id=f"forecast:{row.get('tongtool_sku')}:{row.get('canonical_warehouse')}",
        source_layer="forecast", stage="demand_forecast", sku=None,
        warehouse=row.get("canonical_warehouse"), uom=row.get("canonical_uom"),
        qty=qty, available_date=None, date_confidence=None, scope="in_house",
        identity_confidence=None, warehouse_confidence=None, b_min_eligible=False,
        b_max_eligible=False, batch_key=None, batch_proven=False, document_key=None,
        source_key=None, exclusion_reason=reason, disposition_reason=reason,
        bucket_id=None, counted=False, conditional=True, scenario="any",
        raw_sku=str(row.get("tongtool_sku")), raw_warehouse=str(row.get("canonical_warehouse")),
        exclusion_detail=detail,
    )


def _is_true(value) -> bool:
    """严格布尔判断：字符串 'false'、NaN 都不算 True。"""
    if value is None:
        return False
    if isinstance(value, float) and value != value:
        return False
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1")
    try:
        return bool(value) is True
    except (TypeError, ValueError):
        return False


def forecast_demand_rows(forecast: ForecastInput, sku_map: pd.DataFrame, *,
                         buckets, as_of, skip_keys: set | None = None) -> tuple[list[dict], list[dict], dict]:
    """把预测窗口换算成桶需求。

    ``skip_keys`` 是「已有实际订单覆盖」的键；这些键的预测整体留证据，
    防止实际与预测在同一窗口重复计入。
    """
    lookup = {str(row.tongtool_sku): tuple(row.item_codes)
              for row in sku_map.itertuples(index=False)
              if row.mapping_status == "mapped" and len(row.item_codes) == 1}
    rows: list[dict] = []
    evidence: list[dict] = []
    skipped: dict[str, int] = {}
    total_quantity = Decimal(0)

    def note(reason_key: str, row, detail: str = "", qty=None):
        evidence.append(_evidence(EVIDENCE_REASON[reason_key], row._asdict(), detail, qty))
        skipped[EVIDENCE_REASON[reason_key]] = skipped.get(EVIDENCE_REASON[reason_key], 0) + 1

    for record in forecast.rows.itertuples(index=False):
        eligible = record.netting_eligible
        if not _is_true(eligible):
            note("ineligible", record, detail=str(record.netting_block_reason or ""))
            continue
        quantity = record.p50
        try:
            quantity = float(quantity)
        except (TypeError, ValueError):
            quantity = float("nan")
        if quantity != quantity or quantity < 0:       # NaN / 负值
            note("quantity", record, detail="p50 缺失或为负")
            continue
        start = day_instant(record.window_start, as_of.tzinfo)
        end = day_instant(record.window_end, as_of.tzinfo)
        if start is None or end is None or end <= start:
            note("window", record, detail=f"{record.window_start}..{record.window_end}")
            continue
        items = lookup.get(str(record.tongtool_sku).strip())
        if not items or len(items) != 1:
            note("identity", record, detail="通途 SKU 未映射或一对多")
            continue
        uom = record.canonical_uom
        if not isinstance(uom, str) or not uom.strip() or uom == "unknown":
            note("uom", record, detail=str(uom))
            continue
        item = items[0]
        key = (item, str(record.canonical_warehouse), uom.strip())
        if skip_keys and key in skip_keys:
            note("overlap", record, qty=Decimal(str(round(quantity, 6))))
            continue
        if quantity == 0:
            skipped["forecast_zero"] = skipped.get("forecast_zero", 0) + 1
            continue

        span_days = (end - start).total_seconds() / 86400
        daily = quantity / span_days
        for bucket in buckets:
            overlap_start = max(start, bucket.start)
            overlap_end = min(end, bucket.end)
            if overlap_end <= overlap_start:
                continue
            days = (overlap_end - overlap_start).total_seconds() / 86400
            amount = Decimal(str(round(daily * days, 6)))
            if amount <= 0:
                continue
            rows.append(dict(
                demand_row_id=f"forecast:{record.tongtool_sku}:{record.canonical_warehouse}:"
                              f"{bucket.bucket_id}",
                demand_date=bucket.start.isoformat(),
                canonical_sku=item,
                canonical_warehouse=key[1],
                canonical_uom=key[2],
                quantity=amount,
                demand_source="forecast",
                forecast_run_id=forecast.run_id,
                series="forecast",
            ))
            total_quantity += amount

    meta = dict(
        run_id=forecast.run_id,
        root=str(forecast.root),
        run_dir=str(forecast.run_dir),
        manifest_path=str(forecast.run_dir / "forecast_manifest.json"),
        manifest_sha256=forecast.manifest_sha256,
        windows_path=str(forecast.windows_path),
        windows_sha256=forecast.windows_sha256,
        decision_date=forecast.decision_date,
        data_cutoff=forecast.data_cutoff,
        lead_days=forecast.lead_days,
        window_start=forecast.window_start,
        window_end=forecast.window_end,
        rows_in=int(len(forecast.rows)),
        used_rows=len({row["demand_row_id"].rsplit(":", 1)[0] for row in rows}),
        demand_rows=len(rows),
        demand_quantity=float(total_quantity),
        excluded=skipped,
        allocation_rule="window p50 spread uniformly over window days; bucket gets its overlap days",
        qualification="forecast netting_eligible + unique sku_map identity + proven uom; "
                      "independent from demand_netting.netting_allowed",
        code_git_head=(forecast.manifest.get("code") or {}).get("git_head"),
        generated_at=forecast.manifest.get("generated_at"),
    )
    return rows, evidence, meta


def overlap_keys(demand_rows, window_start: str, tzinfo) -> set:
    """已有实际订单（>= 预测窗口起点）覆盖的键；这些键不再叠加预测。"""
    start = day_instant(window_start, tzinfo)
    if start is None:
        return set()
    keys = set()
    for row in demand_rows:
        instant = day_instant(row.get("demand_date"), tzinfo)
        if instant is not None and instant >= start:
            keys.add((row["canonical_sku"], row["canonical_warehouse"], row["canonical_uom"]))
    return keys
