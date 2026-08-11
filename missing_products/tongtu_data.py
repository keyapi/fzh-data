# -*- coding: utf-8 -*-
"""Shared read-only helpers for Tongtu/EN/Sellfox mapping deliverables."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Optional

import pandas as pd

HERE = Path(__file__).resolve().parent
MAIN = Path(r"D:\Work\赛狐\Cursor")
OUT = HERE / "out"
TONGTU_ZIP_DIR = Path(r"D:\Work\赛狐\商品")


def norm(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def latest_file(directory: Path, pattern: str) -> Optional[Path]:
    if not directory.exists():
        return None
    candidates = [
        p for p in directory.glob(pattern) if not p.name.startswith("~$")
    ]
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def latest_mainline_audit_path() -> Optional[Path]:
    return latest_file(OUT, "通途SKU未在EN产品登记及赛狐状态_*.xlsx")


def latest_bom_path() -> Optional[Path]:
    return latest_file(
        MAIN / "warehouse_restock" / "数据源", "EN产品BOM成本列表_*.xlsx"
    ) or latest_file(HERE / "数据源", "EN产品BOM成本列表_*.xlsx")


def latest_tongtu_zip_path() -> Optional[Path]:
    return latest_file(TONGTU_ZIP_DIR, "通途商品导出_*.zip")


def load_mainline_mapping(audit_path: Path) -> pd.DataFrame:
    xl = pd.ExcelFile(audit_path)
    sheet = (
        "通途映射全量"
        if "通途映射全量" in xl.sheet_names
        else xl.sheet_names[-1]
    )
    df = xl.parse(sheet, dtype=str)
    df = df[df["通途SKU"].notna() & (df["通途SKU"].astype(str).str.strip() != "")].copy()
    return df


def load_foam_status_sheet(audit_path: Path) -> pd.DataFrame:
    xl = pd.ExcelFile(audit_path)
    sheet = (
        "海绵通途SKU"
        if "海绵通途SKU" in xl.sheet_names
        else next((s for s in xl.sheet_names if "海绵" in s), xl.sheet_names[0])
    )
    df = xl.parse(sheet, dtype=str)
    return df[df["通途SKU"].notna() & (df["通途SKU"].astype(str).str.strip() != "")].copy()


def load_tongtu_aliases(zip_path: Path) -> pd.DataFrame:
    """Return one row per alias from the Tongtu simple-template export zip."""
    rows: list[dict] = []
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            if not name.endswith(".xlsx"):
                continue
            df = pd.read_excel(io.BytesIO(z.read(name)), sheet_name=0, dtype=str)
            source = Path(name).stem
            sku_col = next((c for c in df.columns if str(c).strip() == "SKU"), None)
            alias_col = next(
                (c for c in df.columns if str(c).strip() == "SKU别名"), None
            )
            name_col = next(
                (c for c in df.columns if str(c) in ("商品名称", "产品名称")), None
            )
            if not sku_col or not alias_col:
                continue
            for _, row in df.iterrows():
                sku = norm(row.get(sku_col))
                if not sku:
                    continue
                aliases = norm(row.get(alias_col))
                for alias in str(aliases).replace("\n", ";").split(";"):
                    alias = norm(alias)
                    if alias:
                        rows.append(
                            {
                                "通途SKU": sku,
                                "SKU别名": alias,
                                "商品名称": norm(row.get(name_col)) if name_col else "",
                                "来源表": source,
                            }
                        )
    return pd.DataFrame(rows)
