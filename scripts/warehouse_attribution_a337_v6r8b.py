# -*- coding: utf-8 -*-
"""B v6 r8b：仓库归属 A337（只读）—— r8 + 修 `订单证据明细.产品键` 方法对象污染。

r8b 相对 r8（唯一代码改动 + 一处新增强制校验）
- BUG(r8)：`_order_row()` 对 pandas Series 用 `r.product` 取到的是 `Series.prod`
  **方法对象**（`<bound method Series.prod of ...>`），污染 `订单证据明细.产品键` 2709 行；
  r8b 改为显式 `to_dict()` 后按键取值。
- 新增「全表扫描」构建期校验：写完工作簿后重读全部表，统计 ASCII 字面 East/Central
  与裸仓侧值（美东/美中，`旧市场原值` 为源历史原值除外）命中数，必须为 0。

r8 相对 r7（r7 其余已通过项保持不变）
- N3 own2025 平局裁决闭环：`break_own2025_tie()` 先比**最后有效销售日**，
  再查**正确形态 DN**（皮壳 PK# / 成品），仍平局才出 `us_owner_conflict` 卡
  并保留**逐笔时间线**（订单行 + DN 行）。`--selftest` 跑 3 个内存测试：
  ①两侧 2026 都有 DN（不得短路）、②own2025 平局→最后销售日、③DN 也平局→冲突卡。
- N5 证据行级可回放：
  * 库存证据带 `source_hash + source_row_id(parquet 1基行号) + snapshot_date +
    warehouse_name + raw_sku + available`；
  * DN 证据带 `DN Item.name/docstatus/is_return/so_detail/posting_date/customer/
    item_code/qty`——本地 DN 明细**没有**的字段一律标 `missing`，不伪造；
  * 旧151/未证13 逐行按「旧EN×旧市场」引用真实订单行/DN号/库存源行，不再只写产品键；
    `证据强度` 明确 stock_placement = 低置信。
- 血缘：工作簿由本脚本重新生成；输出 `manifest.json`（输入 SHA、输出 SHA、行数、
  规则版本 r8、生成时间、脚本 SHA）并给 r7→r8 差异摘要（`r7_r8差异` 表 + 报告）。

保持 r7 已通过（不得回退）：共享订单池只入池、多件后缀乘 N、星球整组 1:1、
级联 own90→own180→own2026→DN2026→DN2025→own2025→库存、命名 美东USNJ/美中USTX、
A 覆盖 2337、需求行 1914、④冲突 0、待审 0、East/Central 裸值 0。

只读：不写 EN / 通途 / 不发消息 / 不 push。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

B = "D:/Work/fzh-order-store"
RULES_VERSION = "B-v6-rules-2026-10-30-r8b"

CUSTOMER_REGION = {"CENTRADE": ("US", "East"), "DANEEY": ("US", "Central"),
                   "波兰公司": ("PL", None)}
SIDE_CN = {"East": "美东USNJ（美东-CENTRADE）", "Central": "美中USTX（美中-FZH-DANEEY）"}
SIDE_LABEL = {"East": "美东USNJ", "Central": "美中USTX"}
MARKET_LABEL = {("US", "East"): "美国·美东", ("US", "Central"): "美国·美中",
                ("PL", None): "波兰"}
MARKET_CN = {"美东": "East", "美中": "Central", "波兰": None}
# N4：统一级联（DN 内先 2026 再 2025，均先于 own2025）
TIERS_ORDER = ("own90", "own180", "own2026", "dn2026", "dn2025", "own2025",
               "stock_placement")
STRIP = ("删除", "~", "?", "？")
PIECE_RE = re.compile(r"(\d+)\s*(?:PCS|PC)$", re.I)
DEMAND_FORM_PRIORITY = ("成品", "皮壳", "独立海绵", "套件", "主体骨架")

# UOM-CANONICAL §2.1 的 uom_exception_map（**组级**）：
# EN 物料组 `星球抱枕`（KS0019）整组 1:1，不按后缀乘 N；库存与销量都 1:1；
# 老产品默认不补（待业务确认，不硬删行）。
EXCEPTION_GROUPS = ("星球抱枕",)
EXCEPTION_SKUS: set[str] = set()       # main 从 A 该组来源码填充
EXCEPTION_PRODUCTS: set[str] = set()   # 该组对应的产品键
OLD_PRODUCT_NOTE = "老产品-默认不补(待确认)"
EXCEPTION_SKU_PATTERNS = (
    re.compile(r"^xingqiu-", re.I),
    re.compile(r"^tt0009", re.I),
    re.compile(r"^stppw-13", re.I),
)
# N3：正确形态 DN 的口径（皮壳 → PK#；成品 → 非 PK#；海绵随成品/皮壳出货）
DN_FORM_OF = {"成品": ("成品",), "皮壳": ("皮壳",), "套件": ("套件",),
              "独立海绵": ("成品", "皮壳"), "主体骨架": ("成品",)}

MISSING = "missing"
MISSING_NOTE = ("本地 DN 明细快照仅有 dn/posting_date/customer/item_code/"
                "customer_item_code/qty/uom/so，本字段不在快照内，标 missing 不伪造")

PROD_FORMS: dict[str, list[str]] = {}   # main 填充；供正确形态 DN 判定


def side_text(raw) -> str:
    if raw is None or isinstance(raw, float):
        return ""
    return ";".join(SIDE_LABEL.get(x.strip(), x.strip())
                    for x in str(raw).split(";") if x.strip())


def side_cn_name(cn: str) -> str:
    """N6：现行仓侧列统一显示名。"""
    return {"美东": "美东USNJ", "美中": "美中USTX", "波兰": "波兰"}.get(cn, cn)


def sha256(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def norm_code(c) -> str:
    s = str(c).strip().replace(" ", "")
    changed = True
    while changed:
        changed = False
        for pre in STRIP:
            if s.startswith(pre):
                s = s[len(pre):].strip().replace(" ", "")
                changed = True
    return s.casefold()


def pieces_per_unit(sku, form: str = "") -> tuple[int, str]:
    """N2：显式 PCS/PC 后缀默认乘 N；裸 -2/-3 不推；Bundle/TJ# 按套不拆。"""
    s = str(sku)
    n_key = norm_code(s)
    if n_key in EXCEPTION_SKUS or any(p.search(s) for p in EXCEPTION_SKU_PATTERNS):
        return 1, "组级例外：EN物料组=星球抱枕（KS0019）整组 1:1（UOM-CANONICAL §2.1）"
    if form == "套件" or s.upper().startswith("TJ#"):
        return 1, "Bundle/TJ# 按套，不二次拆倍"
    m = PIECE_RE.search(s.strip())
    if m:
        n = int(m.group(1))
        if n > 1:
            return n, f"显式多件后缀 {m.group(0)}"
    return 1, "无显式多件后缀（裸 -N 不推倍数）"


def _ppu_ignore_exception(sku) -> int:
    """若**不**套用组级例外，该 SKU 会乘几倍（用于统计 r7 退回的数量）。"""
    s = str(sku)
    if form_like_tj(s):
        return 1
    m = PIECE_RE.search(s.strip())
    if m:
        n = int(m.group(1))
        return n if n > 1 else 1
    return 1


def form_like_tj(s: str) -> bool:
    return s.upper().startswith("TJ#")


def strip_pk(en: str) -> str:
    s = str(en).strip()
    return s[3:] if s.startswith("PK#") else s


def merge60(en: str) -> str:
    m = re.match(r"^(KS0248|KS0001)-(.*-)?60(-.*)$", str(en))
    return f"KS0248-{m.group(2) or ''}60{m.group(3)}" if m else str(en)


def product_of(en: str) -> str:
    return merge60(strip_pk(en))


def side_of_warehouse(w) -> str:
    s = str(w)
    if "CENTRADE" in s:
        return "美东"
    if "DANEEY" in s:
        return "美中"
    if "Poland" in s or "波兰" in s:
        return "波兰"
    return "其他"


def form_of(en: str, role: str, ship_type: str) -> tuple[str, str]:
    raw = (ship_type or "").strip()
    if str(en).startswith("ND#") or role == "内胆":
        return "内胆", raw or "内胆"
    if str(en).startswith("TJ#") or role == "套件":
        return "套件", raw or "套件"
    if str(en).startswith("PK#") or role == "皮壳":
        return "皮壳", raw or "皮壳"
    if role in ("海绵", "海绵/关联成品"):
        if raw in ("皮壳", "半成品"):
            return "皮壳", raw
        if raw == "成品":
            return "成品", raw
        return "独立海绵", raw or "海绵（发货方式未取，item_group 快照无该组）"
    if role == "主体骨架":
        return "主体骨架", raw or "成品"
    return "成品", raw or "成品"


def dn_form_of(item_code: str) -> str:
    """DN 行供货形态（与 form_of 同口径，供 N3 正确形态 DN 判定）。"""
    s = str(item_code)
    if s.startswith("ND#"):
        return "内胆"
    if s.upper().startswith("TJ#"):
        return "套件"
    if s.startswith("PK#"):
        return "皮壳"
    return "成品"


def demand_form_of(prod: str) -> str:
    forms = [f for f in PROD_FORMS.get(prod, ["成品"]) if f != "内胆"]
    return next((f for f in DEMAND_FORM_PRIORITY if f in forms),
                forms[0] if forms else "成品")


def build_code_index(a_final: Path, customer_codes: Path, sku_map: Path) -> dict:
    idx: dict[str, str] = {}

    def add(code, en):
        n = norm_code(code)
        if n and n not in ("nan", "none") and n not in idx:
            idx[n] = en

    u = pd.read_excel(a_final, sheet_name="活跃宇宙")
    for r in u[u["活跃分类"] != "不活跃"].itertuples(index=False):
        raw = getattr(r, "来源码")
        if isinstance(raw, str):
            for tok in re.split(r"[,;，]", raw):
                add(tok, r[0])
    cc = pd.read_csv(customer_codes, dtype=str)
    deleted = []
    for r in cc.itertuples(index=False):
        for c in str(r.customer_code).split(","):
            c = c.strip()
            if c:
                (deleted.append((c[2:], r.name)) if c.startswith("删除") else add(c, r.name))
    sm = pd.read_csv(sku_map, sep="\t", dtype=str).iloc[:, :2]
    sm.columns = ["en", "tt"]
    for r in sm.dropna().itertuples(index=False):
        add(r.tt, r.en)
    for c, en in deleted:
        add(c, en)
    return idx


def side_facts(prod, region, ord26, ord25, dn_facts) -> dict:
    o26 = ord26[(ord26["product"] == prod) & (ord26["region"] == region)]
    o25 = ord25[(ord25["product"] == prod) & (ord25["region"] == region)]
    d26 = dn_facts[(dn_facts["product"] == prod) & (dn_facts["region"] == region)
                   & (dn_facts["year"] == 2026)]
    d25 = dn_facts[(dn_facts["product"] == prod) & (dn_facts["region"] == region)
                   & (dn_facts["year"] == 2025)]
    sides = ["East", "Central"] if region == "US" else [None]
    out = {}
    for side in sides:
        def pick(frame, col):
            if not len(frame):
                return 0.0
            sel = frame[frame["side"].isna()] if side is None else frame[frame["side"] == side]
            return float(pd.to_numeric(sel[col], errors="coerce").fillna(0).sum()) if len(sel) else 0.0
        out[side] = dict(own90=pick(o26, "90天"), own180=pick(o26, "180天"),
                         own2026=pick(o26, "2026"), own2025=pick(o25, "2025"),
                         dn2026_count=pick(d26, "DN笔数"), dn2026_qty=pick(d26, "DN供货量"),
                         dn2025_count=pick(d25, "DN笔数"), dn2025_qty=pick(d25, "DN供货量"))
    return out


def tier_of(f: dict) -> str | None:
    """N4：与 TIERS_ORDER 完全一致：own90→own180→own2026→dn2026→dn2025→own2025。"""
    if f["own90"] > 0:
        return "own90"
    if f["own180"] > 0:
        return "own180"
    if f["own2026"] > 0:
        return "own2026"
    if f["dn2026_count"] > 0:
        return "dn2026"
    if f["dn2025_count"] > 0:
        return "dn2025"
    if f["own2025"] > 0:
        return "own2025"
    return None


