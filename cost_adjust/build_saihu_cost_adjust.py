"""
build_saihu_cost_adjust.py
生成赛狐「成本补录单」导入文件（按「仓库+SKU」或「单据+SKU」改采购成本）

背景（2026-09-18 实测，详见 docs/research/2026-09-18-sellfox-cost-accounting-fifo.md）:
  赛狐里成本挂在「仓库×SKU」维度。已入库库存要改采购成本，公开 OpenAPI 没有写入口
  （成本补录单在公开 OpenAPI 下只有查询一个端点）。批量/多规则改成本走本脚本生成导入文件，
  即 仓库 → 成本补录 → 成本补录单 → 导入成本补录单，有两种模式：

  单张海外仓按单据的改成本另有纯 API 路径（create + audit，无点击），见
  `sellfox_cost_adjust_api.py` —— 本脚本仍是批量/多规则场景的主路径。

  ┌ 按SKU导入 ── 列: *仓库 *SKU 店铺 FNSKU 专属类型 采购单价 总货值 单位费用 总费用
  │              限制: **不支持海外仓**（报错原文「创建类型为按sku时,不能为海外仓」）
  │              适用: 非海外仓（国内仓等）
  └ 按单据导入 ── 列: *单据号 *单据类型 *SKU 组合SKU 店铺 FNSKU 专属类型 MSKU 货件号 采购单价 总货值 单位费用 总费用
                 单据类型 ∈ 发货单 / 采购单 / 其他入库单 / 调拨单 / 海外仓备货单 / 移除入库单 / 多平台发货单
                 **发货单/海外仓备货单/多平台发货单 不许填 单位费用、总费用**（填了整行失败）

  补录单导入后是「待审核」，需点「审核通过」才生效（可页面点击，也可调 audit.json）；
  生效后库存按加权平均重算。

数据流:
  激励成本规则.xlsx（仓库/SKU/[单据号/单据类型]/规则类型/规则值）
    + 赛狐库存明细导出（可选，取当前采购单价做「前值」对照与比例/差额基准）
    → 复制官方模板 → 逐行填 → 分批输出(≤5000条/文件)，两种模式各出一套文件

使用:
  uv run python build_saihu_cost_adjust.py
  uv run python build_saihu_cost_adjust.py --dry-run    # 只出对照表
"""
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

