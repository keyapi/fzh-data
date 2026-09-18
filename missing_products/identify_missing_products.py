# -*- coding: utf-8 -*-
"""
Saihu missing product gap analysis.

Identifies products that should exist in Saihu (based on EN Item Groups + Tongtu
inventory status) but were potentially missed during the initial May-June 2026 import.

Data sources (4):
  1. Tongtu inventory   → browser-automation export
  2. EN BOM cost list   → local xlsx
  3. Saihu products     → Sellfox OpenAPI
  4. EN Item Groups     → ERPNext REST API

Usage:
  uv run python identify_missing_products.py
"""

from __future__ import annotations

import json, os, sys, time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from requests.adapters import HTTPAdapter

# ── Paths ──────────────────────────────────────────────────────
_HERE   = Path(__file__).resolve().parent
_ROOT   = _HERE.parent
_MAIN   = Path(r"D:\Work\赛狐\Cursor")
_WEB    = _ROOT / "web_automation"

for _p in [_ROOT, _MAIN]:
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from SELLFOX_API.client import SellfoxClient, SellfoxConfig

# ── Config ─────────────────────────────────────────────────────
ENV = os.environ

def _load_dotenv(paths: list[Path]) -> None:
    for p in paths:
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line: continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"',"'"): v = v[1:-1]
                ENV.setdefault(k, v)
        except FileNotFoundError: pass

_load_dotenv([_MAIN / ".env", _MAIN / "EN_API" / ".env", _HERE / ".env"])

# ── Constants ──────────────────────────────────────────────────
_EN_BOM_DIR = _MAIN / "warehouse_restock" / "数据源"
_OUT_DIR    = _HERE / "out"
_OUT_DIR.mkdir(parents=True, exist_ok=True)

KNOWN_SUFFIXES = ["-淘汰","-out","-Cover","-Foam"]

# ── Helpers ────────────────────────────────────────────────────
def _clean(sku: str) -> str:
    s = str(sku).strip()
    for sfx in KNOWN_SUFFIXES:
        if s.endswith(sfx): s = s[:-len(sfx)]; break
    return s

def _spu(sku: str) -> str:
    parts = str(sku).strip().split("-", 1)
    return parts[0] if parts else ""

def _norm(x: Any) -> str:
    if pd.isna(x) or x is None: return ""
    return str(x).strip()

def _suffix(sku: str) -> str:
    s = str(sku).strip()
    if s.endswith("-ALL"):    return "套件(-ALL)"
    if s.endswith("-Cover"):  return "拆多包(-Cover)"
    if s.endswith("-Foam"):   return "拆多包(-Foam)"
    if s.endswith("-淘汰"):    return "淘汰(-淘汰)"
    if s.endswith("-out"):    return "淘汰(-out)"
    return ""

def _auto_select(d: Path, pat: str) -> Path | None:
    cs = [f for f in d.glob(pat) if not f.name.startswith("~$")]
    return max(cs, key=lambda f: f.stat().st_mtime) if cs else None

# ═══════════════════════════════════════════════════════════════
# Data loaders
# ═══════════════════════════════════════════════════════════════

def load_tongtu() -> pd.DataFrame:
    for d in [_WEB / "output", _WEB / "downloads", _HERE / "数据源"]:
        f = _auto_select(d, "通途合并库存结存清单*.xlsx")
        if f:
            print(f"通途: {f.name}")
            df = pd.read_excel(f)
            n = len(df)
            if "可用库存" in df.columns:
                df = df[df["可用库存"] > 0].copy()
            print(f"  全量 {n} → 有库存 {len(df)} 行 ({df['SKU'].nunique()} SKU)")
            return df
    raise FileNotFoundError("No Tongtu file")

def load_bom() -> pd.DataFrame:
    for d in [_EN_BOM_DIR, _HERE / "数据源"]:
        f = _auto_select(d, "EN产品BOM成本列表*.xlsx")
        if f:
            print(f"EN BOM: {f.name}")
            return pd.read_excel(f)
    raise FileNotFoundError("No BOM file")