def decide_region(prod, region, ord26, ord25, dn_facts, own_stock, shared_stock):
    facts = side_facts(prod, region, ord26, ord25, dn_facts)
    tiers = {s: tier_of(f) for s, f in facts.items() if tier_of(f)}
    if tiers:
        best = min(tiers.values(), key=TIERS_ORDER.index)
        status = ("observed_current" if best in ("own90", "own180", "own2026", "dn2026")
                  else "observed_historical")
        agg = {k: sum(f[k] for f in facts.values()) for k in
               ("own90", "own180", "own2026", "own2025", "dn2026_count", "dn2026_qty",
                "dn2025_count", "dn2025_qty")}
        per = {}
        for side, f in facts.items():
            key = "PL" if side is None else side
            per[f"v2026_{key}"] = f["own2026"]
            per[f"v2025_{key}"] = f["own2025"]
        return dict(product=prod, region=region, tier=best, market_status=status,
                    sides_with_evidence=";".join(sorted(str(s) for s in tiers)),
                    stock_own=0.0, stock_shared_pool=0.0, stock_note="", **agg, **per)

    own = own_stock.get(prod, {})
    shr = shared_stock.get(prod, {})
    base = dict(product=prod, region=region, own90=0.0, own180=0.0, own2026=0.0, own2025=0.0,
                dn2026_count=0, dn2026_qty=0.0, dn2025_count=0, dn2025_qty=0.0)
    if region == "PL":
        q_own, q_shr = float(own.get("波兰", 0.0)), float(shr.get("波兰", 0.0))
        if q_own > 0 or q_shr > 0:
            return dict(base, tier="stock_placement", market_status="stock_placement",
                        sides_with_evidence="波兰", v2026_PL=0.0, v2025_PL=0.0,
                        stock_own=q_own, stock_shared_pool=q_shr,
                        stock_note="shared_pool" if q_shr and q_own == 0 else "")
    else:
        e_own, c_own = float(own.get("美东", 0.0)), float(own.get("美中", 0.0))
        e_shr, c_shr = float(shr.get("美东", 0.0)), float(shr.get("美中", 0.0))
        if (e_own + e_shr + c_own + c_shr) > 0:
            return dict(base, tier="stock_placement", market_status="stock_placement",
                        sides_with_evidence=";".join(
                            k for k, v in (("East", e_own + e_shr),
                                           ("Central", c_own + c_shr)) if v > 0),
                        v2026_East=0.0, v2026_Central=0.0, v2025_East=0.0, v2025_Central=0.0,
                        stock_own=e_own + c_own, stock_shared_pool=e_shr + c_shr,
                        stock_note="shared_pool" if (e_shr or c_shr) and not (e_own or c_own) else "")
    return None


def _fmt(d):
    if d is None or (isinstance(d, float) and pd.isna(d)):
        return ""
    return d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)


def dn_dates_by_side(prod, region, dn_year) -> dict:
    """按年返回 {side: [date,...]}。"""
    if dn_year is None or not len(dn_year):
        return {}
    sel = dn_year[(dn_year["product"] == prod) & (dn_year["region"] == region)]
    return {side: sorted(g["posting_date"].tolist()) for side, g in sel.groupby("side")}


def _last_sale(records) -> pd.Timestamp | None:
    dates = [r["date"] for r in (records or ()) if r.get("date") is not None and r.get("qty", 0) > 0]
    return max(dates) if dates else None


def break_own2025_tie(prod, facts, own25_by_side, dn_by_side, demand_form):
    """N3：own2025 量平局时的唯一裁决实现（r7 只按排序首项，缺契约）。

    顺序：①量（非平局直接判）→ ②最后有效销售日 → ③正确形态 DN（皮壳 PK#/成品）
    → ④仍平局：返回 us_owner_conflict 卡（带逐笔时间线）。
    返回 (owner, basis, conflict) 或 None（两侧均无 own2025）。
    """
    q = {s: facts[s]["own2025"] for s in facts if facts[s]["own2025"] > 0}
    if not q:
        return None
    top = max(q.values())
    tied = sorted([s for s, v in q.items() if v == top])
    if len(tied) == 1:
        if len(q) == 1:
            s = tied[0]
            return s, f"own2025 单侧有量（{SIDE_CN[s]}）", None
        s = tied[0]
        (other,) = [x for x in q if x != s]
        return s, (f"own2025 量较高（{SIDE_CN[s]} {q[s]:g} vs "
                   f"{SIDE_CN[other]} {q[other]:g}）"), None

    own25_by_side = own25_by_side or {}
    dn_by_side = dn_by_side or {}
    qty_txt = ";".join(f"{SIDE_CN[s]} {q[s]:g}" for s in tied)

    # ② 最后有效销售日期
    last = {s: _last_sale(own25_by_side.get(s)) for s in tied}
    have_d = {s: d for s, d in last.items() if d is not None}
    if len(have_d) == 1:
        (s,) = have_d
        return s, (f"own2025 平局（{qty_txt}）→ 仅 {SIDE_CN[s]} 有有效销售日 "
                   f"{_fmt(have_d[s])}"), None
    if len(have_d) > 1:
        later = max(have_d.values())
        latest = [s for s, d in have_d.items() if d == later]
        if len(latest) == 1:
            s = latest[0]
            other = [x for x in have_d if x != s]
            return s, (f"own2025 平局（{qty_txt}）→ 最后有效销售日较晚 {SIDE_CN[s]} "
                       f"{_fmt(later)}（另一侧 "
                       + "、".join(f"{SIDE_CN[o]} {_fmt(have_d[o])}" for o in other)
                       + "）"), None

    # ③ 正确形态 DN（皮壳 PK# / 成品）
    forms = DN_FORM_OF.get(demand_form, ("成品",))
    dn_side = {s: [r for r in (dn_by_side.get(s) or ())
                   if str(r.get("form", "")) in forms] for s in tied}
    dn_last = {s: max((r["posting_date"] for r in rs), default=None)
               for s, rs in dn_side.items()}
    dn_last = {s: d for s, d in dn_last.items() if d is not None}
    if len(dn_last) == 1:
        (s,) = dn_last
        return s, (f"own2025 与最后销售日均平局→仅 {SIDE_CN[s]} 有正确形态 DN"
                   f"（{'/'.join(forms)}，{len(dn_side[s])} 笔，末笔 {_fmt(dn_last[s])}）"), None
    if len(dn_last) > 1:
        later = max(dn_last.values())
        latest = [s for s, d in dn_last.items() if d == later]
        if len(latest) == 1:
            s = latest[0]
            return s, (f"own2025/销售日平局→正确形态 DN 较晚 {SIDE_CN[s]} "
                       f"{_fmt(later)}（{'/'.join(forms)}）"), None

    # ④ 仍平局：冲突卡 + 逐笔时间线
    timeline = []
    for s in tied:
        for r in sorted(own25_by_side.get(s) or (), key=lambda x: x.get("date") or pd.Timestamp.min):
            timeline.append(f"{SIDE_LABEL[s]} 订单 {r.get('line_id', '')}/{r.get('sku', '')}"
                            f"×{r.get('qty', 0):g}/{_fmt(r.get('date'))}")
        for r in sorted(dn_side.get(s) or (), key=lambda x: x.get("posting_date") or pd.Timestamp.min):
            timeline.append(f"{SIDE_LABEL[s]} DN {r.get('dn', '')}/{_fmt(r.get('posting_date'))}"
                            f"/{r.get('item_code', '')}×{r.get('qty', 0):g}")
    return "未定", (f"own2025 平局且最后销售日/正确形态 DN（{'/'.join(forms)}）均平局"
                    " → us_owner_conflict（保留逐笔时间线）"), dict(
        原因="us_owner_conflict：own2025 两侧等量，最后有效销售日与正确形态 DN 均无法决胜",
        两侧=qty_txt + ("；最后销售日 " + "、".join(
            f"{SIDE_CN[s]} {_fmt(last.get(s))}" for s in tied)),
        时间线="｜".join(timeline))


def pick_us_owner(prod, ord26, ord25, dn_facts, dn=None, own_stock=None, shared_stock=None,
                  own25_records=None, demand_form=None, dn_records=None):
    """N3/N4：own90→own180→own2026→DN2026→DN2025→own2025（平局走 break_own2025_tie）→库存。"""
    facts = side_facts(prod, "US", ord26, ord25, dn_facts)
    for key in ("own90", "own180", "own2026"):
        pos = {s: facts[s][key] for s in facts if facts[s][key] > 0}
        if len(pos) == 1:
            s = list(pos)[0]
            return s, f"{key} 单侧有量（{SIDE_CN[s]}）", None
        if len(pos) > 1:
            top = sorted(pos.items(), key=lambda kv: -kv[1])
            if top[0][1] > top[1][1]:
                return (top[0][0], f"{key} 量较高（{SIDE_CN[top[0][0]]} {top[0][1]:g} vs "
                                   f"{SIDE_CN[top[1][0]]} {top[1][1]:g}）", None)
            return "未定", f"{key} 两侧等量", dict(
                原因=f"{key} 两侧等量且无迁移记录",
                两侧=";".join(f"{SIDE_CN[s]} {v:g}" for s, v in top))

    # ---- DN：先 2026，再 2025（N4 顺序）
    for yr in (2026, 2025):
        sub = dn[dn["year"] == yr] if dn is not None and len(dn) else None
        dates = dn_dates_by_side(prod, "US", sub)
        if not dates:
            continue
        label = f"DN{yr}"
        if len(dates) == 1:
            s = list(dates)[0]
            return s, f"唯一美国 {label} 仓：{SIDE_CN[s]}（{len(dates[s])} 笔）", None
        span = {s: (v[0], v[-1]) for s, v in dates.items()}
        if yr == 2026:
            # N3：只有「另一侧最后日期 ≤2025」才可直接判；两侧都有 2026 必须继续判定
            has25 = {s: bool(dn_dates_by_side(prod, "US", dn[dn["year"] == 2025])
                             .get(s)) for s in span}
            only_here = [s for s in span if not has25[s]]
            if len(only_here) == 1:
                other = [s for s in span if s != only_here[0]][0]
                if not dn_dates_by_side(prod, "US", dn[dn["year"] == 2025]).get(other):
                    return (only_here[0],
                            f"{SIDE_CN[only_here[0]]} 有 2026 DN，{SIDE_CN[other]} 止于 2025"
                            "（2025 侧保留历史）", None)
        order = sorted(span.items(), key=lambda kv: kv[1][1])
        (s_early, (_, e1)), (s_late, (l0, _)) = order[0], order[1]
        if e1 < l0:
            return (s_late, f"inferred_migration：{SIDE_CN[s_early]} 止于 {_fmt(e1)}，"
                            f"{SIDE_CN[s_late]} 自 {_fmt(l0)} 起（迁移日=新仓首笔 DN）；"
                            "未经正式审批，置信中", None)
        return "未定", f"{label} 两仓时间交错", dict(
            原因=f"us_owner_conflict：{label} 内美东/美中 DN 时间交错且有量",
            两侧="; ".join(f"{SIDE_CN[s]}：" + "、".join(_fmt(x) for x in v)
                           for s, v in dates.items()))

    # ---- own2025（N3 平局：最后销售日 → 正确形态 DN → 冲突卡）
    tie = break_own2025_tie(prod, facts,
                            (own25_records or {}).get(prod, {}),
                            dn_records.get(prod, {}) if dn_records is not None
                            else (own25_dn_by_side(dn, prod)
                                  if dn is not None and len(dn) else {}),
                            demand_form or demand_form_of(prod))
    if tie:
        return tie

    own = own_stock.get(prod, {}) if own_stock else {}
    shr = shared_stock.get(prod, {}) if shared_stock else {}
    east = float(own.get("美东", 0.0)) + float(shr.get("美东", 0.0))
    central = float(own.get("美中", 0.0)) + float(shr.get("美中", 0.0))
    if east > 0 and central > 0:
        return "未定", "库存两侧都有货", dict(
            原因="us_owner_stock_conflict：美东USNJ 与 美中USTX 两侧都有库存，不自动选一侧",
            两侧=f"{SIDE_CN['East']} {east:g} 个；{SIDE_CN['Central']} {central:g} 个")
    if east > 0:
        return "East", "stock_placement（仅库存投放，低置信）", None
    if central > 0:
        return "Central", "stock_placement（仅库存投放，低置信）", None
    return "未定", "无任何美国证据", dict(原因="无任何美国订单/DN/库存证据")


def own25_dn_by_side(dn, prod) -> dict:
    """N3：该产品美国 DN 逐笔（含形态），供平局时查正确形态 DN。"""
    sub = dn[(dn["product"] == prod) & (dn["region"] == "US")]
    out: dict[str, list[dict]] = {}
    for r in sub.itertuples(index=False):
        if pd.isna(r.posting_date) or r.side not in ("East", "Central"):
            continue
        out.setdefault(r.side, []).append(dict(dn=r.dn, posting_date=r.posting_date,
                                               item_code=r.item_code, qty=float(r.qty),
                                               form=r.form))
    return out


# ============================ 内存测试（N3） ============================

def _ord_frame(qty_col):
    return pd.DataFrame(columns=["product", "region", "side", qty_col],
                        dtype=object).astype({qty_col: float})


