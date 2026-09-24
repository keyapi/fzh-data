#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PB 订单履约的结构化处理服务层。

CLI（`run_pb_orders.py`）与 Web worker（`web/tasks.py`）共用这一层：

- 输入是文件路径 + 选项，输出是结构化报告 + 产物清单；
- 不 `print`、不 `sys.exit`，改用异常 + 进度回调，方便队列工人记录失败原因；
- 所有硬校验失败都抛 `PBJobError`，失败时**不产出**任何可下载的正式产物。

业务算法一律复用既有模块（`sps_pb_pdf` / `pb_tongtu_excel` / `pb_label_pdf` /
`pb_back_label_pdf`），本文件只做编排、校验和报告。
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd

_MODULE_DIR = Path(__file__).resolve().parent
if str(_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(_MODULE_DIR))

import pb_back_label_pdf  # noqa: E402
import pb_label_pdf  # noqa: E402
import pb_tongtu_excel  # noqa: E402
import sps_pb_pdf  # noqa: E402

PDF_PATTERN = "Packslip*.pdf"
CSV_PATTERN = "checked0stock*.csv"
SHIPMENT_PATTERN = "shipment*.csv"

MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MIME_PDF = "application/pdf"


class PBJobError(Exception):
    """业务失败：面向用户可读，不含堆栈与服务器绝对路径。"""

    def __init__(self, message: str, hint: str = "", code: str = "job_error"):
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.code = code

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "hint": self.hint}


@dataclass
class ArtifactSpec:
    """一个待发布的产物：worker 负责落盘到正式目录并登记。"""

    kind: str
    path: Path
    download_name: str
    mime_type: str


@dataclass
class JobOptions:
    no_stock: list[str] = field(default_factory=list)
    no_stock_note: str | None = None
    allow_unmatched: bool = False
    cache_only: bool = False
    check_shipment: bool = False
    validate_only: bool = False
    timestamp: str | None = None
    sku_cache_path: Path | None = None
    nltk_dir: Path | None = None
    # 通途 xlsx 文件名里的订单标识，缺省用订单 CSV 的词干。
    # 网页上传的磁盘名固定是 `order.csv`，词干就是 "order"（产物看不出是哪一批），
    # 所以 worker 把用户的原始文件名词干传进来；命令行不传，行为与从前一致。
    csv_stem: str | None = None


@dataclass
class JobResult:
    report: dict
    artifacts: list[ArtifactSpec]


ProgressFn = Callable[[str, str], None]

# 未匹配页在标签上的占位文字。留空会让错件看起来像正常件；印出可见标记，
# 拿到纸就能一眼看出这页有问题。（此前 --allow-unmatched 会直接崩在 reportlab。）
UNMATCHED_MARK = "？？未匹配"


def _noop(_step: str, _message: str) -> None:
    return None


# 输出文件名里不能出现的字符（Windows 最严）。词干可能来自用户上传的文件名。
_UNSAFE_STEM = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def _output_csv_stem(options: JobOptions, csv_path: Path) -> str:
    """通途 xlsx 文件名里的订单标识。

    优先用调用方给的 `options.csv_stem`（网页上传的磁盘名固定是 `order.csv`，
    不传就会把产物命名成 `..._order_on_...`，看不出是哪一批）；没给就用 CSV 自己的词干。
    词干可能来自用户文件名，洗掉不合法字符，洗空了回落 `order`。
    """
    stem = str(options.csv_stem or csv_path.stem or "")
    stem = _UNSAFE_STEM.sub("-", stem).strip(" .-")
    return stem or "order"


def sku_overlay_texts(df: pd.DataFrame) -> list[str]:
    """取 SKUxQTY 列做叠加文字，NA 换成可见占位符，其余原样保留。"""
    return [UNMATCHED_MARK if pd.isna(v) else str(v) for v in df["SKUxQTY"].tolist()]


def pick_newest(dir_path: Path, pattern: str) -> Path | None:
    """取最新修改的匹配文件（跳过 ~$ 锁文件）；无则返回 None。"""
    if not dir_path.is_dir():
        return None
    files = [p for p in dir_path.glob(pattern) if not p.name.startswith("~$")]
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def resolve_input(dir_path: Path, explicit, pattern: str, label: str) -> Path:
    path = Path(explicit).resolve() if explicit else pick_newest(dir_path, pattern)
    if path is None or not path.is_file():
        raise PBJobError(
            f"找不到{label}",
            hint=f"目录下没有匹配 {pattern} 的文件，请显式指定",
            code="input_missing",
        )
    return path.resolve()


