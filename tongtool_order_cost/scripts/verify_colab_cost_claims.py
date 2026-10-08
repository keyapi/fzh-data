# -*- coding: utf-8 -*-
"""复查 `docs/solutions/architecture-patterns/colab-cost-pipeline-current-state.md`
与 `colab-gsheet-inventory.md` 里的关键断言（可被独立复跑，不写任何 GS）。

用法（在仓库根）：
    GSPREAD_SERVICE_ACCOUNT_FILE=<父仓库>/secrets/gsheets-service-account.json \
      uv run python tongtool_order_cost/scripts/verify_colab_cost_claims.py

约定：
- 只读：不改 notebook、不写 Google Sheet；GS 读取带退避重试 + 落盘缓存（/tmp/gs_cache）。
- 输出 `[OK]/[FAIL]/[SKIP]`；任一 FAIL ⇒ 退出码 1。
- 断言里凡引用"档案"的，均指上述两份档案；改档案时同步改本脚本。
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import hashlib
import time

NOTEBOOK = pathlib.Path(
    r"G:/我的云端硬盘/Colab Notebooks/成本核算/透视表订单/处理通途订单/"
    r"20250409 合并en成本 测算成本核算20250110 尺寸提取 产品名称-品类 海外仓成本.ipynb"
)
CACHE = pathlib.Path("/tmp/gs_cache")
SX_BOOK = "15CjWsxoYt8fKtJaJIAdT-G_l6T6-2Np8hWtdh82vysk"  # 财务部绍兴成本核算表单2023
CFO_BOOK = "1UhFiMF9tLmndoOaz7PaEP_Fz1ZGYK9GVT6hiIYLM8Go"  # 和财务部共享

RESULTS: list[tuple[bool, str]] = []


def check(ok: bool, claim: str) -> None:
    RESULTS.append((ok, claim))
    print(f"  [{'OK' if ok else 'FAIL'}] {claim}")


def skip(claim: str) -> None:
    print(f"  [SKIP] {claim}")


# ---------------------------------------------------------------- notebook
def cells() -> list[str]:
    data = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    return ["".join(c.get("source", [])) for c in data["cells"]]


def active_source(text: str) -> str:
    # 去掉三引号块与以 # 开头的行，只留真正会执行的代码。
    text = re.sub(r'""".*?"""', "", text, flags=re.S)
    text = re.sub(r"'''.*?'''", "", text, flags=re.S)
    return "\n".join(l for l in text.splitlines() if not l.strip().startswith("#"))


def check_notebook() -> None:
    print("\n== Notebook 断言 ==")
    cs = cells()
    check(len(cs) == 227, "cell 数 == 227")

    # 只匹配"真会执行"的赋值（排除 `"""…"""` 块与注释行）——否则会命中已注释的
    # `gsheet_name_order = "2022年6月份销售报表"`（cell 66/111/128/144/195/199/214）。
    text = active_source("\n".join(cs))
    for lit, expect in [
        ("if_0_PL_cost", "注意-清零PL二次加工成本"),
        ("if_use_EN_cost_sxbzbcp", "注意-用EN绍兴包装半成品成本"),
        ("if_use_EN_cost_sxbzcp", "注意-用EN绍兴包装成品成本"),
        ("option_head_source", "头程用:头程运费合并替换EN"),
        ("if_use_test_cost", "正常-不用测算成本"),
        ("col_name_select_exchange_rate", "202607"),
    ]:
        m = re.findall(rf"{lit}\s*=\s*['\"]([^'\"]+)['\"]", text)
        check(bool(m) and m[-1] == expect, f"{lit} 当前字面量 == {expect!r}（实得 {m[-1:]!r}）")

    # gsheet_name_order 在 ≤4.8 的活跃赋值应为 通途订单202607（cell 36/56/138）
    act = [(i, mm.group(1)) for i, s in enumerate(cs[:145])
           for mm in re.finditer(r"^\s*gsheet_name_order\s*=\s*['\"]([^'\"]+)['\"]",
                                 active_source(s), re.M)]
    check(bool(act) and all(v == "通途订单202607" for _, v in act),
          f"cell 0–144 的活跃 gsheet_name_order 全为 '通途订单202607'（实得 {act}）")

    # cell 128 的 0.001 注入 + 月列
    c128 = cs[128]
    check("df_order_cost.loc[filter_condition, '二次加工成本'] = 0.001" in c128,
          "cell 128 存在 `二次加工成本 = 0.001` 注入")
    check("二次加工成本多月202511" in "".join(cs[111:128]),
          "cell 111 月列字面量含 二次加工成本多月202511")

    # cell 145 纪律
    check("不要运行4.6.1" in cs[145].replace(" ", ""),
          "cell 145 标题含「不要运行4.6.1」")

    # cell 135 白名单：源码为 `ls_col_order_keep = \` 换行后 `['订单号',`，收尾 `]` 在行内
    m = re.search(r"ls_col_order_keep\s*=\s*(?:\\\s*)?\[(.*?)\]", cs[135], re.S)
    if m:
        cols = re.findall(r"['\"]([^'\"]+)['\"]", m.group(1))
        check(len(cols) == 71, f"ls_col_order_keep 列数 == 71（实得 {len(cols)}）")
        check("EN绍兴包装半成品成本" not in cols and "EN绍兴包装成品成本" not in cols,
              "ls_col_order_keep 不含 EN绍兴包装半成品/成品成本（即非 FBA 侧会丢这两列）")
        check("运营部当月是否新品" in cols and "运营部当月是否为新品" not in cols,
              "ls_col_order_keep 用 '运营部当月是否新品'（少'为'），上游 cell 36/101 用 '运营部当月是否为新品'"
              " ⇒ 名称不一致：白名单那列被 reindex 造出恒 0，真实列被丢")
    else:
        check(False, "能解析 ls_col_order_keep")

    # cell 95 的未定义变量（静态）
    if "gsheet_name" in cs[95]:
        prior = "\n".join(cs[:95])
        check(not re.search(r"^\s*gsheet_name\s*=", prior, re.M),
              "cell 95 用到的 gsheet_name 未在 0–94 内赋值（静态）")

    # 两遍跑法
    check("df_order_cost_fba = df_order_cost.copy()" in "\n".join(cs[146:150]),
          "cell 146 附近存在 df_order_cost_fba = df_order_cost.copy()")


# ---------------------------------------------------------------- Google Sheets
_gc = None


def gc():
    global _gc
    if _gc is None:
        sys.path.insert(0, "tongtool_order_cost")
        from tongtool_order_cost.gsheets import client

        _gc = client()
    return _gc


def fetch(key: str, ws: str, rng: str | None = None, formulas: bool = False, tries: int = 10):
    """缓存优先；open_by_key 绕过 Drive 列表（见档案 §0 排错）。"""
    CACHE.mkdir(exist_ok=True)
    tag = hashlib.md5(f"{key}|{ws}|{rng}|{formulas}".encode()).hexdigest()[:12]
    f = CACHE / f"{tag}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    last = None
    for _ in range(tries):
        try:
            kw = {} if rng is None else {"range_name": rng}
            if formulas:
                kw["value_render_option"] = "FORMULA"
            g = gc()
            # 纯 ascii 且够长 ⇒ 视为 spreadsheet key（open_by_key 绕过 Drive 列表）；否则按标题
            sh = (g.open_by_key(key)
                  if re.fullmatch(r"[A-Za-z0-9_-]{24,}", key) else g.open(key))
            vals = sh.worksheet(ws).get_values(**kw)
            f.write_text(json.dumps(vals, ensure_ascii=False), encoding="utf-8")
            return vals
        except Exception as e:  # noqa: BLE001
            last = type(e).__name__
            time.sleep(4)
    print(f"  !! 读取失败 {key}/{ws}: {last}")
    return None


def col_index(header: list[str], name: str) -> int | None:
    return header.index(name) if name in header else None


def check_gs() -> None:
    print("\n== Google Sheets 断言（只读；缓存 /tmp/gs_cache）==")

    key2 = "二次加工成本2022"
    for ws, expect_total, expect_fallback in [
        ("绍兴二次加工成本", 903, 188),
        ("美国二次加工成本", 228, 40),
        ("波兰二次加工成本", 648, 112),
    ]:
        v = fetch(key2, ws)
        if v is None:
            skip(f"{ws} 行数/兜底")
            continue
        hdr = v[0]
        k = col_index(hdr, "品类尺寸面料编码")
        rows = [r for r in v[1:] if k is not None and k < len(r) and r[k].strip()]
        check(len(rows) == expect_total, f"二次加工成本2022/{ws} 数据行 == {expect_total}（实得 {len(rows)}）")
        # 兜底 = 键不在 import皮壳成本 或 EN 模板号为空
        imp = fetch(key2, "import皮壳成本")
        if imp is None:
            skip(f"{ws} 兜底数")
            continue
        m = {}
        for r in imp[1:]:
            if r and r[0].strip():
                m[r[0].strip()] = (r[1].strip() if len(r) > 1 else "")
        fb = sum(1 for r in rows if not m.get(r[k].strip()))
        check(fb == expect_fallback, f"{ws} 手填兜底 == {expect_fallback}（实得 {fb}）")

    v = fetch(key2, "importBOMCostList", "A1:A1", formulas=True)
    if v:
        check("EN产品BOM成本列表20260202!A:Y" in v[0][0],
              "importBOMCostList!A1 = IMPORTRANGE(EN产品BOM成本列表20260202!A:Y)")
    v = fetch(key2, "import皮壳成本", "A1:E2", formulas=True)
    if v:
        a1 = v[0][0] if v and v[0] else ""
        check("皮壳成本平均" in a1, "import皮壳成本!A1 = IMPORTRANGE(皮壳成本平均…!E:F)")
        joined = " ".join(x for row in v for x in row)
        check("importBOMCostList!$N:$N" in joined and "importBOMCostList!$Y:$Y" in joined,
              "import皮壳成本 用 INDEX(importBOMCostList!$N/$R/$X, MATCH(码, $Y)) 取 EN 值")

    sh = fetch(SX_BOOK, "皮壳成本平均202409-202410-202411（用于通途订单202502）", "A1:V3")
    if sh:
        hdr = sh[0]
        check(col_index(hdr, "当月给分公司发货类型") is not None,
              "旧表含列 当月给分公司发货类型")
        check(col_index(hdr, "EN重量模板物料号") is not None, "旧表含列 EN重量模板物料号（桥接键）")
    try:
        titles = [w.title for w in gc().open_by_key(SX_BOOK).worksheets()]
        check(len(titles) == 82, f"财务部绍兴成本核算表单2023 ws 数 == 82（实得 {len(titles)}）")
    except Exception as e:  # noqa: BLE001
        skip(f"ws 数（{type(e).__name__}）")

    # 通途订单202606：行/列恒等式
    book3 = "通途订单202606"
    counts = {}
    for ws, er, ec in [
        ("写回2026年6月订单", 7873, 166),
        ("写回2026年6月FBA订单", 1386, 95),
        ("写回2026年6月FBA订单和非FBA订单", 9259, 78),
    ]:
        v = fetch(book3, ws)
        if v is None:
            skip(f"{ws} 行列")
            continue
        data = [r for r in v[1:] if any(str(x).strip() for x in r)]
        counts[ws] = len(data)
        check(len(data) == er, f"{book3}/{ws} 行 == {er}（实得 {len(data)}）")
        check(len(v[0]) == ec, f"{book3}/{ws} 列 == {ec}（实得 {len(v[0])}）")
    if len(counts) == 3:
        check(counts["写回2026年6月订单"] + counts["写回2026年6月FBA订单"]
              == counts["写回2026年6月FBA订单和非FBA订单"],
              "行数恒等式：非FBA + FBA == 最终合并表")

    v = fetch(CFO_BOOK, "订单发货仓库对应成本来源")
    if v:
        rows = [r for r in v[1:] if any(str(x).strip() for x in r)]
        check(len(rows) == 47, f"订单发货仓库对应成本来源 数据行 == 47（+ 表头；实得 {len(rows)}）")
        check(len(v) == 48, f"订单发货仓库对应成本来源 get_all_values 行 == 48（含表头；实得 {len(v)}）")
        check(len(v[0]) == 8, f"订单发货仓库对应成本来源 列 == 8（实得 {len(v[0])}）")

    v = fetch(CFO_BOOK, "汇率", "A1:CZ3")
    if v:
        months = [c for c in v[0] if str(c).strip().isdigit() and len(str(c).strip()) == 6]
        check(len(months) == 50, f"汇率 月列数 == 50（实得 {len(months)}）")
        check("202606" in months and "202607" in months, "汇率 含 202606 与 202607 月列")


def main() -> int:
    if not NOTEBOOK.exists():
        print(f"找不到 notebook：{NOTEBOOK}")
        return 2
    check_notebook()
    check_gs()
    bad = [c for ok, c in RESULTS if not ok]
    print(f"\n=== 合计 {len(RESULTS)} 项，FAIL {len(bad)} ===")
    for c in bad:
        print(f"  FAIL: {c}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