def _dn_frame(rows) -> pd.DataFrame:
    cols = ["dn", "posting_date", "customer", "item_code", "qty", "year",
            "product", "region", "side", "form"]
    df = pd.DataFrame(rows, columns=cols)
    df["posting_date"] = pd.to_datetime(df["posting_date"])
    df["qty"] = df["qty"].astype(float)
    df["year"] = df["year"].astype(float)
    return df


def _dn_facts_of(df: pd.DataFrame) -> pd.DataFrame:
    """与主流程同口径的 DN 聚合（测试用）。"""
    if not len(df):
        return pd.DataFrame(columns=["product", "region", "side", "year",
                                     "DN笔数", "DN供货量"], dtype=object)
    out = (df.groupby(["product", "region", "side", "year"], dropna=False)
           .agg(DN笔数=("dn", "nunique"), DN供货量=("qty", "sum")).reset_index())
    out["side"] = out["side"].astype(object)
    return out


def test_both_sides_2026_dn():
    """① 两侧 2026 都有 DN：不得短路判本侧，交错 → us_owner_conflict。"""
    p = "TEST-BOTH-2026"
    ord26, ord25 = _ord_frame("90天").assign(**{"180天": []}), _ord_frame("2025")
    for c in ("180天", "2026"):
        ord26[c] = []
    dn = _dn_frame([
        ["DN-E1", "2026-03-01", "CENTRADE", "KS0001-T", 5, 2026, p, "US", "East", "成品"],
        ["DN-E2", "2026-08-01", "CENTRADE", "KS0001-T", 5, 2026, p, "US", "East", "成品"],
        ["DN-C1", "2026-05-01", "DANEEY", "KS0001-T", 5, 2026, p, "US", "Central", "成品"],
    ])
    owner, basis, conflict = pick_us_owner(p, ord26, ord25, _dn_facts_of(dn), dn=dn,
                                           own25_records={}, demand_form="成品")
    ok = (owner == "未定" and bool(conflict)
          and "us_owner_conflict" in str(conflict.get("原因", ""))
          and "时间交错" in basis and "止于 2025" not in basis)
    return "① 两侧2026都有DN→不短路", ok, f"owner={owner} basis={basis}"


def test_own2025_tie_last_sale_date():
    """② own2025 平局：比最后有效销售日，晚的一侧胜。"""
    p = "TEST-TIE-DATE"
    ord26 = _ord_frame("90天")
    for c in ("180天", "2026"):
        ord26[c] = []
    ord25 = pd.DataFrame([dict(product=p, region="US", side="East", **{"2025": 10.0}),
                          dict(product=p, region="US", side="Central", **{"2025": 10.0})])
    recs = {p: {"East": [dict(date=pd.Timestamp("2025-11-20"), qty=10.0, sku="TT1",
                             line_id="202511:1")],
                "Central": [dict(date=pd.Timestamp("2025-04-10"), qty=10.0, sku="TT2",
                                 line_id="202504:2")]}}
    owner, basis, conflict = pick_us_owner(p, ord26, ord25, _dn_facts_of(_dn_frame([])),
                                           dn=_dn_frame([]),
                                           own25_records=recs, demand_form="成品")
    ok = owner == "East" and conflict is None and "最后有效销售日" in basis
    return "② own2025平局→最后销售日", ok, f"owner={owner} basis={basis}"


def test_own2025_and_dn_tie_conflict():
    """③ own2025 平局 + 销售日平局 + 正确形态 DN 也平局 → 冲突卡 + 逐笔时间线。

    额外放一条**错误形态**（皮壳）DN 在 Central 且日期更晚：必须被忽略，
    否则说明未按「正确形态 DN（皮壳 PK#/成品）」判定。
    """
    p = "TEST-TIE-DN"
    facts = {"East": {"own2025": 10.0}, "Central": {"own2025": 10.0}}
    own25 = {"East": [dict(date=pd.Timestamp("2025-09-15"), qty=10.0, sku="TT1",
                           line_id="202509:1")],
             "Central": [dict(date=pd.Timestamp("2025-09-15"), qty=10.0, sku="TT2",
                              line_id="202509:2")]}
    dn_by_side = {
        "East": [dict(dn="DN-E9", posting_date=pd.Timestamp("2025-01-05"),
                      item_code="KS0001-T", qty=5.0, form="成品")],
        "Central": [dict(dn="DN-C9", posting_date=pd.Timestamp("2025-01-05"),
                         item_code="KS0001-T", qty=5.0, form="成品"),
                    dict(dn="DN-C8", posting_date=pd.Timestamp("2025-12-01"),
                         item_code="PK#KS0001-T", qty=5.0, form="皮壳")],
    }
    owner, basis, conflict = break_own2025_tie(p, facts, own25, dn_by_side, "成品")
    tl = str(conflict.get("时间线", "")) if conflict else ""
    ok = (owner == "未定" and bool(conflict)
          and "us_owner_conflict" in str(conflict.get("原因", ""))
          and "DN-E9" in tl and "DN-C9" in tl and "DN-C8" not in tl
          and "订单" in tl)
    return "③ DN也平局→冲突卡+时间线", ok, f"owner={owner} basis={basis} timeline={tl[:120]}"


def run_selftests() -> list[tuple[str, bool, str]]:
    return [test_both_sides_2026_dn(), test_own2025_tie_last_sale_date(),
            test_own2025_and_dn_tie_conflict()]


# ============================ 血缘 / 差异 ============================

def workbook_diff(old_path: Path, new_path: Path) -> dict:
    """r7→r8 工作簿差异：表增删、行/列变化、共有列逐格差异、汇总指标变化。"""
    o, n = pd.ExcelFile(old_path), pd.ExcelFile(new_path)
    so, sn = o.sheet_names, n.sheet_names
    out = {"r7_path": str(old_path), "r8_path": str(new_path),
           "r7_sha256": sha256(old_path), "r8_sha256": sha256(new_path),
           "r7_bytes": Path(old_path).stat().st_size,
           "r8_bytes": Path(new_path).stat().st_size,
           "sheets_only_r7": [s for s in so if s not in sn],
           "sheets_only_r8": [s for s in sn if s not in so],
           "sheet_diff": {}, "metrics_changed": []}
    for s in sn:
        if s not in so:
            continue
        a, b = pd.read_excel(o, sheet_name=s), pd.read_excel(n, sheet_name=s)
        common = [c for c in a.columns if c in b.columns]
        per_col, cell = {}, 0
        if len(a) == len(b) and common:
            for c in common:
                left = a[c].astype(str).fillna("")
                right = b[c].astype(str).fillna("")
                d = int((left != right).sum())
                if d:
                    per_col[c] = d
                    cell += d
        out["sheet_diff"][s] = dict(rows_r7=int(len(a)), rows_r8=int(len(b)),
                                    cols_r7=int(a.shape[1]), cols_r8=int(b.shape[1]),
                                    cols_added=[c for c in b.columns if c not in a.columns],
                                    cols_removed=[c for c in a.columns if c not in b.columns],
                                    cell_diff=cell, cell_diff_by_col=per_col)
    if "汇总" in so and "汇总" in sn:
        ma = dict(pd.read_excel(o, sheet_name="汇总").values.tolist())
        mb = dict(pd.read_excel(n, sheet_name="汇总").values.tolist())
        for k in mb:
            if k in ma and str(ma[k]) != str(mb[k]):
                out["metrics_changed"].append(dict(指标=k, r7=ma[k], r8=mb[k]))
        out["metrics_added"] = [k for k in mb if k not in ma]
        out["metrics_removed"] = [k for k in ma if k not in mb]
    return out


def diff_rows(d: dict) -> pd.DataFrame:
    rows = []
    for s, v in d.get("sheet_diff", {}).items():
        rows.append(dict(表=s, rows_r7=v["rows_r7"], rows_r8=v["rows_r8"],
                         cols_r7=v["cols_r7"], cols_r8=v["cols_r8"],
                         新增列="；".join(v["cols_added"]), 移除列="；".join(v["cols_removed"]),
                         逐格差异=v["cell_diff"],
                         差异列="；".join(f"{c} {n}"
                                         for c, n in v.get("cell_diff_by_col", {}).items())))
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["表", "逐格差异"])


def diff_summary(d: dict) -> str:
    L = [f"r7 `{d['r7_sha256'][:16]}…` → r8b `{d['r8_sha256'][:16]}…`；"
         f"表仅 r7 有 {len(d['sheets_only_r7'])} 个，仅 r8 有 {len(d['sheets_only_r8'])} 个"
         f"（{('、'.join(d['sheets_only_r8']) or '无')}）。"]
    for s, v in d["sheet_diff"].items():
        bits = []
        if v["rows_r7"] != v["rows_r8"]:
            bits.append(f"行 {v['rows_r7']}→{v['rows_r8']}")
        if v["cols_added"]:
            bits.append("新增列 " + "、".join(v["cols_added"][:6]) +
                        ("…" if len(v["cols_added"]) > 6 else ""))
        if v["cols_removed"]:
            bits.append("移除列 " + "、".join(v["cols_removed"][:6]))
        if v["cell_diff"]:
            top = sorted(v.get("cell_diff_by_col", {}).items(), key=lambda kv: -kv[1])
            bits.append(f"逐格差异 {v['cell_diff']}（" +
                        "、".join(f"{c} {n}" for c, n in top[:5]) + "）")
        if bits:
            L.append(f"- `{s}`：" + "；".join(bits))
    if d.get("metrics_added"):
        L.append("- 汇总新增指标：" + "、".join(d["metrics_added"]))
    if d.get("metrics_changed"):
        L.append("- 汇总指标变化：" + "；".join(
            f"{m['指标']} {m['r7']}→{m['r8']}" for m in d["metrics_changed"]))
    else:
        L.append("- 汇总指标无变化（主口径与 r7 完全一致）")
    return "\n".join(L)


def verify_evidence(main_tbl, old_recon, un13, dn_tbl, stk_tbl, ord_tbl,
                    dn_all, stk_all, g, sample_rows=10) -> dict:
    """N5 抽查回放：从证据行 → 源行号 → 原始文件逐字段比对（不改任何数据）。"""
    dn_raw = dn_all.set_index("src_row_id")
    stk_raw = stk_all.set_index("src_row_id")
    g_raw = g.set_index("src_row_id")
    by_id = {}
    for df in (dn_tbl, stk_tbl, ord_tbl):
        for rec in df.to_dict("records"):
            by_id[rec["证据ID"]] = rec

    def _same(a, b):
        try:
            return abs(float(a) - float(b)) < 1e-9
        except (TypeError, ValueError):
            return str(a) == str(b)

    def check(eid) -> tuple[bool, str]:
        rec = by_id.get(eid)
        if rec is None:
            return False, f"{eid} 未在明细表找到"
        rid = int(eid.split(":")[1])
        kind = eid.split(":")[0]
        if kind == "DN":
            src = dn_raw.loc[rid]
            ok = (_same(src["dn"], rec["DN单号"]) and str(src["item_code"]) == rec["item_code"]
                  and _same(src["qty"], rec["qty"])
                  and str(src["posting_date"])[:10] == rec["posting_date"]
                  and str(src["customer"]) == rec["customer"]
                  and rec["docstatus"] == MISSING and rec["is_return"] == MISSING)
            return ok, (f"DN#{rid} {rec['DN单号']}/{rec['item_code']}×{rec['qty']}/"
                        f"{rec['posting_date']}/{rec['customer']}（Item.name/docstatus/is_return="
                        f"{MISSING}）")
        if kind == "ST":
            src = stk_raw.loc[rid]
            ok = (str(src["sku"]) == rec["原始SKU"] and _same(src["available"], rec["available"])
                  and str(src["warehouse_name"]) == rec["仓库名"]
                  and str(src["snapshot_date"])[:10] == rec["快照日"]
                  and _same(rec["available"] * rec["pieces_per_unit"], rec["canonical_qty"]))
            return ok, (f"ST#{rid} {rec['原始SKU']}/{rec['仓库名']}/avail={rec['available']}"
                        f"×{rec['pieces_per_unit']}={rec['canonical_qty']}/{rec['快照日']}")
        src = g_raw.loc[rid]
        ok = (str(src["order_id"]) == rec["order_id"] and str(src["sku_tongtool"]) == rec["SKU"]
              and _same(src["qty"], rec["raw_qty"]) and str(src["line_id"]) == rec["line_id"]
              and str(src["sale_date"])[:10] == rec["sale_date"])
        return ok, (f"OR#{rid} {rec['SKU']}×{rec['raw_qty']}→{rec['qty']}/{rec['sale_date']}/"
                    f"{rec['仓侧']}/line={rec['line_id']}")

    def ids_of(*cells):
        out = []
        for c in cells:
            for x in str(c).split(";"):
                x = x.strip()
                if ":" in x and not x.startswith("…") and x not in out:
                    out.append(x)
        return out

    samples, seen_obj = [], set()

    def add_sample(tag, obj, ids):
        if (tag, obj) in seen_obj or not ids:
            return
        seen_obj.add((tag, obj))
        samples.append((tag, obj, ids))

    for _, r in main_tbl[main_tbl["是否需求行"] == "Y"].iterrows():
        add_sample("主表", r["产品键"], ids_of(r["证据入口"]))
        if sum(1 for t, *_ in samples if t == "主表") >= 4:
            break
    for _, r in old_recon.iterrows():
        add_sample("旧151", f"{r['旧EN物料']}@{r['旧市场原值']}",
                   ids_of(r["订单源行"], r["DN源行"], r["库存源行"]))
        if sum(1 for t, *_ in samples if t == "旧151") >= 4:
            break
    for _, r in un13.iterrows():
        add_sample("未证13", r["旧EN物料"],
                   ids_of(r["订单源行"], r["DN源行"], r["库存源行"]))
        if sum(1 for t, *_ in samples if t == "未证13") >= max(0, sample_rows - 8):
            break

    rows, n_ok, n_tot, seen_id = [], 0, 0, set()
    for tag, obj, ids in samples:
        for eid in ids[:4]:
            if eid in seen_id:
                continue
            seen_id.add(eid)
            ok, msg = check(eid)
            n_ok += int(ok)
            n_tot += 1
            rows.append(dict(抽查来源=tag, 对象=obj, 证据ID=eid, 回放通过="是" if ok else "否",
                             说明=msg))
    return dict(抽查行数=len(samples), 证据ID数=n_tot, 通过数=n_ok,
                全部通过=(n_ok == n_tot and n_tot > 0), 明细=rows)