def shipment_report(shipment_csv: Path, df_rows: pd.DataFrame) -> dict:
    """只读交叉核对：用 ASN(shipment) CSV 的实发数量比对订单数量。不删行。"""
    ship = pd.read_csv(shipment_csv, dtype=str)
    ship["_qty"] = pd.to_numeric(ship["Qty Ship"], errors="coerce").fillna(0).astype(int)
    ordered = df_rows.groupby("Vendor Style")["Qty Ordered"].sum().astype(int)
    shipped = ship.groupby("Vdr Item #")["_qty"].sum()
    cmp = pd.DataFrame({"ordered": ordered, "shipped": shipped}).fillna(0).astype(int)
    short = cmp[cmp["shipped"] < cmp["ordered"]]
    return {
        "file": shipment_csv.name,
        "ordered": int(cmp["ordered"].sum()),
        "shipped": int(cmp["shipped"].sum()),
        "short": [
            {
                "sku": str(sku),
                "ordered": int(r["ordered"]),
                "shipped": int(r["shipped"]),
                "diff": int(r["shipped"] - r["ordered"]),
            }
            for sku, r in short.iterrows()
        ],
    }


def run_job(
    pdf_path,
    csv_path,
    options: JobOptions | None = None,
    output_dir=None,
    progress: ProgressFn | None = None,
    shipment_csv=None,
) -> JobResult:
    """执行步骤 1-2 / 3 / 4 / 4.2，返回结构化报告与产物清单。

    `output_dir` 为 None 时只在内存里跑（等价 dry-run），不写任何文件。
    """
    options = options or JobOptions()
    progress = progress or _noop
    pdf_path = Path(pdf_path).resolve()
    csv_path = Path(csv_path).resolve()
    out_dir = Path(output_dir).resolve() if output_dir else None

    for p, label in ((pdf_path, "Packslip PDF"), (csv_path, "订单 CSV")):
        if not p.is_file():
            raise PBJobError(f"{label}不存在", hint=f"路径无效：{p.name}", code="input_missing")

    warnings: list[str] = []
    ts_full = options.timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ts_stamp = datetime.strptime(ts_full, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d_%H-%M-%S")
    ts_mmdd = datetime.strptime(ts_full, "%Y-%m-%d %H:%M:%S").strftime("%m.%d")

    # ---------- 步骤 1-2：PDF 抽取 ----------
    progress("extract", "抽取 Packslip PDF 的 PO / Item Number")
    df_pdf = sps_pb_pdf.build_page_df(pdf_path)
    po_fail = int(df_pdf[sps_pb_pdf.COL_PO].isna().sum())
    item_fail = int(df_pdf[sps_pb_pdf.COL_ITEM].isna().sum())
    if po_fail or item_fail:
        warnings.append(f"PDF 抽取失败：PO {po_fail} 页 / Item {item_fail} 页")

    # ---------- 步骤 3：订单 CSV -> 通途 xlsx ----------
    progress("orders", "处理订单 CSV 并拆行")
    df_order = pb_tongtu_excel.build_order_df(csv_path)
    no_stock_skus = [s for s in options.no_stock if str(s).strip()]
    importable, no_stock = pb_tongtu_excel.split_no_stock(df_order, no_stock_skus)

    # ---------- 1:1 硬校验（对全量订单行；无货拆分是之后的事）----------
    if len(df_pdf) != len(df_order):
        raise PBJobError(
            f"1:1 校验失败：PDF {len(df_pdf)} 页 != 订单 {len(df_order)} 行，拒绝生成标签",
            hint="请检查 SPS PDF 导出设置，可能 Qty per Carton 有不是 1 的。",
            code="one_to_one_failed",
        )

    # ---------- join：页 -> SKUxQTY（先用全量行 join，再按无货拆页）----------
    progress("join", "关联 PDF 页与订单行")
    df_join, unmatched = sps_pb_pdf.join_pages_with_orders(df_pdf, df_order)
    if unmatched and not options.allow_unmatched:
        raise PBJobError(
            f"join 未匹配 {len(unmatched)} 条，会在标签上写空 SKU，已中止",
            hint=f"未匹配示例：{', '.join(str(u) for u in unmatched[:10])}",
            code="join_unmatched",
        )
    if unmatched:
        # 未匹配行的 Vendor Style / Qty Ordered 都是 NA，直接进下游会崩在
        # reportlab 与 astype(int)。按「一页 = 一包裹 = 一件」补上，
        # 并把 SKU 换成可见标记，避免错件看起来像正常件。
        df_join = df_join.copy()
        df_join["Vendor Style"] = df_join["Vendor Style"].fillna(UNMATCHED_MARK)
        df_join["Qty Ordered"] = pd.to_numeric(
            df_join["Qty Ordered"], errors="coerce"
        ).fillna(1)

    ship = None
    if options.check_shipment:
        sp = Path(shipment_csv).resolve() if shipment_csv else pick_newest(
            pdf_path.parent, SHIPMENT_PATTERN
        )
        if sp is None or not sp.is_file():
            warnings.append("发货核对跳过：未提供 shipment ASN CSV")
        else:
            progress("shipment", "核对 ASN 实发数量")
            ship = shipment_report(sp, importable)

    # 按无货 SKU 把「页」分成两组（df_join 行序 == PDF 页序）
    if no_stock_skus:
        wanted = {str(s).strip().lower() for s in no_stock_skus if str(s).strip()}
        is_no_stock = df_join["Vendor Style"].astype(str).str.strip().str.lower().isin(wanted)
    else:
        is_no_stock = pd.Series(False, index=df_join.index)
    ns_idx = [i for i, flag in enumerate(is_no_stock) if flag]
    ok_idx = [i for i, flag in enumerate(is_no_stock) if not flag]
    if no_stock_skus and not ns_idx:
        warnings.append(f"指定的无货 SKU 本批都没有，按全量出件：{no_stock_skus}")

    split = bool(ns_idx)
    df_ok = df_join.iloc[ok_idx].reset_index(drop=True) if split else df_join
    df_ns = df_join.iloc[ns_idx].reset_index(drop=True) if split else df_join.iloc[0:0]
    note = options.no_stock_note or f"{df_ns['PO Number'].nunique()}单{len(df_ns)}件"

    main_label_name = pb_label_pdf.LABEL_PDF_NAME.format(mmdd=ts_mmdd)
    main_back_name = pb_back_label_pdf.BACK_LABEL_PDF_NAME.format(mmdd=ts_mmdd)
    ns_label_name = pb_label_pdf.NO_STOCK_LABEL_PDF_NAME.format(note=note, mmdd=ts_mmdd)
    ns_back_name = pb_back_label_pdf.NO_STOCK_BACK_LABEL_PDF_NAME.format(note=note, mmdd=ts_mmdd)

    report = {
        "inputs": {
            "packslip": pdf_path.name,
            "order_csv": csv_path.name,
        },
        "pdf": {"pages": len(df_pdf), "unique_po": int(df_pdf[sps_pb_pdf.COL_PO].nunique()),
                "po_fail": po_fail, "item_fail": item_fail},
        "orders": {
            "rows": len(df_order), "columns": int(df_order.shape[1]),
            "importable": len(importable), "no_stock_rows": len(no_stock),
        },
        "one_to_one": {"pdf_pages": len(df_pdf), "order_rows": len(df_order), "ok": True},
        "join": {"unmatched": len(unmatched),
                 "unmatched_sample": [str(u) for u in unmatched[:10]]},
        "split": {"enabled": split, "in_stock_pages": len(ok_idx), "no_stock_pages": len(ns_idx),
                  "no_stock_skus": no_stock_skus, "note": note if split else None},
        "shipment": ship,
        "outputs": [],
        "reconciliation": [
            {"label": "订单行", "total": len(df_order),
             "parts": f"可导入 {len(importable)} + 无库存 {len(no_stock)}",
             "diff": len(df_order) - len(importable) - len(no_stock)},
            {"label": "PDF 页", "total": len(df_pdf),
             "parts": f"有货 {len(ok_idx)} + 无货 {len(ns_idx)}",
             "diff": len(df_pdf) - len(ok_idx) - len(ns_idx)},
            {"label": "标签页", "total": len(df_pdf) * 2,
             "parts": f"有货 {len(ok_idx)}×2" + (f" + 无货 {len(ns_idx)}×2" if split else ""),
             "diff": len(df_pdf) * 2 - len(ok_idx) * 2 - (len(ns_idx) * 2 if split else 0)},
            {"label": "背贴页", "total": len(df_join),
             "parts": f"有货 {len(df_ok)}" + (f" + 无货 {len(df_ns)}" if split else ""),
             "diff": len(df_join) - len(df_ok) - len(df_ns)},
        ],
        "warnings": warnings,
        "timestamp": ts_full,
        "validate_only": bool(options.validate_only),
    }

    if out_dir is None or options.validate_only:
        if options.validate_only:
            progress("done", "仅校验完成，未生成文件")
        return JobResult(report=report, artifacts=[])

    out_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[ArtifactSpec] = []

    # ---------- 通途 xlsx ----------
    progress("tongtool", "生成通途导入 xlsx")
    written = pb_tongtu_excel.export(
        df_order, importable, no_stock, out_dir, _output_csv_stem(options, csv_path), ts_stamp
    )
    kind_map = {
        "PB_0_导入_原始": "tongtool",
        "PB_0_不可导入_原始": "tongtool",
        "PB_1_不可导入_无库存": "tongtool_no_stock",
        "PB_2_导入_库存有货": "tongtool_importable",
    }
    for prefix, path in written.items():
        artifacts.append(ArtifactSpec(kind_map[prefix], path, path.name, MIME_XLSX))
        report["outputs"].append({"kind": kind_map[prefix], "name": path.name})

    # ---------- 步骤 4 / 4.2：标签 PDF + 背贴 PDF ----------
    progress("label", "叠加 SKU 并拆分标签 PDF")
    label_path, label_pages = pb_label_pdf.build_label_pdf(
        pdf_path, sku_overlay_texts(df_ok), out_dir, ts_mmdd=ts_mmdd,
        page_indices=ok_idx if split else None,
    )
    artifacts.append(ArtifactSpec("label", label_path, main_label_name, MIME_PDF))
    report["outputs"].append({"kind": "label", "name": label_path.name, "pages": label_pages})

    progress("back_label", "生成背贴 PDF（本地缓存）")
    back_path, back_pages, missing_names = pb_back_label_pdf.build_back_label_pdf(
        df_ok, out_dir, ts_mmdd=ts_mmdd, use_cache_only=options.cache_only,
        cache_path=options.sku_cache_path or pb_back_label_pdf.CACHE_CSV,
    )
    artifacts.append(ArtifactSpec("back_label", back_path, main_back_name, MIME_PDF))
    report["outputs"].append({"kind": "back_label", "name": back_path.name, "pages": back_pages})
    report["missing_names"] = [str(m) for m in missing_names]
    if missing_names:
        warnings.append(f"{len(missing_names)} 个 SKU 在名称表里没有中/西语名")

    if split:
        progress("no_stock", "生成无货子集标签/背贴")
        ns_label, ns_label_pages = pb_label_pdf.build_label_pdf(
            pdf_path, sku_overlay_texts(df_ns), out_dir, ts_mmdd=ts_mmdd,
            filename=ns_label_name, page_indices=ns_idx,
        )
        artifacts.append(ArtifactSpec("label_no_stock", ns_label, ns_label_name, MIME_PDF))
        report["outputs"].append(
            {"kind": "label_no_stock", "name": ns_label.name, "pages": ns_label_pages}
        )

        ns_back, ns_back_pages, _ = pb_back_label_pdf.build_back_label_pdf(
            df_ns, out_dir, ts_mmdd=ts_mmdd, filename=ns_back_name, use_cache_only=True,
            cache_path=options.sku_cache_path or pb_back_label_pdf.CACHE_CSV,
        )
        artifacts.append(ArtifactSpec("back_label_no_stock", ns_back, ns_back_name, MIME_PDF))
        report["outputs"].append(
            {"kind": "back_label_no_stock", "name": ns_back.name, "pages": ns_back_pages}
        )

    progress("done", "处理完成")
    return JobResult(report=report, artifacts=artifacts)


def scan_dir(dir_path, output_dir=None, options=None, progress=None) -> JobResult:
    """从目录里自动挑最新的 Packslip PDF / 订单 CSV 后执行（CLI 用）。"""
    dir_path = Path(dir_path).resolve()
    if not dir_path.is_dir():
        raise PBJobError("目录不存在", hint=dir_path.name, code="input_missing")
    pdf_path = resolve_input(dir_path, None, PDF_PATTERN, "Packslip PDF")
    csv_path = resolve_input(dir_path, None, CSV_PATTERN, "订单 CSV")
    return run_job(pdf_path, csv_path, options, output_dir if output_dir else dir_path, progress)
