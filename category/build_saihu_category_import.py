# -*- coding: utf-8 -*-
"""
Build Saihu 导入更新商品分类 xlsx: join 商品导出 SKU list with EN物料属性 末级类名
and expand to full 一级..四级 path using 商品分类导出 tree.

Usage:
  python build_saihu_category_import.py [--out path.xlsx]
"""

from __future__ import annotations

import argparse
import importlib.util
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import shutil

import pandas as pd

_DIR = Path(__file__).resolve().parent
_ROOT = _DIR.parent
_DEFAULT_CATEGORY_EXPORT = _DIR / "商品分类导出-20260423114344342.xlsx"
_DEFAULT_TEMPLATE = _DIR / "模板 导入更新商品分类-20260423114106574.xlsx"
_DEFAULT_SPU_STATUS = _ROOT / "multi_attr_saihu" / "EN物料属性 产品 x1167 修正后 20260415 1102.xlsx"
_DEFAULT_COMMODITIES = _ROOT / "edit_item" / "商品导出 x2215 Commodities2026_04_23(1).xlsx"

CATEGORY_COLS = ("一级分类", "二级分类", "三级分类", "四级分类")
OUT_COLS = ("*SKU", "一级分类", "二级分类", "三级分类", "四级分类")
SHEET_MAIN = "商品"
SHEET_REPORT = "核对"
SHEET_ERRORS = "错误报告"
SHEET_STYLE_AUDIT = "款式_赛狐分类校验"

# 行状态与中文、建议（与官方「商品分类导出」及 EN物料属性 对照）
STATUS_TO_CN: dict[str, str] = {
    "ok": "正常",
    "no_sku": "SKU 为空",
    "no_style": "物料表无此款式ID",
    "no_category": "物料表赛狐分类为空",
    "unknown": "赛狐分类在官方分类树中无匹配",
    "not_leaf": "非末级类名(存在下级,需用末级名)",
    "ambiguous_leaf": "末级类名在树中对应多条路径",
    "物料表注记": "物料表注记(多行去重等)",
}

PLACEHOLDER_CATS = frozenset({"?", "？"})


def _advice_sku(
    status: str, 赛狐分类: str, flow_msg: str, spu_inferred: bool
) -> str:
    t = (赛狐分类 or "").strip()
    if status == "ok":
        return (
            "可导入; spu 列已空并从 SKU 推断款式"
            if spu_inferred
            else "可导入"
        )
    if status == "no_style":
        return "在 EN物料属性 中补全该款式,或从赛狐端移除测试用 SKU,再重新导出对照。"
    if status == "no_category":
        return (
            "在 EN物料属性 Sheet1 的「赛狐分类」中填写与「商品分类导出」一致的末级分类名称(不可留空)。"
        )
    if status == "unknown":
        if t in PLACEHOLDER_CATS:
            return "「?」为占位,请改成分类导出中已存在的实际末级类名(如 其他靠枕、坐垫 等)。"
        if t and t not in PLACEHOLDER_CATS:
            return (
                f"将物料表中「{t}」改为「商品分类导出-*.xlsx」中某行的末级类名(最深一列),"
                "或先在该导出中新增对应分类后重跑本脚本。"
            )
        return "核对 EN物料属性 的赛狐分类与赛狐官方分类表是否一致。"
    if status == "not_leaf":
        return "改为该分类在树中最后一层末级名(有子类时不能选中间层)。"
    if status == "ambiguous_leaf":
        return "在分类导出中同末级名出现多条路径,需人工在物料表指定可区分的更细类名或调整分类导出。"
    if status == "no_sku":
        return "补全赛狐导出的 SKU。"
    return flow_msg or ""


def _audit_one_style(
    赛狐分类: str, rstatus: str, flow_msg: str
) -> tuple[str, str]:
    t = (赛狐分类 or "").strip()
    if not t:
        return "空值", "在 EN物料属性 中为该款式填写「赛狐分类」(末级名),与赛狐「商品分类导出」一致。"
    if t in PLACEHOLDER_CATS:
        return "占位符", "将「?」改为分类导出中真实末级名。"
    if rstatus == "ok":
        return "与官方树一致(末级可解析)", "无需修改分类字段。"
    if rstatus == "not_leaf":
        return "非末级", _advice_sku("not_leaf", t, flow_msg, False)
    if rstatus == "ambiguous_leaf":
        return "末级重名", _advice_sku("ambiguous_leaf", t, flow_msg, False)
    if rstatus == "unknown":
        return "在官方树中无匹配", (
            f"将「{t}」改为「商品分类导出」中已存在的末级;若业务确需新类,请先在赛狐中维护分类再导出 xlsx 重跑。"
        )
    return rstatus, flow_msg


