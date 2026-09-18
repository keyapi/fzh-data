"""
build_saihu_cost_adjust.py
生成赛狐「成本补录单」按SKU导入文件（仓库+SKU 维度改采购单价）

背景:
  赛狐里成本挂在「仓库 × SKU」维度。已入库库存要改采购单价，
  公开 OpenAPI 没有写入口，只能走 仓库 → 成本补录 → 成本补录单 → 导入成本补录单 → 按SKU导入。

数据流:
  激励成本规则.xlsx（仓库/SKU/规则类型/规则值）
    + 赛狐库存明细导出（可选，取当前采购单价做「前值」对照与比例/差额基准）
    → 复制官方模板 → 逐行填 *仓库/*SKU/采购单价 → 分批输出(≤5000条/文件)

使用:
  uv run python build_saihu_cost_adjust.py
  uv run python build_saihu_cost_adjust.py --dry-run    # 只出对照表，不生成导入文件
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
TEMPLATE_FILE = Path("数据源样例/赛狐_成本补录单_模板_按SKU.xlsx")

# 赛狐限制: 单个备货单/补录单导入文件最多 5000 条记录
MAX_ROWS = 5000

# 模板表头（官方模板固定 9 列，不可增删改）
TEMPLATE_HEADER = ["*仓库", "*SKU", "店铺", "FNSKU", "专属类型", "采购单价", "总货值", "单位费用", "总费用"]

# 规则类型别名 → 规范名
RULE_ALIASES = {
    "固定值": "固定值", "固定": "固定值", "fixed": "固定值",
    "按比例": "按比例", "比例": "按比例", "ratio": "按比例", "系数": "按比例",
    "按差额": "按差额", "差额": "按差额", "diff": "按差额",
}


# ── 工具函数 ──────────────────────────────────────────

def norm_col(name) -> str:
    """列名归一化：去空白/星号/全角符号，便于跨表匹配。"""
    s = str(name).strip()
    s = s.replace("（", "(").replace("）", ")").replace("＊", "*")
    s = re.sub(r"[\s　]+", "", s)
    return s.lstrip("*")


def _pick_col(df: pd.DataFrame, aliases: list[str]) -> str | None:
    """在 df 中按别名找列（归一化后比对）。"""
    lut = {norm_col(c): c for c in df.columns}
    for a in aliases:
        key = norm_col(a)
        if key in lut:
            return lut[key]
    return None


def _fmt(v) -> float:
    """金额统一保留 4 位小数（赛狐采购单价最多 4 位）。"""
    return round(float(v), 4)


# ── 数据加载 ──────────────────────────────────────────

def load_rules() -> pd.DataFrame:
    """读取激励成本规则表。必需列: 仓库 / SKU / 规则类型 / 规则值。可选: 基准值 / 单位费用 / 备注。"""
    files = [f for f in DATA_DIR.glob("*.xlsx") if "规则" in f.name and not f.name.startswith("~$")]
    if not files:
        raise SystemExit(f"[错误] {DATA_DIR}/ 下没找到规则表（文件名需含「规则」）。")
    path = max(files, key=lambda f: f.stat().st_mtime)
    df = pd.read_excel(path, dtype=str)
    print(f"规则表: {path.name}  ({len(df)} 行)")

    cols = {k: _pick_col(df, v) for k, v in {
        "仓库": ["仓库", "收货仓库", "warehouse"],
        "SKU": ["SKU", "商品SKU", "commoditySku", "sku"],
        "规则类型": ["规则类型", "类型", "rule"],
        "规则值": ["规则值", "值", "value"],
        "基准值": ["基准值", "基准", "base"],
        "单位费用": ["单位费用", "单个头程费用", "头程", "perFee"],
    }.items()}

    for need in ("仓库", "SKU", "规则类型", "规则值"):
        if not cols.get(need):
            raise SystemExit(f"[错误] 规则表缺少必填列「{need}」。实际列: {list(df.columns)}")

    out = pd.DataFrame({
        "仓库": df[cols["仓库"]].astype(str).str.strip(),
        "SKU": df[cols["SKU"]].astype(str).str.strip(),
        "规则类型": df[cols["规则类型"]].astype(str).str.strip().map(
            lambda x: RULE_ALIASES.get(x, RULE_ALIASES.get(x.lower(), None))),
        "规则值": pd.to_numeric(df[cols["规则值"]], errors="coerce"),
        "基准值": pd.to_numeric(df[cols["基准值"]], errors="coerce") if cols.get("基准值") else pd.NA,
        "单位费用": pd.to_numeric(df[cols["单位费用"]], errors="coerce") if cols.get("单位费用") else pd.NA,
    })

    bad = out[out["规则类型"].isna()]
    if len(bad):
        raise SystemExit(f"[错误] 有 {len(bad)} 行规则类型无法识别（支持 固定值/按比例/按差额）。示例: {bad['规则类型'].head(3).tolist()}")
    badv = out[out["规则值"].isna()]
    if len(badv):
        raise SystemExit(f"[错误] 有 {len(badv)} 行规则值不是数字。示例: {badv[['SKU','规则值']].head(3).to_dict('records')}")

    out["仓库"] = out["仓库"].str.upper()
    return out


def load_current() -> dict[tuple[str, str], float]:
    """读取赛狐库存明细导出（可选），返回 {(仓库, SKU): 当前采购单价}。

    导出由 `dispatch.py sellfox.stock.export` 产生，列名可能中英混排，按别名匹配。
    找不到文件时返回空 dict —— 此时「按比例/按差额」规则必须自带 基准值。
    """
    cands = [f for f in DATA_DIR.glob("*.xlsx")
             if "规则" not in f.name and not f.name.startswith("~$")]
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
        print(f"       实际列: {list(df.columns)[:15]}")
        return {}
    cur = {}
    for _, r in df.iterrows():
        wh = str(r[wh_c]).strip().upper()
        sku = str(r[sku_c]).strip()
        c = pd.to_numeric(r[cost_c], errors="coerce")
        if wh and sku and pd.notna(c):
            cur[(wh, sku)] = float(c)
    print(f"库存明细: {path.name}  ({len(cur)} 个 仓库+SKU 组合)")
    return cur


# ── 计算 ──────────────────────────────────────────────

def compute_new_cost(row, current: dict) -> tuple[float | None, str]:
    """返回 (新采购单价, 说明)。无法计算时返回 (None, 原因)。"""
    wh, sku, kind, val = row["仓库"], row["SKU"], row["规则类型"], row["规则值"]
    base = row.get("基准值")
    if pd.isna(base):
        base = current.get((wh, sku))

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


# ── 输出 ──────────────────────────────────────────────

def write_import_files(rows: list[dict], out_dir: Path, stamp: str) -> list[Path]:
    """复制模板 → 按列名定位列号 → 填 *仓库/*SKU/采购单价(+/单位费用) → 分批保存。"""
    import openpyxl

    paths = []
    batches = [rows[i:i + MAX_ROWS] for i in range(0, len(rows), MAX_ROWS)]
    for bi, batch in enumerate(batches, 1):
        tag = "" if len(batches) == 1 else f"_p{bi}"
        path = out_dir / f"赛狐_成本补录单_导入_{stamp}{tag}.xlsx"
        shutil.copy(TEMPLATE_FILE, path)
        wb = openpyxl.load_workbook(path)
        ws = wb["Sheet1"]

        # 按表头文字定位列号（不硬编码列序）
        ci = {}
        for cell in ws[1]:
            if cell.value is not None:
                ci[norm_col(cell.value)] = cell.column
        for col in TEMPLATE_HEADER:
            if norm_col(col) not in ci:
                raise SystemExit(f"[错误] 模板缺少列「{col}」。实际: {[c.value for c in ws[1]]}")

        for i, r in enumerate(batch):
            row_idx = 2 + i
            ws.cell(row=row_idx, column=ci[norm_col("*仓库")], value=r["仓库"])
            ws.cell(row=row_idx, column=ci[norm_col("*SKU")], value=r["SKU"])
            ws.cell(row=row_idx, column=ci[norm_col("采购单价")], value=r["新采购单价"])
            if r.get("单位费用") is not None:
                ws.cell(row=row_idx, column=ci[norm_col("单位费用")], value=r["单位费用"])

        wb.save(path)
        paths.append(path)
        print(f"  {len(batch)} 条 → {path.name}")
    return paths


def main():
    dry_run = "--dry-run" in sys.argv

    if not TEMPLATE_FILE.exists():
        raise SystemExit(f"[错误] 模板不存在: {TEMPLATE_FILE}")

    rules = load_rules()
    current = load_current()

    rows, skipped = [], []
    for _, r in rules.iterrows():
        new_cost, why = compute_new_cost(r, current)
        if new_cost is None:
            skipped.append({"仓库": r["仓库"], "SKU": r["SKU"], "规则类型": r["规则类型"], "规则值": r["规则值"], "跳过原因": why})
            continue
        if new_cost <= 0:
            skipped.append({"仓库": r["仓库"], "SKU": r["SKU"], "规则类型": r["规则类型"], "规则值": r["规则值"], "跳过原因": f"算出的采购单价={new_cost} 不为正（赛狐将 0 视为空，不导入）"})
            continue
        old = current.get((r["仓库"], r["SKU"]))
        rows.append({
            "仓库": r["仓库"], "SKU": r["SKU"],
            "规则类型": r["规则类型"], "规则值": r["规则值"],
            "新采购单价": new_cost,
            "原采购单价": old,
            "差额": round(new_cost - old, 4) if old is not None else None,
            "单位费用": None if pd.isna(r.get("单位费用")) else _fmt(r["单位费用"]),
            "计算说明": why,
        })

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_dir = OUT_BASE / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    # 对照表（人工复核用，也是导入前后比对的依据）
    cmp_path = out_dir / f"成本补录_对照_{stamp}.xlsx"
    with pd.ExcelWriter(cmp_path, engine="openpyxl") as w:
        pd.DataFrame(rows).to_excel(w, sheet_name="待导入", index=False)
        if skipped:
            pd.DataFrame(skipped).to_excel(w, sheet_name="跳过", index=False)
    print(f"\n对照表: {cmp_path}")
    print(f"待导入 {len(rows)} 条, 跳过 {len(skipped)} 条")

    if skipped:
        print("\n跳过明细:")
        for s in skipped[:10]:
            print(f"  {s['仓库']}/{s['SKU']}: {s['跳过原因']}")

    if dry_run:
        print("\n[--dry-run] 不生成导入文件。")
        return

    if not rows:
        print("\n没有可导入的行，未生成导入文件。")
        return

    print("\n生成导入文件:")
    paths = write_import_files(rows, out_dir, stamp)
    print(f"\n共 {len(paths)} 个文件 → {out_dir}")
    print("\n下一步:")
    print(f"  uv run python ../web_automation/scripts/dispatch.py sellfox.cost-adjust.import "
          f"--confirm-scope \"{paths[0].name}\"")


if __name__ == "__main__":
    main()