def load_spu_status() -> dict[str, dict]:
    for d in [_HERE / "数据源", _MAIN / "multi_attr_saihu"]:
        f = _auto_select(d, "EN物料属性*.xlsx")
        if f:
            print(f"物料属性: {f.name}")
            df = pd.read_excel(f, sheet_name="Sheet1")
            r = {}
            for _, x in df.iterrows():
                s = _norm(x.get("款式ID",""));
                if not s: continue
                r[s] = {"onsale": int(float(x.get("在售",0) or 0)),
                        "has_stock": _norm(x.get("还有库存","")) == "有"}
            print(f"  {len(r)} 款式ID")
            return r
    print("物料属性: 未找到")
    return {}

def fetch_en_items() -> tuple[list[dict], dict[str,dict]]:
    """Fetch all Item Groups under 产品 + all Items from EN API."""
    u = ENV.get("ERP_URL","https://erpnext.vilavi.cn").rstrip("/")
    k = ENV.get("PROD_ERP_API_KEY") or ENV.get("ERP_API_KEY","")
    s = ENV.get("PROD_ERP_API_SECRET") or ENV.get("ERP_API_SECRET","")
    if not k or not s: raise RuntimeError("No EN API credentials")
    print(f"EN API: {u}")

    class A(HTTPAdapter):
        def send(self, r, **kw): r.headers.pop("Expect",None); return super().send(r,**kw)
    ses = requests.Session()
    ses.headers["Authorization"] = f"token {k}:{s}"
    ses.mount("https://", A()); ses.mount("http://", A())

    # Item Groups
    ig = ses.get(f"{u}/api/resource/Item Group", params={
        "fields": json.dumps(["name","item_group_name","parent_item_group","is_group","custom_model_id"]),
        "limit_page_length": "0",
    }, timeout=(60,120)).json().get("data",[])
    print(f"  Item Group: {len(ig)} total")

    # Filter: under 产品, leaf, has custom_model_id
    idx = {d["name"]: d for d in ig if d.get("name")}
    def _under(n, v=None):
        if v is None: v=set()
        if n in v: return False; v.add(n)
        if n == "产品": return True
        p = idx.get(n,{}).get("parent_item_group",""); return _under(p,v) if p else False

    leaves = [d for d in ig if d.get("is_group")==0 and _norm(d.get("custom_model_id")) and _under(d["name"])]
    print(f"  产品子树叶子(有model_id): {len(leaves)}")

    # All Items for full product list
    items = ses.get(f"{u}/api/resource/Item", params={
        "fields": json.dumps(["name","item_code","item_name","item_group","disabled","custom_tongtu_sku"]),
        "limit_page_length": "0",
    }, timeout=(60,180)).json().get("data",[])
    print(f"  Items: {len(items)} total")

    return leaves, ig, items

def fetch_saihu() -> tuple[dict,dict,set]:
    """Fetch Saihu SPU + SKU lists. Returns (spu_map, saihu_sku_map, all_skus)."""
    print("赛狐 API: 拉取...")
    cfg = SellfoxConfig.from_env()
    cl = SellfoxClient(cfg)
    spu_map, all_skus = {}, set()
    # SKU map: SKU → {spu, name, isGroup, state}
    sku_map = {}

    pg, sz = 1, 200
    while True:
        try:
            d = cl.signed_post("/api/commodity/getCommoditySpuList.json",
                               {"pageNo":str(pg),"pageSize":str(sz)})
        except Exception as e:
            print(f"  SPU err: {e}"); break
        rows = d.get("rows") or []
        if not rows: break
        for obj in rows:
            sp = _norm(obj.get("spu"));
            if not sp: continue
            skus = set()
            for s in (obj.get("skuList") or []):
                sc = _norm(s.get("sku"))
                if sc: skus.add(sc); all_skus.add(sc)
            spu_map[sp] = {"spu":sp,"name":_norm(obj.get("spuName")),"id":_norm(obj.get("spuId")),"skus":skus}
        if len(rows) < sz: break
        pg += 1; time.sleep(0.3)

    # Full SKU pageList for non-SPU SKUs
    pg = 1
    while True:
        try:
            d = cl.signed_post("/api/commodity/pageList.json",
                               {"pageNo":str(pg),"pageSize":str(sz)})
        except Exception as e:
            print(f"  SKU err: {e}"); break
        rows = d.get("rows") or []
        if not rows: break
        for obj in rows:
            sc = _norm(obj.get("sku"))
            if sc:
                all_skus.add(sc)
                sp = _norm(obj.get("spu",""))
                sku_map[sc] = {"spu":sp,"name":_norm(obj.get("name","")),
                               "isGroup":_norm(obj.get("isGroup","")),
                               "state":_norm(obj.get("state",""))}
        if len(rows) < sz: break
        pg += 1; time.sleep(0.3)

    print(f"  赛狐 SPU={len(spu_map)} SKU={len(all_skus)}")
    return spu_map, sku_map, all_skus