def _build_sku_error_rows(
    report_data: list[dict[str, str]],
) -> list[dict[str, str]]:
    """仅 SKU 行：排除「核对」中正常、物料表注记行。"""
    out: list[dict[str, str]] = []
    for r in report_data:
        stt = r.get("状态", "")
        if stt in ("", "ok", "物料表注记"):
            continue
        st_物料 = (r.get("赛狐分类(物料表)") or "").strip()
        adv = _advice_sku(
            stt, st_物料, r.get("说明", "") or "", False
        )
        out.append(
            {
                "错误类型": STATUS_TO_CN.get(stt, stt),
                "SKU": r.get("SKU", ""),
                "款式ID": r.get("款式ID", ""),
                "赛狐分类(物料表)": st_物料,
                "导出分类(原表)": r.get("导出分类(原表)", ""),
                "技术状态": stt,
                "说明": r.get("说明", ""),
                "处理建议": adv,
            }
        )
    return out


def _build_style_audit(
    style_map: dict[str, str], idx: CategoryIndex
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for sid in sorted(style_map.keys()):
        st = _norm(style_map[sid])
        if not st:
            out.append(
                {
                    "款式ID": sid,
                    "赛狐分类(物料表)": "",
                    "校验结果": "空值",
                    "技术状态": "empty",
                    "说明": "EN物料属性 中无末级类名",
                    "处理建议": "在「赛狐分类」中填写与「商品分类导出」末级一致的名称。",
                }
            )
            continue
        rstatus, _path, msg = idx.resolve(st)
        short, rec = _audit_one_style(st, rstatus, msg)
        out.append(
            {
                "款式ID": sid,
                "赛狐分类(物料表)": st,
                "校验结果": short,
                "技术状态": rstatus,
                "说明": msg,
                "处理建议": rec,
            }
        )
    return out


def _print_console(
    n_total: int,
    n_ok: int,
    by_status: Counter,
    out_path: Path,
    style_audit: list[dict[str, str]],
) -> None:
    n_bad = n_total - n_ok
    print()
    print("=" * 60)
    print("赛狐 导入更新商品分类 — 结果摘要(请同时查看工作簿中「错误报告」「款式_赛狐分类校验」)")
    print("=" * 60)
    print(f"输出文件: {out_path}")
    print(f"主表行数(与商品导出行一致): {n_total}")
    print(
        f"可写入多级分类(核对状态为 ok 且一级分类有值 或 末级在树中可解析): {n_ok} 行; "
        f"需处理: {n_bad} 行"
    )
    print("--- 按技术状态(仅 SKU) ---")
    for k, c in by_status.most_common():
        if not k or k == "ok":
            continue
        if k == "物料表注记":
            continue
        print(f"  {k} ({STATUS_TO_CN.get(k, k)}): {c} 行")
    print("--- EN物料属性 中款式「赛狐分类」与官方分类树(商品分类导出) ---")
    bad_style = [r for r in style_audit if r.get("校验结果") not in ("与官方树一致(末级可解析)",)]
    print(f"  款式总数: {len(style_audit)}; 需关注(非与官方树一致): {len(bad_style)} 个款式")
    for r in bad_style[:25]:
        rtip = (r.get("处理建议", "") or "")[:90]
        print(
            f"  · 款式 {r.get('款式ID', '')!r} "
            f"物料表类名 {r.get('赛狐分类(物料表)', '')!r} "
            f"=> {r.get('校验结果', '')} — {rtip}"
        )
    if len(bad_style) > 25:
        print(f"  … 另有 {len(bad_style) - 25} 个款式,见工作表「{SHEET_STYLE_AUDIT}」。")
    print("=" * 60)
    print()

def _import_default_spu_from_sku() -> Any:
    mod_path = _ROOT / "multi_attr_saihu" / "erpnext_to_saihu.py"
    spec = importlib.util.spec_from_file_location("erpnext_to_saihu", mod_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {mod_path}")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)  # type: ignore[union-attr]
    return m._default_spu_from_sku


def _norm(x: Any) -> str:
    if pd.isna(x) or x is None:
        return ""
    s = str(x).strip()
    if not s or s.lower() == "nan":
        return ""
    return s


class CategoryIndex:
    def __init__(self, path: str | Path, sheet: str | int = 0) -> None:
        df = pd.read_excel(path, sheet_name=sheet, header=0)
        missing = [c for c in CATEGORY_COLS if c not in df.columns]
        if missing:
            raise ValueError(f"分类导出缺列 {missing!r}，实际: {list(df.columns)}")

        self.leaf_to_paths: dict[str, list[tuple[str, str, str, str]]] = defaultdict(
            list
        )
        self.all_names: set[str] = set()
        for _, row in df.iterrows():
            p = tuple(_norm(row[c]) for c in CATEGORY_COLS)
            d_idx = -1
            for i in range(4):
                if p[i]:
                    d_idx = i
            if d_idx < 0:
                continue
            for i in range(4):
                if p[i]:
                    self.all_names.add(p[i])
            leaf = p[d_idx]
            self.leaf_to_paths[leaf].append(p)

        for k, paths in self.leaf_to_paths.items():
            seen: set[tuple[str, str, str, str]] = set()
            uniq: list[tuple[str, str, str, str]] = []
            for t in paths:
                if t not in seen:
                    seen.add(t)
                    uniq.append(t)
            self.leaf_to_paths[k] = uniq

    def resolve(self, name: str) -> tuple[str, tuple[str, str, str, str] | None, str]:
        n = _norm(name)
        if not n:
            return "empty", None, "赛狐分类为空"
        if n in self.leaf_to_paths:
            paths = self.leaf_to_paths[n]
            if len(paths) > 1:
                return "ambiguous_leaf", None, f"末级重名: {len(paths)}条不同路径"
            return "ok", paths[0], ""
        if n in self.all_names:
            return "not_leaf", None, "非末级类名(在树中但存在下级)"
        return "unknown", None, "类名在分类树中无匹配"


def load_style_saihu_map(path: str | Path) -> tuple[dict[str, str], list[str]]:
    df = pd.read_excel(path, sheet_name="Sheet1", header=0)
    for c in ("款式ID", "赛狐分类"):
        if c not in df.columns:
            raise ValueError(f"物料属性表缺列 {c!r}，有: {list(df.columns)}")

    warnings: list[str] = []
    out: dict[str, str] = {}
    for _, row in df.iterrows():
        sid = _norm(row["款式ID"])
        if not sid:
            continue
        cat = _norm(row["赛狐分类"])
        if sid in out and out[sid] != cat:
            warnings.append(f"款式ID {sid!r} 多行: {out[sid]!r} -> {cat!r} (采用末行)")
        out[sid] = cat
    return out, warnings


def _write_excel(
    template_path: Path,
    out_path: Path,
    rows: list[dict[str, str]],
    report: list[dict[str, str]],
    sku_error_rows: list[dict[str, str]],
    style_audit: list[dict[str, str]],
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(template_path, out_path)

    # 读取模板表头
    template_cols = pd.read_excel(template_path, sheet_name=SHEET_MAIN, nrows=0).columns.tolist()

    # 构建主 DataFrame，用模板覆写「商品」sheet
    df_main = pd.DataFrame(rows)
    for c in template_cols:
        if c not in df_main.columns:
            df_main[c] = None
    df_main = df_main[template_cols]

    with pd.ExcelWriter(out_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
        df_main.to_excel(writer, sheet_name=SHEET_MAIN, index=False)

    # 用 pandas 追加其余 sheet
    with pd.ExcelWriter(out_path, engine='openpyxl', mode='a', if_sheet_exists='overlay') as writer:
        if report:
            keys = [k for k in report[0] if not str(k).startswith("__")]
            pd.DataFrame(report)[keys].to_excel(writer, sheet_name=SHEET_REPORT, index=False)
        else:
            pd.DataFrame({"(无核对数据)": []}).to_excel(writer, sheet_name=SHEET_REPORT, index=False)

        if sku_error_rows:
            pd.DataFrame(sku_error_rows).to_excel(writer, sheet_name=SHEET_ERRORS, index=False)
        else:
            pd.DataFrame({"(无数据)": []}).to_excel(writer, sheet_name=SHEET_ERRORS, index=False)

        if style_audit:
            pd.DataFrame(style_audit).to_excel(writer, sheet_name=SHEET_STYLE_AUDIT, index=False)
        else:
            pd.DataFrame({"(无数据)": []}).to_excel(writer, sheet_name=SHEET_STYLE_AUDIT, index=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--category-export", type=Path, default=_DEFAULT_CATEGORY_EXPORT)
    ap.add_argument("--template", type=Path, default=_DEFAULT_TEMPLATE)
    ap.add_argument("--spu-status", type=Path, default=_DEFAULT_SPU_STATUS)
    ap.add_argument("--commodities", type=Path, default=_DEFAULT_COMMODITIES)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = args.out or (_ROOT / "edit_item" / f"赛狐_导入更新商品分类_{ts}.xlsx")

    spu_from_sku = _import_default_spu_from_sku()
    idx = CategoryIndex(args.category_export)
    style_map, _mat_warnings = load_style_saihu_map(args.spu_status)

    df = pd.read_excel(args.commodities, sheet_name=0, header=0)
    for c in ("SKU", "spu"):
        if c not in df.columns:
            raise ValueError(f"商品导出缺列 {c!r}，有: {list(df.columns)}")

    rows_out: list[dict[str, str]] = []
    report_commod: list[dict[str, str]] = []

    for j in range(len(df)):
        row = df.iloc[j]
        sku = _norm(row["SKU"])
        spu_raw = _norm(row["spu"])
        spu_inferred = bool((not spu_raw) and bool(sku))
        spu_cell = spu_raw
        if not spu_cell and sku:
            spu_cell = str(spu_from_sku(sku))
        current_cat = _norm(row["分类"]) if "分类" in df.columns else ""

        st = style_map.get(spu_cell, "") if spu_cell else ""
        l1, l2, l3, l4 = "", "", "", ""
        status_main = "ok"
        expl = ""

        if not sku:
            status_main = "no_sku"
            expl = "SKU为空"
        elif not spu_cell:
            status_main = "no_style"
            expl = "无法从SKU解析款式ID"
        elif spu_cell and spu_cell not in style_map:
            status_main = "no_style"
            expl = "无款式ID对照(物料表无此款式ID)"
        elif not _norm(st):
            status_main = "no_category"
            expl = "物料表中赛狐分类为空"
        else:
            rstatus, path, msg = idx.resolve(st)
            if rstatus == "ok" and path is not None:
                l1, l2, l3, l4 = path[0], path[1], path[2], path[3]
                expl = "ok"
            else:
                status_main = rstatus
                expl = msg

        if spu_inferred:
            suffix = "spu列空，已从SKU首段推断款式ID"
            if status_main == "ok":
                expl = f"ok; {suffix}"
            else:
                expl = (expl + "；" if expl else "") + suffix
        if status_main == "ok" and current_cat and (l1 or l2 or l3 or l4):
            built = " > ".join(x for x in (l1, l2, l3, l4) if x)
            sameish = (st and st in current_cat) or any(
                p and p in current_cat for p in (l1, l2, l3, l4)
            )
            if not sameish and (current_cat not in built) and (built not in current_cat):
                expl = (expl or "ok") + f"；与导出[分类]可能不一致(导出: {current_cat})"

        rows_out.append(
            {
                "*SKU": sku,
                "一级分类": l1,
                "二级分类": l2,
                "三级分类": l3,
                "四级分类": l4,
            }
        )
        report_commod.append(
            {
                "SKU": sku,
                "款式ID": spu_cell,
                "赛狐分类(物料表)": st,
                "导出分类(原表)": current_cat,
                "状态": status_main,
                "说明": expl,
                "__spu_inferred": "1" if spu_inferred else "",
            }
        )

    err_rows = _build_sku_error_rows(report_commod)
    style_audit = _build_style_audit(style_map, idx)
    by_status: Counter = Counter(
        (r.get("状态") or "") for r in report_commod
    )
    n_ok = sum(1 for r in report_commod if r.get("状态") == "ok")

    report = list(report_commod)
    for w in _mat_warnings:
        report.append(
            {
                "SKU": "",
                "款式ID": "",
                "赛狐分类(物料表)": "",
                "导出分类(原表)": "",
                "状态": "物料表注记",
                "说明": w,
            }
        )

    _write_excel(
        args.template, out_path, rows_out, report, err_rows, style_audit
    )
    _print_console(len(df), n_ok, by_status, out_path, style_audit)
    print(
        f"已写入: {out_path} | 主表 {len(rows_out)} 行 | "
        f"错误报告 {len(err_rows)} 行 | 款式校验 {len(style_audit)} 行"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
