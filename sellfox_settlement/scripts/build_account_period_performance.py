#!/usr/bin/env python3
"""账期业绩（渠道账号维度）只读核对脚本.

输入（全部只读，不写任何 Google Sheet）:
  - Google Sheet「和运营部共享」/ 渠道账号（20260521起在此维护）
  - Google Sheet「钉钉OA收款费用Amazon多平台&附加费&Tax」
      外币层 YYYYMMDD-YYYYMMDD、人民币层 人民币YYYYMMDD-YYYYMMDD、原始审批明细
  - Google Sheet「附加费&Tax」/ 附加费YYYYMM、TaxYYYYMM（交叉校验）
  - Google Sheet「通途订单YYYYMM」/ 写回…订单 + 写回…FBA订单（带发货日期）
      以及「账号」ws（若已生成，作为“规则后”管道口径）

输出（默认落在 sellfox_settlement/out/，该目录已 gitignore）:
  - account_period_performance_YYYYMM.xlsx
  - account_period_performance_YYYYMM.json（概要，便于跨月对比）
  - .gs_ids.json（按名称解析的 spreadsheet id 缓存）

口径要点:
  - 收入侧有两套基准：
      A 应收金额_人民币（财务对银行到账）
      B 销售额_人民币 - 收款费用累加人民币（= 应收 + 应收账款，剔除预留变动）
  - Tax 为显式开关列：同时输出含税/不含税，不静默二选一。
  - 附加费只单列，不并入业绩主公式。
  - 通途成本拆四桶（绍兴产品/头程/国外二次加工/尾程）+ 海外仓。
  - 成本默认按整月订单；--include-window 时才额外算 04–03 窗口参考。
  - 尾程来自写回「运费」列，7–9 月 EN 预估覆盖率 >99%，列内有标记。

用法:
  uv run python sellfox_settlement/scripts/build_account_period_performance.py --month 202608
  uv run python sellfox_settlement/scripts/build_account_period_performance.py --month 202610
  uv run python sellfox_settlement/scripts/build_account_period_performance.py \
      --period 20260804-20260903 --out-dir sellfox_settlement/out

凭证:
  默认读取 D:/Work/赛狐/Cursor/secrets/gsheets-service-account.json
  可用 --sa-json 或 GSHEETS_SA_JSON 覆盖。绝不把凭证写入输出。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np
import pandas as pd

try:
    import gspread
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2.service_account import Credentials
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "缺少依赖。请用父仓库 venv 运行：D:/Work/赛狐/Cursor/.venv/Scripts/python.exe"
    ) from exc


DEFAULT_SA_JSON = Path(r"D:/Work/赛狐/Cursor/secrets/gsheets-service-account.json")

SHEET_ACCOUNT = "和运营部共享"
SHEET_OA = "钉钉OA收款费用Amazon多平台&附加费&Tax"
SHEET_SURCHARGE_TAX = "附加费&Tax"

WS_ACCOUNT = "渠道账号（20260521起在此维护）"

# 通途写回里的成本列（单位：人民币；均为“行合计 × 系数”后的金额）
COST_PAIRS = {
    "绍兴产品": ["皮壳成本*系数*数量", "绍兴二次加工成本*系数*数量"],
    "国外二次加工": ["二次加工成本*系数*数量"],
    "头程": ["头程运费*数量"],
    "尾程": ["运费"],
    "海外仓": ["海外仓成本*数量"],
}
COST_TOTAL_COL = "订单总成本*系数"
COST_BUCKETS = list(COST_PAIRS.keys())

OA_DETAIL_COLS = [
    "客户退货至平台运费_人民币",
    "退款_人民币",
    "退货服务费_人民币",
    "客户退货至我司运费_人民币",
    "广告费_人民币",
    "佣金_人民币",
    "UPS重新测量包裹费用_人民币",
    "迟发货费用_人民币",
    "折扣促销费用_人民币",
    "平台月租费_人民币",
    "其他费用_人民币",
]
SURCHARGE_DETAIL_COLS = [
    "账号单独费用",
    "账号销售费用附加费",
    "账号头程运费附加费",
    "账号尾程运费附加费",
]


# ---------------------------------------------------------------------------
# 通用
# ---------------------------------------------------------------------------
def retry(fn: Callable[[], Any], label: str, tries: int = 6, base_sleep: float = 1.5) -> Any:
    last: Exception | None = None
    for i in range(tries):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - 需要把 SSL EOF 等一并重试
            last = exc
            if i == tries - 1:
                break
            delay = base_sleep * (i + 1)
            if "429" in str(exc) or "Quota exceeded" in str(exc):
                delay = max(delay, 15.0)  # Sheets 每分钟读配额，短退避无效
            time.sleep(delay)
    raise RuntimeError(f"{label} 读取失败（已重试 {tries} 次）: {last!r}") from last


def to_num(series: pd.Series) -> pd.Series:
    if series.dtype.kind in "if":
        return pd.to_numeric(series, errors="coerce")
    cleaned = (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("￥", "", regex=False)
        .str.replace("¥", "", regex=False)
        .str.replace("%", "", regex=False)
        .str.strip()
        .replace({"": np.nan, "nan": np.nan, "None": np.nan, "nan%": np.nan})
    )
    return pd.to_numeric(cleaned, errors="coerce")


def numeric(df: pd.DataFrame, cols: Iterable[str]) -> pd.DataFrame:
    for col in cols:
        if col in df.columns:
            df[col] = to_num(df[col])
    return df


def month_to_period(month: str) -> tuple[str, pd.Timestamp, pd.Timestamp]:
    """202608 -> (20260804-20260903, 2026-08-04, 2026-09-03)."""
    if not re.fullmatch(r"\d{6}", month):
        raise SystemExit(f"--month 需要 YYYYMM，收到 {month!r}")
    year, mon = int(month[:4]), int(month[4:])
    end_year, end_mon = (year + 1, 1) if mon == 12 else (year, mon + 1)
    start = pd.Timestamp(year=year, month=mon, day=4)
    end = pd.Timestamp(year=end_year, month=end_mon, day=3)
    title = f"{start:%Y%m%d}-{end:%Y%m%d}"
    return title, start, end


def period_to_month(period: str) -> str:
    m = re.fullmatch(r"(\d{4})(\d{2})\d{2}-(\d{4})(\d{2})\d{2}", period)
    if not m:
        raise SystemExit(f"--period 需要 YYYYMMDD-YYYYMMDD，收到 {period!r}")
    return f"{m.group(1)}{m.group(2)}"


def pct(numerator: float, denominator: float) -> float | None:
    if denominator in (0, None) or pd.isna(denominator):
        return None
    return numerator / denominator


# ---------------------------------------------------------------------------
# Google Sheets 访问
# ---------------------------------------------------------------------------
@dataclass
class SheetReader:
    sa_json: Path
    ids_cache: Path
    cache_enabled: bool = True

    def __post_init__(self) -> None:
        info = json.loads(self.sa_json.read_text(encoding="utf-8"))
        self.client = gspread.service_account_from_dict(info)
        creds = Credentials.from_service_account_file(
            str(self.sa_json),
            scopes=[
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/spreadsheets.readonly",
            ],
        )
        self.session = AuthorizedSession(creds)
        if self.ids_cache.exists():
            self.ids: dict[str, str] = json.loads(self.ids_cache.read_text(encoding="utf-8"))
        else:
            self.ids = {}

    def _drive_lookup(self, name: str) -> str:
        escaped = name.replace("'", "\\'")
        query = (
            "mimeType='application/vnd.google-apps.spreadsheet' "
            f"and name='{escaped}' and trashed=false"
        )

        def call() -> str:
            resp = self.session.get(
                "https://www.googleapis.com/drive/v3/files",
                params={"q": query, "fields": "files(id,name)", "pageSize": 10},
                timeout=25,
            )
            resp.raise_for_status()
            files = resp.json().get("files", [])
            if not files:
                raise FileNotFoundError(f"Drive 中找不到表格: {name}")
            return files[0]["id"]

        return retry(call, f"Drive lookup {name}")

    def spreadsheet_id(self, name: str) -> str:
        env_key = {
            SHEET_ACCOUNT: "FZH_GS_ID_ACCOUNT",
            SHEET_OA: "FZH_GS_ID_OA",
            SHEET_SURCHARGE_TAX: "FZH_GS_ID_SURCHARGE_TAX",
        }.get(name)
        import os

        if env_key and os.environ.get(env_key):
            return os.environ[env_key]
        if name not in self.ids:
            self.ids[name] = self._drive_lookup(name)
            if self.cache_enabled:
                self.ids_cache.parent.mkdir(parents=True, exist_ok=True)
                self.ids_cache.write_text(
                    json.dumps(self.ids, ensure_ascii=False, indent=1), encoding="utf-8"
                )
        return self.ids[name]

    def worksheet(self, sheet_name: str, ws_name: str) -> pd.DataFrame:
        sid = self.spreadsheet_id(sheet_name)

        def call() -> pd.DataFrame:
            sh = self.client.open_by_key(sid)
            ws = sh.worksheet(ws_name)
            values = ws.get_all_values()
            if not values:
                return pd.DataFrame()
            width = max(len(r) for r in values)
            header = values[0] + [""] * (width - len(values[0]))
            rows = [r + [""] * (width - len(r)) for r in values[1:]]
            return pd.DataFrame(rows, columns=header)

        return retry(call, f"{sheet_name}/{ws_name}")

    def worksheet_titles(self, sheet_name: str) -> list[str]:
        sid = self.spreadsheet_id(sheet_name)

        def call() -> list[str]:
            return [w.title for w in self.client.open_by_key(sid).worksheets()]

        return retry(call, f"{sheet_name} 工作表列表")


# ---------------------------------------------------------------------------
# 渠道账号别名
# ---------------------------------------------------------------------------
def build_alias_map(acc: pd.DataFrame) -> tuple[dict[str, str], pd.DataFrame, pd.DataFrame]:
    acc = acc.copy()
    acc["渠道账号"] = acc["渠道账号"].fillna("").astype(str).str.strip()
    acc["渠道账号别名"] = (
        acc["渠道账号别名"].fillna("").astype(str).str.replace("，", ",", regex=False)
    )
    records: list[dict[str, str]] = []
    for _, row in acc.iterrows():
        canon = row["渠道账号"]
        if not canon:
            continue
        aliases = [canon] + [
            x.strip() for x in str(row["渠道账号别名"]).split(",") if x.strip()
        ]
        for alias in aliases:
            records.append({"渠道账号": canon, "别名": alias})
    exploded = pd.DataFrame(records, columns=["渠道账号", "别名"]).drop_duplicates(
        subset=["别名"], keep="first"
    )
    mapping = {
        str(r["别名"]).strip().lower(): str(r["渠道账号"]).strip()
        for _, r in exploded.iterrows()
        if str(r["别名"]).strip()
    }
    # 重复别名的原始行（去重前）用于异常清单
    raw = pd.DataFrame(records, columns=["渠道账号", "别名"])
    dups = raw[raw["别名"].duplicated(keep=False)].sort_values("别名")
    return mapping, acc, dups


def map_account(value: Any, mapping: dict[str, str], fallback: str = "UNMATCHED") -> str:
    text = "" if value is None else str(value).strip()
    if text in ("", "nan", "None"):
        return ""
    return mapping.get(text.lower(), fallback)


# ---------------------------------------------------------------------------
# OA / 订单数据整理
# ---------------------------------------------------------------------------
def load_oa(reader: SheetReader, period: str) -> dict[str, pd.DataFrame]:
    base = reader.worksheet(SHEET_OA, period)
    rmb = reader.worksheet(SHEET_OA, f"人民币{period}")
    raw = reader.worksheet(SHEET_OA, f"{period}原始")
    for df, cols in [
        (base, ["应收金额", "销售额", "应收金额_人民币", "销售额_人民币", "收款费用累加人民币"]),
        (rmb, ["收款费用累加人民币", "Tax amount人民币", "附加费累加人民币", *OA_DETAIL_COLS, *SURCHARGE_DETAIL_COLS]),
        (
            raw,
            [
                "应收金额",
                "应收账款",
                "销售额",
                "汇率",
                "返还上期预留金额",
                "本期预留金额",
                "应收金额_人民币",
                "销售额_人民币",
                *OA_DETAIL_COLS,
            ],
        ),
    ]:
        numeric(df, cols)
    return {"base": base, "rmb": rmb, "raw": raw}


def load_surcharge_tax(reader: SheetReader, month: str) -> dict[str, pd.DataFrame | None]:
    suffix = month
    out: dict[str, pd.DataFrame | None] = {"surcharge": None, "tax": None}
    try:
        titles = reader.worksheet_titles(SHEET_SURCHARGE_TAX)
    except Exception:
        return out
    if f"附加费{suffix}" in titles:
        df = reader.worksheet(SHEET_SURCHARGE_TAX, f"附加费{suffix}")
        numeric(df, ["附加费累加人民币", *SURCHARGE_DETAIL_COLS])
        out["surcharge"] = df
    if f"Tax{suffix}" in titles:
        df = reader.worksheet(SHEET_SURCHARGE_TAX, f"Tax{suffix}")
        numeric(df, ["amount", "Tax amount人民币"])
        out["tax"] = df
    return out


def load_orders(reader: SheetReader, month: str) -> dict[str, pd.DataFrame]:
    sheet = f"通途订单{month}"
    year, mon = int(month[:4]), int(month[4:])
    ws_non_fba = f"写回{year}年{mon}月订单"
    ws_fba = f"写回{year}年{mon}月FBA订单"
    non_fba = reader.worksheet(sheet, ws_non_fba)
    fba = reader.worksheet(sheet, ws_fba)
    for df in (non_fba, fba):
        numeric(
            df,
            [c for cols in COST_PAIRS.values() for c in cols]
            + [COST_TOTAL_COL, "产品成本*系数*数量", "发货数量", "售价*汇率"],
        )
    non_fba["_is_fba"] = False
    fba["_is_fba"] = True
    orders = pd.concat([non_fba, fba], ignore_index=True, sort=False)
    pipeline: pd.DataFrame | None = None
    try:
        pipeline = reader.worksheet(sheet, "账号")
        numeric(
            pipeline,
            [c for cols in COST_PAIRS.values() for c in cols]
            + [COST_TOTAL_COL, "售价*汇率", "订单利润*系数"],
        )
    except Exception:
        pipeline = None
    return {"orders": orders, "pipeline": pipeline, "sheet": sheet}


def add_cost_buckets(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    for bucket, cols in COST_PAIRS.items():
        present = [c for c in cols if c in df.columns]
        if present:
            values = df[present].apply(pd.to_numeric, errors="coerce")
            df[f"{prefix}{bucket}"] = values.fillna(0).sum(axis=1)
        else:
            df[f"{prefix}{bucket}"] = 0.0
    df[f"{prefix}成本合计"] = df[[f"{prefix}{b}" for b in COST_BUCKETS]].sum(axis=1)
    return df


def next_month(month: str) -> str:
    year, mon = int(month[:4]), int(month[4:])
    if mon == 12:
        return f"{year + 1}01"
    return f"{year}{mon + 1:02d}"


def load_next_month_non_fba(reader: SheetReader, month: str) -> tuple[pd.DataFrame, str]:
    """读取次月非FBA写回（只用于补齐 04–03 窗口的次月 1–3 日）。"""
    nxt = next_month(month)
    year, mon = int(nxt[:4]), int(nxt[4:])
    try:
        df = reader.worksheet(f"通途订单{nxt}", f"写回{year}年{mon}月订单")
    except Exception as exc:  # 次月表未建是正常状态
        return pd.DataFrame(), f"次月 {nxt} 写回缺失（{type(exc).__name__}）"
    numeric(df, [c for cols in COST_PAIRS.values() for c in cols] + [COST_TOTAL_COL, "产品成本*系数*数量", "发货数量", "售价*汇率"])
    df["_is_fba"] = False
    return df, f"次月 {nxt} 写回已读取 {len(df)} 行"


def aggregate_order_costs(
    orders: pd.DataFrame,
    next_orders: pd.DataFrame,
    mapping: dict[str, str],
    start: pd.Timestamp,
    end: pd.Timestamp,
    include_window: bool = False,
) -> pd.DataFrame:
    df = orders.copy()
    df["_canon"] = df["渠道账号"].apply(lambda x: map_account(x, mapping))
    df["发货日期"] = pd.to_datetime(df.get("发货日期"), errors="coerce")
    is_fba = df.get("_is_fba", pd.Series(False, index=df.index)).fillna(False).astype(bool)
    df = add_cost_buckets(df, "自然月_")

    def agg(frame: pd.DataFrame, suffix: str) -> pd.DataFrame:
        if frame.empty:
            return pd.DataFrame(columns=["_canon", f"订单_行数{suffix}"] + [
                f"订单_{b}{suffix}" for b in COST_BUCKETS
            ] + [f"订单_成本合计{suffix}", f"订单_售价{suffix}", f"订单_尾程{suffix}"]).set_index("_canon")
        g = frame.groupby("_canon", dropna=False).agg(
            **{
                f"订单_行数{suffix}": ("_canon", "size"),
                **{f"订单_{b}{suffix}": (f"自然月_{b}", "sum") for b in COST_BUCKETS},
                f"订单_成本合计{suffix}": ("自然月_成本合计", "sum"),
                f"订单_售价{suffix}": ("售价*汇率", "sum"),
                f"订单_尾程{suffix}": ("自然月_尾程", "sum"),
            }
        )
        return g

    natural = agg(df, "_自然月")
    out = natural.copy()
    if include_window:
        in_window = (df["发货日期"] >= start) & (df["发货日期"] <= end)
        # FBA 按付款/销售日期归月；合并表无日期，窗口成本只能整月计入并标记。
        next_df = next_orders.copy() if next_orders is not None and not next_orders.empty else pd.DataFrame()
        if not next_df.empty:
            next_df["_canon"] = next_df["渠道账号"].apply(lambda x: map_account(x, mapping))
            next_df["发货日期"] = pd.to_datetime(next_df.get("发货日期"), errors="coerce")
            next_df = add_cost_buckets(next_df, "自然月_")
            next_in_window = next_df[(next_df["发货日期"] >= start) & (next_df["发货日期"] <= end)]
        else:
            next_in_window = pd.DataFrame()
        window_non_fba = agg(
            pd.concat([df[(~is_fba) & in_window], next_in_window], ignore_index=True),
            "_窗口非FBA",
        )
        next_month_part = agg(next_in_window, "_下月1-3天")
        fba_full = agg(df[is_fba], "_FBA整月")
        out = natural.join(window_non_fba, how="outer").join(fba_full, how="outer").join(next_month_part, how="outer")
        out = out.loc[:, ~out.columns.duplicated()]

    def col(name: str) -> pd.Series:
        if name in out.columns:
            series = out[name]
            if isinstance(series, pd.DataFrame):
                series = series.iloc[:, 0]
            return series.fillna(0)
        return pd.Series(0.0, index=out.index)

    if include_window:
        for bucket in COST_BUCKETS:
            out[f"订单_窗口_{bucket}"] = col(f"订单_{bucket}_窗口非FBA") + col(f"订单_{bucket}_FBA整月")
        out["订单_窗口_成本合计"] = col("订单_成本合计_窗口非FBA") + col("订单_成本合计_FBA整月")
        out["订单_窗口_售价"] = col("订单_售价_窗口非FBA") + col("订单_售价_FBA整月")
        out["订单_窗口_尾程"] = col("订单_尾程_窗口非FBA") + col("订单_尾程_FBA整月")
        out["订单_窗口_行数"] = col("订单_行数_窗口非FBA") + col("订单_行数_FBA整月")
        out["订单_窗口_非FBA成本"] = col("订单_成本合计_窗口非FBA")
        out["订单_窗口_下月1-3天成本"] = col("订单_成本合计_下月1-3天")
        out["订单_FBA整月成本"] = col("订单_成本合计_FBA整月")
    else:
        # 本轮口径：成本按整月，不单独算 04–03 窗口；窗口列与自然月相同，避免误读。
        for bucket in COST_BUCKETS:
            out[f"订单_窗口_{bucket}"] = out[f"订单_{bucket}_自然月"]
        out["订单_窗口_成本合计"] = out["订单_成本合计_自然月"]
        out["订单_窗口_售价"] = out["订单_售价_自然月"]
        out["订单_窗口_尾程"] = out["订单_尾程_自然月"]
        out["订单_窗口_行数"] = out["订单_行数_自然月"]
        out["订单_窗口_非FBA成本"] = 0.0
        out["订单_窗口_下月1-3天成本"] = 0.0
        out["订单_FBA整月成本"] = 0.0
    fba_flag = df.groupby("_canon", dropna=False)["_is_fba"].any().rename("订单_含FBA")
    platform = (
        df.groupby("_canon", dropna=False)["渠道"]
        .agg(lambda s: ",".join(sorted({str(x).strip() for x in s if str(x).strip()})))
        .rename("订单_平台")
    )
    out = out.join(fba_flag, how="left").join(platform, how="left")
    # 统一列名：自然月
    out = out.rename(
        columns={
            "订单_行数_自然月": "订单_自然月_行数",
            **{f"订单_{b}_自然月": f"订单_自然月_{b}" for b in COST_BUCKETS},
            "订单_成本合计_自然月": "订单_自然月_成本合计",
            "订单_售价_自然月": "订单_自然月_售价",
            "订单_尾程_自然月": "订单_自然月_尾程",
        }
    )
    return out.reset_index().rename(columns={"_canon": "渠道账号"})


def aggregate_pipeline(pipeline: pd.DataFrame | None, mapping: dict[str, str]) -> pd.DataFrame:
    if pipeline is None or pipeline.empty:
        return pd.DataFrame(columns=["渠道账号"])
    df = pipeline.copy()
    df["_canon"] = df["渠道账号"].apply(lambda x: map_account(x, mapping, fallback=str(x).strip()))
    df = add_cost_buckets(df, "管道_")
    agg = df.groupby("_canon", dropna=False).agg(
        **{
            "账号ws_行数": ("_canon", "size"),
            **{f"账号ws_{b}": (f"管道_{b}", "sum") for b in COST_BUCKETS},
            "账号ws_成本合计": ("管道_成本合计", "sum"),
            "账号ws_售价": ("售价*汇率", "sum"),
            "账号ws_尾程": ("管道_尾程", "sum"),
        }
    )
    return agg.reset_index().rename(columns={"_canon": "渠道账号"})


def aggregate_oa(oa: dict[str, pd.DataFrame], mapping: dict[str, str]) -> pd.DataFrame:
    base, rmb, raw = oa["base"], oa["rmb"], oa["raw"]
    for df in (base, rmb, raw):
        df["_canon"] = df["渠道账号"].apply(lambda x: map_account(x, mapping, fallback=str(x).strip()))

    b = base.groupby("_canon", dropna=False).agg(
        OA_销售额_人民币=("销售额_人民币", "sum"),
        OA_应收_人民币=("应收金额_人民币", "sum"),
        OA_收款费用_人民币=("收款费用累加人民币", "sum"),
        OA_行数=("_canon", "size"),
        OA_平台=("选择平台", lambda s: ",".join(sorted({str(x).strip() for x in s if str(x).strip()}))),
        OA_收款归属=("收款归属", lambda s: ",".join(sorted({str(x).strip() for x in s if str(x).strip()}))),
        OA_运营人员=("运营人员", lambda s: ",".join(sorted({str(x).strip() for x in s if str(x).strip()}))),
    )
    r = rmb.groupby("_canon", dropna=False).agg(
        OA_Tax_人民币=("Tax amount人民币", "sum"),
        OA_附加费_人民币=("附加费累加人民币", "sum"),
        **{f"OA_{c}": (c, "sum") for c in OA_DETAIL_COLS + SURCHARGE_DETAIL_COLS},
    )

    raw = raw.copy()
    raw["应收账款_人民币"] = raw["应收账款"].fillna(0) * raw["汇率"].fillna(0)
    raw["_完成"] = raw.get("审批状态", "").astype(str).str.strip().eq("完成")
    raw["_审批中"] = raw.get("审批状态", "").astype(str).str.strip().eq("审批中")
    rr = raw.groupby("_canon", dropna=False).agg(
        OA_应收账款_人民币=("应收账款_人民币", "sum"),
        OA_返还预留=("返还上期预留金额", "sum"),
        OA_本期预留=("本期预留金额", "sum"),
        OA_审批完成行数=("_完成", "sum"),
        OA_审批中行数=("_审批中", "sum"),
        OA_原始行数=("_canon", "size"),
    )
    out = b.join(r, how="outer").join(rr, how="outer").reset_index().rename(columns={"_canon": "渠道账号"})
    out["OA_销售减费用_人民币"] = out["OA_销售额_人民币"].fillna(0) - out["OA_收款费用_人民币"].fillna(0)
    out["OA_预留净变动_人民币"] = out["OA_应收账款_人民币"].fillna(0)
    return out


# ---------------------------------------------------------------------------
# 主表
# ---------------------------------------------------------------------------
def build_main_table(
    acc: pd.DataFrame,
    month: str,
    oa_agg: pd.DataFrame,
    order_agg: pd.DataFrame,
    pipeline_agg: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    staff_col = f"运营人员{month}"
    acc = acc.copy()
    if staff_col not in acc.columns:
        raise SystemExit(f"渠道账号主表缺少列 {staff_col}")
    acc["主表_运营人员"] = acc[staff_col].fillna("").astype(str).str.strip()
    master = acc[["渠道账号", "主表_运营人员"]].drop_duplicates(subset=["渠道账号"], keep="first")
    master["渠道账号"] = master["渠道账号"].astype(str).str.strip()
    master = master[master["渠道账号"] != ""]

    universe = (
        set(master["渠道账号"])
        | set(oa_agg.get("渠道账号", pd.Series(dtype=str)).dropna().astype(str))
        | set(order_agg.get("渠道账号", pd.Series(dtype=str)).dropna().astype(str))
        | set(pipeline_agg.get("渠道账号", pd.Series(dtype=str)).dropna().astype(str))
    )
    universe.discard("")

    main = pd.DataFrame({"渠道账号": sorted(universe)})
    main = main.merge(master, on="渠道账号", how="left")
    main = main.merge(oa_agg, on="渠道账号", how="left")
    main = main.merge(order_agg, on="渠道账号", how="left")
    main = main.merge(pipeline_agg, on="渠道账号", how="left")

    required_defaults = {
        "OA_行数": 0,
        "OA_销售额_人民币": 0,
        "OA_应收_人民币": 0,
        "OA_收款费用_人民币": 0,
        "OA_Tax_人民币": 0,
        "OA_附加费_人民币": 0,
        "OA_应收账款_人民币": 0,
        "OA_销售减费用_人民币": 0,
        "OA_运营人员": "",
        "订单_自然月_行数": 0,
        "订单_自然月_成本合计": 0,
        "订单_窗口_行数": 0,
        "订单_窗口_成本合计": 0,
        "账号ws_行数": 0,
        "账号ws_成本合计": 0,
        "订单_窗口_非FBA成本": 0,
        "订单_FBA整月成本": 0,
        "订单_含FBA": False,
        "订单_平台": "",
        **{f"订单_自然月_{b}": 0 for b in COST_BUCKETS},
        **{f"订单_窗口_{b}": 0 for b in COST_BUCKETS},
        **{f"账号ws_{b}": 0 for b in COST_BUCKETS},
    }
    for col, default in required_defaults.items():
        if col not in main.columns:
            main[col] = default
    for col in required_defaults:
        if col not in ("OA_运营人员", "订单_平台"):
            main[col] = main[col].fillna(0)
    main["OA_运营人员"] = main["OA_运营人员"].fillna("").astype(str)
    main["订单_平台"] = main["订单_平台"].fillna("").astype(str)

    main["有OA"] = main["OA_行数"].fillna(0).gt(0)
    main["有订单"] = main["订单_自然月_行数"].fillna(0).gt(0) | main["订单_窗口_行数"].fillna(0).gt(0)
    main["有管道输出"] = main["账号ws_行数"].fillna(0).gt(0)
    main["在主表"] = main["主表_运营人员"].notna()

    def status(row: pd.Series) -> str:
        if str(row["渠道账号"]).strip() == "UNMATCHED":
            return "未匹配别名（不得并入真实账号）"
        has_oa, has_order, has_pipe, in_master = row["有OA"], row["有订单"], row["有管道输出"], row["在主表"]
        if has_oa and has_order:
            return "双边"
        if has_oa and not has_order:
            return "仅OA（无通途成本）"
        if has_order and not has_oa:
            return "仅订单（无可收/应收）"
        if in_master:
            return "仅主表（本月无OA无发货）"
        return "未落主表"

    main["账号状态"] = main.apply(status, axis=1)
    main["OA运营人员"] = main.get("OA_运营人员", "")
    main["运营人员"] = main["OA运营人员"].where(main["OA运营人员"].astype(str) != "", main["主表_运营人员"].fillna(""))
    main["运营人员数"] = main["运营人员"].astype(str).apply(
        lambda s: len({x.strip() for x in s.split(",") if x.strip()})
    )
    main["运营人员不一致"] = (
        main["OA运营人员"].fillna("").astype(str).str.strip().ne("")
        & main["主表_运营人员"].fillna("").astype(str).str.strip().ne("")
        & (main["OA运营人员"].astype(str).str.strip() != main["主表_运营人员"].astype(str).str.strip())
    )

    # 主口径：写回（202608–202610 均未建 -特殊规则 副本，即不含 1.7.0）。
    # 「账号」ws 是历史上某次管道运行的快照，与当前写回不一致（202609 差约 -55.6 万），仅作对照。
    pipeline_cost = main["账号ws_成本合计"].fillna(0)
    raw_cost = main["订单_自然月_成本合计"].fillna(0)
    main["成本_合计"] = raw_cost
    main["成本口径"] = "写回（规则前；默认不使用 1.7.0）"
    main["成本_窗口"] = main["订单_窗口_成本合计"].fillna(0)
    main["窗口成本口径"] = "写回（按发货日期 04–03 窗口；FBA 无日期按整月计入）"
    main["对照_账号ws成本"] = pipeline_cost
    main["对照_账号ws减写回"] = np.where(main["有管道输出"], pipeline_cost - raw_cost, np.nan)
    main["对照_账号ws状态"] = np.where(main["有管道输出"], "存在（仅对照）", "缺失")

    for bucket in COST_BUCKETS:
        main[f"成本_{bucket}"] = main[f"订单_自然月_{bucket}"].fillna(0)

    tax = main["OA_Tax_人民币"].fillna(0)
    surcharge = main["OA_附加费_人民币"].fillna(0)
    cost = main["成本_合计"]
    recv = main["OA_应收_人民币"].fillna(0)
    sales_net = main["OA_销售减费用_人民币"].fillna(0)
    cost_win = main["成本_窗口"]

    # 四套基础业绩（应收/剔预留 × 不含税/含税）+ 附加费另列/扣减两版
    main["业绩_应收_不含税_不扣附加费"] = recv - cost
    main["业绩_应收_不含税_扣附加费"] = recv - cost - surcharge
    main["业绩_应收_含税_不扣附加费"] = recv - cost - tax
    main["业绩_应收_含税_扣附加费"] = recv - cost - tax - surcharge
    main["业绩_剔预留_不含税_不扣附加费"] = sales_net - cost
    main["业绩_剔预留_不含税_扣附加费"] = sales_net - cost - surcharge
    main["业绩_剔预留_含税_不扣附加费"] = sales_net - cost - tax
    main["业绩_剔预留_含税_扣附加费"] = sales_net - cost - tax - surcharge
    main["业绩_应收_不含税_不扣附加费_窗口"] = recv - cost_win
    main["业绩_剔预留_不含税_不扣附加费_窗口"] = sales_net - cost_win
    main["Tax占销售额"] = [
        pct(t, s) for t, s in zip(tax, main["OA_销售额_人民币"].fillna(0))
    ]
    main["附加费占销售额"] = [
        pct(t, s) for t, s in zip(surcharge, main["OA_销售额_人民币"].fillna(0))
    ]

    # 平台分类（OA 优先；订单-only 用通途「渠道」推断）
    def platform_class(row: pd.Series) -> str:
        oa_platform = row.get("OA_平台", "")
        order_platform = row.get("订单_平台", "")
        oa_platform = "" if pd.isna(oa_platform) else str(oa_platform)
        order_platform = "" if pd.isna(order_platform) else str(order_platform)
        if "亚马逊" in oa_platform or "亚马逊" in order_platform or "amazon" in order_platform.lower():
            return "Amazon"
        if oa_platform.strip() or order_platform.strip():
            return "非Amazon"
        return "未分类"

    main["平台分类"] = main.apply(platform_class, axis=1)
    main["规则版本"] = "无（默认不使用 1.7.0）"
    main["成本来源"] = "写回（非FBA+FBA）"
    main["期间口径"] = "收入=OA 04–03 账期；成本=自然月/同窗口两版并列"
    main["尾程来源"] = "EN预估（写回「运费」列）；未导入承运商实际账单"
    main["窗口成本构成"] = "非FBA按发货日期窗口 + FBA整月（FBA写回无发货日期）"
    main["退货冲成本"] = "未实现（OA退款已在费用内；COGS未按可售性冲回）"

    main = main.sort_values(
        ["账号状态", "OA_销售额_人民币", "订单_自然月_售价"], ascending=[True, False, False], na_position="last"
    )
    dups = main.columns[main.columns.duplicated()].tolist()
    if dups:
        print(f"[WARN] 主表存在重复列，已保留首列: {dups}")
        main = main.loc[:, ~main.columns.duplicated()].copy()
    return main, master


def build_checks(
    oa: dict[str, pd.DataFrame],
    surcharge_tax: dict[str, pd.DataFrame | None],
    main: pd.DataFrame,
    orders: pd.DataFrame,
    mapping: dict[str, str],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    def add(check: str, expected: Any, actual: Any, note: str = "") -> None:
        if isinstance(expected, (int, float, np.integer, np.floating)) and isinstance(
            actual, (int, float, np.integer, np.floating)
        ):
            diff = float(actual) - float(expected)
            rows.append(
                {
                    "检查项": check,
                    "期望/左": round(float(expected), 4),
                    "实际/右": round(float(actual), 4),
                    "差额": round(diff, 4),
                    "通过": abs(diff) <= 0.02,
                    "说明": note,
                }
            )
        else:
            rows.append(
                {
                    "检查项": check,
                    "期望/左": expected,
                    "实际/右": actual,
                    "差额": "",
                    "通过": expected == actual,
                    "说明": note,
                }
            )

    base, rmb, raw = oa["base"], oa["rmb"], oa["raw"]
    raw_recv_rmb = float((raw["应收账款"].fillna(0) * raw["汇率"].fillna(0)).sum())
    add(
        "OA：销售额−收款费用 = 应收 + 应收账款",
        round(float(base["销售额_人民币"].sum() - base["收款费用累加人民币"].sum()), 2),
        round(float(base["应收金额_人民币"].sum()) + raw_recv_rmb, 2),
        "口径 B 的会计基础",
    )
    add(
        "OA 原始层：应收账款×汇率",
        round(raw_recv_rmb, 2),
        round(
            float(base["销售额_人民币"].sum() - base["收款费用累加人民币"].sum())
            - float(base["应收金额_人民币"].sum()),
            2,
        ),
        "本期预留−返还上期预留",
    )
    add(
        "OA 人民币层：11项费用合计 ≈ 收款费用累加",
        round(float(rmb["收款费用累加人民币"].sum()), 2),
        round(float(rmb[OA_DETAIL_COLS].sum().sum()), 2),
        "max 行级差 <0.01",
    )
    add(
        "OA 人民币层：收款费用累加 = 外币层",
        round(float(base["收款费用累加人民币"].sum()), 2),
        round(float(rmb["收款费用累加人民币"].sum()), 2),
    )
    # 附加费：人民币层 vs 独立附加费表
    if surcharge_tax.get("surcharge") is not None:
        add(
            "附加费：人民币层 = 独立附加费表",
            round(float(rmb["附加费累加人民币"].sum()), 2),
            round(float(surcharge_tax["surcharge"]["附加费累加人民币"].sum()), 2),
        )
        comp = surcharge_tax["surcharge"][SURCHARGE_DETAIL_COLS].sum().sum()
        add(
            "附加费：累加 = 4个分项之和",
            round(float(surcharge_tax["surcharge"]["附加费累加人民币"].sum()), 2),
            round(float(comp), 2),
        )
    else:
        add("附加费：独立表存在", "存在", "缺失", "无法交叉校验")
    if surcharge_tax.get("tax") is not None:
        add(
            "Tax：人民币层 = 独立Tax表",
            round(float(rmb["Tax amount人民币"].sum()), 2),
            round(float(surcharge_tax["tax"]["Tax amount人民币"].sum()), 2),
        )
    else:
        add("Tax：独立表存在", "存在", "缺失", "无法交叉校验")

    # 成本恒等式（写回）
    df = orders.copy()
    numeric(df, [COST_TOTAL_COL, "产品成本*系数*数量", *[c for cols in COST_PAIRS.values() for c in cols]])
    df = add_cost_buckets(df, "校验_")
    add(
        "写回：四桶+海外仓 = 订单总成本*系数",
        round(float(df[COST_TOTAL_COL].fillna(0).sum()), 2),
        round(float(df["校验_成本合计"].sum()), 2),
        "差异 >0.02 说明列映射或空值有问题",
    )
    row_diff = (df["校验_成本合计"] - df[COST_TOTAL_COL].fillna(0)).abs()
    add(
        "逐行：五桶之和 = 订单总成本*系数",
        0,
        round(float(row_diff.max()), 4),
        f"违例>0.01 的行数: {int((row_diff > 0.01).sum())}",
    )
    add(
        "写回：产品成本*系数*数量 = 绍兴产品 + 国外二次加工",
        round(float(df["产品成本*系数*数量"].fillna(0).sum()), 2),
        round(float((df["校验_绍兴产品"] + df["校验_国外二次加工"]).sum()), 2),
    )
    # 窗口覆盖：非FBA 有发货日期；FBA 写回是月度汇总，无日期
    df["_is_fba"] = df.get("_is_fba", False).fillna(False).astype(bool)
    dt = pd.to_datetime(df.get("发货日期"), errors="coerce")
    in_window = ((dt >= start) & (dt <= end)).sum()
    non_fba = df[~df["_is_fba"]]
    fba = df[df["_is_fba"]]
    add(
        "写回非FBA：发货日期齐全",
        len(non_fba),
        int(pd.to_datetime(non_fba.get("发货日期"), errors="coerce").notna().sum()),
        f"窗口 {start.date()}~{end.date()} 命中 {int(in_window)} 行（含FBA需另算）",
    )
    fba_dated = int(pd.to_datetime(fba.get("发货日期"), errors="coerce").notna().sum())
    add(
        "写回FBA：无发货日期（月度汇总）",
        "0 行有日期（共 %d 行）" % len(fba),
        f"{fba_dated} 行有日期（共 {len(fba)} 行）",
        "窗口成本按整月FBA计入，列内有标记；精确窗口需另取 FBA 订单级明细",
    )

    # 主表对账
    add("主表：账号数", len(main), main["渠道账号"].nunique())
    add("主表：订单成本合计（去重后）", round(float(df["校验_成本合计"].sum()), 2), round(float(main["订单_自然月_成本合计"].sum()), 2))
    add("主表：OA应收合计", round(float(base["应收金额_人民币"].sum()), 2), round(float(main["OA_应收_人民币"].sum()), 2))

    # 逐账号恒等式（防止账号间正负抵消掩盖单账号错误）
    oa_rows = main[main["OA_行数"].fillna(0).gt(0)]
    if len(oa_rows):
        d_identity = (
            oa_rows["OA_销售减费用_人民币"]
            - (oa_rows["OA_应收_人民币"] + oa_rows["OA_应收账款_人民币"])
        ).abs()
        add(
            "逐账号：销售减费用 = 应收 + 应收账款",
            0,
            round(float(d_identity.max()), 4),
            f"违例>0.01 的账号数: {int((d_identity > 0.01).sum())}",
        )
    d_bucket = (
        main["成本_合计"]
        - sum(main[f"成本_{b}"].fillna(0) for b in COST_BUCKETS)
    ).abs()
    add(
        "逐账号：成本合计 = 五桶之和",
        0,
        round(float(d_bucket.max()), 4),
        f"违例>0.01 的账号数: {int((d_bucket > 0.01).sum())}",
    )
    return pd.DataFrame(rows)


def build_unmatched_detail(orders: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    df = orders.copy()
    if df.empty:
        return pd.DataFrame(columns=["渠道账号(原始)", "行数", "成本合计", "平台", "订单号样例"])
    df["_canon"] = df["渠道账号"].apply(lambda x: map_account(x, mapping))
    df = df[df["_canon"] == "UNMATCHED"]
    if df.empty:
        return pd.DataFrame(columns=["渠道账号(原始)", "行数", "成本合计", "平台", "订单号样例"])
    df = add_cost_buckets(df, "未匹配_")
    g = df.groupby("渠道账号", dropna=False).agg(
        行数=("_canon", "size"),
        成本合计=("未匹配_成本合计", "sum"),
        平台=("渠道", lambda s: ",".join(sorted({str(x).strip() for x in s if str(x).strip()}))),
        订单号样例=("订单号", lambda s: ",".join(list(dict.fromkeys(str(x) for x in s))[:3])),
    ).reset_index().rename(columns={"渠道账号": "渠道账号(原始)"})
    return g.sort_values("成本合计", ascending=False)


def build_exceptions(main: pd.DataFrame, duplicates: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in main[main["账号状态"] != "双边"].iterrows():
        rows.append(
            {
                "类型": row["账号状态"],
                "渠道账号": row["渠道账号"],
                "运营人员": row["运营人员"],
                "OA应收_人民币": row.get("OA_应收_人民币", 0),
                "订单成本_人民币": row.get("订单_自然月_成本合计", 0),
                "说明": "单边/未匹配账号：收入或成本只有一侧，业绩不可直接当真实经营结果",
            }
        )
    for _, row in duplicates.head(20).iterrows():
        rows.append(
            {
                "类型": "主表别名重复（已保留首条）",
                "渠道账号": row["渠道账号"],
                "运营人员": "",
                "OA应收_人民币": 0,
                "订单成本_人民币": 0,
                "说明": f"别名 {row['别名']}",
            }
        )
    return pd.DataFrame(rows)


def build_readiness(
    month: str,
    oa: dict[str, pd.DataFrame],
    surcharge_tax: dict[str, pd.DataFrame | None],
    orders: dict[str, pd.DataFrame],
    pipeline: pd.DataFrame | None,
    start: pd.Timestamp,
    end: pd.Timestamp,
    next_note: str = "",
) -> pd.DataFrame:
    rows = []
    raw = oa["raw"]
    status = raw.get("审批状态", pd.Series(dtype=str)).astype(str).str.strip()
    rows.append(
        {
            "输入": "OA 外币层（应收/销售额）",
            "状态": "就绪" if len(oa["base"]) else "缺失",
            "行数": len(oa["base"]),
            "说明": f"账期 {start.date()}~{end.date()}",
        }
    )
    rows.append(
        {
            "输入": "OA 人民币层（费用/Tax/附加费）",
            "状态": "就绪" if len(oa["rmb"]) else "缺失",
            "行数": len(oa["rmb"]),
            "说明": "",
        }
    )
    rows.append(
        {
            "输入": "OA 原始审批明细",
            "状态": "就绪" if len(raw) else "缺失",
            "行数": len(raw),
            "说明": f"完成 {int((status == '完成').sum())} / 审批中 {int((status == '审批中').sum())}；审批中未定稿会影响应收",
        }
    )
    sur = surcharge_tax.get("surcharge")
    tax = surcharge_tax.get("tax")
    rows.append(
        {
            "输入": "附加费（独立表）",
            "状态": "就绪" if sur is not None and len(sur) else "缺失/为空",
            "行数": 0 if sur is None else len(sur),
            "说明": "若为 0，需确认是“本月无附加费”还是“尚未录入”",
        }
    )
    rows.append(
        {
            "输入": "Tax（独立表）",
            "状态": "就绪" if tax is not None and len(tax) else "缺失/为空",
            "行数": 0 if tax is None else len(tax),
            "说明": "",
        }
    )
    df_orders = orders["orders"]
    dt = pd.to_datetime(df_orders.get("发货日期"), errors="coerce")
    rows.append(
        {
            "输入": "通途写回（非FBA+FBA，带发货日期）",
            "状态": "就绪" if len(df_orders) else "缺失",
            "行数": len(df_orders),
            "说明": f"日期 {dt.min().date() if dt.notna().any() else '-'} ~ {dt.max().date() if dt.notna().any() else '-'}",
        }
    )
    rows.append(
        {
            "输入": "「账号」ws（历史管道快照，仅对照）",
            "状态": "存在（仅对照）" if pipeline is not None and len(pipeline) else "缺失",
            "行数": 0 if pipeline is None else len(pipeline),
            "说明": "实测与写回不一致（疑似旧快照），主口径不使用；主成本用写回",
        }
    )
    rows.append(
        {
            "输入": "次月 1–3 日非FBA发货（补齐 04–03 窗口）",
            "状态": "不适用（本轮按整月）" if "不适用" in next_note else ("就绪" if "已读取" in next_note else "缺失（窗口成本不含次月1–3日）"),
            "行数": "",
            "说明": next_note,
        }
    )
    rows.append(
        {
            "输入": "尾程实际账单",
            "状态": "未接入",
            "行数": 0,
            "说明": "当前「运费」列来自 EN 预估，不是承运商实际；不得标成实际值",
        }
    )
    rows.append(
        {
            "输入": "退货可售性与 COGS 冲回",
            "状态": "未实现",
            "行数": 0,
            "说明": "需 FBA/FBM 退货报告 detailedDisposition + status；当前 OA 退款只在费用内",
        }
    )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------
def safe_excel(path: Path, sheets: dict[str, pd.DataFrame]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, df in sheets.items():
            out = df.loc[:, ~df.columns.duplicated()].copy()
            for col in out.columns:
                if out[col].dtype == object:
                    out[col] = out[col].map(lambda x: "" if pd.isna(x) else x)
            out.to_excel(writer, sheet_name=name[:31], index=False)


def json_safe(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="账期业绩（渠道账号维度）只读核对")
    parser.add_argument("--month", help="YYYYMM，例如 202608")
    parser.add_argument("--period", help="显式账期窗口 YYYYMMDD-YYYYMMDD，例如 20260804-20260903")
    parser.add_argument("--out-dir", default="sellfox_settlement/out")
    parser.add_argument("--sa-json", default=str(DEFAULT_SA_JSON))
    parser.add_argument("--ids-cache", default="sellfox_settlement/out/.gs_ids.json")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只读计算并打印概要，不落本地 xlsx/json（Google Sheet 始终不写）",
    )
    parser.add_argument(
        "--include-window",
        action="store_true",
        help="额外计算 04–03 窗口成本（默认不算；本轮口径是成本按整月）",
    )
    parser.add_argument(
        "--active-only",
        action="store_true",
        help="主表只保留有 OA 或有发货的账号（默认保留主表 0 行，便于核对账号全集）",
    )
    args = parser.parse_args()

    if not args.month and not args.period:
        parser.error("需要 --month 或 --period")
    if args.period:
        period = args.period
        month = period_to_month(period)
        if args.month and args.month != month:
            parser.error(f"--month {args.month} 与 --period 推导的 {month} 不一致")
    else:
        month = args.month
        period, _, _ = month_to_period(month)
    _, start, end = month_to_period(month)
    if args.period:
        m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})-(\d{4})(\d{2})(\d{2})", period)
        assert m
        start = pd.Timestamp(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        end = pd.Timestamp(int(m.group(4)), int(m.group(5)), int(m.group(6)))

    out_dir = Path(args.out_dir)
    sa_json = Path(args.sa_json)
    if not sa_json.exists():
        raise SystemExit(f"凭证不存在: {sa_json}")
    reader = SheetReader(sa_json=sa_json, ids_cache=Path(args.ids_cache), cache_enabled=not args.dry_run)

    print(f"[1/6] 读取渠道账号主表 + 解析别名 … ({month})")
    acc = reader.worksheet(SHEET_ACCOUNT, WS_ACCOUNT)
    mapping, acc_clean, duplicates = build_alias_map(acc)

    print(f"[2/6] 读取 OA 账期 {period} …")
    oa = load_oa(reader, period)
    surcharge_tax = load_surcharge_tax(reader, month)

    print(f"[3/6] 读取通途订单 {month} 写回 + 账号 ws …")
    orders = load_orders(reader, month)
    if args.include_window:
        next_orders, next_note = load_next_month_non_fba(reader, month)
    else:
        next_orders, next_note = pd.DataFrame(), "不适用（本轮按整月）"

    print("[4/6] 聚合 …")
    oa_agg = aggregate_oa(oa, mapping)
    order_agg = aggregate_order_costs(
        orders["orders"], next_orders, mapping, start, end, include_window=args.include_window
    )
    pipeline_agg = aggregate_pipeline(orders["pipeline"], mapping)
    main_df, master = build_main_table(acc_clean, month, oa_agg, order_agg, pipeline_agg)
    if not args.include_window:
        main_df["窗口成本口径"] = "未单独计算（本轮按整月）"
        main_df["窗口成本构成"] = "与自然月相同（本轮不做 04–03 二次过滤）"
    master_only_count = int((main_df["账号状态"] == "仅主表（本月无OA无发货）").sum())
    if args.active_only:
        main_df = main_df[main_df["账号状态"] != "仅主表（本月无OA无发货）"].copy()
    checks = build_checks(oa, surcharge_tax, main_df, orders["orders"], mapping, start, end)
    exceptions = build_exceptions(main_df, duplicates)
    unmatched_detail = build_unmatched_detail(orders["orders"], mapping)
    readiness = build_readiness(month, oa, surcharge_tax, orders, orders["pipeline"], start, end, next_note)

    print("[5/6] 生成说明页 …")
    effective_cost_basis = main_df["成本口径"].value_counts().to_dict()

    staff_cols = [
        "OA_应收_人民币",
        "OA_销售减费用_人民币",
        "OA_销售额_人民币",
        "OA_收款费用_人民币",
        "OA_Tax_人民币",
        "OA_附加费_人民币",
        "成本_合计",
        "成本_窗口",
        "业绩_应收_不含税_不扣附加费",
        "业绩_应收_不含税_扣附加费",
        "业绩_应收_含税_不扣附加费",
        "业绩_应收_含税_扣附加费",
        "业绩_剔预留_不含税_不扣附加费",
        "业绩_剔预留_不含税_扣附加费",
        "业绩_剔预留_含税_不扣附加费",
        "业绩_剔预留_含税_扣附加费",
        "业绩_应收_不含税_不扣附加费_窗口",
        "业绩_剔预留_不含税_不扣附加费_窗口",
    ]
    staff_summary = (
        main_df.groupby("运营人员", dropna=False)
        .agg(**{c: (c, "sum") for c in staff_cols}, 账号数=("渠道账号", "nunique"))
        .reset_index()
        .sort_values("OA_销售减费用_人民币", ascending=False)
    )
    notes = pd.DataFrame(
        [
            ["生成时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            ["账期", f"{start.date()} ~ {end.date()}"],
            ["收入基准 A", "OA 应收金额_人民币（财务可对银行到账）"],
            ["收入基准 B", "OA 销售额_人民币 − 收款费用累加人民币（= 应收 + 应收账款，剔除预留变动）"],
            ["业绩公式", "收入基准 − 通途成本（绍兴产品+头程+国外二次加工+尾程+海外仓）"],
            ["Tax", "同时输出含税/不含税两列；销售额是否含税未获财务最终确认（比率与 VAT/销售税一致，倾向含税）"],
            ["成本口径", "主口径=写回（非FBA+FBA，规则前）；默认不使用 1.7.0（即使存在 -特殊规则 副本）。「账号」ws 仅作对照（实测与写回差异大，疑似旧快照）"],
            ["期间", "收入=OA 账期；成本同时给自然月与同窗口（按发货日期）两版，不能混比；FBA 无发货日期，窗口成本按整月计入"],
            ["附加费", "只单列；另给「扣附加费后」列。已验证附加费=4个分项之和，且未包含在收款费用内，不重复扣"],
            ["尾程", "写回「运费」= EN 预估，不是承运商实际账单；无正式实际/预估标记列"],
            ["FBA", "FBA 尾程（运费）当前全 0，不双算；但「账期是否已扣 FBA 配送费」未证实"],
            ["退款/退货", "OA 退款已在费用内；未做可售退货 COGS 冲回，属已知缺口"],
            ["未匹配", "订单账号未匹配别名时单列 UNMATCHED，不并入真实账号"],
            ["只读声明", "本脚本不写任何 Google Sheet；明细输出在本地 out/"],
        ],
        columns=["项目", "说明"],
    )

    sheets = {
        "说明": notes,
        "账号业绩": main_df,
        "运营人员汇总": staff_summary,
        "单边与异常": exceptions,
        "未匹配明细": unmatched_detail,
        "口径核对": checks,
        "输入就绪": readiness,
        "数量对账": pd.DataFrame(
            [
                ["主表账号数", len(main_df)],
                ["其中双边", int((main_df["账号状态"] == "双边").sum())],
                ["其中仅OA", int((main_df["账号状态"] == "仅OA（无通途成本）").sum())],
                ["其中仅订单", int((main_df["账号状态"] == "仅订单（无可收/应收）").sum())],
                ["其中仅主表", master_only_count],
                ["通途写回行数", len(orders["orders"])],
                ["通途写回账号数", orders["orders"]["渠道账号"].nunique()],
                ["OA 外币层账号数", oa["base"]["渠道账号"].nunique()],
                ["OA 原始审批行数", len(oa["raw"])],
                ["主表账号数", master["渠道账号"].nunique()],
                ["别名总数（去重后）", len(mapping)],
            ],
            columns=["项目", "数值"],
        ),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    xlsx_path = out_dir / f"account_period_performance_{month}.xlsx"
    if not args.dry_run:
        safe_excel(xlsx_path, sheets)
        print(f"[6/6] 已写出 {xlsx_path}")
    else:
        print("[6/6] dry-run：未写文件")

    summary = {
        "month": month,
        "period": f"{start.date()}~{end.date()}",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "accounts": {
            "main": int(len(main_df)),
            "both": int((main_df["账号状态"] == "双边").sum()),
            "oa_only": int((main_df["账号状态"] == "仅OA（无通途成本）").sum()),
            "order_only": int((main_df["账号状态"] == "仅订单（无可收/应收）").sum()),
            "master_only": master_only_count,
            "unmatched": int((main_df["账号状态"] == "未匹配别名（不得并入真实账号）").sum()),
        },
        "oa": {
            "sales_rmb": float(main_df["OA_销售额_人民币"].fillna(0).sum()),
            "fees_rmb": float(main_df["OA_收款费用_人民币"].fillna(0).sum()),
            "receivable_rmb": float(main_df["OA_应收_人民币"].fillna(0).sum()),
            "reserve_delta_rmb": float(main_df["OA_应收账款_人民币"].fillna(0).sum()),
            "sales_minus_fees_rmb": float(main_df["OA_销售减费用_人民币"].fillna(0).sum()),
            "tax_rmb": float(main_df["OA_Tax_人民币"].fillna(0).sum()),
            "surcharge_rmb": float(main_df["OA_附加费_人民币"].fillna(0).sum()),
        },
        "cost": {
            "order_raw_natural_month_rmb": float(main_df["订单_自然月_成本合计"].fillna(0).sum()),
            "order_raw_window_rmb": float(main_df["订单_窗口_成本合计"].fillna(0).sum()),
            "window_next_month_1_3_rmb": float(main_df.get("订单_窗口_下月1-3天成本", pd.Series(dtype=float)).fillna(0).sum()),
            "window_fba_full_month_rmb": float(main_df.get("订单_FBA整月成本", pd.Series(dtype=float)).fillna(0).sum()),
            "pipeline_natural_month_rmb": float(main_df["账号ws_成本合计"].fillna(0).sum()),
            "used_for_performance_rmb": float(main_df["成本_合计"].fillna(0).sum()),
            "cost_basis": effective_cost_basis,
        },
        "unmatched_detail": unmatched_detail.to_dict("records"),
        "checks_passed": int(checks["通过"].sum()),
        "checks_total": int(len(checks)),
        "readiness_issues": readiness[
            ~readiness["状态"].isin(["就绪", "存在（仅对照）", "不适用（本轮按整月）"])
        ][["输入", "状态"]].to_dict("records"),
    }
    summary_path = out_dir / f"account_period_performance_{month}.json"
    if not args.dry_run:
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=json_safe),
            encoding="utf-8",
        )
        print(f"        概要 {summary_path}")
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=json_safe))
    return 0


if __name__ == "__main__":
    sys.exit(main())