os.chdir(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = Path("数据源")
OUT_BASE = Path("out")

# 赛狐限制: 单个导入文件最多 5000 条记录
MAX_ROWS = 5000

# 两种模式的官方模板 + 必填列
SKU_MODE = "按SKU"
ORDER_MODE = "按单据"
TEMPLATES = {
    SKU_MODE: Path("数据源样例/赛狐_成本补录单_模板_按SKU.xlsx"),
    ORDER_MODE: Path("数据源样例/赛狐_成本补录单_模板_按单据.xlsx"),
}

# 单据类型可选值（取自按单据模板的 data validation）
DOC_TYPES = ["发货单", "采购单", "其他入库单", "调拨单", "海外仓备货单", "移除入库单", "多平台发货单"]
# 这些单据类型不许填 单位费用/总费用
NO_FEE_DOC_TYPES = {"发货单", "海外仓备货单", "多平台发货单"}

RULE_ALIASES = {
    "固定值": "固定值", "固定": "固定值", "fixed": "固定值",
    "按比例": "按比例", "比例": "按比例", "ratio": "按比例", "系数": "按比例",
    "按差额": "按差额", "差额": "按差额", "diff": "按差额",
}


def norm_col(name) -> str:
    s = str(name).strip().replace("（", "(").replace("）", ")").replace("＊", "*")
    return re.sub(r"[\s　]+", "", s).lstrip("*")


def _pick_col(df: pd.DataFrame, aliases: list[str]) -> str | None:
    lut = {norm_col(c): c for c in df.columns}
    for a in aliases:
        if norm_col(a) in lut:
            return lut[norm_col(a)]
    return None


def _fmt(v) -> float:
    return round(float(v), 4)


COL_ALIASES = {
    "仓库": ["仓库", "收货仓库", "warehouse"],
    "SKU": ["SKU", "商品SKU", "commoditySku", "sku"],
    "单据号": ["单据号", "关联单号", "备货单号", "pickSn"],
    "单据类型": ["单据类型", "类型", "docType"],
    "规则类型": ["规则类型", "类型", "rule"],
    "规则值": ["规则值", "值", "value"],
    "基准值": ["基准值", "基准", "base"],
    "单位费用": ["单位费用", "单个头程费用", "头程", "perFee"],
}


def load_rules() -> pd.DataFrame:
    files = [f for f in DATA_DIR.glob("*.xlsx") if "规则" in f.name and not f.name.startswith("~$")]
    if not files:
        raise SystemExit(f"[错误] {DATA_DIR}/ 下没找到规则表（文件名需含「规则」）。")
    path = max(files, key=lambda f: f.stat().st_mtime)
    df = pd.read_excel(path, dtype=str)
    print(f"规则表: {path.name}  ({len(df)} 行)")

    # 「单据类型」和「规则类型」可能同名，先按位置区分：规则类型是 RULE_ALIASES 里认得出的那个
    cols = {}
    for key, aliases in COL_ALIASES.items():
        c = _pick_col(df, aliases)
        if c:
            cols[key] = c
    # 「类型」歧义处理：若把「类型」认成了规则类型但取值不是规则别名，则回退
    if "规则类型" in cols and "单据类型" not in cols:
        vals = df[cols["规则类型"]].astype(str).str.strip()
        if not vals.isin(RULE_ALIASES).any():
            cols["单据类型"] = cols.pop("规则类型")

    for need in ("SKU", "规则类型", "规则值"):
        if not cols.get(need):
            raise SystemExit(f"[错误] 规则表缺少必填列「{need}」。实际列: {list(df.columns)}")
    if not cols.get("仓库") and not cols.get("单据号"):
        raise SystemExit("[错误] 规则表至少要有一列「仓库」(按SKU模式) 或「单据号」(按单据模式)。")

    def s(key):
        return df[cols[key]].astype(str).str.strip() if cols.get(key) else pd.Series([pd.NA] * len(df))

    out = pd.DataFrame({
        "仓库": s("仓库").str.upper(),
        "SKU": s("SKU"),
        "单据号": s("单据号"),
        "单据类型": s("单据类型"),
        "规则类型": s("规则类型").map(lambda x: RULE_ALIASES.get(x, RULE_ALIASES.get(str(x).lower(), None))),
        "规则值": pd.to_numeric(df[cols["规则值"]], errors="coerce"),
        "基准值": pd.to_numeric(df[cols["基准值"]], errors="coerce") if cols.get("基准值") else pd.NA,
        "单位费用": pd.to_numeric(df[cols["单位费用"]], errors="coerce") if cols.get("单位费用") else pd.NA,
    })
    out = out.replace({"nan": pd.NA, "": pd.NA})

    bad = out[out["规则类型"].isna()]
    if len(bad):
        raise SystemExit(f"[错误] {len(bad)} 行规则类型无法识别（支持 固定值/按比例/按差额）。示例: {bad['规则类型'].head(3).tolist()}")
    badv = out[out["规则值"].isna()]
    if len(badv):
        raise SystemExit(f"[错误] {len(badv)} 行规则值不是数字。示例: {badv[['SKU','规则值']].head(3).to_dict('records')}")

    # 模式判定：有单据号 → 按单据；否则 → 按SKU
    out["模式"] = out["单据号"].apply(lambda x: ORDER_MODE if pd.notna(x) else SKU_MODE)
    return out


def load_current() -> dict[tuple[str, str], float]:
    """读取赛狐库存明细导出（可选），返回 {(仓库, SKU): 当前采购单价}。"""
    cands = [f for f in DATA_DIR.glob("*.xlsx") if "规则" not in f.name and not f.name.startswith("~$")]
    if not cands:
        print("库存明细: 未提供（跳过「前值」对照；比例/差额规则需自带 基准值）")
        return {}
    path = max(cands, key=lambda f: f.stat().st_mtime)
    df = pd.read_excel(path, dtype=str)
    wh_c = _pick_col(df, ["仓库", "warehouse", "收货仓库"])
    sku_c = _pick_col(df, ["SKU", "商品SKU", "commoditySku", "sku"])
    cost_c = _pick_col(df, ["采购单价", "perPurchase", "单位采购成本"])
    if not (wh_c and sku_c and cost_c):
        print(f"[警告] 库存明细 {path.name} 列名无法识别（需要 仓库/SKU/采购单价），已跳过前值对照。")
        return {}
    cur = {}
    for _, r in df.iterrows():
        wh, sku, c = str(r[wh_c]).strip().upper(), str(r[sku_c]).strip(), pd.to_numeric(r[cost_c], errors="coerce")
        if wh and sku and pd.notna(c):
            cur[(wh, sku)] = float(c)
    print(f"库存明细: {path.name}  ({len(cur)} 个 仓库+SKU 组合)")
    return cur


def compute_new_cost(row, current: dict) -> tuple[float | None, str]:
    kind, val = row["规则类型"], row["规则值"]
    base = row.get("基准值")
    if pd.isna(base):
        base = current.get((row["仓库"], row["SKU"]))
    if kind == "固定值":
        return _fmt(val), f"固定 {val}"
    if pd.isna(base):
        return None, "缺基准值（规则表未填 且 库存明细里没有该 仓库+SKU）"
    base = float(base)
    if kind == "按比例":
        return _fmt(base * val), f"{base} × {val}"
    if kind == "按差额":
        return _fmt(base - val), f"{base} − {val}"
    return None, f"未知规则类型 {kind}"


def validate(row) -> str | None:
    """返回跳过原因，或 None 表示可用。"""
    mode, doc_type = row["模式"], row.get("单据类型")
    if mode == SKU_MODE:
        if pd.isna(row["仓库"]):
            return "按SKU模式必须有「仓库」"
        return None
    # 按单据模式
    if pd.isna(doc_type):
        return "按单据模式必须有「单据类型」"
    if doc_type not in DOC_TYPES:
        return f"单据类型「{doc_type}」不在可选值内: {'/'.join(DOC_TYPES)}"
    if doc_type in NO_FEE_DOC_TYPES and row.get("单位费用") is not None and not pd.isna(row.get("单位费用")):
        return f"{doc_type} 不许填「单位费用/总费用」（赛狐会整行拒收）"
    return None


def write_import_files(bucket: dict[str, list[dict]], out_dir: Path, stamp: str) -> list[Path]:
    import openpyxl

    paths = []
    for mode, rows in bucket.items():
        tpl = TEMPLATES[mode]
        if not tpl.exists():
            raise SystemExit(f"[错误] 模板不存在: {tpl}")
        batches = [rows[i:i + MAX_ROWS] for i in range(0, len(rows), MAX_ROWS)]
        for bi, batch in enumerate(batches, 1):
            tag = "" if len(batches) == 1 else f"_p{bi}"
            path = out_dir / f"赛狐_成本补录单_{mode}_导入_{stamp}{tag}.xlsx"
            shutil.copy(tpl, path)          # 必须复制模板：含 data validation，重建表头会被拒
            wb = openpyxl.load_workbook(path)
            ws = wb["Sheet1"]
            ci = {}
            for cell in ws[1]:
                if cell.value is not None:
                    ci[norm_col(cell.value)] = cell.column

            def put(r, col, val):
                key = norm_col(col)
                if key not in ci:
                    raise SystemExit(f"[错误] {mode} 模板缺列「{col}」。实际: {[c.value for c in ws[1]]}")
                if val is not None and not pd.isna(val):
                    ws.cell(row=r, column=ci[key], value=val)

            for i, rec in enumerate(batch):
                r = 2 + i
                if mode == ORDER_MODE:
                    put(r, "单据号", rec["单据号"])
                    put(r, "单据类型", rec["单据类型"])
                    put(r, "SKU", rec["SKU"])
                else:
                    put(r, "仓库", rec["仓库"])
                    put(r, "SKU", rec["SKU"])
                put(r, "采购单价", rec["新采购单价"])
                # 按单据模式下，NO_FEE_DOC_TYPES 的单位费用已在 validate() 拦掉
                put(r, "单位费用", rec.get("单位费用"))
            wb.save(path)
            paths.append(path)
            print(f"  [{mode}] {len(batch)} 条 → {path.name}")
    return paths


def main():
    dry_run = "--dry-run" in sys.argv

    rules = load_rules()
    current = load_current()

    rows, skipped = [], []
    for _, r in rules.iterrows():
        reason = validate(r)
        if reason:
            skipped.append({"模式": r["模式"], "仓库": r["仓库"], "单据号": r["单据号"], "SKU": r["SKU"],
                            "单据类型": r["单据类型"], "跳过原因": reason})
            continue
        new_cost, why = compute_new_cost(r, current)
        if new_cost is None:
            skipped.append({"模式": r["模式"], "仓库": r["仓库"], "单据号": r["单据号"], "SKU": r["SKU"],
                            "单据类型": r["单据类型"], "跳过原因": why})
            continue
        if new_cost <= 0:
            skipped.append({"模式": r["模式"], "仓库": r["仓库"], "单据号": r["单据号"], "SKU": r["SKU"],
                            "单据类型": r["单据类型"], "跳过原因": f"算出的采购单价={new_cost} 不为正（赛狐视 0 为空）"})
            continue
        old = current.get((r["仓库"], r["SKU"]))
        rows.append({
            "模式": r["模式"], "仓库": r["仓库"], "单据号": r["单据号"], "单据类型": r["单据类型"], "SKU": r["SKU"],
            "规则类型": r["规则类型"], "规则值": r["规则值"],
            "原采购单价": old, "新采购单价": new_cost,
            "差额": round(new_cost - old, 4) if old is not None else None,
            "单位费用": None if pd.isna(r.get("单位费用")) else _fmt(r["单位费用"]),
            "计算说明": why,
        })

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_dir = OUT_BASE / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    cmp_path = out_dir / f"成本补录_对照_{stamp}.xlsx"
    with pd.ExcelWriter(cmp_path, engine="openpyxl") as w:
        pd.DataFrame(rows).to_excel(w, sheet_name="待导入", index=False)
        if skipped:
            pd.DataFrame(skipped).to_excel(w, sheet_name="跳过", index=False)
    print(f"\n对照表: {cmp_path}")
    mode_counts = pd.DataFrame(rows)["模式"].value_counts().to_dict() if rows else {}
    print(f"待导入 {len(rows)} 条 {mode_counts}, 跳过 {len(skipped)} 条")

    if skipped:
        print("\n跳过明细:")
        for s in skipped[:10]:
            print(f"  [{s['模式']}] {s.get('单据号') or s.get('仓库')}/{s['SKU']}: {s['跳过原因']}")

    if dry_run:
        print("\n[--dry-run] 不生成导入文件。")
        return
    if not rows:
        print("\n没有可导入的行，未生成导入文件。")
        return

    print("\n生成导入文件:")
    bucket: dict[str, list[dict]] = {}
    for rec in rows:
        bucket.setdefault(rec["模式"], []).append(rec)
    paths = write_import_files(bucket, out_dir, stamp)

    print(f"\n共 {len(paths)} 个文件 → {out_dir}")
    print("\n下一步（注意：导入后补录单是「待审核」，需在页面点「审核通过」才生效）:")
    for p in paths:
        print(f"  uv run python ../web_automation/scripts/dispatch.py sellfox.cost-adjust.import "
              f"--confirm-scope \"{p.name}\"")


if __name__ == "__main__":
    main()