# ═══════════════════════════════════════════════════════════════
# Classification helpers
# ═══════════════════════════════════════════════════════════════

def _classify_tt_unmatched(sku: str) -> str:
    s = sku.upper()
    if any(k in s for k in ["BUTTONKIT","COTTON","CARD","-PP","5LB","BOX-PL"]):
        return "辅料/耗材类"
    if s.startswith("497") and len(s)>=9: return "疑似Amazon ASIN"
    if s.startswith("TT0") and any(c.isdigit() for c in s[2:]): return "TT编码(需核实)"
    if s.startswith("CEN") and ("OLD" in s): return "淘汰旧编码"
    return "其他未分类"

# ═══════════════════════════════════════════════════════════════
# Core analysis
# ═══════════════════════════════════════════════════════════════

def analyze(df_tt, df_bom, en_leaves, saihu_spu_map, saihu_sku_map, all_saihu_skus, spu_status):
    """Returns dict of report sheets."""

    # ── EN structures (case-insensitive matching for customer material numbers)──
    cust_to_en = {}
    for _, r in df_bom.iterrows():
        c = _norm(r.get("客户物料号","")).lower(); p = _norm(r.get("产品编号",""))
        if c and p: cust_to_en.setdefault(c,[]).append(p)

    en_prod_info = {}
    for _, r in df_bom.iterrows():
        p = _norm(r.get("产品编号",""))
        if p: en_prod_info[p] = {"name":_norm(r.get("产品名称","")),
                                  "group":_norm(r.get("物料组","")),
                                  "ship":_norm(r.get("绍兴发货方式","")),
                                  "cust":_norm(r.get("客户物料号",""))}

    en_spu_set = set(); en_spu_info = {}
    for lf in en_leaves:
        sp = _norm(lf.get("custom_model_id"))
        if sp: en_spu_set.add(sp); en_spu_info[sp] = {"name":lf.get("item_group_name",""),
                                                       "parent":lf.get("parent_item_group","")}

    # Tongtu SKU → stock
    tt_sku_stock = {}; tt_sku_wh = {}; tt_sku_name = {}
    for _, r in df_tt.iterrows():
        sk = _norm(r.get("SKU",""))
        if not sk: continue
        q = int(r.get("可用库存",0) or 0)
        if q<=0: continue
        wh = _norm(r.get("仓库",""))
        tt_sku_stock[sk] = tt_sku_stock.get(sk,0) + q
        tt_sku_wh.setdefault(sk,set()).add(wh)
        if sk not in tt_sku_name: tt_sku_name[sk] = _norm(r.get("货品名称/规格",""))

    # Per-SPU Tongtu stock — via EN customer material number, NOT Tongtu SKU prefix
    spu_tt_stock = {}
    for sk,q in tt_sku_stock.items():
        cln = _clean(sk)
        en_pids = cust_to_en.get(cln.lower(),[]) or cust_to_en.get(sk.lower(),[])
        for pid in en_pids:
            sp = _spu(pid)
            if sp: spu_tt_stock[sp] = spu_tt_stock.get(sp,0) + q

    # ── Build sheets ──
    need_create = []
    tt_unmatched = []
    no_stock = []
    spu_all = []
    in_saihu_extra = []

    # Phase 1: EN SPU → Saihu
    for sp in sorted(en_spu_set):
        ei = en_spu_info.get(sp,{})
        st = spu_status.get(sp,{})
        ons = st.get("onsale"); ahs = st.get("has_stock",False); ts = spu_tt_stock.get(sp,0)
        in_sx = sp in saihu_spu_map
        nm = ei.get("name","")
        rb = {"EN_SPU":sp,"EN_物料组名":nm,"EN_父级":ei.get("parent",""),
              "属性表_在售": ons if ons is not None else "未在表中",
              "属性表_有库存":"有" if ahs else ("无" if ons is not None else "N/A"),
              "通途实际库存":ts,"在赛狐SPU":"是" if in_sx else "否"}

        if in_sx:
            rb["分类"]="已存在赛狐"; spu_all.append(rb); continue

        eff_stock = ahs or ts > 0

        if ons == 1 or (ons == 0 and eff_stock) or (ons is None and ts > 0):
            # Should be created in Saihu
            prods = [p for p in en_prod_info if _spu(p)==sp]
            for pr in sorted(prods):
                pi = en_prod_info[pr]; cust = pi["cust"]
                tt_skus_for = [s for s in tt_sku_stock if _clean(s)==cust]
                tt_tot = sum(tt_sku_stock[s] for s in tt_skus_for)
                need_create.append({
                    "EN_SPU":sp,"EN_物料组名":nm,
                    "EN产品编号":pr,"EN产品名称":pi["name"],
                    "绍兴发货方式":pi["ship"] or "(空)","EN客户物料号":cust,
                    "属性表_在售":ons if ons is not None else "未在表中",
                    "属性表_有库存":"有" if ahs else "N/A",
                    "通途累计库存":tt_tot,"关联通途SKU数":len(tt_skus_for),
                    "建议操作":"创建赛狐商品(多属性SPU)",
                    "备注":"SPU不在属性表但通途有库存" if ons is None else
                           ("在售=0但通途有库存" if ons==0 and not ahs else
                            "在售=0+属性表有库存" if ons==0 and ahs else "在售=1"),
                })
        elif ons == 0 and not eff_stock:
            rb["分类"]="不在售无库存"; rb["说明"]="属性表在售=0,无库存,通途也无库存"
            no_stock.append(rb); spu_all.append(rb)
        elif ons is None and ts == 0:
            rb["分类"]="不在属性表+无库存"; rb["说明"]="SPU不在属性表,通途也无库存"
            no_stock.append(rb); spu_all.append(rb)

    # Phase 2: Tongtu unmatched
    for sk in sorted(tt_sku_stock):
        cln = _clean(sk)
        exact_en = cust_to_en.get(sk.lower(), [])
        candidate_en = cust_to_en.get(cln.lower(), []) if cln.lower() != sk.lower() else []
        en_m = exact_en or candidate_en
        in_sx_sku = sk in all_saihu_skus or cln in all_saihu_skus
        sfx = _suffix(sk)
        semi = sk.lower().endswith(("-cover", "-foam")) or sfx
        if exact_en or (not semi and in_sx_sku):
            continue
        q = tt_sku_stock[sk]; whs = ", ".join(sorted(tt_sku_wh[sk]))
        cls = _classify_tt_unmatched(sk) if not semi else "皮壳/海绵半成品待评估"
        tt_unmatched.append({
            "通途SKU":sk,"清理后SKU":cln,"后缀类型":sfx,
            "匹配EN成品(清洗后)": ",".join(candidate_en) if semi else "",
            "SPU":_spu(sk),"仓库":whs,"可用库存":q,
            "货品名称":tt_sku_name.get(sk,""),"分类":cls,
            "匹配EN客户物料号":"否","在赛狐SKU":"否",
            "建议":"发给运营核对" if q>0 else "库存为0",
        })

    # Saihu-only SPUs
    for sp in sorted(saihu_spu_map):
        if sp in en_spu_set: continue
        in_saihu_extra.append({
            "赛狐SPU":sp,"赛狐款名":saihu_spu_map[sp]["name"],
            "赛狐SKU数":len(saihu_spu_map[sp]["skus"]),
            "EN里有此SPU":"否","说明":"仅在赛狐存在",
        })

    # Stats
    nc_spus = len(set(r["EN_SPU"] for r in need_create))
    tt_c = {c:sum(1 for r in tt_unmatched if r["分类"]==c) for c in ["辅料/耗材类","疑似Amazon ASIN","TT编码(需核实)","淘汰旧编码","其他未分类"]}
    tt_c["皮壳/海绵半成品待评估"] = sum(1 for r in tt_unmatched if r["分类"]=="皮壳/海绵半成品待评估")
    summ = [
        {"指标":"EN SPU总数(产品子树)","值":len(en_spu_set)},
        {"指标":"已在赛狐","值":len([r for r in spu_all if r.get("分类")=="已存在赛狐"])+len(in_saihu_extra)},
        {"指标":"需创建赛狐商品(条目数/SPU数)","值":f"{len(need_create)} / {nc_spus}"},
        {"指标":"不在售无库存","值":len(no_stock)},
        {"指标":"---","值":"---"},
        {"指标":"通途未匹配EN客户物料号","值":len(tt_unmatched)},
        *[{"指标":f"  {k}","值":v} for k,v in tt_c.items() if v],
        {"指标":"---","值":"---"},
        {"指标":"赛狐SPU/SKU总数","值":f"{len(saihu_spu_map)} / {len(all_saihu_skus)}"},
        {"指标":"运行时间","值":datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
    ]
    return {"summary":summ,"need_create":need_create,"tt_unmatched":tt_unmatched,
            "no_stock":no_stock,"spu_all":spu_all,"in_saihu_extra":in_saihu_extra,
            "nc_spus":nc_spus}

# ═══════════════════════════════════════════════════════════════
# Report writer
# ═══════════════════════════════════════════════════════════════

def write_report(d: dict, stamp: str) -> Path:
    p = _OUT_DIR / f"赛狐缺失商品排查_{stamp}.xlsx"
    with pd.ExcelWriter(p, engine="openpyxl") as w:
        pd.DataFrame(d["summary"]).to_excel(w, sheet_name="汇总", index=False)

        nd = d["need_create"]
        df = pd.DataFrame(nd).sort_values(["EN_SPU","EN产品编号"]) if nd else pd.DataFrame({"说明":["无"]})
        df.to_excel(w, sheet_name="需创建赛狐商品", index=False)

        tt = d["tt_unmatched"]
        df2 = pd.DataFrame(tt).sort_values(["分类","可用库存"], ascending=[True,False]) if tt else pd.DataFrame({"说明":["无"]})
        df2.to_excel(w, sheet_name="通途有货但EN未登记", index=False)

        ns = d["no_stock"]
        df3 = pd.DataFrame(ns) if ns else pd.DataFrame({"说明":["无"]})
        df3.to_excel(w, sheet_name="不在售无库存", index=False)

        sa = d["spu_all"]
        df4 = pd.DataFrame(sa) if sa else pd.DataFrame({"说明":["无"]})
        df4.to_excel(w, sheet_name="SPU比对全量", index=False)

        ie = d["in_saihu_extra"]
        df5 = pd.DataFrame(ie) if ie else pd.DataFrame({"说明":["无"]})
        df5.to_excel(w, sheet_name="仅赛狐有EN无", index=False)

    print(f"\n报告: {p}")
    return p

# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    print("="*60+"\n赛狐缺失商品排查\n"+"="*60+"\n── 加载 ──")

    try: en_leaves, en_ig, en_items = fetch_en_items()
    except Exception as e: print(f"EN API 失败: {e}"); en_leaves = []; en_items = []

    try: df_tt = load_tongtu()
    except Exception as e: print(f"通途失败: {e}"); return
    try: df_bom = load_bom()
    except Exception as e: print(f"BOM失败: {e}"); return

    spu_status = load_spu_status()
    try: sx_spu, sx_sku, all_skus = fetch_saihu()
    except Exception as e: print(f"赛狐API失败: {e}"); return

    print("\n── 分析 ──")
    data = analyze(df_tt, df_bom, en_leaves, sx_spu, sx_sku, all_skus, spu_status)

    print("\n"+"="*60+"\n结果\n"+"="*60)
    for it in data["summary"]: print(f"  {it['指标']}: {it['值']}")

    print("\n── 写报告 ──")
    rp = write_report(data, ts)

    nc = data["nc_spus"]
    print(f"\n完成!\n  需创建: {len(data['need_create'])} 条 ({nc} 个SPU)")
    print(f"  通途未匹配: {len(data['tt_unmatched'])} 个SKU")
    print(f"  不在售无库存: {len(data['no_stock'])} 个SPU")
    print(f"  报告: {rp}")

if __name__ == "__main__":
    main()