BANNED_ALLOWED_COLS = ("旧市场原值",)   # 源历史原值，保留原样（r7 复审已允许）


def scan_banned_terms(path: Path) -> dict:
    """全表扫描：确实没有 ASCII 字面「东/西仓侧英文名」与裸仓侧中文值。

    用 chr() 拼出被禁字面，避免本函数/输出表自身命中（自查表不写被禁字符串）。
    """
    east, central = "E" + "ast", "C" + "entral"
    bare_east, bare_central = "美东", "美中"
    xl = pd.ExcelFile(path)
    per_sheet, tot = {}, dict(ascii_side=0, bare_side=0, allowed_exempt=0)
    for s in xl.sheet_names:
        d = pd.read_excel(xl, sheet_name=s)
        rows = []
        for c in d.columns:
            col = d[c].astype(str)
            a = int(col.str.contains(east, regex=False, na=False).sum()
                    + col.str.contains(central, regex=False, na=False).sum())
            b = int((col == bare_east).sum() + (col == bare_central).sum())
            if str(c) in BANNED_ALLOWED_COLS:
                tot["allowed_exempt"] += b
                rows.append(dict(表=s, 列=str(c), 英文字面命中=a, 裸仓侧值命中=b,
                                 说明="源历史原值列，豁免（裸值保留）"))
                tot["ascii_side"] += a
                continue
            if a or b:
                rows.append(dict(表=s, 列=str(c), 英文字面命中=a, 裸仓侧值命中=b,
                                 说明="禁止"))
            tot["ascii_side"] += a
            tot["bare_side"] += b
        if rows:
            per_sheet[s] = rows
    detail = [r for rs in per_sheet.values() for r in rs]
    return dict(英文字面命中=tot["ascii_side"], 裸仓侧命中=tot["bare_side"],
                豁免_旧市场原值裸值=tot["allowed_exempt"],
                通过=(tot["ascii_side"] == 0 and tot["bare_side"] == 0),
                明细=detail)


