"""蜴国际 Excel upload / tracking-return spreadsheet helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import pandas as pd

from sellfox_shipping.carriers.lizard.dims import DimsLookup
from sellfox_shipping.package_models import SellfoxPackageRecord

LIZARD_TEMPLATE_VERSION = "lizard-upload-v1-2026-07"
SHIPPER_CODE_DEFAULT = "S0143"
UPLOAD_SHEET_NAME = "自定义邮寄方式数据"

UPLOAD_COLUMNS = [
    "参考编号/Reference Code",
    "派送方式/Delivery Style",
    "渠道优选",
    "全名/Consignee Name",
    "收件人国家/Consignee Country",
    "州/Province",
    "城市/City",
    "地址1/Street1",
    "地址2/Street2",
    "邮编/Zip Code",
    "收件人电话/Consignee Phone",
    "备注/Remark",
    "重量",
    "长",
    "宽",
    "高",
    "箱数",
    "收件人公司名称",
    "发货编码/shipper Code",
    "签名服务",
    "计量单位",
    "门牌号",
]

COL_REF = "参考编号/Reference Code"
COL_TRACKING = "物流单号"
COL_CARRIER_ORDER = "订单号"
COL_DELIVERY_STYLE = "派送方式/Delivery Style"
COL_FREIGHT = "运费"
COL_STATUS = "订单状态"

_COUNTRY_MAP = {
    "美国": "United States",
    "US": "United States",
    "USA": "United States",
}

_STATE2ABBREV = {
    k.upper(): v
    for k, v in {
        "Alaska": "AK",
        "Alabama": "AL",
        "Arkansas": "AR",
        "Arizona": "AZ",
        "California": "CA",
        "Colorado": "CO",
        "Connecticut": "CT",
        "District of Columbia": "DC",
        "Delaware": "DE",
        "Florida": "FL",
        "Georgia": "GA",
        "Hawaii": "HI",
        "Iowa": "IA",
        "Idaho": "ID",
        "Illinois": "IL",
        "Indiana": "IN",
        "Kansas": "KS",
        "Kentucky": "KY",
        "Louisiana": "LA",
        "Massachusetts": "MA",
        "Maryland": "MD",
        "Maine": "ME",
        "Michigan": "MI",
        "Minnesota": "MN",
        "Missouri": "MO",
        "Mississippi": "MS",
        "Montana": "MT",
        "North Carolina": "NC",
        "North Dakota": "ND",
        "Nebraska": "NE",
        "New Hampshire": "NH",
        "New Jersey": "NJ",
        "New Mexico": "NM",
        "Nevada": "NV",
        "New York": "NY",
        "Ohio": "OH",
        "Oklahoma": "OK",
        "Oregon": "OR",
        "Pennsylvania": "PA",
        "Rhode Island": "RI",
        "South Carolina": "SC",
        "South Dakota": "SD",
        "Tennessee": "TN",
        "Texas": "TX",
        "Utah": "UT",
        "Virginia": "VA",
        "Vermont": "VT",
        "Washington": "WA",
        "Wisconsin": "WI",
        "West Virginia": "WV",
        "Wyoming": "WY",
    }.items()
}


@dataclass
class SkippedUploadRow:
    package_sn: str
    reason: str


@dataclass
class UploadBuildResult:
    dataframe: pd.DataFrame
    template_version: str = LIZARD_TEMPLATE_VERSION
    total: int = 0
    exported: int = 0
    skipped: int = 0
    skipped_rows: list[SkippedUploadRow] = field(default_factory=list)


@dataclass
class TrackingReturnRow:
    package_sn: str
    tracking_number: str
    carrier_order_no: str = ""
    delivery_style: str = ""
    freight: float | None = None
    order_status: str = ""
    matched: bool = False
    row_index: int = 0


@dataclass
class TrackingReturnParseResult:
    rows: list[TrackingReturnRow]
    total: int = 0
    matched: int = 0
    unmatched: int = 0

    @property
    def unmatched_rows(self) -> list[TrackingReturnRow]:
        return [r for r in self.rows if not r.matched]


def state_abbrev(value: str) -> str:
    if not value:
        return ""
    cleaned = re.sub(r"[^a-zA-Z ]", "", str(value).strip()).upper()
    if len(cleaned) == 2:
        return cleaned
    return _STATE2ABBREV.get(cleaned, cleaned)


def clean_phone(value: str) -> str:
    if not value:
        return "0000000000"
    text = re.sub(r"\s*ext\.?\s*\d+", "", str(value), flags=re.I)
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 10:
        return digits[-10:]
    return digits or "0000000000"


def map_country(country: str, country_code: str) -> str:
    for key in (country, country_code):
        mapped = _COUNTRY_MAP.get(key or "")
        if mapped:
            return mapped
    return country or country_code or ""


def build_upload_dataframe(
    packages: Iterable[SellfoxPackageRecord],
    *,
    dims_lookup: DimsLookup,
    shipper_code: str = SHIPPER_CODE_DEFAULT,
) -> UploadBuildResult:
    rows: list[dict] = []
    skipped: list[SkippedUploadRow] = []
    total = 0
    for package in packages:
        total += 1
        try:
            row = _package_to_upload_row(
                package, dims_lookup=dims_lookup, shipper_code=shipper_code
            )
        except ValueError as exc:
            skipped.append(
                SkippedUploadRow(package_sn=package.package_sn, reason=str(exc))
            )
            continue
        rows.append(row)

    dataframe = pd.DataFrame(rows, columns=UPLOAD_COLUMNS)
    return UploadBuildResult(
        dataframe=dataframe,
        total=total,
        exported=len(rows),
        skipped=len(skipped),
        skipped_rows=skipped,
    )


def write_upload_xlsx(dataframe: pd.DataFrame, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_excel(path, index=False, sheet_name=UPLOAD_SHEET_NAME)
    return path


def parse_tracking_return(
    path: Path,
    *,
    known_package_sns: set[str],
) -> TrackingReturnParseResult:
    path = Path(path)
    df = pd.read_excel(path)
    missing = [c for c in (COL_REF, COL_TRACKING) if c not in df.columns]
    if missing:
        raise ValueError(f"tracking return missing columns: {', '.join(missing)}")

    parsed: list[TrackingReturnRow] = []
    for idx, series in df.iterrows():
        package_sn = str(series.get(COL_REF) or "").strip()
        tracking = str(series.get(COL_TRACKING) or "").strip()
        if not package_sn and not tracking:
            continue
        freight_raw = series.get(COL_FREIGHT)
        freight: float | None
        try:
            freight = float(freight_raw) if pd.notna(freight_raw) else None
        except (TypeError, ValueError):
            freight = None
        matched = bool(package_sn) and package_sn in known_package_sns
        parsed.append(
            TrackingReturnRow(
                package_sn=package_sn,
                tracking_number=tracking,
                carrier_order_no=str(series.get(COL_CARRIER_ORDER) or "").strip(),
                delivery_style=str(series.get(COL_DELIVERY_STYLE) or "").strip(),
                freight=freight,
                order_status=str(series.get(COL_STATUS) or "").strip(),
                matched=matched,
                row_index=int(idx) + 1,
            )
        )

    matched_n = sum(1 for r in parsed if r.matched)
    return TrackingReturnParseResult(
        rows=parsed,
        total=len(parsed),
        matched=matched_n,
        unmatched=len(parsed) - matched_n,
    )


def _package_to_upload_row(
    package: SellfoxPackageRecord,
    *,
    dims_lookup: DimsLookup,
    shipper_code: str,
) -> dict:
    if not package.package_sn:
        raise ValueError("missing package_sn")
    if not package.items:
        raise ValueError("missing items for dims lookup")

    total_grams = 0.0
    lengths: list[float] = []
    widths: list[float] = []
    heights: list[float] = []
    sku_parts: list[str] = []
    name_parts: list[str] = []

    for item in package.items:
        sku_key = (item.commodity_sku or "").strip()
        seller = (item.seller_sku or "").strip()
        qty = item.quantity or 1
        if seller:
            sku_parts.append(seller if qty == 1 else f"{seller}*{qty}")
        if item.variation:
            name_parts.append(item.variation)
        if not sku_key:
            raise ValueError("missing commodity_sku for dims lookup")
        dims = dims_lookup.get(sku_key)
        if dims is None:
            raise ValueError(f"missing carton dims for commodity_sku={sku_key}")
        total_grams += dims.weight_kg * 1000.0 * qty
        lengths.append(dims.length_cm)
        widths.append(dims.width_cm)
        heights.append(dims.height_cm)

    addr = package.address
    remark = ",".join(sku_parts)
    company = " / ".join(p for p in name_parts if p) or remark
    return {
        "参考编号/Reference Code": package.package_sn,
        "派送方式/Delivery Style": "",
        "渠道优选": "是",
        "全名/Consignee Name": addr.name,
        "收件人国家/Consignee Country": map_country(addr.country, addr.country_code),
        "州/Province": state_abbrev(addr.state_or_region),
        "城市/City": addr.city,
        "地址1/Street1": addr.address_line_1,
        "地址2/Street2": addr.address_line_2,
        "邮编/Zip Code": addr.postal_code,
        "收件人电话/Consignee Phone": clean_phone(addr.phone or addr.mobile),
        "备注/Remark": remark,
        "重量": round(total_grams, 1),
        "长": max(lengths),
        "宽": max(widths),
        "高": max(heights),
        "箱数": 1,
        "收件人公司名称": company,
        "发货编码/shipper Code": shipper_code,
        "签名服务": "",
        "计量单位": "cm/kg",
        "门牌号": "",
    }
