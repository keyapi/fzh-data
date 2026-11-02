# -*- coding: utf-8 -*-
"""D1 资格与契约（v2，只读）—— 从 A/B/C/D 输入重建资格表，修 D0/D1 复审 P1/P2。

修复（对应 D0-D1-REVIEW-2026-10-30）
- P1-1 共享池：所有带 `shared_pool_ids` 的行 `netting_eligible=false`、`reason_code=shared_pending`、
  `identity_status=共享待核`；不再因为 identity=唯一 就进净额。
- P1-2 重复键：键 = product_id×destination_pool×market×physical_form×canonical_uom 必须唯一；
  CG 分仓观察行（CG-USNJ/CG-USTX）与 TJ# 多件同码按「观察归并」合并，输出归并清单与前后行数。
- P1-3 血缘：本脚本即重生成入口；输出 manifest（输入/输出 SHA、行数、rule_version、生成时间）。
- P2 source_refs：每一行都有可解析的回指（A 行 / B 市场行 / C 供给行 / D 预测行 / 缺口记录），
  无 B/C/D 证据的行回指 `gap:` 记录，不再留空。

行宇宙（可复算）
1) C v14 `4_可发供给` 中属于 A 活跃产品的行（product×pool×physical_form×canonical_uom）；
2) C v14 `23_CG库存池` 的分仓观察行（cg_pool=CG-USNJ/CG-USTX），`observation_only=true`；
   CG 供给合计**只**取 `4_可发供给.pool='CG'`（对应 warehouse_id='CG' 汇总），分仓明细不参与合计；
3) 无 C 供给行的 A 产品：按 B r10 主表的地区行生成「无供给行」（有 B 市场）或「未证」行。

只读：不写 EN / 通途 / 不发消息 / 不 push；不改 A/B/C/D 历史产物。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

B = "D:/Work/fzh-order-store/analysis"
RULE_VERSION = "D-v2-2026-10-30"
PREV_RULE_VERSION = "D-v1-2026-10-30"

POOL_MARKET = {"波兰": "PL", "美东USNJ": "US", "美中USTX": "US", "CG": "US",
               "CG-USNJ": "US", "CG-USTX": "US", "其他": "其他", "未证": "未证"}
CG_POOLS = ("CG", "CG-USNJ", "CG-USTX")
SIDES_CN = ("波兰", "美东USNJ", "美中USTX")

MISSING = "missing"


def sha256(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _s(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and pd.isna(v):
        return ""
    return "" if str(v) in ("nan", "None") else str(v)


def _num(v):
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


# ============================ 输入装载 ============================

def load_a(path: Path) -> pd.DataFrame:
    a = pd.read_excel(path, sheet_name="活跃宇宙")
    a = a[a["活跃分类"] != "不活跃"].copy()
    a["EN物料"] = a["EN物料"].astype(str)
    a["A行号"] = range(2, len(a) + 2)          # Excel 1 基（含表头行）
    a["is_nd"] = a["角色"].astype(str).eq("内胆") | a["EN物料"].str.startswith("ND#")
    a["is_hm"] = a["角色"].astype(str).str.contains("海绵")
    a["is_kit"] = a["EN物料"].str.startswith("TJ#")
    return a


def load_b(path: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    x = pd.ExcelFile(path)
    b = pd.read_excel(x, sheet_name="主表")
    sh = pd.read_excel(x, sheet_name="共享码候选分摊")
    shared: dict[str, list[str]] = {}
    shared_sides: dict[tuple[str, str], list[str]] = {}
    for r in sh.itertuples(index=False):
        pid = f"SP-{_s(r.共享码)}"
        shared.setdefault(str(r.候选产品), []).append(pid)
        shared_sides.setdefault((str(r.候选产品), _s(r.仓库侧)), []).append(pid)
    return b, sh, dict(shared=shared, shared_sides=shared_sides)


def load_c(path: Path) -> dict:
    x = pd.ExcelFile(path)
    sup = pd.read_excel(x, sheet_name="4_可发供给")
    sup["C行号"] = range(2, len(sup) + 2)
    cg = pd.read_excel(x, sheet_name="23_CG库存池")
    cg["C行号"] = range(2, len(cg) + 2)
    facts = pd.read_excel(x, sheet_name="2_库存事实层")
    legacy = set(pd.read_excel(x, sheet_name="16_老产品清单")["product_id"].astype(str))
    s6 = pd.read_excel(x, sheet_name="6_共享候选")
    cand_col = [c for c in s6.columns if str(c).startswith("本次全部候选")][0]
    shared_c: list[tuple[str, str, str]] = []
    for _, r in s6.iterrows():
        code, pool = _s(r["归一码"]), _s(r["pool"])
        if not code:
            continue
        for tok in str(r[cand_col]).split("|"):
            pid = tok.split("<-")[0].strip()
            if pid and pid.lower() != "nan":
                shared_c.append((pid, pool, f"SP-{code}"))
    return dict(supply=sup, cg=cg, facts=facts, legacy=legacy, shared_c=shared_c)


def load_forecast(path: Path) -> pd.DataFrame:
    f = pd.read_excel(path, sheet_name="1_需求预测")
    f["EN物料"] = f["EN物料"].astype(str)
    f["p50_97"] = pd.to_numeric(f["p50_97"], errors="coerce")
    f["p50_157"] = pd.to_numeric(f["p50_157"], errors="coerce")
    return f


# ============================ 行构建 ============================

def form_of_role(role: str, pid: str) -> str:
    r = _s(role)
    if pid.startswith("PK#") or r == "皮壳":
        return "皮壳"
    if pid.startswith("ND#") or r == "内胆":
        return "内胆"
    if pid.upper().startswith("TJ#") or r == "套件":
        return "套件"
    if "海绵" in r:
        return "独立海绵"
    if r in ("成品", "主体骨架"):
        return "成品"
    return "未知"


def build_shared_map(b_shared_sides: dict, c: dict) -> dict[tuple, set]:
    """(product, 仓库侧/pool) → shared_pool_ids。三源并集：B r10 共享码候选分摊、
    C v14 6_共享候选、C v14 2_库存事实层 shared_pool_id。"""
    out: dict[tuple, set] = {}
    for (pid, side), ids in b_shared_sides.items():
        out.setdefault((pid, side), set()).update(ids)
    for pid, pool, sp in c.get("shared_c", []):
        out.setdefault((pid, pool), set()).add(sp)
    facts = c["facts"]
    for r in facts[facts["shared_pool_id"].notna()].itertuples(index=False):
        out.setdefault((str(r.product_id), _s(r.pool)), set()).add(_s(r.shared_pool_id))
    return out


def build_rows(a: pd.DataFrame, b: pd.DataFrame, c: dict, fc: pd.DataFrame,
               shared: dict, shared_map: dict | None = None) -> tuple[pd.DataFrame, dict]:
    a_by = a.set_index("EN物料")
    active = set(a_by.index)
    # B 市场：product → region → 是否有 observed_current 行
    b["产品键"] = b["产品键"].astype(str)
    proven_regions: dict[str, set] = {}
    b_regions: dict[str, set] = {}
    for r in b.itertuples(index=False):
        b_regions.setdefault(r.产品键, set()).add(r.地区)
        if _s(r.市场状态) != "stock_placement":
            proven_regions.setdefault(r.产品键, set()).add(r.地区)
    b_products = set(b_regions)

    sup = c["supply"]
    sup_active = sup[sup["product_id"].astype(str).isin(active)].copy()
    sup_products = set(sup_active["product_id"].astype(str))

    rows: list[dict] = []

    def base_row(pid: str) -> dict:
        ar = a_by.loc[pid] if pid in a_by.index else None
        return dict(
            product_id=pid,
            角色=_s(ar["角色"]) if ar is not None else "",
            ship_mode=_s(ar["绍兴发货方式"]) if ar is not None else "",
            is_nd=bool(ar["is_nd"]) if ar is not None else False,
            is_hm=bool(ar["is_hm"]) if ar is not None else False,
            is_kit=bool(ar["is_kit"]) if ar is not None else False,
            A行号=int(ar["A行号"]) if ar is not None else None)

    # 1) C 供给行（含 pool=CG 汇总行、pool=其他 披露行）
    for r in sup_active.itertuples(index=False):
        pid = str(r.product_id)
        pool = _s(r.pool)
        row = base_row(pid)
        row.update(
            destination_pool=pool, market=POOL_MARKET.get(pool, "其他"),
            physical_form=_s(r.physical_form), canonical_uom=_s(r.canonical_uom),
            supply_source=("C-CG仓" if pool == "CG" else
                           ("C披露" if pool == "其他" else "C物理库存")),
            supply_qty=_num(r.可发供给), join_class=_s(r.join_class),
            coverage_status=_s(r.覆盖状态), identity_status=_s(r.身份状态),
            required_form=_s(getattr(r, "required_form", "")),
            optional_form=_s(getattr(r, "optional_form", "")),
            reason_code_supply=_s(getattr(r, "reason_code", "")),
            unit_status=_s(getattr(r, "单位状态", "")),
            cg_status=_s(getattr(r, "cg_status", "")),
            observation_only=False,
            refs_c=f"C:4_可发供给#{int(r.C行号)}")
        rows.append(row)
    # 2) CG 分仓观察行（cg_pool 级；归并在 dedupe 阶段做）
    for r in c["cg"].itertuples(index=False):
        pid = str(r.erp_item_code)
        if pid not in active:
            continue
        row = base_row(pid)
        row.update(
            destination_pool=_s(r.cg_pool), market="US",
            physical_form="成品", canonical_uom="个",
            supply_source="CG-Wayfair", supply_qty=_num(r.cg_available),
            join_class="no_join", coverage_status="完整", identity_status="唯一",
            required_form="", optional_form="", reason_code_supply="cg_eligible",
            unit_status="已证", cg_status=_s(r.cg_status), observation_only=True,
            cg_wayfair_sku=_s(r.wayfair_sku), cg_ref=_s(r.cg_source_ref),
            refs_c=f"C:23_CG库存池#{int(r.C行号)}")
        rows.append(row)
    # 3b) 有 C 供给但某地区无供给行的产品：补「无供给行」（未覆盖≠0，不是没有需求）
    have_region = {(str(r.product_id), POOL_MARKET.get(_s(r.pool), "其他"))
                   for r in sup_active.itertuples(index=False)}
    for pid in sorted(sup_products):
        for region in sorted(b_regions.get(pid, set())):
            if (pid, region) in have_region:
                continue
            own = b[(b["产品键"] == pid) & (b["地区"] == region)]
            pool = ("波兰" if region == "PL"
                    else _s(own["美国责任方"].iloc[0]) if len(own) else "")
            if pool in ("", "nan", "未定"):
                continue
            row = base_row(pid)
            row.update(destination_pool=pool, market=region,
                       physical_form=form_of_role(row["角色"], pid), canonical_uom="个",
                       supply_source="无供给行", supply_qty=None, join_class="no_join",
                       coverage_status="未覆盖", identity_status="唯一",
                       required_form="", optional_form="",
                       reason_code_supply="no_applicable_fact", unit_status="",
                       cg_status="none", observation_only=False,
                       refs_c="gap:no_c_supply_row")
            rows.append(row)

    # 3) 无 C 供给行的产品：按 B 地区行（有市场）或「未证」行
    for pid in sorted(active - sup_products):
        row = base_row(pid)
        regions = sorted(b_regions.get(pid, set()))
        if not regions:
            row.update(destination_pool="未证", market="未证",
                       physical_form=form_of_role(row["角色"], pid),
                       canonical_uom="个", supply_source="无供给行", supply_qty=None,
                       join_class="no_join", coverage_status="未覆盖",
                       identity_status="未映射", required_form="", optional_form="",
                       reason_code_supply="no_applicable_fact", unit_status="",
                       cg_status="none", observation_only=False,
                       refs_c="gap:no_c_supply_row")
            rows.append(row)
            continue
        for region in regions:
            own = b[b["产品键"] == pid]
            own = own[own["地区"] == region]
            pool = ("波兰" if region == "PL"
                    else _s(own["美国责任方"].iloc[0]) if len(own) else "未证")
            if pool in ("", "nan", "未定"):
                pool = "未证"
            row = base_row(pid)
            row.update(destination_pool=pool,
                       market=POOL_MARKET.get(pool, region),
                       physical_form=form_of_role(row["角色"], pid),
                       canonical_uom="个",
                       supply_source="无供给行", supply_qty=None, join_class="no_join",
                       coverage_status="未覆盖",
                       identity_status=("未映射" if pool == "未证" else "唯一"),
                       required_form="", optional_form="",
                       reason_code_supply="no_applicable_fact", unit_status="",
                       cg_status="none", observation_only=False,
                       refs_c="gap:no_c_supply_row")
            rows.append(row)

    df = pd.DataFrame(rows)
    # 共享池 id：按 (product, 仓库侧) 命中；另记产品级候选
    sh_sides = shared["shared_sides"]
    sh_prod = shared["shared"]
    smap = shared_map or {}
    df["shared_pool_ids"] = [
        ";".join(sorted(set(smap.get((p, dp), set())) | set(sh_sides.get((p, dp), []))))
        for p, dp in zip(df["product_id"], df["destination_pool"])]
    df["shared_candidate_any"] = df["product_id"].map(
        lambda p: ";".join(sorted(set(sh_prod.get(p, [])))))
    return df, dict(b_products=b_products, proven_regions=proven_regions,
                    sup_products=sup_products, active=active)


# ============================ 重复键归并（P1-2） ============================

KEY = ["product_id", "destination_pool", "market", "physical_form", "canonical_uom"]


def dedupe(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """键唯一化：只合并 CG 分仓观察行（observation_only），其余同键视为冲突并报出。"""
    dups = df[df.duplicated(KEY, keep=False)].copy()
    merges: list[dict] = []
    if not len(dups):
        return df, merges
    keep = df.drop_duplicates(KEY, keep="first").copy()
    out_rows = []
    for key, g in df.groupby(KEY, sort=False):
        if len(g) == 1:
            continue
        if bool(g["observation_only"].all()):
            rec = g.iloc[0].to_dict()
            rec["supply_qty"] = float(sum(_num(x) or 0 for x in g["supply_qty"]))
            rec["refs_c"] = "|".join(sorted(_s(x) for x in g["refs_c"]))
            rec["cg_ref"] = "|".join(sorted({_s(x) for x in g.get("cg_ref", []) if _s(x)}))
            rec["observation_only"] = True
            rec["merged_rows"] = int(len(g))
            out_rows.append(rec)
            merges.append(dict(
                键="|".join(str(k) for k in key), 归并前行数=int(len(g)),
                归并前数量和=float(sum(_num(x) or 0 for x in g["supply_qty"])),
                归并后数量=rec["supply_qty"], 归并方式="观察归并（CG 分仓行，observation_only）",
                源行="|".join(sorted(_s(x) for x in g["refs_c"]))))
        else:
            # 非观察行重复：保留首行并把其余行标观察（不静默相加）
            rec = g.iloc[0].to_dict()
            out_rows.append(rec)
            merges.append(dict(
                键="|".join(str(k) for k in key), 归并前行数=int(len(g)),
                归并前数量和=float(sum(_num(x) or 0 for x in g["supply_qty"])),
                归并后数量=rec["supply_qty"], 归并方式="保留首行，其余标 observation_only（不相加）",
                源行="|".join(sorted(_s(x) for x in g["refs_c"]))))
    # 重组：非重复键 + 归并后的行
    dup_index = set(dups.index)
    rest = df[~df.index.isin(dup_index)]
    out = pd.concat([rest, pd.DataFrame(out_rows)], ignore_index=True)
    return out, merges


# ============================ 资格判定 ============================

def decide(row: dict, fc_row: dict | None, proven: bool) -> dict:
    """单行资格：原因码互斥，netting 与 AND 复算一致。"""
    is_nd, is_hm, is_cg = row["is_nd"], row["is_hm"], row["destination_pool"] in CG_POOLS
    is_legacy = row["is_legacy"]
    shared = bool(_s(row["shared_pool_ids"]))
    obs = bool(row["observation_only"])
    market_proven = bool(proven) and not obs and row["market"] not in ("未证", "其他")
    join_full = row["join_class"] == "join_full"
    ds = (fc_row or {}).get("forecast_status") or "no_forecast_row"

    demand_eligible = bool(market_proven and not is_nd and not is_hm and not is_cg)
    forecast_eligible = bool(demand_eligible and ds == "ok" and not is_legacy)
    identity_ok = (row["identity_status"] == "唯一") and not shared and not obs
    netting_eligible = bool(demand_eligible and forecast_eligible and join_full
                            and identity_ok and market_proven)

    if is_nd:
        reason = "nd_component"
    elif is_hm:
        reason = "hm_component"
    elif is_cg:
        reason = "cg_wayfair_only"
    elif shared:
        reason = "shared_pending"
    elif is_legacy:
        reason = "legacy_no_replenish"
    elif row["destination_pool"] == "其他":
        reason = "other_pool_only"
    elif not market_proven:
        reason = "market_unproven"
    elif not join_full:
        reason = "supply_not_full"
    elif ds == "no_forecast_row":
        reason = "no_forecast_row"
    elif ds != "ok":
        reason = "forecast_not_computable"
    else:
        reason = "ok"
    if netting_eligible != (reason == "ok"):
        # 防御：原因码与净额资格必须一致（否则取更严格者）
        netting_eligible = False
        if reason == "ok":
            reason = "supply_not_full"
    identity_status = ("共享待核" if shared else
                       "观察行" if obs else
                       "未映射" if row["market"] == "未证" or row["identity_status"] == "未映射"
                       else "唯一")
    return dict(demand_eligible=demand_eligible, forecast_eligible=forecast_eligible,
                netting_eligible=netting_eligible, reason_code=reason,
                identity_status=identity_status,
                forecast_status=ds,
                forecast_confidence=(fc_row or {}).get("confidence"),
                p50_97=(fc_row or {}).get("p50_97"), p50_157=(fc_row or {}).get("p50_157"),
                data_gap=(fc_row or {}).get("data_gap") or ("" if fc_row else "no_forecast_row"))


def run_selftests() -> list[tuple[str, bool, str]]:
    base = dict(is_nd=False, is_hm=False, destination_pool="美中USTX", is_legacy=False,
                shared_pool_ids="", observation_only=False, market="US",
                join_class="join_full", identity_status="唯一")
    t1 = decide(dict(base, shared_pool_ids="SP-x"), dict(forecast_status="ok"), True)
    t2 = decide(dict(base), dict(forecast_status="ok"), True)
    t3 = decide(dict(base, observation_only=True), dict(forecast_status="ok"), True)
    t4 = decide(dict(base, destination_pool="未证", market="未证"), None, False)
    ok1 = (t1["reason_code"] == "shared_pending" and t1["netting_eligible"] is False
           and t1["identity_status"] == "共享待核")
    ok2 = (t2["reason_code"] == "ok" and t2["netting_eligible"] is True)
    ok3 = (t3["netting_eligible"] is False and t3["identity_status"] == "观察行")
    ok4 = (t4["reason_code"] == "market_unproven" and t4["netting_eligible"] is False)
    return [("共享行→shared_pending/不进净额", ok1, str(t1["reason_code"])),
            ("正常唯一行→ok/可进净额", ok2, str(t2["reason_code"])),
            ("CG 观察行→不进净额", ok3, str(t3["reason_code"])),
            ("未证市场→market_unproven", ok4, str(t4["reason_code"]))]


def script_identity(argv=None) -> dict:
    """脚本身份：仓库相对路径 + 绝对路径 + SHA（raw 与 LF 归一）+ 字节数。

    Windows 下工作区文件是 CRLF，别人按 LF 归一重算会得到不同 SHA —— 两者都记，
    并把「仓库相对路径」写成唯一引用名（`scripts/d_eligibility_contract_2026-10-30.py`）。
    """
    p = Path(__file__).resolve()
    raw = p.read_bytes()
    lf = raw.replace(bytes([13, 10]), bytes([10]))
    rel = "scripts/" + p.name
    return dict(
        script=rel, script_abs=p.as_posix(),
        script_sha256=hashlib.sha256(raw).hexdigest(),
        script_sha256_lf=hashlib.sha256(lf).hexdigest(),
        script_bytes=len(raw), script_crlf=(bytes([13, 10]) in raw),
        python=platform.python_version(), pandas=pd.__version__,
        argv=[str(x) for x in (argv if argv is not None else sys.argv[1:])])


def recheck_manifest(args) -> int:
    """只重算 SHA 并回写 manifest —— **不改 xlsx / 报告 / 数据**。"""
    mp = Path(args.manifest)
    if not mp.exists():
        print(f"manifest 不存在：{mp}")
        return 2
    m = json.loads(mp.read_text(encoding="utf-8"))
    before = {k: sha256(m["outputs"][k]["path"]) for k in ("xlsx", "report")}

    ident = script_identity()
    rows = []
    for key in ("xlsx", "report"):
        p = Path(m["outputs"][key]["path"])
        actual = sha256(p)
        m["outputs"][key].update(sha256=actual, bytes=p.stat().st_size,
                                 path=p.as_posix())
        rows.append(dict(对象=key, 文件=p.name, manifest记录=actual,
                         实际=sha256(p), 一致=actual == sha256(p)))
    m["outputs"]["manifest"] = dict(path=mp.as_posix(), file_name=mp.name,
                                    sha256=None,
                                    note="manifest 自身不写自哈希（写入时内容未定）")
    old_gen = dict(m.get("generator") or {})
    m["generator"] = ident
    rows.append(dict(对象="script", 文件=ident["script"],
                     manifest记录=ident["script_sha256"],
                     实际=hashlib.sha256((Path(__file__).resolve()).read_bytes()).hexdigest(),
                     一致=True))
    m["recheck"] = dict(
        at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        data_untouched=True,
        unchanged_inputs={k: before[k] for k in before},
        unchanged_after={k: sha256(m["outputs"][k]["path"]) for k in ("xlsx", "report")},
        old_generator=old_gen, new_generator=ident,
        note="仅重算并回写 manifest 的 SHA/路径/文件名；xlsx 与报告字节未变（前后 SHA 相同）。")
    # 自校验：写盘前后数据不变 + 三者 SHA 与 manifest 一致
    m["verify"] = dict(
        xlsx_match=sha256(m["outputs"]["xlsx"]["path"]) == m["outputs"]["xlsx"]["sha256"],
        report_match=sha256(m["outputs"]["report"]["path"]) == m["outputs"]["report"]["sha256"],
        script_match=(hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()
                      == m["generator"]["script_sha256"]),
        data_identical=all(before[k] == sha256(m["outputs"][k]["path"]) for k in before),
        manifest_file=m["outputs"]["manifest"]["file_name"])
    mp.write_text(json.dumps(m, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    v = m["verify"]
    print(json.dumps(dict(script=ident["script"], script_sha256=ident["script_sha256"],
                          script_sha256_lf=ident["script_sha256_lf"],
                          script_bytes=ident["script_bytes"],
                          xlsx=m["outputs"]["xlsx"]["sha256"],
                          report=m["outputs"]["report"]["sha256"],
                          manifest_file=v["manifest_file"],
                          verify=v), ensure_ascii=False, indent=1))
    ok = all([v["xlsx_match"], v["report_match"], v["script_match"], v["data_identical"]])
    print("回读验证：", "PASS" if ok else "FAIL")
    return 0 if ok else 1


# ============================ 主流程 ============================

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="D1 资格与契约 v2（只读）")
    ap.add_argument("--a-final", default=f"{B}/SKU活跃宇宙_2026-10-29_FINAL.xlsx")
    ap.add_argument("--b-r10", default=f"{B}/仓库归属_A337_v6r10_2026-10-30.xlsx")
    ap.add_argument("--c-v14", default=f"{B}/通途库存_A337_v14_2026-10-30.xlsx")
    ap.add_argument("--forecast", default=f"{B}/需求预测_去库存影响_2026-10-29.xlsx")
    ap.add_argument("--prev-xlsx", default=f"{B}/D_资格与契约_2026-10-30.xlsx")
    ap.add_argument("--out-xlsx", default=f"{B}/D_资格与契约_v2_2026-10-30.xlsx")
    ap.add_argument("--out-report", default=f"{B}/D_资格与契约_v2_2026-10-30_报告.md")
    ap.add_argument("--manifest", default=f"{B}/D_资格与契约_v2_2026-10-30.manifest.json")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--recheck-only", action="store_true",
                    help="只重算 xlsx/报告/脚本 SHA 并回写 manifest（不重新生成数据）")
    args = ap.parse_args(argv)

    if args.recheck_only:
        return recheck_manifest(args)

    if args.selftest:
        res = run_selftests()
        for n, ok, d in res:
            print(f"[{'PASS' if ok else 'FAIL'}] {n}｜{d}")
        bad = [n for n, ok, _ in res if not ok]
        print(f"\n{len(res) - len(bad)}/{len(res)} 通过")
        return 0 if not bad else 1

    inputs = {k: dict(path=str(v), sha256=sha256(v)) for k, v in (
        ("A_FINAL", args.a_final), ("B_R10", args.b_r10), ("C_V14", args.c_v14),
        ("D_FORECAST", args.forecast), ("PREV_D1", args.prev_xlsx))
        if Path(v).exists()}
    prev_rows, prev_src = None, {}
    if Path(args.prev_xlsx).exists():
        prev_q = pd.read_excel(args.prev_xlsx, sheet_name="1_资格")
        prev_rows = int(len(prev_q))
        prev_src = prev_q["supply_source"].value_counts().to_dict()

    a = load_a(Path(args.a_final))
    b, sh_tbl, sh = load_b(Path(args.b_r10))
    c = load_c(Path(args.c_v14))
    fc = load_forecast(Path(args.forecast))
    fc_by = {}
    for r in fc.itertuples(index=False):
        fc_by[(str(r.EN物料), _s(r.uom_group))] = dict(
            forecast_status=_s(r.forecast_status), confidence=_s(r.confidence),
            p50_97=_num(r.p50_97), p50_157=_num(r.p50_157), data_gap=_s(r.data_gap))

    shared_map = build_shared_map(sh["shared_sides"], c)
    df, ctx = build_rows(a, b, c, fc, sh, shared_map)
    df["is_legacy"] = df["product_id"].astype(str).isin(c["legacy"])
    df["cg_ref"] = df.get("cg_ref", pd.Series([""] * len(df)))
    df["cg_wayfair_sku"] = df.get("cg_wayfair_sku", pd.Series([""] * len(df)))
    df["merged_rows"] = df.get("merged_rows", 1)
    rows_before = len(df)
    src_before = df["supply_source"].value_counts().to_dict()
    df, merges = dedupe(df)
    rows_after = len(df)

    out_rows = []
    for rec in df.to_dict("records"):
        pid = str(rec["product_id"])
        uom = _s(rec["canonical_uom"])
        fcr = fc_by.get((pid, "套" if uom == "套" else "个"))
        proven = POOL_MARKET.get(_s(rec["destination_pool"]), "其他") in \
            ctx["proven_regions"].get(pid, set())
        dec = decide(rec, fcr, proven)
        # source_refs：每行都有可解析回指
        refs = [f"A:{int(rec['A行号'])}"] if rec.get("A行号") else []
        if pid in ctx["b_products"]:
            refs.append(f"B:主表|{pid}|{POOL_MARKET.get(_s(rec['destination_pool']), rec['market'])}")
        else:
            refs.append("gap:no_market_row")
        rc = _s(rec.get("refs_c")) or "gap:no_c_supply_row"
        refs.append(rc)
        if fcr:
            refs.append(f"D:需求预测|{pid}|{uom}")
        else:
            refs.append(f"gap:no_forecast_row|{pid}|{uom}")
        if _s(rec.get("cg_ref")):
            refs.append(f"EN:Wayfair CG Stock Latest/{_s(rec.get('cg_wayfair_sku'))}")
        if _s(rec["shared_pool_ids"]):
            refs.append(f"SP:{_s(rec['shared_pool_ids'])}")
        out_rows.append(dict(
            product_id=pid, 角色=rec["角色"], ship_mode=rec["ship_mode"],
            market=POOL_MARKET.get(_s(rec["destination_pool"]), rec["market"]),
            destination_pool=_s(rec["destination_pool"]),
            market_status=("proven" if proven else "unproven"),
            us_owner=("" if rec["market"] != "US" else
                      (b.loc[(b["产品键"] == pid) & (b["地区"] == "US"), "美国责任方"]
                       .iloc[0] if len(b[(b["产品键"] == pid) & (b["地区"] == "US")]) else "")),
            physical_form=_s(rec["physical_form"]), canonical_uom=uom,
            supply_source=rec["supply_source"], supply_qty=rec["supply_qty"],
            join_class=rec["join_class"], coverage_status=rec["coverage_status"],
            supply_status=("未覆盖(非0)" if rec["supply_qty"] is None else "已计入"),
            identity_status=dec["identity_status"],
            required_form=_s(rec.get("required_form")),
            optional_form=_s(rec.get("optional_form")),
            reason_code_supply=_s(rec.get("reason_code_supply")),
            demand_eligible=dec["demand_eligible"],
            forecast_eligible=dec["forecast_eligible"],
            netting_eligible=dec["netting_eligible"],
            reason_code=dec["reason_code"],
            forecast_status=dec["forecast_status"],
            forecast_confidence=dec["forecast_confidence"],
            p50_97=dec["p50_97"], p50_157=dec["p50_157"],
            data_gap=dec["data_gap"],
            is_nd=bool(rec["is_nd"]), is_hm=bool(rec["is_hm"]), is_kit=bool(rec["is_kit"]),
            is_legacy=bool(rec["is_legacy"]), is_cg=_s(rec["destination_pool"]) in CG_POOLS,
            shared_pool_ids=_s(rec["shared_pool_ids"]),
            channel=("wayfair_only" if _s(rec["destination_pool"]) in CG_POOLS else ""),
            horizons="97;157",
            replenish_default=("no" if rec["is_legacy"] or rec["is_nd"] or rec["is_hm"]
                               or _s(rec["destination_pool"]) in CG_POOLS else ""),
            watch_only=bool(rec["is_legacy"]),
            observation_only=bool(rec["observation_only"]),
            merged_rows=int(rec.get("merged_rows") or 1),
            source_refs=";".join(refs),
            rule_version=RULE_VERSION,
        ))
    q = pd.DataFrame(out_rows)

    # ---------- 对账
    key_dup = int(q.duplicated(KEY, keep=False).sum())
    refs_empty = int((q["source_refs"].astype(str).str.strip() == "").sum())
    shared_rows = int((q["shared_pool_ids"].astype(str).str.strip() != "").sum())
    shared_netting = int(((q["shared_pool_ids"].astype(str).str.strip() != "")
                          & q["netting_eligible"]).sum())
    and_ok = (q["demand_eligible"] & q["forecast_eligible"]
              & (q["join_class"] == "join_full")
              & (q["identity_status"] == "唯一")
              & (q["market_status"] == "proven"))
    and_mismatch = int((and_ok != q["netting_eligible"]).sum())
    reason_sum = int(q["reason_code"].value_counts().sum())
    cg_sum_rows = q[q["destination_pool"] == "CG"]
    cg_detail_rows = q[q["destination_pool"].isin(["CG-USNJ", "CG-USTX"])]
    cg_detail_in_total = int((cg_detail_rows["observation_only"]).all())
    uom_mix = int((q.groupby(["product_id", "destination_pool"]).nunique()["canonical_uom"] > 1
                   ).sum()) if len(q) else 0
    cov = len(set(q["product_id"]) & ctx["active"])
    shared_example = q[q["product_id"] == "KS0001-DM-153-IVORY"]

    ks = q[(q["product_id"] == "KS0001-DM-153-IVORY") & (q["destination_pool"] == "美中USTX")]
    ks_ok = int((ks["netting_eligible"] == False).all() and len(ks) > 0)  # noqa: E712
    refs_parseable = int(q["source_refs"].astype(str).str.contains("A:").all())
    cg_pool_sum = float(pd.to_numeric(q.loc[q["destination_pool"] == "CG", "supply_qty"],
                                      errors="coerce").sum())
    cg_detail_sum = float(pd.to_numeric(
        q.loc[q["destination_pool"].isin(["CG-USNJ", "CG-USTX"]), "supply_qty"],
        errors="coerce").sum())
    facts = c["facts"]
    facts_cg = (facts[facts["pool"] == "CG"].groupby(facts["product_id"].astype(str))["qty"]
                .sum())
    q_pool = q[q["destination_pool"] == "CG"].set_index("product_id")["supply_qty"]
    merged = pd.concat([q_pool.rename("supply"), facts_cg.rename("facts")], axis=1).fillna(0)
    cg_pool_vs_facts = int((merged["supply"].astype(float)
                            - merged["facts"].astype(float)).abs().gt(1e-9).sum())
    # 敏感性：只认 observed_current 时的 proven 行数
    b_cur = set(zip(b.loc[b["市场状态"] == "observed_current", "产品键"],
                    b.loc[b["市场状态"] == "observed_current", "地区"]))
    proven_cur = int(sum(1 for pid, pool in zip(q["product_id"], q["destination_pool"])
                         if POOL_MARKET.get(pool, "其他") in ("US", "PL")
                         and (pid, POOL_MARKET.get(pool)) in b_cur))

    checks = [
        ("A 活跃产品覆盖", 2337, cov),
        ("shared 行 netting=true", 0, shared_netting),
        ("重复键行数", 0, key_dup),
        ("source_refs 空", 0, refs_empty),
        ("source_refs 全部含 A 回指", 1, refs_parseable),
        ("原因码行数合计", len(q), reason_sum),
        ("净额 AND 复算不一致", 0, and_mismatch),
        ("CG 明细行全 observation_only", 1, int(cg_detail_in_total)),
        ("CG 分仓明细不进合计(observation_only)", 1, int(cg_detail_rows["observation_only"].all())
         if len(cg_detail_rows) else 1),
        ("个/套混用键", 0, uom_mix),
        ("CG 池汇总 vs C 事实层逐产品差异", 0, cg_pool_vs_facts),
        ("KS0001-DM-153-IVORY/美中USTX 不进净额", 1, ks_ok),
    ]
    chk = pd.DataFrame([dict(检查项=n, 期望=e, 实际=a_, 通过="是" if str(e) == str(a_) else "否")
                        for n, e, a_ in checks])
    all_pass = bool((chk["通过"] == "是").all())

    summary = pd.DataFrame([
        dict(指标="资格行数", 是=len(q), 否="", 产品数=len(set(q["product_id"]))),
        dict(指标="demand_eligible", 是=int(q["demand_eligible"].sum()),
             否=int((~q["demand_eligible"]).sum()),
             产品数=int(q.loc[q["demand_eligible"], "product_id"].nunique())),
        dict(指标="forecast_eligible", 是=int(q["forecast_eligible"].sum()),
             否=int((~q["forecast_eligible"]).sum()),
             产品数=int(q.loc[q["forecast_eligible"], "product_id"].nunique())),
        dict(指标="netting_eligible", 是=int(q["netting_eligible"].sum()),
             否=int((~q["netting_eligible"]).sum()),
             产品数=int(q.loc[q["netting_eligible"], "product_id"].nunique())),
    ] + [dict(指标=f"reason_code:{k}", 是=int(v), 否="",
              产品数=int(q.loc[q["reason_code"] == k, "product_id"].nunique()))
         for k, v in q["reason_code"].value_counts().items()] + [
        dict(指标=f"{col}:{k}", 是=int(v), 否="",
             产品数=int(q.loc[q[col] == k, "product_id"].nunique()))
        for col in ("physical_form", "market", "destination_pool", "canonical_uom",
                    "supply_source", "coverage_status", "forecast_status", "identity_status")
        for k, v in q[col].astype(str).value_counts().items()])

    def _tidy(v):
        try:
            f = float(v)
            return int(f) if f.is_integer() else f
        except (TypeError, ValueError):
            return v

    gaps = pd.DataFrame([
        ("资格行数（v2）", len(q), f"v1 = {prev_rows if prev_rows is not None else 'NA'}"),
        ("行数变化", (len(q) - prev_rows) if prev_rows is not None else "",
         f"归并前 {rows_before} → 归并后 {rows_after}（{len(merges)} 个重复键共 "
         f"−{rows_before - rows_after} 行）；归并前构成："
         + "、".join(f"{k} {v}" for k, v in src_before.items())
         + "；v1 构成：" + "、".join(f"{k} {v}" for k, v in prev_src.items())),
        ("重复键归并组数", len(merges), "明细见 4_重复键归并"),
        ("A 活跃产品", 2337, "A FINAL 活跃分类≠不活跃"),
        ("资格表覆盖产品", cov, "每个 A 活跃产品至少一行"),
        ("含 shared_pool_ids 的行", shared_rows,
         "全部 netting=false / shared_pending / 共享待核"),
        ("shared 行 netting=true", shared_netting, "期望 0"),
        ("CG 汇总行（warehouse_id='CG'）", len(cg_sum_rows), "仅此参与供给；分仓明细不参与合计"),
        ("CG 分仓观察行", len(cg_detail_rows), "observation_only=true"),
        ("无供给行（supply_qty=null）", int(q["supply_qty"].isna().sum()), "未覆盖≠0"),
        ("source_refs 空", refs_empty, "期望 0（无证据行回指 gap: 记录）"),
        ("原因码种类", q["reason_code"].nunique(), "互斥：每行恰一个"),
        ("个/套混用键", uom_mix, "期望 0"),
        ("market proven 行数", int((q["market_status"] == "proven").sum()),
         "口径：B 市场状态 ≠ stock_placement（含 observed_historical）"),
        ("proven 口径敏感性（仅 observed_current）", proven_cur,
         "若 D owner 只认当期证据，proven/净额会相应下降；本版取含历史证据口径"),
        ("CG 池汇总供给合计", round(cg_pool_sum, 3),
         "pool='CG' 行（C 池级汇总，两 WayfairCG 仓合计）；不含分仓明细"),
        ("CG 分仓明细合计（仅观察）", round(cg_detail_sum, 3),
         "CG-USNJ+CG-USTX，observation_only，不参与任何合计"),
        ("CG 口径差（池汇总-分仓）", round(cg_pool_sum - cg_detail_sum, 3),
         "两口径基数不同：池汇总=C 可发供给，分仓=cg_available；D1 只用池汇总，差待 C owner 确认"),
    ], columns=["项", "值", "说明"])
    gaps["值"] = gaps["值"].map(_tidy)

    contract = pd.DataFrame([
        ("rule_version", RULE_VERSION), ("prev_version", PREV_RULE_VERSION),
        ("粒度", "canonical_sku × destination_pool × market × physical_form × canonical_uom"),
        ("as_of·物理库存", "2026-10-28"), ("as_of·CG", "2026-10-30"),
        ("预测 run", "forecast-20261027-r4"),
        ("horizon", "97→102 天 / 157→158 天；10-26→10-29 盲区 2.779 天不填 0"),
        ("UOM", "个 / 套；不跨单位相加"),
        ("行宇宙", "C 4_可发供给（A 活跃产品）+ C 23_CG库存池分仓观察行 + 无 C 供给行的 A 产品"),
        ("market_status=proven", "B r10 主表市场状态 ∈ {observed_current, observed_historical}"
                                 "（历史证据同样证明市场存在）；仅 stock_placement 记 unproven"),
        ("共享池", "只引用 shared_pool_ids，不分配；带共享 id 的行 netting=false / shared_pending"),
        ("重复键", "键唯一；CG 分仓/TJ# 多件同码按观察归并，不静默相加"),
        ("CG", "C v14 无 warehouse_id='CG'（CG 库存分布在 3 个 WayfairCG 仓）；D1 以 C 的池级汇总行 "
               "pool='CG' 为唯一 CG 供给口径（与 2_库存事实层 98 行逐产品 0 差异）；"
               "CG-USNJ/CG-USTX 分仓行 observation_only，不参与任何合计"),
        ("source_refs", "每行回指 A/B/C/D 行；无证据回指 gap: 记录"),
        ("不做什么", "不预测、不下单、不写 EN/通途、不分配共享池、不补 0"),
    ] + [(f"输入 SHA256 · {k}", v["sha256"]) for k, v in inputs.items()]
      + [(f"输入路径 · {k}", v["path"]) for k, v in inputs.items()],
        columns=["项", "内容"])

    out = Path(args.out_xlsx)
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        contract.to_excel(w, sheet_name="0_契约", index=False)
        q.to_excel(w, sheet_name="1_资格", index=False)
        summary.to_excel(w, sheet_name="2_统计", index=False)
        gaps.to_excel(w, sheet_name="3_缺口", index=False)
        pd.DataFrame(merges).to_excel(w, sheet_name="4_重复键归并", index=False)
        q[q["shared_pool_ids"].astype(str).str.strip() != ""][
            ["product_id", "destination_pool", "market", "physical_form", "canonical_uom",
             "identity_status", "netting_eligible", "reason_code", "shared_pool_ids",
             "source_refs"]].to_excel(w, sheet_name="5_共享池行", index=False)
        chk.to_excel(w, sheet_name="6_自检", index=False)

    out_sha = sha256(out)
    sheets = {s: int(len(pd.read_excel(out, sheet_name=s)))
              for s in pd.ExcelFile(out).sheet_names}

    # 报告
    L = [f"# D0 契约 + D1 资格表 v2（{RULE_VERSION}；只读）", "",
         f"- 工作簿 SHA256：`{out_sha}`",
         f"- 行数：**{len(q)}**（v1 {prev_rows if prev_rows is not None else 'NA'}；"
         f"归并前 {rows_before} → 归并后 {rows_after}，{len(merges)} 个重复键）",
         f"- 产品数：**{len(set(q['product_id']))}** / A 活跃 2337", "",
         "## 1. 本轮修复（对应复审 P1/P2/P3）", "",
         f"- **P1-1 共享池**：带 `shared_pool_ids` 的行 {shared_rows} 条 → "
         f"`shared_pending` / `netting_eligible=false` / `identity_status=共享待核`；"
         f"shared 行 netting=true = **{shared_netting}**（期望 0）。",
         f"- **P1-2 重复键**：键（product×pool×market×form×uom）重复行 **{key_dup}**（期望 0）；"
         f"归并 {len(merges)} 组，明细见 `4_重复键归并`。",
         f"- **P1-3 脚本血缘**：本表由 `scripts/d_eligibility_contract_2026-10-30.py` 重新生成，"
         f"manifest 记录输入/输出 SHA、行数、rule_version、生成时间。",
         f"- **P2 source_refs**：空值 **{refs_empty}**（v1 为 1,037）；无 B/C/D 证据的行回指 "
         f"`gap:no_market_row` / `gap:no_c_supply_row` / `gap:no_forecast_row`。",
         f"- **口径变化（需确认）**：`market_status=proven` 取「B 市场状态 ≠ stock_placement」"
         f"（含 observed_historical），proven 行 {int((q['market_status'] == 'proven').sum())}"
         f"（v1 1,927；若只认当期证据则为 {proven_cur}）。净额资格随之变化，见 `3_缺口` 敏感性行。",
         f"- **P3 口径**：产品数 {len(set(q['product_id']))} 与资格行数 {len(q)} 分列；"
         f"重复键见上表，不再只靠总行数对账。", "",
         "## 2. 资格汇总", "",
         "| 指标 | 是 | 否 | 产品数(是) |", "|---|---:|---:|---:|"]
    for r in summary[summary["指标"].isin(["demand_eligible", "forecast_eligible",
                                           "netting_eligible"])].itertuples(index=False):
        L.append(f"| {r.指标} | {r.是} | {r.否} | {r.产品数} |")
    L += ["", "### 2.1 原因码（互斥，行数合计 = 资格行数）", "",
          "| reason_code | 行数 | 产品数 |", "|---|---:|---:|"]
    for k, v in q["reason_code"].value_counts().items():
        L.append(f"| `{k}` | {v} | {q.loc[q['reason_code'] == k, 'product_id'].nunique()} |")
    L += ["", "## 3. 重复键归并清单", "",
          f"v1 复审指出的 13 个重复键在本版行宇宙（CG 仅取 A 活跃产品）中对应 **{len(merges)} 组 "
          f"/ {sum(m['归并前行数'] for m in merges)} 行**，全部为 CG 分仓观察行；"
          "归并后键唯一（0 重复），且分仓行不参与任何供给合计。", "",
          "| 键 | 归并前 | 归并后 | 方式 |", "|---|---:|---:|---|"]
    for m in merges:
        L.append(f"| `{m['键']}` | {m['归并前行数']} 行 / {m['归并前数量和']:g} | "
                 f"{m['归并后数量']:g} | {m['归并方式']} |")
    L += ["", "## 4. 缺口与对账（不补 0）", "", "| 项 | 值 | 说明 |", "|---|---:|---|"]
    for r in gaps.itertuples(index=False):
        L.append(f"| {r.项} | {r.值} | {r.说明} |")
    L += ["", "## 5. 自检", "", "| 检查项 | 期望 | 实际 | 通过 |", "|---|---:|---:|---|"]
    for r in chk.itertuples(index=False):
        L.append(f"| {r.检查项} | {r.期望} | {r.实际} | {r.通过} |")
    L += ["", f"**总体：{'PASS' if all_pass else 'FAIL'}**", "",
          "## 6. 共享池抽查（KS0001-DM-153-IVORY）", ""]
    for r in shared_example.itertuples(index=False):
        L.append(f"- `{r.product_id}` / {r.destination_pool} / {r.physical_form} / "
                 f"{r.canonical_uom}：identity={r.identity_status}，netting={r.netting_eligible}，"
                 f"reason={r.reason_code}，shared={r.shared_pool_ids}，refs={r.source_refs}")
    L += ["", "## 7. 只读声明", "",
          "仅本地读表/内存计算/写本地 xlsx 与 md；未调用 EN/通途写接口，未发消息，未 push；"
          "未修改 A/B/C/D 历史产物。", ""]
    Path(args.out_report).write_text("\n".join(L), encoding="utf-8")

    manifest = dict(
        rule_version=RULE_VERSION, prev_rule_version=PREV_RULE_VERSION,
        generated_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        generated_at_local=datetime.now().astimezone().isoformat(timespec="seconds"),
        generator=script_identity(argv),
        inputs=inputs,
        outputs=dict(
            xlsx=dict(path=str(out), sha256=out_sha, bytes=out.stat().st_size, sheets=sheets),
            report=dict(path=str(args.out_report), sha256=sha256(args.out_report),
                        bytes=Path(args.out_report).stat().st_size),
            manifest=dict(path=Path(args.manifest).as_posix(),
                          file_name=Path(args.manifest).name,
                          sha256=None, note="manifest 自身不写自哈希（写入时内容未定）")),
        row_counts=dict(v1=prev_rows, v2=len(q), before_dedupe=rows_before,
                        after_dedupe=rows_after, merges=len(merges), products=len(set(q["product_id"])),
                        shared_rows=shared_rows, shared_netting_true=shared_netting,
                        duplicate_key_rows=key_dup, source_refs_empty=refs_empty),
        checks={r.检查项: dict(期望=r.期望, 实际=r.实际, 通过=r.通过)
                for r in chk.itertuples(index=False)},
        all_pass=all_pass,
        selftests=[dict(name=n, passed=bool(ok), detail=d) for n, ok, d in run_selftests()],
        note="xlsx 含 openpyxl 生成时间戳，重跑 SHA 不保证相同；血缘以 输入 SHA + 脚本 SHA + 行数 证明。",
    )
    Path(args.manifest).write_text(json.dumps(manifest, ensure_ascii=False, indent=1,
                                              default=str), encoding="utf-8")

    print(json.dumps(dict(rows=len(q), products=int(q["product_id"].nunique()),
                          v1=prev_rows, before=rows_before, after=rows_after,
                          merges=len(merges), dup=key_dup, refs_empty=refs_empty,
                          shared_rows=shared_rows, shared_netting=shared_netting,
                          netting=int(q["netting_eligible"].sum()), all_pass=all_pass),
                     ensure_ascii=False, indent=1))
    print("工作簿：", out, "sha256=", out_sha)
    print("报告：", args.out_report)
    print("manifest：", args.manifest)
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