# ============================ 主流程 ============================

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="仓库归属 A337 v6 r8b")
    ap.add_argument("--a-final", default=f"{B}/analysis/SKU活跃宇宙_2026-10-29_FINAL.xlsx")
    ap.add_argument("--v5b", default=f"{B}/analysis/仓库归属_A337_v5b_2026-10-29.xlsx")
    ap.add_argument("--dn", default=f"{B}/analysis/leadtime/dn_items_with_customer_code.csv")
    ap.add_argument("--item-group", default=f"{B}/analysis/item_group_shipment_type_2026-10-28.csv")
    ap.add_argument("--stock", default=f"{B}/en_stock.parquet")
    ap.add_argument("--gs", default=f"{B}/gs_orders.parquet")
    ap.add_argument("--sku-map", default=f"{B}/sku_map.tsv")
    ap.add_argument("--customer-codes", default=f"{B}/analysis/en_item_customer_codes.csv")
    ap.add_argument("--out-xlsx", default=f"{B}/analysis/仓库归属_A337_v6r8b_2026-10-30.xlsx")
    ap.add_argument("--out-report", default=f"{B}/analysis/仓库归属_A337_v6r8b_2026-10-30_报告.md")
    ap.add_argument("--manifest", default=f"{B}/analysis/仓库归属_A337_v6r8b_manifest.json")
    ap.add_argument("--r7-xlsx", default=f"{B}/analysis/仓库归属_A337_v6r7_2026-10-30.xlsx")
    ap.add_argument("--r6-xlsx", default=f"{B}/analysis/仓库归属_A337_v6r6_2026-10-29.xlsx")
    ap.add_argument("--selftest", action="store_true", help="只跑 N3 内存测试")
    args = ap.parse_args(argv)

    if args.selftest:
        results = run_selftests()
        for name, ok, detail in results:
            print(f"[{'PASS' if ok else 'FAIL'}] {name}｜{detail}")
        failed = [n for n, ok, _ in results if not ok]
        print(f"\n{len(results) - len(failed)}/{len(results)} 通过")
        return 0 if not failed else 1

    inputs = {k: {"path": str(v), "sha256": sha256(v)} for k, v in (
        ("A_FINAL", args.a_final), ("V5B_BASE", args.v5b), ("DN", args.dn),
        ("ITEM_GROUP", args.item_group), ("EN_STOCK_10-28", args.stock),
        ("GS_ORDERS", args.gs), ("SKU_MAP", args.sku_map),
        ("CUSTOMER_CODES", args.customer_codes))}
    dn_sha = inputs["DN"]["sha256"]
    stk_sha = inputs["EN_STOCK_10-28"]["sha256"]
    gs_sha = inputs["GS_ORDERS"]["sha256"]

    # ---------- A 活跃宇宙
    uni = pd.read_excel(args.a_final, sheet_name="活跃宇宙")
    act = uni[uni["活跃分类"] != "不活跃"].copy()
    act["EN物料"] = act["EN物料"].astype(str)
    act["product"] = act["EN物料"].map(product_of)
    grp = pd.read_csv(args.item_group, dtype=str)
    ship_type = dict(zip(grp["name"].astype(str),
                         grp["custom_shipment_type_to_branch"].astype(str)))
    act["ship_type"] = act["物料组"].astype(str).map(ship_type).fillna("")
    pairs = [form_of(e, r, s) for e, r, s in
             zip(act["EN物料"], act["角色"], act["ship_type"])]
    act["form"] = [p[0] for p in pairs]
    act["raw_ship_mode"] = [p[1] for p in pairs]
    act["is_nd"] = act["form"] == "内胆"
    act["a_stock"] = pd.to_numeric(act["当前库存"], errors="coerce").fillna(0.0)

    bridge = {}
    for prod, mem in act[~act["is_nd"]].groupby("product")["EN物料"]:
        if [e for e in set(mem) if strip_pk(e) != prod]:
            bridge[prod] = sorted(set(mem))

    products = sorted(set(act.loc[~act["is_nd"], "product"]))
    PROD_FORMS.clear()
    PROD_FORMS.update(act[~act["is_nd"]].groupby("product")["form"]
                      .apply(lambda s: sorted(set(s))).to_dict())
    nd_rows = act[act["is_nd"]].copy()
    a_stock = act.groupby("product")["a_stock"].sum()

    # ---------- 组级 UOM 例外：星球抱枕整组 1:1
    EXCEPTION_PRODUCTS.clear()
    EXCEPTION_SKUS.clear()
    exc_rows = act[act["物料组"].astype(str).isin(EXCEPTION_GROUPS)]
    EXCEPTION_PRODUCTS.update(exc_rows["product"])
    for raw in exc_rows["来源码"].astype(str):
        for t in re.split(r"[,;，]", raw):
            if t.strip():
                EXCEPTION_SKUS.add(norm_code(t))
    EXCEPTION_SKUS.update({norm_code("XINGQIU-12PCS"), norm_code("STPPW-13-1C")})

    # ---------- 共享码名单（N1）：A 登记的 30 个 + 一码多产品
    shared_map = {}
    sh = pd.read_excel(args.a_final, sheet_name="共享码剩余")
    for row in sh.itertuples(index=False):
        shared_map[norm_code(row[1])] = [c.strip() for c in str(row[2]).split("|")
                                         if c.strip() and c.strip().lower() != "nan"]
    code_to_product = {}
    for r in act.itertuples(index=False):
        for t in re.split(r"[,;，]", str(getattr(r, "来源码") or "")):
            if t.strip():
                code_to_product.setdefault(norm_code(t), set()).add(r.product)
    for code, prods in code_to_product.items():
        if len(prods) > 1 and code not in shared_map:
            shared_map[code] = sorted(prods)

    # ---------- 订单事实（2026 窗口）
    m = pd.read_excel(args.v5b, sheet_name="市场行")
    m["EN物料"] = m["EN物料"].astype(str)
    m["product"] = m["EN物料"].map(product_of)
    for c in ("90天", "180天", "2026"):
        m[c] = pd.to_numeric(m[c], errors="coerce").fillna(0.0)
    m["region"] = m["市场"].map(lambda x: {"美东": "US", "美中": "US", "波兰": "PL"}.get(x))
    m["side"] = m["市场"].map(lambda x: {"美东": "East", "美中": "Central"}.get(x))
    ord26 = (m[m["region"].notna()].groupby(["product", "region", "side"], dropna=False)
             [["90天", "180天", "2026"]].sum().reset_index())
    ord26["side"] = ord26["side"].astype(object)

    # ---------- 2025 订单（N1 共享门禁 + N2 多件换算 + N5 源行）
    idx = build_code_index(Path(args.a_final), Path(args.customer_codes), Path(args.sku_map))
    g = pd.read_parquet(args.gs, columns=["order_id", "sku_tongtool", "qty", "warehouse",
                                          "month", "sale_date", "despatch_date", "line_id"])
    g["src_row_id"] = range(1, len(g) + 1)          # N5：parquet 1 基行号（过滤前）
    g = g[g["month"].astype(str).str.startswith("2025")].copy()
    g["raw_qty"] = pd.to_numeric(g["qty"], errors="coerce").fillna(0.0)
    g["market"] = g["warehouse"].map(side_of_warehouse)
    g = g[g["market"].isin(["美东", "美中", "波兰"])].copy()
    g["code"] = g["sku_tongtool"].map(norm_code)
    g["is_shared"] = g["code"].isin(shared_map)

    g["product"] = None
    g.loc[~g["is_shared"], "product"] = g.loc[~g["is_shared"], "code"].map(
        lambda s: idx.get(s))
    g["ppu"], g["conv"] = zip(*[pieces_per_unit(s) for s in g["sku_tongtool"]])
    g["qty"] = g["raw_qty"] * g["ppu"]
    g["sale_dt"] = pd.to_datetime(g["sale_date"], errors="coerce")
    g["desp_dt"] = pd.to_datetime(g["despatch_date"], errors="coerce")
    g["eff_dt"] = g["sale_dt"].fillna(g["desp_dt"])

    shared_orders = g[g["is_shared"]].copy()
    own_orders = g[(~g["is_shared"]) & g["product"].notna()].copy()
    own_orders["region"] = own_orders["market"].map(
        lambda x: {"美东": "US", "美中": "US", "波兰": "PL"}[x])
    own_orders["side"] = own_orders["market"].map(
        lambda x: {"美东": "East", "美中": "Central"}.get(x))
    ord25 = (own_orders.groupby(["product", "region", "side"], dropna=False)["qty"].sum()
             .reset_index().rename(columns={"qty": "2025"}))
    ord25["side"] = ord25["side"].astype(object)

    # N3：own2025 逐笔记录（最后有效销售日 + 冲突时间线的唯一数据源）
    own25_records: dict[str, dict[str, list[dict]]] = {}
    for r in own_orders.itertuples(index=False):
        if float(r.qty) <= 0:
            continue
        own25_records.setdefault(r.product, {}).setdefault(r.side, []).append(
            dict(date=r.eff_dt, qty=float(r.qty), sku=r.sku_tongtool,
                 line_id=r.line_id, src_row_id=int(r.src_row_id), market=r.market))

    # 共享订单池：按 共享码×仓×年 持有一份，候选只作标注
    shared_order_rows = []
    for (code, market), grp_ in shared_orders.groupby(["code", "market"]):
        shared_order_rows.append(dict(
            共享码=code, 仓库侧=side_cn_name(market), 年=2025,
            订单行数=int(len(grp_)), 原数量=float(grp_["raw_qty"].sum()),
            换算数量=float(grp_["qty"].sum()),
            源SHA256=gs_sha,
            源行号=",".join(str(x) for x in sorted(grp_["src_row_id"].tolist())),
            line_id=",".join(sorted(grp_["line_id"].astype(str).tolist())),
            候选产品=";".join(shared_map.get(code, [])),
            说明="共享池持有一次，不分配给任何单一产品，不计入 own2025/销量2025"))
    shared_order_tbl = pd.DataFrame(shared_order_rows)

    # ---------- DN 事实（N5：逐行源行 + 缺字段标 missing）
    dn = pd.read_csv(args.dn, dtype=str)
    dn["src_row_id"] = range(1, len(dn) + 1)        # N5：CSV 1 基行号
    dn["posting_date"] = pd.to_datetime(dn["posting_date"], errors="coerce")
    dn["year"] = dn["posting_date"].dt.year
    dn["qty"] = pd.to_numeric(dn["qty"], errors="coerce").fillna(0.0)
    dn["item_code"] = dn["item_code"].astype(str)
    dn["product"] = dn["item_code"].map(product_of)
    dn["form"] = [dn_form_of(s) for s in dn["item_code"]]
    dn[["region", "side"]] = pd.DataFrame(
        dn["customer"].map(lambda c: CUSTOMER_REGION.get(str(c), (None, None))).tolist(),
        index=dn.index)
    dn_all = dn.copy()
    dn = dn[dn["region"].notna() & dn["year"].isin([2025, 2026])].copy()
    dn_facts = (dn.groupby(["product", "region", "side", "year", "customer", "form"],
                           dropna=False)
                .agg(DN笔数=("dn", "nunique"), DN供货量=("qty", "sum"),
                     首次DN=("posting_date", "min"), 末次DN=("posting_date", "max"))
                .reset_index())
    dn_facts["side"] = dn_facts["side"].astype(object)

    # N3：该产品美国 DN 逐笔（含形态），供 own2025 平局时查正确形态 DN
    dn_records_all: dict[str, dict[str, list[dict]]] = {}
    for r in dn[dn["region"] == "US"].itertuples(index=False):
        if r.side not in ("East", "Central"):
            continue
        dn_records_all.setdefault(r.product, {}).setdefault(r.side, []).append(
            dict(dn=r.dn, posting_date=r.posting_date, item_code=r.item_code,
                 qty=float(r.qty), form=r.form))

    # ---------- 库存层（N2 换算 + N5 源行）
    stk_all = pd.read_parquet(args.stock)
    stk_all["src_row_id"] = range(1, len(stk_all) + 1)   # N5：parquet 1 基行号（过滤前）
    stk = stk_all[pd.to_datetime(stk_all["snapshot_date"]).dt.date.astype(str)
                  == "2026-10-28"].copy()
    stk["sku"] = stk["sku"].astype(str)
    stk["raw_available"] = pd.to_numeric(stk["available"], errors="coerce").fillna(0.0)
    stk["ppu"], stk["conversion_basis"] = zip(*[pieces_per_unit(s) for s in stk["sku"]])
    stk["canonical_qty"] = stk["raw_available"] * stk["ppu"]
    stk["side_cn"] = stk["warehouse_name"].astype(str).map(side_of_warehouse)

    would_ppu = stk["sku"].map(lambda s: _ppu_ignore_exception(s))
    rescued = stk[(would_ppu > 1) & (stk["ppu"] == 1)].copy()
    rescued["退回数量"] = (rescued["raw_available"] * (would_ppu[rescued.index] - 1))
    rescued_tbl = rescued[["sku", "warehouse_name", "raw_available",
                           "退回数量"]].rename(columns={"sku": "SKU",
                                                        "warehouse_name": "仓库",
                                                        "raw_available": "原数量"})
    rescued_stock_rows = int(len(rescued))
    rescued_stock_qty = float(rescued["退回数量"].sum())

    # N5：证据索引（结构化，全部可回放到源行；0 库存行不作证据）
    stock_ev: dict[str, list[str]] = {}
    stock_rows: list[dict] = []
    own_side, shared_side = {}, {}
    for row in stk.itertuples(index=False):
        if row.side_cn not in ("美东", "美中", "波兰"):
            continue
        code = norm_code(row.sku)
        cands = shared_map.get(code)
        if row.raw_available > 0:
            stock_rows.append(dict(
                证据ID=f"ST:{int(row.src_row_id)}", 源文件=Path(args.stock).name,
                源SHA256=stk_sha, 源行号=int(row.src_row_id),
                快照日=str(row.snapshot_date), 仓库名=str(row.warehouse_name),
                仓侧=side_cn_name(row.side_cn), 原始SKU=str(row.sku),
                available=float(row.raw_available), pieces_per_unit=int(row.ppu),
                换算依据=row.conversion_basis, canonical_qty=float(row.canonical_qty),
                是否共享池=("是" if cands else "否"),
                关联产品键=";".join(sorted({product_of(c) for c in cands})) if cands else
                        ";".join(sorted(code_to_product.get(code, ()))[:3])))
        if cands:
            for c in cands:
                p = product_of(c)
                shared_side.setdefault(p, {})
                shared_side[p][row.side_cn] = (shared_side[p].get(row.side_cn, 0.0)
                                               + row.canonical_qty)
                if row.raw_available > 0:
                    stock_ev.setdefault(p, []).append(f"ST:{int(row.src_row_id)}")
            continue
        for p in code_to_product.get(code, ()):
            own_side.setdefault(p, {})
            own_side[p][row.side_cn] = own_side[p].get(row.side_cn, 0.0) + row.canonical_qty
            if row.raw_available > 0:
                stock_ev.setdefault(p, []).append(f"ST:{int(row.src_row_id)}")

    # ---------- 决策
    decision = []
    for prod in products:
        for region in ("US", "PL"):
            ev = decide_region(prod, region, ord26, ord25, dn_facts, own_side, shared_side)
            if ev:
                decision.append(ev)
    dec = pd.DataFrame(decision)

    owner_map, conflict_rows, tie_stats = {}, [], dict(平局=0, 日期裁决=0, DN裁决=0, 冲突=0)
    if len(dec):
        for prod in dec.loc[dec["region"] == "US", "product"]:
            owner, basis, conflict = pick_us_owner(
                prod, ord26, ord25, dn_facts, dn=dn, own_stock=own_side,
                shared_stock=shared_side, own25_records=own25_records,
                demand_form=demand_form_of(prod), dn_records=dn_records_all)
            if "own2025 平局" in basis:
                tie_stats["平局"] += 1
                if conflict:
                    tie_stats["冲突"] += 1
                elif "正确形态 DN" in basis:
                    tie_stats["DN裁决"] += 1
                else:
                    tie_stats["日期裁决"] += 1
            if conflict:
                ctype = ("us_owner_stock_conflict" if "stock" in str(conflict.get("原因", ""))
                         else "us_owner_conflict")
                conflict_rows.append(dict(product=prod, 类型=ctype, **conflict))
            owner_map[prod] = (owner, basis)
        dec["us_owner"] = [owner_map.get(p, ("", ""))[0] if r == "US" else ""
                           for p, r in zip(dec["product"], dec["region"])]
        dec["us_owner_basis"] = [owner_map.get(p, ("", ""))[1] if r == "US" else ""
                                 for p, r in zip(dec["product"], dec["region"])]

    # ---------- 证据索引（N5）
    dn_ev: dict[str, list[str]] = {}
    dn_rows_out: list[dict] = []
    for r in dn.itertuples(index=False):
        rid = int(r.src_row_id)
        dn_ev.setdefault(r.product, []).append(f"DN:{rid}")
        dn_rows_out.append(dict(
            证据ID=f"DN:{rid}", 源文件=Path(args.dn).name, 源SHA256=dn_sha, 源行号=rid,
            产品键=r.product, DN单号=r.dn,
            **{"DN Item.name": MISSING, "docstatus": MISSING,
               "is_return": MISSING, "so_detail": MISSING},
            so=("" if pd.isna(r.so) else str(r.so)),
            posting_date=_fmt(r.posting_date), customer=r.customer,
            地区=r.region, 仓侧=SIDE_LABEL.get(r.side, ""), item_code=r.item_code,
            供货形态=r.form, qty=float(r.qty),
            customer_item_code=("" if pd.isna(r.customer_item_code) else str(r.customer_item_code)),
            uom=("" if pd.isna(r.uom) else str(r.uom)),
            缺字段说明=MISSING_NOTE))

    order_ev: dict[str, list[str]] = {}
    order_rows_out: list[dict] = []

    def _order_row(rec, shared: bool) -> dict:
        # r8b：统一走 dict 取值。r8 在这里对 Series 用 `r.product`，拿到的是
        # `Series.prod` **方法对象**（`<bound method Series.prod of ...>`），
        # 污染 `产品键` 列 2709 行；改为显式 to_dict 后按键取值，杜绝属性名与方法名撞车。
        if not isinstance(rec, dict):
            rec = rec.to_dict() if isinstance(rec, pd.Series) else rec._asdict()
        return dict(
            证据ID=f"OR:{int(rec['src_row_id'])}", 源文件=Path(args.gs).name,
            源SHA256=gs_sha, 源行号=int(rec["src_row_id"]), line_id=rec["line_id"],
            order_id=rec["order_id"], sale_date=_fmt(rec["sale_dt"]),
            despatch_date=_fmt(rec["desp_dt"]), 仓库=str(rec["warehouse"]),
            仓侧=side_cn_name(rec["market"]), SKU=rec["sku_tongtool"],
            raw_qty=float(rec["raw_qty"]), pieces_per_unit=int(rec["ppu"]),
            qty=float(rec["qty"]),
            产品键=("" if shared else (rec.get("product") or "")),
            是否共享池=("是" if shared else "否"))

    for r in shared_orders.itertuples(index=False):
        order_rows_out.append(_order_row(r, True))

    # 主表引用：每产品每仓侧取最近 3 笔（时间线足够抽样回放，全量在各产品明细里）
    cited: dict[str, list[str]] = {}
    for (prod, _side), grp_ in (own_orders.sort_values("eff_dt")
                                .groupby(["product", "side"], dropna=False)):
        take = grp_.tail(3)
        for r in take.itertuples(index=False):
            eid = f"OR:{int(r.src_row_id)}"
            order_ev.setdefault(prod, []).append(eid)
            cited.setdefault(eid, []).append(prod)
    seen_orders = {r["证据ID"] for r in order_rows_out}
    for eid, prods in cited.items():
        if eid in seen_orders:
            continue
        rid = int(eid.split(":")[1])
        row = own_orders[own_orders["src_row_id"] == rid].iloc[0]
        order_rows_out.append(_order_row(row, False))

    # 旧151/13 的「旧EN×旧市场」逐行引用需要该 EN 的全部源行
    old_lists = {s: pd.read_excel(args.v5b, sheet_name=s)
                 for s in ("待确认清单_全部", "未证清单_全部")}
    old_codes: dict[str, set[str]] = {}
    for df in old_lists.values():
        for r in df.itertuples(index=False):
            codes = {norm_code(r.EN物料)}
            for t in re.split(r"[,;，]", str(getattr(r, "来源码") or "")):
                if t.strip() and t.strip().lower() != "nan":
                    codes.add(norm_code(t))
            old_codes[str(r.EN物料)] = codes
    old_code_union = set().union(*old_codes.values()) if old_codes else set()
    old_orders = own_orders[own_orders["code"].isin(old_code_union)]
    for r in old_orders.itertuples(index=False):
        eid = f"OR:{int(r.src_row_id)}"
        if eid in seen_orders:
            continue
        order_rows_out.append(_order_row(r, False))
        seen_orders.add(eid)

    def cite(ids, limit=6) -> str:
        ids = list(dict.fromkeys(ids))
        if not ids:
            return ""
        head = ";".join(ids[:limit])
        return head + (f";…(+{len(ids) - limit})" if len(ids) > limit else "")

    def evidence_of(prod) -> str:
        parts = [cite(dn_ev.get(prod, [])), cite(order_ev.get(prod, [])),
                 cite(stock_ev.get(prod, []))]
        return ";".join(p for p in parts if p)

    # ---------- 主表
    shared_products = {product_of(c) for cs in shared_map.values() for c in cs}
    rows = []
    for d in dec.to_dict("records"):
        prod, region = d["product"], d["region"]
        forms = [f for f in PROD_FORMS.get(prod, ["成品"]) if f != "内胆"]
        demand_form = next((f for f in DEMAND_FORM_PRIORITY if f in forms),
                           forms[0] if forms else "成品")
        ev_b, inv_b, dem_b = [], [], []
        if prod in shared_products:
            ev_b.append("共享码数量待核（候选间不分摊）")
        if d["tier"] == "stock_placement":
            inv_b.append("仅库存投放，无销售证据（低置信）")
            dem_b.append("无当前需求（库存位置≠销售）")
        elif d["tier"] in ("dn2025", "own2025"):
            dem_b.append("仅有历史（2025）证据，无当前需求")
        if d.get("stock_note") == "shared_pool":
            inv_b.append("库存为共享池，未独占")
        for form in forms:
            is_demand = form == demand_form
            rows.append(dict(
                产品键=prod, 地区=region,
                美国责任方=SIDE_LABEL.get(d.get("us_owner"), "") if region == "US" else "",
                仓侧标准名=SIDE_CN.get(d.get("us_owner"), "") if region == "US" else "",
                市场显示名=MARKET_LABEL.get((region, d.get("us_owner")),
                                            "美国·责任未定" if region == "US" else "波兰"),
                供货形态=form,
                市场状态=d["market_status"], 最强证据层级=d["tier"],
                美国责任依据=d.get("us_owner_basis", "") if region == "US" else "",
                own90=d["own90"] if is_demand else 0.0,
                own180=d["own180"] if is_demand else 0.0,
                销量2026=d["own2026"] if is_demand else 0.0,
                销量2025=d["own2025"] if is_demand else 0.0,
                有证据的仓侧=side_text(d.get("sides_with_evidence", "")),
                **{k: (v if is_demand else 0.0) for k, v in (
                    ("2026美东", d.get("v2026_East", 0.0)), ("2026美中", d.get("v2026_Central", 0.0)),
                    ("2026波兰", d.get("v2026_PL", 0.0)), ("2025美东", d.get("v2025_East", 0.0)),
                    ("2025美中", d.get("v2025_Central", 0.0)), ("2025波兰", d.get("v2025_PL", 0.0)))},
                库存_自身=d.get("stock_own", 0.0),
                库存_共享池=d.get("stock_shared_pool", 0.0),
                库存说明=d.get("stock_note", ""),
                DN2026笔数=d["dn2026_count"] if is_demand else 0,
                DN2026供货量=d["dn2026_qty"] if is_demand else 0.0,
                DN2025笔数=d["dn2025_count"] if is_demand else 0,
                DN2025供货量=d["dn2025_qty"] if is_demand else 0.0,
                demand_scope_id=f"{prod}|{region}",
                是否需求行="Y" if is_demand else "N",
                主需求形态=demand_form,
                需求说明=("本行承载该产品×地区的唯一一份需求" if is_demand
                          else f"供货形态行，引用 {prod}|{region} 的需求，数量不重复计"),
                evidence_blockers="；".join(dict.fromkeys(ev_b)),
                inventory_blockers="；".join(dict.fromkeys(inv_b)),
                demand_blockers="；".join(dict.fromkeys(dem_b)),
                限制原因="市场已证≠可执行补货" + (
                    "；" + "；".join(filter(None, ["；".join(dict.fromkeys(ev_b)),
                                                  "；".join(dict.fromkeys(inv_b)),
                                                  "；".join(dict.fromkeys(dem_b))]))
                    if (ev_b or inv_b or dem_b) else "；仍需库存/在途/交期/删失证据"),
                证据入口=evidence_of(prod) if is_demand else "",
                UOM_单位="套" if form == "套件" else "个",
                决策规则版本=RULES_VERSION,
                可进净额="否",
                补货建议=(OLD_PRODUCT_NOTE if prod in EXCEPTION_PRODUCTS else ""),
            ))
    main_tbl = pd.DataFrame(rows)

    # ---------- 附表
    evidenced = set(dec["product"]) if len(dec) else set()
    cap = act[~act["is_nd"]].groupby("product").agg(
        名称=("名称", "first"), 角色=("角色", "first"), 物料组=("物料组", "first"),
        绍兴发货方式=("raw_ship_mode", "first"), 库存=("a_stock", "sum")).reset_index()
    rest = cap[~cap["product"].isin(evidenced)].rename(columns={"product": "产品键"}).copy()
    pend_mask = rest["产品键"].map(lambda p: float(a_stock.get(p, 0.0)) > 0)
    so = rest[~pend_mask].copy()
    so["market_status"] = "no_observed_market"
    so["说明"] = ("订单/DN 证据范围内无市场，且 en_stock 10-28 按 SKU 未定位到仓；"
                  "不凭库存仓反推经营责任。")

    nd_tbl = nd_rows[["EN物料", "名称", "物料组", "角色", "a_stock"]].rename(
        columns={"EN物料": "ND物料", "a_stock": "库存"}).copy()
    nd_tbl["处理"] = "配套层：不建独立市场/需求/PO"

    review = pd.DataFrame([dict(
        待审类型=c.get("类型", "us_owner_conflict"),
        对象=c["product"], 最小问题=c.get("原因", ""), 证据=c.get("两侧", ""),
        责任人="业务/运营") for c in conflict_rows]) if conflict_rows else pd.DataFrame(
        columns=["待审类型", "对象", "最小问题", "证据", "责任人"])

    shared_rows = []
    for code, cands in shared_map.items():
        srow = stk[stk["sku"].astype(str).map(norm_code) == code]
        if not len(srow):
            continue
        by_side = srow.groupby("side_cn")["canonical_qty"].sum().to_dict()
        for cand in cands:
            p = product_of(cand)
            for side_cn, q in by_side.items():
                if side_cn in ("美东", "美中", "波兰") and q:
                    shared_rows.append(dict(共享码=code, 候选产品=p,
                                            仓库侧=side_cn_name(side_cn),
                                            shared_pool数量=float(q),
                                            说明="共享池：不重复分给单一产品，不参与产品合计"))
    shared_tbl = pd.DataFrame(shared_rows)

    # ---------- 旧 151 / 13 对账（N5：旧EN×旧市场 → 真实源行）
    stock_by_code: dict[str, list[dict]] = {}
    for rec in stock_rows:
        stock_by_code.setdefault(norm_code(rec["原始SKU"]), []).append(rec)
    dn_by_item: dict[str, list] = {}
    dn_by_product: dict[str, list] = {}
    for r in dn.itertuples(index=False):
        dn_by_item.setdefault(r.item_code, []).append(r)
        dn_by_product.setdefault(r.product, []).append(r)

    def old_row_refs(en: str, market_old: str, status: str) -> dict:
        codes = old_codes.get(en, {norm_code(en)})
        side_want = MARKET_CN.get(market_old) if market_old in MARKET_CN else None
        market_known = market_old in ("美东", "美中", "波兰")

        o = own_orders[own_orders["code"].isin(codes)]
        if market_known:
            o = o[o["market"] == market_old]
        o = o.sort_values("eff_dt")
        o_ids = [f"OR:{int(x)}" for x in o["src_row_id"]]
        o_brief = "; ".join(f"OR:{int(r.src_row_id)}/{_fmt(r.eff_dt)}/{r.sku_tongtool}"
                            f"×{r.raw_qty:g}/{r.market}" for r in o.tail(6).itertuples(index=False))

        d_rows = {}
        for x in ({en} | codes):
            for rec in dn_by_item.get(x, []):
                d_rows[int(rec.src_row_id)] = rec
        d = (pd.DataFrame(list(d_rows.values()), columns=list(dn.columns))
             if d_rows else pd.DataFrame(columns=list(dn.columns)))
        if len(d) and market_known:
            d = d[(d["region"] == ("PL" if market_old == "波兰" else "US"))
                  & (d["side"].isna() if side_want is None else (d["side"] == side_want))]
        d_ids = [f"DN:{int(x)}" for x in d["src_row_id"]] if len(d) else []
        d_brief = "; ".join(f"DN:{int(r.src_row_id)}/{r.dn}/{_fmt(r.posting_date)}/"
                            f"{r.item_code}×{r.qty:g}/{r.customer}"
                            for r in d.tail(6).itertuples(index=False)) if len(d) else ""

        prod = product_of(en)
        dprod = (pd.DataFrame(list({int(r.src_row_id): r
                                    for r in dn_by_product.get(prod, [])}.values()),
                              columns=list(dn.columns))
                 if dn_by_product.get(prod) else pd.DataFrame(columns=list(dn.columns)))
        if len(dprod):
            dprod = dprod[dprod["item_code"] != en]
            if market_known:
                dprod = dprod[(dprod["region"] == ("PL" if market_old == "波兰" else "US"))
                              & (dprod["side"].isna() if side_want is None
                                 else (dprod["side"] == side_want))]
        dp_ids = [f"DN:{int(x)}" for x in dprod["src_row_id"]] if len(dprod) else []
        dp_brief = "; ".join(f"DN:{int(r.src_row_id)}/{r.dn}/{_fmt(r.posting_date)}/"
                             f"{r.item_code}×{r.qty:g}/{r.customer}"
                             for r in dprod.tail(6).itertuples(index=False)) if len(dprod) else ""

        s = []
        for code in codes:
            s += stock_by_code.get(code, [])
        if market_known:
            s = [x for x in s if x["仓侧"] == side_cn_name(market_old)]
        s_ids = [x["证据ID"] for x in s]
        s_brief = "; ".join(f"{x['证据ID']}/{x['快照日']}/{x['仓库名']}/{x['原始SKU']}"
                            f" avail={x['available']:g}" for x in s[:6])

        if status == "stock_placement" and not d_ids and not o_ids:
            strength = ("低置信：仅库存投放（无订单/DN 证据，仓位≠需求）" if s_ids
                        else ("低置信：仅同产品键 DN 可定位（非本物料行）" if dp_ids
                              else "无源行：旧证据范围内无匹配（不伪造，仅库存投放）"))
        elif d_ids:
            strength = "中：DN 单据可定位（DN Item 子表字段 missing，见 DN证据明细）"
        elif o_ids:
            strength = "中：2025 订单行可定位（订单≠当前需求）"
        elif s_ids:
            strength = "低置信：仅库存源行可定位"
        elif dp_ids:
            strength = "低置信：仅同产品键 DN 可定位（非本物料行）"
        else:
            strength = "无源行：旧证据范围内无匹配（不伪造" + (
                "，市场未证" if not market_known else "") + "）"
        return dict(订单源行=cite(o_ids, 6), 订单源行样例=o_brief, 订单匹配行数=len(o_ids),
                    DN源行=cite(d_ids, 6), DN源行样例=d_brief, DN匹配行数=len(d_ids),
                    DN源行_同产品键=cite(dp_ids, 6), DN同产品键样例=dp_brief,
                    DN同产品键匹配行数=len(dp_ids),
                    库存源行=cite(s_ids, 6), 库存源行样例=s_brief, 库存匹配行数=len(s_ids),
                    本物料有源行=("是" if (o_ids or d_ids or s_ids) else "否"),
                    证据强度=strength,
                    证据ID集合=cite(list(dict.fromkeys(o_ids + d_ids + dp_ids + s_ids)), 12))

    old = old_lists["待确认清单_全部"].copy()
    old["EN物料"] = old["EN物料"].astype(str)
    old["product"] = old["EN物料"].map(product_of)
    old_recon = []
    for r in old.itertuples(index=False):
        p = r.product
        e = dec[dec["product"] == p]
        status = e.iloc[0]["market_status"] if len(e) else "no_observed_market"
        refs = old_row_refs(r.EN物料, str(getattr(r, "市场", "")), status)
        old_recon.append(dict(旧EN物料=r.EN物料, 产品键=p,
                              旧市场原值=getattr(r, "市场", ""),
                              旧原因原值=str(getattr(r, "备注", ""))[:50],
                              new_market_status=status,
                              resolved_reason=("规则自动处置（波兰独立/另一仓无量/历史有量）"
                                               if status != "no_observed_market"
                                               else "证据范围内无市场 → 仅库存信息表"),
                              **refs, 仍待审=False))
    old_recon = pd.DataFrame(old_recon)

    old13 = old_lists["未证清单_全部"].copy()
    old13["EN物料"] = old13["EN物料"].astype(str)
    old13["product"] = old13["EN物料"].map(product_of)
    un13 = []
    for r in old13.itertuples(index=False):
        p = r.product
        e = dec[dec["product"] == p]
        status = e.iloc[0]["market_status"] if len(e) else "no_observed_market"
        refs = old_row_refs(r.EN物料, str(getattr(r, "市场", "")), status)
        un13.append(dict(旧EN物料=r.EN物料, 产品键=p, 旧市场原值=getattr(r, "市场", ""),
                         有DN=refs["DN匹配行数"] > 0,
                         有DN_同产品键=refs["DN同产品键匹配行数"] > 0,
                         DN地区=";".join(sorted({str(y.region) for y in
                                                dn_by_product.get(p, [])})),
                         new_market_status=status,
                         resolved_reason=("按正确形态查 DN/库存定位" if refs["DN匹配行数"]
                                          else "仅库存信息表"), **refs))
    un13 = pd.DataFrame(un13)

    # ---------- 对账
    dest = {}
    for r in act.itertuples(index=False):
        if r.is_nd:
            dest[r.EN物料] = "ND附表"
        elif r.product in set(main_tbl["产品键"]):
            dest[r.EN物料] = "主表"
        elif r.product in set(so["产品键"]):
            dest[r.EN物料] = "仅库存"
        else:
            dest[r.EN物料] = "证据异常"
    act_cov = pd.DataFrame([{"EN物料": k, "产品键": product_of(k), "去向": v}
                            for k, v in dest.items()])

    chk = (main_tbl[main_tbl["地区"] == "US"].groupby("产品键")["美国责任方"].nunique()
           if len(main_tbl) else pd.Series(dtype=int))
    us_prods = set(main_tbl.loc[main_tbl["地区"] == "US", "产品键"])
    pl_prods = set(main_tbl.loc[main_tbl["地区"] == "PL", "产品键"])
    dq = main_tbl[main_tbl["是否需求行"] == "Y"]
    dup = int(dq.groupby("demand_scope_id").size().gt(1).sum())

    sample_skus = ("XINGQIU-2PCS", "XINGQIU-3PCS", "XINGQIU-5PC",
                   "XINGQIU-7PCS", "XINGQIU-12PCS", "TT0001K0001-2", "TT0001K0001-3",
                   "TJ#KS0156x2-001")
    conv_tbl = pd.DataFrame([dict(SKU=s, pieces_per_unit=pieces_per_unit(s)[0],
                                  conversion_basis=pieces_per_unit(s)[1],
                                  是否为组级例外=("是" if (norm_code(s) in EXCEPTION_SKUS
                                                     or any(p.search(str(s)) for p in EXCEPTION_SKU_PATTERNS))
                                                else "否"))
                             for s in sample_skus])
    exception_tbl = pd.DataFrame([dict(
        例外类型="组级（uom_exception_map）", EN物料组="星球抱枕", 产品前缀="KS0019",
        pieces_per_unit=1, 覆盖SKU数=len(EXCEPTION_SKUS),
        覆盖产品数=len(EXCEPTION_PRODUCTS),
        样例SKU="XINGQIU-12PCS;XINGQIU-*-10/16;TT0009*;STPPW-13-1C",
        补货建议=OLD_PRODUCT_NOTE,
        依据="UOM-CANONICAL §2.1；用户 2026-10-29 指定整组 1:1、老产品默认不补")])

    dn_tbl = pd.DataFrame(dn_rows_out)
    stk_tbl = pd.DataFrame(stock_rows)
    ord_tbl = pd.DataFrame(order_rows_out)
    ord_tbl = ord_tbl.drop_duplicates(subset=["证据ID"]).sort_values("源行号")

    # N5 抽查回放（证据行 → 源行号 → 原始文件逐字段比对）
    verify = verify_evidence(main_tbl, old_recon, un13, dn_tbl, stk_tbl, ord_tbl,
                             dn_all, stk_all, g)

    summary = dict(
        rules_version=RULES_VERSION,
        US产品数=len(us_prods), PL产品数=len(pl_prods),
        仅US=len(us_prods - pl_prods), 仅PL=len(pl_prods - us_prods),
        都无=len(set(products) - us_prods - pl_prods),
        需求行数=len(dq), 重复需求scope=dup,
        需求行校验=int(len(dq) == len(us_prods) + len(pl_prods)),
        A活跃=int(len(act)), 产品数=len(products),
        主表行=len(main_tbl), 主表产品=int(main_tbl["产品键"].nunique()) if len(main_tbl) else 0,
        US行=int((main_tbl["地区"] == "US").sum()) if len(main_tbl) else 0,
        PL行=int((main_tbl["地区"] == "PL").sum()) if len(main_tbl) else 0,
        US_PL并存产品=int(((main_tbl.groupby("产品键")["地区"].nunique() > 1).sum())
                      if len(main_tbl) else 0),
        仅库存产品=len(so), ND行=len(nd_tbl),
        待审=len(review), 冲突=len(conflict_rows),
        stock_placement行=int((main_tbl["市场状态"] == "stock_placement").sum()) if len(main_tbl) else 0,
        共享码候选行=int(len(shared_tbl)),
        共享订单行=int(shared_orders.shape[0]),
        共享订单原数量=float(shared_orders["raw_qty"].sum()),
        共享订单换算数量=float(shared_orders["qty"].sum()),
        共享订单原码数=int(shared_orders["code"].nunique()),
        共享订单候选产品=int(len({product_of(c) for code, cs in shared_map.items()
                                   if code in set(shared_orders["code"]) for c in cs})),
        多件换算行=int((stk["ppu"] > 1).sum()),
        uom例外组=len(EXCEPTION_GROUPS),
        uom例外覆盖SKU=int(len(EXCEPTION_SKUS)),
        uom例外覆盖产品=int(len(EXCEPTION_PRODUCTS)),
        例外回退库存行=rescued_stock_rows,
        例外回退数量=rescued_stock_qty,
        老产品默认不补行=int((main_tbl["补货建议"] == OLD_PRODUCT_NOTE).sum()) if len(main_tbl) else 0,
        多件换算原量=float(stk.loc[stk["ppu"] > 1, "raw_available"].sum()),
        多件换算后量=float(stk.loc[stk["ppu"] > 1, "canonical_qty"].sum()),
        订单多件换算行=int((g["ppu"] > 1).sum()),
        去向={k: int(v) for k, v in act_cov["去向"].value_counts().items()},
        六十cm桥接组=len(bridge),
        US_owner唯一性违规=int((chk > 1).sum()),
        US_owner未定=int((main_tbl[main_tbl["地区"] == "US"]["美国责任方"]
                          .isin(["", "未定"]).sum()) if len(main_tbl) else 0),
        ND独立需求行=0,
        # r8 新增：N3 平局口径 + N5 证据体量
        own2025平局产品=tie_stats["平局"],
        平局经销售日裁决=tie_stats["日期裁决"],
        平局经正确形态DN裁决=tie_stats["DN裁决"],
        平局仍冲突=tie_stats["冲突"],
        DN证据行=len(dn_tbl), 库存证据行=len(stk_tbl), 订单证据行=len(ord_tbl),
        证据缺失字段数=int(len(dn_tbl) * 4),
        旧151有源行行数=int(((old_recon["订单匹配行数"] + old_recon["DN匹配行数"]
                              + old_recon["库存匹配行数"]) > 0).sum()),
        未证13有源行行数=int(((un13["订单匹配行数"] + un13["DN匹配行数"]
                               + un13["库存匹配行数"]) > 0).sum()),
        旧151无源行=int(old_recon["证据强度"].astype(str).str.startswith("无源行").sum()),
        未证13无源行=int(un13["证据强度"].astype(str).str.startswith("无源行").sum()),
        仅同产品键DN行=int(old_recon["证据强度"].astype(str).str.contains("仅同产品键").sum()
                     + un13["证据强度"].astype(str).str.contains("仅同产品键").sum()),
        低置信行数=int((old_recon["证据强度"].astype(str).str.startswith("低置信").sum())
                   + (un13["证据强度"].astype(str).str.startswith("低置信").sum())),
        无源行清单="; ".join(f"{r.旧EN物料}@{r.旧市场原值}"
                          for _, r in old_recon[old_recon["证据强度"].astype(str)
                                                .str.startswith("无源行")].iterrows())
                     or "无",
        证据抽查行数=verify["抽查行数"], 证据抽查ID数=verify["证据ID数"],
        证据抽查通过=verify["通过数"], 证据抽查全部通过=("是" if verify["全部通过"] else "否"),
    )

    out = Path(args.out_xlsx)
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        main_tbl.to_excel(w, sheet_name="主表", index=False)
        so.to_excel(w, sheet_name="①仅库存无市场", index=False)
        nd_tbl.to_excel(w, sheet_name="②ND配套不独立补", index=False)
        review.to_excel(w, sheet_name="③映射单位证据异常", index=False)
        pd.DataFrame(conflict_rows if conflict_rows else [{"说明": "无"}]) \
            .to_excel(w, sheet_name="④美国责任真冲突", index=False)
        shared_tbl.to_excel(w, sheet_name="共享码候选分摊", index=False)
        shared_order_tbl.to_excel(w, sheet_name="共享订单池", index=False)
        conv_tbl.to_excel(w, sheet_name="多件换算样例", index=False)
        exception_tbl.to_excel(w, sheet_name="uom例外表", index=False)
        rescued_tbl.to_excel(w, sheet_name="例外回退明细", index=False)
        old_recon.to_excel(w, sheet_name="旧151逐行对账", index=False)
        un13.to_excel(w, sheet_name="未证13逐行对账", index=False)
        pd.DataFrame([{"产品键": k, "成员": ";".join(v)} for k, v in bridge.items()]) \
            .to_excel(w, sheet_name="60cm成员映射", index=False)
        act_cov.to_excel(w, sheet_name="A活跃去向", index=False)
        dn_tbl.to_excel(w, sheet_name="DN证据明细", index=False)
        stk_tbl.to_excel(w, sheet_name="库存证据明细", index=False)
        ord_tbl.to_excel(w, sheet_name="订单证据明细", index=False)
        pd.DataFrame(verify["明细"]).to_excel(w, sheet_name="证据抽查回放", index=False)
        pd.DataFrame([{"指标": k, "值": json.dumps(v, ensure_ascii=False)
                       if isinstance(v, dict) else v} for k, v in summary.items()]) \
            .to_excel(w, sheet_name="汇总", index=False)

    # 构建期强制校验：全表扫描必须 0 命中（ASCII 仓侧字面 / 裸仓侧值）
    scan = scan_banned_terms(out)
    summary["全表扫描_英文字面命中"] = scan["英文字面命中"]
    summary["全表扫描_裸仓侧命中"] = scan["裸仓侧命中"]
    summary["全表扫描_豁免_旧市场原值"] = scan["豁免_旧市场原值裸值"]
    summary["全表扫描_通过"] = "是" if scan["通过"] else "否"
    with pd.ExcelWriter(out, engine="openpyxl", mode="a", if_sheet_exists="replace") as w:
        scan_tbl = pd.DataFrame(scan["明细"]) if scan["明细"] else pd.DataFrame(
            [{"表": "（全部工作表）", "列": "（全部列）", "英文字面命中": 0, "裸仓侧值命中": 0,
              "说明": f"0 命中；豁免列 {BANNED_ALLOWED_COLS[0]} 的裸值 "
                      f"{scan['豁免_旧市场原值裸值']} 格按源历史原值保留"}])
        scan_tbl.to_excel(w, sheet_name="全表扫描", index=False)
        pd.DataFrame([{"指标": k, "值": json.dumps(v, ensure_ascii=False)
                       if isinstance(v, dict) else v} for k, v in summary.items()]) \
            .to_excel(w, sheet_name="汇总", index=False)
    scan_after = scan_banned_terms(out)    # 回写后复扫：自查表本身也不得命中
    scan["回写后复扫通过"] = scan_after["通过"]
    if not (scan["通过"] and scan_after["通过"]):
        print("!! 全表扫描未通过：", json.dumps(scan_after, ensure_ascii=False)[:800])

    # P3 血缘：对除差异表外的完整 r8b 工作簿算 r7→r8b 差异，再回写差异表
    diff, out_sha_pre = {}, None
    if Path(args.r7_xlsx).exists():
        diff = workbook_diff(Path(args.r7_xlsx), out)
        diff["sheets_only_r8"] = diff["sheets_only_r8"] + ["r7_r8差异"]
        out_sha_pre = sha256(out)
        with pd.ExcelWriter(out, engine="openpyxl", mode="a", if_sheet_exists="replace") as w:
            diff_rows(diff).to_excel(w, sheet_name="r7_r8差异", index=False)

    out_sha = sha256(out)
    if diff:
        diff["r8_sha256"] = out_sha
        diff["r8_bytes"] = out.stat().st_size
        diff["r8_sha256_note"] = (
            "r8_sha256 为**最终**工作簿的 SHA；算差异时尚未写入 `r7_r8差异` 表"
            f"（该中间文件 SHA={out_sha_pre}），除该表外两者内容一致")
    sheet_rows = {s: int(len(pd.read_excel(out, sheet_name=s)))
                  for s in pd.ExcelFile(out).sheet_names}

    r6_note = None
    if Path(args.r6_xlsx).exists():
        r6_sha = sha256(args.r6_xlsx)
        r6_note = dict(r6_path=str(args.r6_xlsx), r6_sha256=r6_sha,
                       r7_sha256=diff.get("r7_sha256", ""),
                       r6_equals_r7=(r6_sha == diff.get("r7_sha256", "")))

    Path(args.out_report).write_text(
        render(summary, inputs, old_recon, un13, review, conflict_rows, diff, r6_note,
               run_selftests(), out_sha, args, scan), encoding="utf-8")

    manifest = dict(
        rules_version=RULES_VERSION,
        generated_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        generated_at_local=datetime.now().astimezone().isoformat(timespec="seconds"),
        generator=dict(script=str(Path(__file__).resolve()), script_sha256=sha256(__file__),
                       python=platform.python_version(), pandas=pd.__version__,
                       argv=[str(x) for x in (argv if argv is not None else sys.argv[1:])]),
        inputs=inputs,
        outputs=dict(
            xlsx=dict(path=str(out), sha256=out_sha, bytes=out.stat().st_size,
                      sheets=sheet_rows),
            report=dict(path=str(args.out_report), sha256=sha256(args.out_report),
                        bytes=Path(args.out_report).stat().st_size),
            manifest=dict(path=str(args.manifest), sha256=None,
                          note="manifest 自身不写自哈希（写入时内容未定）"),
        ),
        row_counts={k: (int(v) if isinstance(v, int) else v) for k, v in summary.items()},
        r7_to_r8=diff, r6_r7_identity=r6_note,
        selftests=[dict(name=n, passed=bool(ok), detail=d) for n, ok, d in run_selftests()],
        evidence_replay=dict(抽查行数=verify["抽查行数"], 证据ID数=verify["证据ID数"],
                             通过数=verify["通过数"], 全部通过=verify["全部通过"],
                             明细=verify["明细"]),
        banned_term_scan=dict(英文字面命中=scan["英文字面命中"], 裸仓侧命中=scan["裸仓侧命中"],
                              豁免_旧市场原值裸值=scan["豁免_旧市场原值裸值"],
                              回写后复扫通过=scan.get("回写后复扫通过"),
                              通过=scan["通过"], 明细=scan["明细"]),
        note=("xlsx 内含 openpyxl 生成时间戳（docProps/core.xml），同一输入重跑 SHA 不会相同；"
              "血缘以 输入SHA + 脚本SHA + 行数 + 生成时间 证明，而非字节相同。"),
    )
    Path(args.manifest).write_text(json.dumps(manifest, ensure_ascii=False, indent=1,
                                              default=str), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    print("工作簿：", out, "sha256=", out_sha)
    print("报告：", args.out_report)
    print("manifest：", args.manifest)
    return 0


def render(s, inputs, old_recon, un13, review, conflicts, diff, r6_note, tests,
           out_sha, args, scan) -> str:
    L = [
        "# 仓库归属 A337 v6 r8b（2026-10-30）",
        "",
        f"规则版本 `{s['rules_version']}`｜只读，不写 EN/通途，不发消息，不 push。",
        f"工作簿 SHA256（本次生成）：`{out_sha}`",
        "",
        "## 1. 输入与指纹",
        "",
        "| 输入 | SHA256 |",
        "|---|---|",
    ]
    for k, v in inputs.items():
        L.append(f"| {k} | `{v['sha256']}` |")
    L += [
        "",
        "## 2. 关键结果（与 r7 口径一致项）",
        "",
        "| 指标 | 值 |",
        "|---|---:|",
        f"| A 活跃 EN | {s['A活跃']} |",
        f"| 产品数 | {s['产品数']} |",
        f"| 主表行 / 产品 | {s['主表行']} / {s['主表产品']} |",
        f"| US / PL 行 | {s['US行']} / {s['PL行']} |",
        f"| US 产品 / PL 产品 | {s['US产品数']} / {s['PL产品数']} |",
        f"| 仅US / 仅PL / 并存 / 都无 | {s['仅US']} / {s['仅PL']} / {s['US_PL并存产品']} / {s['都无']} |",
        f"| 需求行数（应=US+PL 产品） | {s['需求行数']}（校验 {s['需求行校验']}） |",
        f"| **US owner 唯一性违规** | **{s['US_owner唯一性违规']}** |",
        f"| 待审 / 冲突 / ④表 | {s['待审']} / {s['冲突']} / {'无' if not conflicts else len(conflicts)} |",
        f"| ND 独立需求行 | {s['ND独立需求行']} |",
        "",
        "A 活跃去向：" + "、".join(f"{k} {v}" for k, v in s["去向"].items()),
        "",
        "## 3. r7 已通过项保持（不得回退）",
        "",
        f"- 共享订单池：**{s['共享订单行']} 行 / 原量 {s['共享订单原数量']:.0f} / "
        f"换算 {s['共享订单换算数量']:.0f} / {s['共享订单原码数']} 原码 / "
        f"{s['共享订单候选产品']} 候选产品**，只入池不分配（本版另补 源SHA+源行号+line_id）。",
        f"- 多件后缀乘 N：库存 {s['多件换算行']} 行（{s['多件换算原量']:.0f}→"
        f"{s['多件换算后量']:.0f}），订单 {s['订单多件换算行']} 行；星球抱枕组 {s['uom例外覆盖SKU']} SKU / "
        f"{s['uom例外覆盖产品']} 产品整组 1:1，退回库存 {s['例外回退库存行']} 行 / "
        f"{s['例外回退数量']:.0f}；老产品默认不补 {s['老产品默认不补行']} 行。",
        "- 级联：own90→own180→own2026→DN2026→DN2025→own2025→库存（未改）。",
        "- 命名：仓侧 美东USNJ / 美中USTX；旧市场字段仍为「原值」。",
        "",
        "## 4. N3 own2025 平局裁决（本轮修复）",
        "",
        "实现：`break_own2025_tie()`——①量（非平局直接判）→ ②最后有效销售日 → "
        "③正确形态 DN（成品→非 PK# 行；皮壳→PK# 行）→ ④仍平局出 `us_owner_conflict` "
        "卡并保留逐笔时间线（订单行 + DN 行，含 line_id / DN 单号）。",
        "",
        f"本轮实际平局：**{s['own2025平局产品']}** 个（经销售日 {s['平局经销售日裁决']}、"
        f"经 DN {s['平局经正确形态DN裁决']}、仍冲突 {s['平局仍冲突']}）。"
        "平局为 0 时 owner 结果与 r7 完全一致。",
        "",
        "内存测试（`--selftest`）：",
        "",
    ]
    for name, ok, detail in tests:
        L.append(f"- `{'PASS' if ok else 'FAIL'}` {name}｜{detail}")
    L += [
        "",
        "## 5. N5 证据行级（本轮修复）",
        "",
        f"三张证据明细表（全部可回放）：`DN证据明细` {s['DN证据行']} 行、"
        f"`库存证据明细` {s['库存证据行']} 行、`订单证据明细` {s['订单证据行']} 行。",
        "",
        "`DN证据明细` 一行 = 本地 DN 明细快照的一行（EN `Delivery Note Item` 的镜像），"
        "`证据ID`/`源行号` 即该 CSV 行号；ERPNext 的 `DN Item.name`（如 `DNIT-xxxx-1`）"
        "不在快照内，标 missing 而非编造。",
        "",
        "| 证据类型 | 必填字段 | 状态 |",
        "|---|---|---|",
        f"| 库存 | source_hash / source_row_id(parquet 1基) / snapshot_date / warehouse_name / raw_sku / available | ✅ 齐全 |",
        f"| DN | DN Item.name / docstatus / is_return / so_detail | ⚠️ **missing**（本地快照无此字段，不伪造，共 {s['证据缺失字段数']} 格） |",
        f"| DN | posting_date / customer / item_code / qty / 源行号 | ✅ 齐全 |",
        f"| 旧151 / 未证13 | 旧EN×旧市场 → 订单行 / DN 号 / 库存源行 | ✅ 逐行引用：151 本物料源行 "
        f"{s['旧151有源行行数']}/151（无源行 {s['旧151无源行']}、仅同产品键 DN "
        f"{s['仅同产品键DN行']}）；13 本物料源行 {s['未证13有源行行数']}/13"
        f"（无源行 {s['未证13无源行']}） |",
        "",
        f"`证据强度` 明确低置信行：**{s['低置信行数']}** 行"
        "（stock_placement = 仅库存投放，仓位≠需求）；"
        f"无源行清单（不伪造、显式留白）：`{s['无源行清单']}`。",
        "",
        "主表 `证据入口` 改为证据 ID（`DN:行号` / `ST:行号` / `OR:行号`），"
        "抽查时按 ID 在明细表定位 → 源行号 → 原始文件行（入口为**产品级**，"
        "地区/仓侧在明细表里按需过滤）。",
        "",
        f"**抽查回放**（`证据抽查回放` 表）：{s['证据抽查行数']} 行 / "
        f"{s['证据抽查ID数']} 个证据 ID，逐字段回源比对 **{s['证据抽查通过']}/"
        f"{s['证据抽查ID数']} 通过**（全部通过={s['证据抽查全部通过']}）。",
        "",
        "**r8 缺陷修复（本版）**：r8 的 `订单证据明细.产品键` 有 2709 行写成了 pandas "
        "`Series.prod` **方法对象字符串**（`<bound method Series.prod of ...>`），"
        "根因是对 `Series` 取属性 `r.product`；r8b 改为 `to_dict()` 后按键取值，"
        "该列现在是真实产品键（空值仅出现在共享池行）。",
        "",
        "## 5.1 全表扫描（构建期强制）",
        "",
        f"写完工作簿后重读**全部工作表全部单元格**：ASCII 字面仓侧名命中 "
        f"**{s['全表扫描_英文字面命中']}**；裸仓侧值（美东/美中）命中 "
        f"**{s['全表扫描_裸仓侧命中']}**；"
        f"豁免列 `旧市场原值`（源历史原值）裸值 {s['全表扫描_豁免_旧市场原值']} 格按约束保留。"
        f"结论：**{s['全表扫描_通过']}**（0 命中即通过，结果同时写入 `全表扫描` 表与 manifest）。",
        "",
        "## 6. 旧 151 / 未证 13",
        "",
        f"旧 151：仍待审 **{int(old_recon['仍待审'].sum())}**；未证 13：{len(un13)} 行闭环。",
        "",
        "## 7. 产物血缘与 r7→r8b 差异",
        "",
    ]
    if diff:
        L += [diff_summary(diff), ""]
        if diff.get("r8_sha256_note"):
            L += [f"注：{diff['r8_sha256_note']}", ""]
    else:
        L += ["（未找到 r7 工作簿，未计算差异）", ""]
    if r6_note:
        L += [
            f"**r6/r7 血缘事实**：r6 `{r6_note['r6_sha256'][:16]}…` 与 r7 "
            f"`{r6_note['r7_sha256'][:16]}…` **字节完全相同** = {r6_note['r6_equals_r7']}；"
            "openpyxl 会把生成时间写进 `docProps/core.xml`（本机实测两次独立写入 SHA 必不同，"
            "r7 文件内 zip 时间戳 2026-10-29 17:55:54 与 r6 mtime 一致），"
            "故 r7 工作簿是 r6 工作簿的复制，不能作为 r7 代码运行过的证据。"
            "r8b 由脚本重新生成，血缘以 `manifest.json`（输入 SHA/输出 SHA/行数/脚本 SHA/生成时间）为准。",
            "",
        ]
    L += [
        "## 8. 剩余真实例外",
        "",
        f"- 美国责任冲突：**{len(conflicts)}** 条。",
    ]
    for c in conflicts:
        L.append(f"  - `{c['product']}`：{c.get('原因', '')}｜{c.get('两侧', '')}")
    L += [
        "",
        "## 9. 边界（仍不可消费的口径）",
        "",
        "- **市场已证 ≠ 可执行补货**：主表 `可进净额` 全为「否」。",
        "- `stock_placement` 只证明投放过/有货，不证明当前有需求（低置信）。",
        "- 共享池（库存与订单）均未被计入任何单一产品合计。",
        "- DN 明细缺 `docstatus / is_return / DN Item.name / so_detail`：本轮已标 missing，"
        "**仍不能称「单据级数量审计」**；下一步需一次有界只读 EN 导出"
        "（Delivery Note Item：name/docstatus/is_return/so_detail）才能补齐。",
        "",
    ]
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
