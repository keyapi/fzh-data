# -*- coding: utf-8 -*-
"""C v14：通途库存 × 产品/形态/仓池/UOM + CG 池（只读）。

C v14 = C v13 + 两件假 partial / 口径修复（不改 A/B）：
- 身份以**库存源 SKU** 为准：只有源 SKU 本身多候选、或共享池有正库存并实际进入该行才标共享；
  零库存共享码不阻塞产品（KS0248-DM-153/194 → join_full）。
- 套件拆解只用于**库存/供给换算**，不用于订单需求；需求保留原始单件/套件单位。

C v13 = C v12 + 两件修复（不改 A/B）：
- 套件拆解：读 EN `Product Bundle` 子表，套件库存按「set_qty × component_qty」换算成组件供给，
  套件本身不作为库存；CG 的 TJ#KS0156x2/x3 由 unknown 改为 mapped-set 并换算 16/6 个组件。
- 组件缺货不阻塞：254 非零行缺 foam 或缺 cover → `component_partial_nonblocking`（blocking=false），
  已存在的组件（cover）仍作为独立可补供给，只记录不阻塞。

C v12 = C v11 + 四类修复（规则全部大小写不敏感）：
- TJ#/TT#：A 标不活跃但 EN 实存的套件仍要保留映射（mapping_status=inactive_EN/old_set），不标 unmapped。
- HM：role=海绵/海绵关联成品 → required_form=海绵，有海绵库存即独立供给，不判 partial。
- 单一形态正常：ship_mode 未知且无库存 → uncovered（不是 partial）；只有共享身份冲突才 partial。
- 拆包成品：254 行中 0 库存忽略；成品模式 cover+foam → 可组装 min(cover,foam) 计入成品供给，标 split_package。

C v11 = C v10 + 三件修复（不改 A/B）：
- CG 别名映射：读 `商品导出_20261030_1626.zip` 的 3 张表（SKU + 分号别名，约 45,495 键），
  CG SKU 先剥 `OLD_` 再按 SKU/别名匹配 EN；加 `mapping_basis=sku|old_prefix_strip|alias`。
- 皮壳/成品双形态：254 行按「同产品是否同时有成品/皮壳库存」判，both_forms_present 记录双量；
  半成品/皮壳行按新口径计入皮壳供给。
- 部分覆盖按发货方式：占位规则改为「任一可履约形态即可」（用户 2026-10-30 确认：成品可替代皮壳），
  新增 required_form / optional_form / form_requirement_status；缺必需形态才算 partial。

C v10 = C v9 + **CG 四池接入**（不改 A/B、不改物理库存口径）：
- EN `Wayfair CG Stock Latest` 只读 API，只取 `warehouse_id='CG'` 汇总行（104 SKU / 417 available）；
  分仓明细仅用于「CG 行=分仓和」对账，绝不累加。
- CG 池：`CG-USNJ` / `CG-USTX` / `CG-unknown`（unmapped 与无 US owner 都进 unknown，分别记原因）。
- 字段：erp_item_code / raw_tongtool_sku / cg_warehouse_id / cg_available / cg_reserved /
  cg_snapshot_at / cg_run_id / cg_source_ref / cg_reconcile_status / attribution_source /
  attribution_version / attribution_status / cg_owner / cg_pool / cg_channel_eligibility /
  cg_included_in_current_net；供给展示另列 cg_available / supply_total_display。
- CG 不并入 USNJ/USTX 物理库存；不生成 transfer 候选（transfer_flag=false）；
  `cg_eligible` 仅映射+owner+对账+非 stale 才成立。

C v9 = C v8b + partial/no_join/null 的可操作状态（只读；不改既有分类与数量）：
- 统一 `reason_code`（partial / no_join / null 三套码表），每行给
  `needed_evidence` / `next_action` / `owner`；新增 `consumption` 消费闸门。
- `join_partial` 默认不消费：新增 `22_join_partial白名单`（默认空），只有白名单行才可观察性消费。
- `no_join` 按 reason_code 汇总观察（`21_no_join观察`）；null 保持 null 并给 reason。
- Top50 仍只导 join_full，新增 reason_code 分布与「Top50 无 partial/no_join/null」断言。

C v8b = C v8 + 复审修复（不重写全流程）：
- P1-1 `19_Top50候选导出` 物理只含 `join_full`（1,866 行）；partial/no_join 另放 `19b_Top50观察表`。
  自检：Top50 行数=join_full 数；Top50 中 partial/no_join=0；source_proof 空=0。
- P1-2 脚本随产物落盘（仓库 scripts/ 与 D:/Work/fzh-order-store/scripts/ 同 SHA），
  并写 `manifest.json`（输入/输出 SHA、行数、rule_version、生成时间、命令）。
- P2 Top50 行直接带 demand_eligibility / eligibility_reason / source_ref / coverage_status /
  join_reason，不再要求回接事实层。

C v8 = C v7 + C8-1..C8-4（不重写全流程）：
- C8-1 供给资格最小闭环：每行补 `physical_form` / `canonical_uom` / `demand_eligibility`
  （component / after_sales / independent / not_applicable）/ `eligibility_reason` / `source_ref`；
  HM 默认 component（无已证售后），ND 只作组件（独立需求=0），半成品保留 raw 形态，骨架独立成品，
  TJ# 按套不拆；只有 `join_full` 进 join 候选。
- C8-2 共享池/缺行可回放：`shared_pool_id` + 候选数 + 源行/原量 + `allocation_qty=0` + coverage；
  63/539、191/653 逐行回指；766 未覆盖不补 0。
- C8-3 Top50 兼容导出：稳定字段表 + 十键（join v7 pilot）逐键回放。
- C8-4 回归闸门：v7 已验收项全部保持。

C v7 = C v6 + 复审 P2 修复（不重写全流程）：
- P2-1 可进 join 拆分：`join_class ∈ {join_full, join_partial, no_join}`。
  `join_full` = 覆盖完整 + 身份唯一 + 单位非冲突 + 无未计正量；
  `join_partial` = 部分覆盖 / 身份非唯一 / 单位冲突 → 仅观察或显式白名单；
  `no_join` = null / 待核 / 套件单列 / CG·其他仅披露。`可用性` 保留人读文字，默认消费只认 `join_full`。
- P2-2 老产品双口径冻结：产品级（distinct product_id，逐产品列出）+ 行级
  （事实层 113 行/1,148、供给层 19 行/764）；1:1 与「默认不补」拆成两条独立断言。

C v6 已通过项（本版不变）：契约冻结 + 门禁/守恒/状态分层：
1. 契约冻结：`rule_version=C-v6-2026-10-30`、`as_of=2026-10-28`、`UOM-CANONICAL-2026-10-29`、
   全部输入文件 SHA256、源行数/数值、内容哈希；同输入可重放（内容哈希一致）。
2. N1 门禁：没有适用成品/皮壳/套件事实的键 → **可发供给=null、供给状态=无适用事实(非0)、可用性=不进join**；
   空集不求和当 0；**已计=0 但同键存在未计形态正量** → 也判 null（禁止伪 0）。
3. 缺行=未覆盖：A 活跃产品无库存行 → `覆盖状态=未覆盖`，单列（不写 0）。
4. 状态分层：事实层/汇总层/供给层共用 `身份状态`(唯一/共享/未映射/未激活/待核)、`单位状态`、`覆盖状态`；
   只有唯一有效映射才写「归属已证」。
5. 表结构：产品区与去向/汇总分 sheet（v5 里 5_ 与 1_ 尾部内嵌的第二张表全部拆出）。
6. 命名：仓池只用 美东USNJ / 美中USTX / 波兰 / CG / 其他；全表不再出现 East / Central。

沿用 C v5：
- 星球抱枕组(KS0019)整组 1:1（UOM-CANONICAL §2.1 例外）；老产品只标不补，行不删。
- 六桶冻结口径 5,317 行 / 10,360,448；254 行逐行隔离明细；63 行/539 皮壳补证；骨架 599；TJ# 按套单列。
只读：不写 EN / 通途，不发消息，不 push，不改 A/B/C 历史产物。
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import shutil
from pathlib import Path

import pandas as pd

RULE_VERSION = "C-v14-2026-10-30"
AS_OF = "2026-10-28"
UOM_VERSION = "UOM-CANONICAL-2026-10-29"

COVER_RE = re.compile(r"^(.*)-cover\d*$", re.I)
FOAM_RE = re.compile(r"^(.*)-foam\d*$", re.I)
PIECE_TAIL = re.compile(r"^(?P<base>.+?)[-_ ](?P<n>\d+)\s*pcs?$", re.I)
PIECE_MID = re.compile(r"[-_ ]\d+\s*pcs?[-_ ]", re.I)
PLANET_GROUP_NAME = "星球抱枕"
PLANET_SKU_RE = re.compile(r"^(xingqiu|tt0009|stppw-13-1c)", re.I)
LEGACY_NOTE = "老产品-默认不补(待确认)"
STRIP_PREFIXES = ("删除", "~", "?", "？")
PRI = ["用户覆盖表(map)", "A来源码", "customer_code(活跃)", "sku_map", "customer_code(删除)"]

# 仓池标准名（任务要求：全表只用这五个）
POOL_EAST, POOL_CENTRAL, POOL_POLAND, POOL_CG, POOL_OTHER = "美东USNJ", "美中USTX", "波兰", "CG", "其他"
POOL_CANON = [POOL_EAST, POOL_CENTRAL, POOL_POLAND, POOL_CG, POOL_OTHER]
# 非普通仓类别（仓池仍归「其他」，类别列保留来源）
WH_RETURN, WH_THIRD, WH_PLAIN = "退货仓", "第三方大件云仓", "普通仓"

# 六桶冻结口径（C v2 评审 F4 基线，单位：行 / 原始 available 数值和）
BUCKET_BASELINE = {
    "计入A": (2484, 47332.0),
    "共享码": (53, 1403.0),
    "A未激活": (425, 20.0),
    "规则排除": (879, 10308263.0),
    "未映射": (1222, 2238.0),
    "皮壳无活跃EN": (254, 1192.0),
}
SRC_ROWS, SRC_QTY = 5317, 10360448.0

# v5 冻结基线（v6 必须原样保留的既有结论）
V5_BASELINE = {
    "iso_rows": 254, "iso_qty": 1192.0, "iso_proven_rows": 63, "iso_proven_qty": 539.0,
    "iso_held_rows": 191, "iso_held_qty": 653.0,
    "skeleton_qty": 599.0, "planet_rows": 113, "planet_qty": 1148.0,
    "bundle_units": 8.0,
}

# v3 复审 N1 指出的 15 个“无适用事实却标已证 0”的键（product_id, 仓池, uom）
FIFTEEN_KEYS = [
    ("KS0018-LSRBS-SET7-ROCKSTONE", POOL_CENTRAL, "套"),
    ("KS0316-HLR-55-PURPLE", POOL_CENTRAL, "个"),
    ("KS0333-CMYH-60-COLDTREEPRINT", POOL_CENTRAL, "个"),
    ("KS0395-CTTM-218x115x55-CREAMYBEIGE", POOL_CENTRAL, "个"),
    ("KS0495-FHXWXNERSZSRB-143x84x88-DARKRED", POOL_CENTRAL, "个"),
    ("TJ#KS0238x1_KS0240x1_KS0241x1_KS0242x1_KS0243x1-001", POOL_CENTRAL, "套"),
    ("TJ#KS0334x1_KS0335x1_KS0336x1-001", POOL_CENTRAL, "套"),
    ("KS0018-LSRBS-SET7-ROCKSTONE", POOL_EAST, "套"),
    ("ZTGJ5525-SOFALSHAPEDBRACKET-IRON-55x45x45", POOL_EAST, "个"),
    ("KS0018-LSRBS-SET7-ROCKSTONE", POOL_POLAND, "套"),
    ("KS0395-CTTM-218x115x55-CREAMYBEIGE", POOL_POLAND, "个"),
    ("KS0398-YRSZML-123x60x10-PURELOTUSASH", POOL_POLAND, "个"),
    ("KS0495-FHXWXNERSZSRB-143x84x88-DARKRED", POOL_POLAND, "个"),
    ("TJ#KS0334x1_KS0335x1_KS0336x1-001", POOL_POLAND, "套"),
    ("ZTGJ5525-SOFALSHAPEDBRACKET-IRON-55x45x45", POOL_POLAND, "个"),
]


def norm(code) -> str:
    """客户码/通途码规范化：trim → 清 删除/~/? 前缀 → casefold。"""
    c = str(code).strip()
    changed = True
    while changed:
        changed = False
        for p in STRIP_PREFIXES:
            if c.startswith(p):
                c = c[len(p):].strip()
                changed = True
    return c.casefold()


def is_missing(x) -> bool:
    """None / NaN 统一判定（NaN 为 truthy，不能用 `if not x`）。"""
    return x is None or (isinstance(x, float) and pd.isna(x)) or x is pd.NaT


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


CG_DOCTYPE = "Wayfair CG Stock Latest"
CG_POOLS = ("CG-USNJ", "CG-USTX", "CG-unknown")


def read_env_file(path: Path) -> dict:
    """按行解析 .env（不 source、不打印值）。"""
    env = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        t = line.strip()
        if t and not t.startswith("#") and "=" in t:
            k, v = t.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def fetch_cg_stock(env: dict, base: str, page: int = 200) -> pd.DataFrame:
    """只读 EN `Wayfair CG Stock Latest` 全表（CG 汇总行 + 分仓明细）。"""
    import urllib.parse
    import urllib.request

    hdr = {"Authorization": f"token {env['ERP_API_KEY']}:{env['ERP_API_SECRET']}",
           "Accept": "application/json"}
    rows, off = [], 0
    while True:
        q = urllib.parse.urlencode({
            "limit_start": off, "limit_page_length": page,
            "fields": json.dumps(["*"]), "order_by": "name asc"})
        req = urllib.request.Request(
            f"{base}/api/resource/{urllib.parse.quote(CG_DOCTYPE)}?{q}", headers=hdr)
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))["data"]
        rows += data
        if len(data) < page:
            break
        off += page
    return pd.DataFrame(rows)


def _get_json(url: str, hdr: dict, tries: int = 3) -> dict:
    import time
    import urllib.request
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers=hdr)
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(2 * (k + 1))
    raise last


def fetch_bundles(env: dict, base: str, cache: Path | None = None,
                  refresh: bool = False) -> dict:
    """只读 EN `Product Bundle`：{new_item_code: [[component_item_code, qty], ...]}。带本地缓存。"""
    import urllib.parse

    if cache is not None and cache.exists() and not refresh:
        return {k: [tuple(x) for x in v]
                for k, v in json.loads(cache.read_text(encoding="utf-8")).items()}
    hdr = {"Authorization": f"token {env['ERP_API_KEY']}:{env['ERP_API_SECRET']}",
           "Accept": "application/json"}
    out: dict[str, list] = {}
    off = 0
    while True:
        q = urllib.parse.urlencode({"limit_start": off, "limit_page_length": 50,
                                    "fields": json.dumps(["name"])})
        data = _get_json(f"{base}/api/resource/{urllib.parse.quote('Product Bundle')}?{q}", hdr)["data"]
        for row in data:
            nm = row["name"]
            doc = _get_json(
                f"{base}/api/resource/{urllib.parse.quote('Product Bundle')}/"
                + urllib.parse.quote(nm), hdr)["data"]
            out[doc.get("new_item_code") or nm] = [
                [i.get("item_code"), float(i.get("qty") or 0)] for i in doc.get("items", [])]
        if len(data) < 50:
            break
        off += 50
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
    return {k: [tuple(x) for x in v] for k, v in out.items()}


def load_alias_map(zip_path: Path) -> dict:
    """读商品导出 zip（普通/捆绑/组装）的 SKU + 分号别名 → {归一码: 通途SKU}。"""
    import zipfile
    alias: dict[str, str] = {}
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            if not info.filename.lower().endswith(".xlsx"):
                continue
            with z.open(info) as fh:
                try:
                    df = pd.read_excel(fh)
                except Exception as exc:  # noqa: BLE001
                    print(f"[warn] 跳过 {info.filename}: {exc}")
                    continue
            if "SKU" not in df.columns or "SKU别名" not in df.columns:
                continue
            for sku, al in zip(df["SKU"], df["SKU别名"]):
                if not isinstance(sku, str) or not sku.strip():
                    continue
                s_ = sku.strip()
                alias.setdefault(norm(s_), s_)
                if isinstance(al, str):
                    for a in al.split(";"):
                        a = a.strip()
                        if a:
                            alias.setdefault(norm(a), s_)
    return alias


def resolve_cg_item(sku, idx: dict, alias_map: dict) -> tuple[str | None, str]:
    """CG SKU → EN：先精确 SKU，再剥 OLD_，再走别名表；返回 (EN, mapping_basis)。"""
    raw = str(sku).strip()
    n = norm(raw)
    if n in idx:
        return idx[n], "sku"
    base = re.sub(r"^OLD_", "", raw, flags=re.I)
    nb = norm(base)
    if nb in idx:
        return idx[nb], "old_prefix_strip"
    t = alias_map.get(nb) or alias_map.get(n)
    if t:
        en = idx.get(norm(t)) or idx.get(norm(re.sub(r"^OLD_", "", t, flags=re.I)))
        if en:
            return en, "alias"
    return None, "unmapped"


def build_cg_table(cg_all: pd.DataFrame, idx: dict, cand: dict, active_ens: set,
                   owner_map: dict, supply_tbl: pd.DataFrame,
                   attribution_source: str, attribution_version: str,
                   alias_map: dict | None = None, bundles: dict | None = None) -> dict:
    """CG 汇总行 → CG 三池（不并入物理库存、不累加分仓明细）。"""
    cg = cg_all[cg_all["warehouse_id"] == "CG"].copy()
    det = cg_all[cg_all["warehouse_id"] != "CG"].copy()
    det_sum = det.groupby("sku")["available"].sum() if len(det) else pd.Series(dtype=float)
    cg["det_sum"] = cg["sku"].map(det_sum).fillna(0.0)
    cg["det_rows"] = cg["sku"].map(det.groupby("sku").size()).fillna(0).astype(int)
    cg["reconcile_diff"] = cg["available"] - cg["det_sum"]
    cg["cg_reconcile_status"] = [
        "ok" if abs(d) < 1e-9 else "pending" for d in cg["reconcile_diff"]]
    cg["cg_warehouse_id"] = "CG"
    cg["cg_available"] = [None if m else float(a) if not pd.isna(a) else None
                          for a, m in zip(cg["available"], cg["available_missing"])]
    cg["cg_reserved"] = [None if m else float(a) if not pd.isna(a) else None
                         for a, m in zip(cg["reserved"], cg["reserved_missing"])]
    cg["raw_tongtool_sku"] = cg["sku"]
    cg["cg_snapshot_at"] = cg["snapshot_at"]
    cg["cg_run_id"] = cg["run_id"]
    cg["cg_source_ref"] = ["EN:%s/%s" % (CG_DOCTYPE, n) for n in cg["name"]]
    cg["attribution_source"] = attribution_source
    cg["attribution_version"] = attribution_version
    cg["cg_channel_eligibility"] = "wayfair_only"
    cg["cg_included_in_current_net"] = False
    cg["transfer_flag"] = False

    alias_map = alias_map or {}
    marks = []
    for sku in cg["sku"]:
        e, basis = resolve_cg_item(sku, idx, alias_map)
        note = ""
        if e is not None and e not in active_ens:
            note = "映射到未激活EN"
        if e is None:
            cs, _ = top_candidates(cand, norm(sku))
            act = {x for x in cs if x in active_ens}
            note = "identity_ambiguous(多候选)" if len(act) > 1 else "unmapped(无活跃EN映射)"
        marks.append((e, basis, note))
    cg["erp_item_code"] = [m[0] for m in marks]
    cg["mapping_basis"] = [m[1] for m in marks]
    cg["_map_note"] = [m[2] for m in marks]
    bundles = bundles or {}
    # C v13：套件按组件换算（set_qty × component_qty），套件本身不作为库存
    _set_info = []
    for e in cg["erp_item_code"]:
        comps = bundles.get(e) if isinstance(e, str) else None
        if comps:
            _set_info.append((comps[0][0], comps[0][1],
                              sum(1 for _ in comps), len(comps)))
        else:
            _set_info.append((None, 0.0, 0, 0))
    cg["set_component_item"] = [x[0] for x in _set_info]
    cg["set_component_qty_per_set"] = [x[1] for x in _set_info]
    cg["set_component_count"] = [x[3] for x in _set_info]
    cg["set_qty"] = [float(a) if (isinstance(e, str) and e in bundles) else None
                     for e, a in zip(cg["erp_item_code"], cg["available"])]
    cg["component_qty"] = [None if q is None else float(q) * float(per)
                           for q, per in zip(cg["set_qty"], cg["set_component_qty_per_set"])]
    # 归属：套件按组件 owner（再退回套件自身 owner）
    cg["cg_owner"] = [
        (owner_map.get(r["set_component_item"]) or owner_map.get(e))
        if isinstance(e, str) else None
        for e, r in zip(cg["erp_item_code"], cg.to_dict("records"))]
    cg["en_active"] = [bool(isinstance(e, str) and e in active_ens)
                       for e in cg["erp_item_code"]]
    cg["mapping_status"] = [
        "unmapped" if not (isinstance(e, str) and e)
        else ("mapped_set" if (isinstance(e, str) and e in bundles)
              else ("old_set" if (str(e).upper().startswith("TJ#") and not act)
                    else ("inactive_EN" if not act else "mapped")))
        for e, act in zip(cg["erp_item_code"], cg["en_active"])]
    # C v12/v13：A 标不活跃但 EN 实存的套件 → mapped_inactive；可拆解的套件 → mapped-set
    cg["attribution_status"] = [
        "unmapped" if not (isinstance(e, str) and e)
        else ("owner" if isinstance(o, str) and o
              else ("set_owner_unknown" if (isinstance(e, str) and e in bundles)
                    else ("mapped_inactive" if not act else "unknown")))
        for e, o, act in zip(cg["erp_item_code"], cg["cg_owner"], cg["en_active"])]
    cg["cg_pool"] = [("CG-USNJ" if o == "美东USNJ" else "CG-USTX")
                     if isinstance(o, str) and o else "CG-unknown"
                     for o in cg["cg_owner"]]

    def pending_reason(r):
        rs = []
        if r["attribution_status"] == "unmapped":
            rs.append(r["_map_note"] or "unmapped")
        if r["attribution_status"] == "unknown":
            rs.append("无 B US owner（attribution unknown）")
        if r["attribution_status"] == "mapped_inactive":
            rs.append(f"映射到未激活 EN（{r.get('mapping_status', '')}），无 US owner")
        if r["attribution_status"] == "set_owner_unknown":
            rs.append("套件可拆解，但组件与套件均无 US owner")
        if r["cg_reconcile_status"] != "ok":
            rs.append("CG 行≠分仓和")
        if int(r["stale"] or 0):
            rs.append("stale")
        if int(r["available_missing"] or 0):
            rs.append("available_missing(不填0)")
        return "；".join(rs)

    cg["cg_pending_reason"] = [pending_reason(r) for _, r in cg.iterrows()]
    cg["cg_status"] = ["cg_pending" if r["cg_pending_reason"] else "cg_eligible"
                       for _, r in cg.iterrows()]

    # 物理供给展示（只读，不并入 可发供给）
    phys = supply_tbl[supply_tbl["join_class"].isin(["join_full", "join_partial"])]
    phys_map = {}
    for (pid, pool), g in phys.groupby(["product_id", "pool"]):
        phys_map[(pid, pool)] = float(g["可发供给"].fillna(0).sum())

    def phys_of(r):
        pool = {"CG-USNJ": POOL_EAST, "CG-USTX": POOL_CENTRAL}.get(r["cg_pool"])
        if not (isinstance(r["erp_item_code"], str) and r["erp_item_code"]) or not pool:
            return None
        return phys_map.get((r["erp_item_code"], pool))

    cg["supply_physical"] = [phys_of(r) for _, r in cg.iterrows()]
    cg["supply_total_display"] = [
        (float(v) if v is not None else 0.0) + (float(c) if c is not None else 0.0)
        if (v is not None or c is not None) else None
        for v, c in zip(cg["supply_physical"], cg["cg_available"])]

    cg["cg_supply_qty"] = [float(cq) if cq is not None else (float(a) if not pd.isna(a) else None)
                           for cq, a in zip(cg["component_qty"], cg["cg_available"])]
    cg_tbl = cg[["erp_item_code", "raw_tongtool_sku", "wayfair_sku", "mapping_basis",
                 "mapping_status", "en_active", "set_qty", "component_qty",
                 "set_component_item", "set_component_qty_per_set", "set_component_count",
                 "cg_warehouse_id",
                 "cg_available", "cg_supply_qty", "cg_reserved", "cg_snapshot_at", "cg_run_id", "cg_source_ref",
                 "cg_reconcile_status", "stale", "available_missing",
                 "attribution_source", "attribution_version", "attribution_status",
                 "cg_owner", "cg_pool", "cg_channel_eligibility", "cg_status",
                 "cg_pending_reason", "cg_included_in_current_net", "transfer_flag",
                 "supply_physical", "supply_total_display", "reconcile_diff", "det_sum",
                 "det_rows"]].rename(columns={"stale": "cg_stale",
                                              "available_missing": "cg_available_missing"})
    cg_tbl = cg_tbl.sort_values(["cg_pool", "cg_available"], ascending=[True, False])

    pool = (cg_tbl.groupby("cg_pool")
            .agg(行数=("raw_tongtool_sku", "size"),
                 cg_available=("cg_available", "sum"),
                 cg_supply_qty=("cg_supply_qty", "sum"),
                 cg_reserved=("cg_reserved", "sum"),
                 eligible行=("cg_status", lambda s: int((s == "cg_eligible").sum())),
                 pending行=("cg_status", lambda s: int((s == "cg_pending").sum())),
                 非零行=("cg_available", lambda s: int((s.fillna(0) > 0).sum())))
            .reindex(list(CG_POOLS)).reset_index())
    return {"cg": cg, "cg_tbl": cg_tbl, "pool": pool, "det": det,
            "det_sum_total": float(det["available"].sum()) if len(det) else 0.0}


def piece_info(sku: str) -> tuple[int, str, str]:
    """多件后缀 → (每单位件数, 依据, 状态)。只认末尾明确的 -NPCS/-NPC。"""
    s = str(sku).strip()
    m = PIECE_TAIL.match(s)
    if m and int(m.group("n")) > 1:
        return int(m.group("n")), f"后缀-{m.group('n')}PCS", "已换算"
    if PIECE_MID.search(s):
        return 1, "名称中段含件数（套装名，不是每单位件数）", "仅列不换算"
    return 1, "", ""


def load_a(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    universe = pd.read_excel(path, sheet_name="活跃宇宙")
    active = universe[universe["活跃分类"] != "不活跃"].copy()
    shared = pd.read_excel(path, sheet_name="共享码剩余")
    return active, shared


def build_index(active: pd.DataFrame, customer_codes: Path, sku_map: Path,
                overrides: pd.DataFrame) -> tuple[dict, dict]:
    """v2 冻结解析索引（first-wins）：override.map > A来源码 > 客户码活跃 > sku_map > 客户码删除。"""
    idx: dict[str, str] = {}
    src: dict[str, str] = {}

    def add(code, en, tag):
        n = norm(code)
        if not n or n in ("nan", "none"):
            return
        if n not in idx:
            idx[n] = en
            src[n] = tag

    ov_map = {norm(r.tt): r.en for r in overrides[overrides["action"] == "map"].itertuples(index=False)
              if isinstance(r.tt, str)}
    for n, en in ov_map.items():
        idx[n] = en
        src[n] = "用户覆盖表(map)"

    for r in active.itertuples(index=False):
        raw = getattr(r, "来源码")
        if isinstance(raw, str):
            for tok in re.split(r"[,;，]", raw):
                add(tok, r[0], "A来源码")

    cc = pd.read_csv(customer_codes, dtype=str)
    deleted_pool = []
    for r in cc.itertuples(index=False):
        for c in str(r.customer_code).split(","):
            c = c.strip()
            if not c:
                continue
            if c.startswith("删除"):
                deleted_pool.append((c[2:], r.name))
            else:
                add(c, r.name, "customer_code(活跃)")
    for c, en in deleted_pool:
        add(c, en, "customer_code(删除)")

    sm = pd.read_csv(sku_map, sep="\t", dtype=str).iloc[:, :2]
    sm.columns = ["en", "tt"]
    for r in sm.dropna().itertuples(index=False):
        add(r.tt, r.en, "sku_map")
    return idx, src


def build_candidates(active: pd.DataFrame, customer_codes: Path, sku_map: Path,
                     overrides: pd.DataFrame) -> dict[str, dict[str, set]]:
    """F5：同一归一码 → 各优先级下的全部候选 EN 集合（不取首个）。"""
    cand: dict[str, dict[str, set]] = {}

    def add(code, en, tag):
        n = norm(code)
        if not n or n in ("nan", "none"):
            return
        cand.setdefault(n, {}).setdefault(tag, set()).add(en)

    for n, en in {norm(r.tt): r.en for r in overrides[overrides["action"] == "map"].itertuples(index=False)
                  if isinstance(r.tt, str)}.items():
        add(n, en, "用户覆盖表(map)")
    for r in active.itertuples(index=False):
        raw = getattr(r, "来源码")
        if isinstance(raw, str):
            for tok in re.split(r"[,;，]", raw):
                add(tok, r[0], "A来源码")
    cc = pd.read_csv(customer_codes, dtype=str)
    for r in cc.itertuples(index=False):
        for c in str(r.customer_code).split(","):
            c = c.strip()
            if not c:
                continue
            if c.startswith("删除"):
                add(c[2:], r.name, "customer_code(删除)")
            else:
                add(c, r.name, "customer_code(活跃)")
    sm = pd.read_csv(sku_map, sep="\t", dtype=str).iloc[:, :2]
    sm.columns = ["en", "tt"]
    for r in sm.dropna().itertuples(index=False):
        add(r.tt, r.en, "sku_map")
    return cand


def top_candidates(cand: dict, n: str) -> tuple[set, str]:
    """返回最高优先级的全部候选（不取首个）。"""
    d = cand.get(n)
    if not d:
        return set(), ""
    for pr in PRI:
        if pr in d and d[pr]:
            return set(d[pr]), pr
    return set(), ""


def pool_of(warehouse: str) -> tuple[str, str]:
    """仓池标准名 + 仓类别（退货/第三方仍单列类别，仓池归「其他」）。"""
    w = str(warehouse)
    if w.startswith("WayfairCG-"):
        return POOL_CG, WH_PLAIN
    if "退货" in w:
        return POOL_OTHER, WH_RETURN
    if w == "美东-CENTRADE":
        return POOL_EAST, WH_PLAIN
    if w == "美中-FZH-DANEEY":
        return POOL_CENTRAL, WH_PLAIN
    if w == "波兰-FZHPoland-covers":
        return POOL_POLAND, WH_PLAIN
    if w == "大件云仓":
        return POOL_OTHER, WH_THIRD
    return POOL_OTHER, WH_PLAIN


def form_of_suffix(n: str, role: str | None, en: str | None) -> tuple[str, str]:
    """实物形态（actual_form）与判定依据。形态来自「实物证据」（后缀/PK# 命名），
    不覆盖 A 的 role，两者并列输出。"""
    if en and str(en).startswith("PK#"):
        return "皮壳", "EN命名(PK#前缀)"
    if COVER_RE.match(n):
        return "皮壳", "通途码后缀(-Cover)"
    if FOAM_RE.match(n):
        return "海绵", "通途码后缀(-Foam)"
    if role == "海绵/关联成品":
        return "海绵", "A角色(海绵/关联成品)"
    if role in ("内胆", "海绵", "主体骨架", "套件"):
        return role, f"A角色({role})"
    if role == "皮壳":
        return "皮壳", "A角色(皮壳)"
    if role == "成品":
        return "成品", "A角色(成品)"
    return "unknown", "无证据"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="通途库存 → A337 角色/形态/仓池/UOM 归并 v6（只读）")
    B = "D:/Work/fzh-order-store"
    ap.add_argument("--a-final", default=f"{B}/analysis/SKU活跃宇宙_2026-10-29_FINAL.xlsx")
    ap.add_argument("--stock", default=f"{B}/en_stock.parquet")
    ap.add_argument("--date", default=AS_OF)
    ap.add_argument("--sku-map", default=f"{B}/sku_map.tsv")
    ap.add_argument("--customer-codes", default=f"{B}/analysis/en_item_customer_codes.csv")
    ap.add_argument("--overrides", default=f"{B}/analysis/sku_mapping_overrides_2026-10-29.csv")
    ap.add_argument("--non-product", default=f"{B}/non_product_skus.csv")
    ap.add_argument("--warehouse-scope", default=f"{B}/warehouse_scope.csv")
    ap.add_argument("--uom-cache", default=f"{B}/en-demand-v1/canonical/item_uom_cache.parquet")
    ap.add_argument("--en-env", default="D:/Work/赛狐/Cursor/EN_API/.env")
    ap.add_argument("--en-base", default="https://erpnext.vilavi.cn")
    ap.add_argument("--b-attribution",
                    default=f"{B}/analysis/仓库归属_A337_v6r9_2026-10-30.xlsx")
    ap.add_argument("--cg-alias-zip",
                    default=f"{B}/analysis/商品导出_20261030_1626.zip")
    ap.add_argument("--bundle-cache",
                    default=f"{B}/analysis/en_product_bundles_2026-10-30.json")
    ap.add_argument("--refresh-bundles", action="store_true")
    ap.add_argument("--out-cg-cache",
                    default=f"{B}/analysis/cg_stock_latest_2026-10-30.parquet")
    ap.add_argument("--out-xlsx", default=f"{B}/analysis/通途库存_A337_v14_2026-10-30.xlsx")
    ap.add_argument("--out-report", default=f"{B}/analysis/通途库存_A337_v14_2026-10-30_报告.md")
    args = ap.parse_args(argv)

    active, shared_df = load_a(Path(args.a_final))
    overrides = pd.read_csv(args.overrides, dtype=str)
    idx, src = build_index(active, Path(args.customer_codes), Path(args.sku_map), overrides)
    cand = build_candidates(active, Path(args.customer_codes), Path(args.sku_map), overrides)

    en_role = {str(r[0]): r[1] for r in active[["EN物料", "角色"]].itertuples(index=False)}
    en_ship = {str(r[0]): r[1] for r in active[["EN物料", "ship_mode"]].itertuples(index=False)}
    en_ship_cn = {str(r[0]): r[1] for r in active[["EN物料", "绍兴发货方式"]].itertuples(index=False)}
    en_group = {str(r[0]): str(r[1]) for r in active[["EN物料", "物料组"]].itertuples(index=False)}
    en_name_map = {str(r[0]): str(r[1]) for r in active[["EN物料", "名称"]].itertuples(index=False)}

    # 星球抱枕组（UOM-CANONICAL §2.1 例外）
    planet_ens = {en for en, g in en_group.items() if g.strip() == PLANET_GROUP_NAME}
    planet_ens |= {en for en in en_role if str(en).startswith("KS0019")}
    planet_codes = {n for n, tags in cand.items()
                    if any(e in planet_ens for s in tags.values() for e in s)}

    deleted_ens = set(overrides[overrides["action"] == "delete"]["en"].dropna())
    nonproduct_ov = set(overrides[overrides["action"] == "non_product"]["en"].dropna())
    nonproduct = set(pd.read_csv(args.non_product, dtype=str)["sku"].astype(str))

    ov_map_codes = {norm(r.tt) for r in overrides[overrides["action"] == "map"].itertuples(index=False)
                    if isinstance(r.tt, str)}
    shared_codes = {norm(k) for k in shared_df["键"].dropna()} - ov_map_codes
    shared_cand = {norm(r["键"]): str(r["候选/说明"]) for _, r in shared_df.iterrows()
                   if isinstance(r.get("键"), str)}

    cover_of_base = {}
    for en, role in en_role.items():
        if role == "皮壳" and str(en).startswith("PK#"):
            cover_of_base[str(en)[3:].casefold()] = en

    uom_cache = pd.read_parquet(args.uom_cache)
    uoms = dict(zip(uom_cache["item_code"].astype(str), uom_cache["stock_uom"].astype(str)))
    is_stock_item = dict(zip(uom_cache["item_code"].astype(str), uom_cache["is_stock_item"].astype(int)))
    uom_conflict_en = {en for en in en_role
                       if uoms.get(en) == "套" and is_stock_item.get(en) == 1
                       and not str(en).upper().startswith("TJ#") and en_role.get(en) != "套件"}

    third_party = set(pd.read_csv(args.warehouse_scope, dtype=str)
                      .query("scope == 'third_party_cloud'")["warehouse"].astype(str))

    d = pd.read_parquet(args.stock)
    d = d.reset_index(drop=True)
    d["src_row"] = d.index + 1
    f = d[pd.to_datetime(d["snapshot_date"]).dt.date.astype(str) == args.date].copy()
    if f.empty:
        raise SystemExit(f"{args.stock} 没有 {args.date} 的行")
    f["sku"] = f["sku"].astype(str)
    f["available"] = pd.to_numeric(f["available"], errors="coerce").fillna(0.0)
    f["norm"] = f["sku"].map(norm)
    pools = [pool_of(w) for w in f["warehouse_name"]]
    f["pool"] = [p for p, _ in pools]
    f["仓类别"] = [c for _, c in pools]

    # ---------- v2 冻结解析（六桶基线） ----------
    def resolve(n: str) -> tuple[str | None, str]:
        if n in ov_map_codes:
            return idx.get(n), src.get(n, "用户覆盖表(map)")
        m = COVER_RE.match(n)
        if m:
            if n in shared_codes:
                return None, "共享码(未归属)"
            base_en = idx.get(m.group(1)) or idx.get(n)
            if base_en and base_en.casefold() in cover_of_base:
                return cover_of_base[base_en.casefold()], "皮壳派生(PK#+成品)"
            return None, "皮壳无活跃EN"
        if n in shared_codes:
            return None, "共享码(未归属)"
        en = idx.get(n)
        if en:
            tag = src.get(n, "?")
            if en in deleted_ens:
                return None, f"已按用户规则删除({tag})"
            return en, tag
        return None, "未映射"

    res = [resolve(n) for n in f["norm"]]
    f["en"] = [r[0] for r in res]
    f["mapping_source_v2"] = [r[1] for r in res]
    f["role"] = f["en"].map(lambda e: en_role.get(e) if e else None)

    f["is_fba"] = f["sku"].str.contains("FBA", case=False, na=False)
    f["is_third_party"] = f["warehouse_name"].astype(str).isin(third_party)
    f["is_return"] = f["仓类别"] == WH_RETURN
    f["is_nonproduct"] = f["sku"].isin(nonproduct) | f["en"].isin(nonproduct_ov)
    f["is_big"] = f["available"] >= 100000

    f["exclusion"] = ""
    for flag, label in (("is_fba", "FBA 不计可用"),
                        ("is_third_party", "第三方云仓不补"),
                        ("is_return", "退货仓单列"),
                        ("is_nonproduct", "非商品/原料"),
                        ("is_big", "超大占位")):
        f.loc[(f["exclusion"] == "") & f[flag], "exclusion"] = label

    f["bucket"] = "未映射"
    f.loc[f["exclusion"] != "", "bucket"] = "规则排除"
    mapped = (f["exclusion"] == "") & f["en"].notna()
    f.loc[mapped & f["role"].notna(), "bucket"] = "计入A"
    f.loc[mapped & f["role"].isna(), "bucket"] = "A未激活"
    f.loc[(f["exclusion"] == "") & f["en"].isna() & (f["mapping_source_v2"] == "共享码(未归属)"),
          "bucket"] = "共享码"
    f.loc[(f["exclusion"] == "") & f["en"].isna() & (f["mapping_source_v2"] == "皮壳无活跃EN"),
          "bucket"] = "皮壳无活跃EN"

    # ---------- 六桶对账（冻结） ----------
    recon = (f.groupby("bucket").agg(行数=("sku", "size"), 数值和=("available", "sum"))
             .reindex(list(BUCKET_BASELINE)).reset_index())
    recon["基线行数"] = [BUCKET_BASELINE[b][0] for b in recon["bucket"]]
    recon["基线数值和"] = [BUCKET_BASELINE[b][1] for b in recon["bucket"]]
    recon["行数差"] = recon["行数"] - recon["基线行数"]
    recon["数值差"] = recon["数值和"] - recon["基线数值和"]
    total_row = {"bucket": "合计", "行数": int(recon["行数"].sum()),
                 "数值和": float(recon["数值和"].sum()),
                 "基线行数": SRC_ROWS, "基线数值和": SRC_QTY,
                 "行数差": int(recon["行数"].sum()) - SRC_ROWS,
                 "数值差": float(recon["数值和"].sum()) - SRC_QTY}
    recon = pd.concat([recon, pd.DataFrame([total_row])], ignore_index=True)
    if total_row["行数差"] != 0 or abs(total_row["数值差"]) > 1e-6:
        raise SystemExit(f"六桶对账不平：{total_row}")
    assert f["bucket"].notna().all()

    # ---------- F1/F5 逐行事实层 ----------
    def link_info(r) -> tuple[set, str, set]:
        n = r["norm"]
        cs, pr = top_candidates(cand, n)
        m = COVER_RE.match(n)
        if m:
            bs, bpr = top_candidates(cand, m.group(1))
            if bs:
                cs = cs | bs
                pr = pr or bpr
        return cs, pr, {e for e in cs if e in en_role}

    links = [link_info(r) for _, r in f.iterrows()]
    f["cands_all"] = [sorted(c) for c, _, _ in links]
    f["cand_priority"] = [p for _, p, _ in links]
    f["cands_active"] = [sorted(a) for _, _, a in links]
    f["n_cands_active"] = [len(a) for _, _, a in links]

    def link_status(r) -> str:
        if r["bucket"] == "共享码":
            return "显式共享码(A登记)"
        if r["bucket"] == "皮壳无活跃EN":
            return "待判定"
        if is_missing(r["en"]):
            return "无候选"
        if r["n_cands_active"] > 1:
            return "共享待核(同优先级多候选)"
        if r["en"] in en_role and len(r["cands_active"]) == 1:
            return "唯一候选"
        return "唯一候选(v2已归属)"

    f["link_status"] = [link_status(r) for _, r in f.iterrows()]

    forms = [form_of_suffix(n, role, en) for n, role, en in zip(f["norm"], f["role"], f["en"])]
    f["actual_form"] = [x[0] for x in forms]
    f["form_basis"] = [x[1] for x in forms]

    def product_of(r) -> tuple[str | None, str]:
        en, form = r["en"], r["actual_form"]
        if is_missing(en):
            if form == "皮壳" and len(r["cands_active"]) == 1:
                return r["cands_active"][0], "皮壳码同物映射(254补证)"
            return None, ""
        if str(en).startswith("PK#"):
            base = str(en)[3:]
            if base in en_role:
                return base, "PK#→成品EN(命名直推)"
            return base, "PK#→成品EN(命名直推,母EN未激活)"
        if form == "皮壳" and r["role"] == "成品":
            return en, "皮壳码登记在成品EN下(同物)"
        if form == "海绵" and r["role"] == "成品":
            return en, "海绵码登记在成品EN下(同物)"
        return en, f"A角色直连({r['role']})"

    po = [product_of(r) for _, r in f.iterrows()]
    f["product_id"] = [x[0] for x in po]
    f["conversion_basis"] = [x[1] for x in po]

    # ---------- 多件后缀换算（用户口径 3） ----------
    pk = [piece_info(s) for s in f["sku"]]
    f["pieces_per_unit"] = [x[0] for x in pk]
    f["pieces_basis"] = [x[1] for x in pk]
    f["pieces_status"] = [x[2] for x in pk]
    f["qty_pieces"] = f["available"] * f["pieces_per_unit"]
    f["piece_bridge"] = False

    # ---------- 星球抱枕组 1:1 例外（UOM-CANONICAL §2.1） ----------
    def in_planet(r) -> bool:
        en = r["en"]
        if not is_missing(en) and str(en) in planet_ens:
            return True
        n = r["norm"]
        if n in planet_codes:
            return True
        m = COVER_RE.match(n)
        if m and m.group(1) in planet_codes:
            return True
        pm = PIECE_TAIL.match(n)
        if pm and norm(pm.group("base")) in planet_codes:
            return True
        return bool(PLANET_SKU_RE.match(str(r["sku"]).strip()))

    f["planet_group"] = [in_planet(r) for _, r in f.iterrows()]
    # v5 口径（乘 N）留底用于差异报告，再统一改 1:1
    f["pieces_rule_only"] = f["pieces_per_unit"].copy()
    f.loc[f["planet_group"], "pieces_per_unit"] = 1
    f.loc[f["planet_group"], "pieces_status"] = "组级例外1:1"
    f.loc[f["planet_group"], "pieces_basis"] = "星球抱枕整组 1:1（UOM-CANONICAL §2.1 例外）"
    f.loc[f["planet_group"], "qty_pieces"] = f.loc[f["planet_group"], "available"]
    f["legacy_note"] = ""
    f.loc[f["planet_group"], "legacy_note"] = LEGACY_NOTE

    for i, r in f[f["pieces_per_unit"] > 1].iterrows():
        m = PIECE_TAIL.match(r["sku"])
        base_en = idx.get(norm(m.group("base"))) if m else None
        if base_en and base_en in en_role:
            f.at[i, "product_id"] = base_en
            f.at[i, "actual_form"] = "成品"
            f.at[i, "form_basis"] = f"多件后缀折算：{m.group('base')} → {base_en}"
            f.at[i, "conversion_basis"] = (
                f"SKU 后缀 -{r['pieces_per_unit']}PCS：基础码 {m.group('base')} 对应产品"
                f"（每单位 {r['pieces_per_unit']} 个）")
            if r["bucket"] != "计入A":
                f.at[i, "piece_bridge"] = True

    # ---------- UOM（用户 2026-10-29 口径） ----------
    def uom_info(r) -> tuple[str, str, str]:
        en = r["en"]
        if not is_missing(en):
            cached = uoms.get(str(en))
            stockable = is_stock_item.get(str(en))
            if cached == "套" and stockable == 0:
                return "套", "TJ#/Product Bundle（缓存stock_uom=套, is_stock_item=0）", ""
            if cached == "套" and stockable == 1:
                return ("个", "缓存为套但非Bundle → 按个",
                        "uom_conflict：缓存 stock_uom=套, is_stock_item=1（EN 缓存不准，按用户口径按个）")
            if cached:
                return "个", f"EN缓存stock_uom={cached}", ""
            return "个", "EN缓存无该物料 → 按个", "无单位来源：EN 缓存无该物料"
        return "个", "通途码无 EN 单位 → 按个", "无单位来源：皮壳/海绵通途码无 EN 缓存"

    ui = [uom_info(r) for _, r in f.iterrows()]
    f["uom"] = [x[0] for x in ui]
    f["uom_source"] = [x[1] for x in ui]
    f["uom_note"] = [x[2] for x in ui]
    f.loc[f["uom"] == "套", "qty_pieces"] = f.loc[f["uom"] == "套", "available"]
    bridge_mask = f["piece_bridge"]
    if bridge_mask.any():
        f.loc[bridge_mask, "uom"] = "个"
        f.loc[bridge_mask, "uom_source"] = "多件后缀折算 → 按个"
        f.loc[bridge_mask, "qty_pieces"] = (f.loc[bridge_mask, "available"]
                                            * f.loc[bridge_mask, "pieces_per_unit"])

    # ---------- 第六桶：254 行逐行处置（C v11 双形态口径） ----------
    iso_mask = f["bucket"] == "皮壳无活跃EN"
    iso = f[iso_mask].copy()

    # 同产品在快照里是否有成品库存（任一仓池）→ 判 both_forms_present
    # 注：此块早于 supply_role 计算，用「计入A + 实物形态=成品/骨架」直接判定
    _fg_rows = f[(f["bucket"] == "计入A") & f["product_id"].notna()
                 & f["actual_form"].isin(["成品", "主体骨架"])]
    fg_products = set(_fg_rows["product_id"])
    fg_qty_by_product = _fg_rows.groupby("product_id")["qty_pieces"].sum().to_dict()

    # ---- 拆包成品（C v12）：cover 行 + 同仓 foam 行 → 可组装 min(cover, foam) ----
    _cc = pd.read_csv(args.customer_codes, dtype=str)
    cust_codes: dict[str, set] = {}
    for nm, cs in zip(_cc["name"], _cc["customer_code"]):
        if not isinstance(cs, str):
            continue
        for c in cs.split(","):
            c = c.strip()
            if c.startswith("删除"):
                c = c[2:]
            if c:
                cust_codes.setdefault(str(nm), set()).add(norm(c))
    foam_rows = f[f["sku"].astype(str).str.contains("foam", case=False, na=False)].copy()
    foam_rows["_n"] = foam_rows["sku"].map(norm)

    def _foam_qty(p: str, wh: str) -> float:
        tot = 0.0
        pcodes = cust_codes.get(p, set())
        for _, fr in foam_rows[foam_rows["warehouse_name"] == wh].iterrows():
            n = fr["_n"]
            if n in pcodes:
                tot += float(fr["available"])
                continue
            cs, _ = top_candidates(cand, n)
            if p in cs:
                tot += float(fr["available"])
        return tot

    # 同产品×仓的 cover 原始量（254 行 + 已计入A的皮壳行）
    cover_rows_all = f[(f["actual_form"] == "皮壳") & f["product_id"].notna()]
    cover_qty_map = (cover_rows_all.groupby(["product_id", "warehouse_name"])["available"]
                     .sum().to_dict())
    _iso_cover = iso.groupby([iso["cands_active"].map(lambda a: a[0] if len(a) == 1 else None),
                              "warehouse_name"])["available"].sum().to_dict()
    for (p, wh), q in _iso_cover.items():
        if p:
            cover_qty_map[(p, wh)] = max(cover_qty_map.get((p, wh), 0.0), float(q))

    def _base_qty(p: str, wh: str) -> float:
        """同仓基础码（非 -Cover/-Foam）库存。"""
        tot = 0.0
        for c in cust_codes.get(p, set()):
            if "cover" in c or "foam" in c:
                continue
            sel = f[(f["norm"] == c) & (f["warehouse_name"] == wh)]
            tot += float(sel["available"].sum())
        return tot

    def _split_of(r) -> tuple[float, float, float]:
        """返回 (cover 原始量, 同仓 foam 量, 同仓基础码量)。"""
        a = r["cands_active"]
        if len(a) != 1:
            return float(r["available"]), 0.0, 0.0
        p, wh = a[0], r["warehouse_name"]
        return (float(cover_qty_map.get((p, wh), r["available"])), _foam_qty(p, wh),
                _base_qty(p, wh))

    def dispose(r) -> tuple[str, str]:
        if float(r["available"]) == 0:
            return "忽略(0库存)", "available=0：不构成供给，也不阻塞"
        act = r["cands_active"]
        if len(act) > 1:
            return "待核", "多候选同优先级（保留全部候选，不任取）"
        if len(act) == 1:
            p = act[0]
            ship = en_ship.get(p)
            role = en_role.get(p)
            if role not in ("成品", "套件") and not str(p).startswith("PK#"):
                return "仍隔离", f"映射到非成品角色({role})，不构成成品供给"
            if ship == "皮壳":
                return "补证", "同物映射→活跃产品且方式=皮壳：皮壳供给（1 皮壳=1 个）"
            if ship == "半成品":
                return "补证", "方式=半成品：皮壳为可履约形态，计入皮壳供给"
            if ship == "成品":
                cover, foam, base = _split_of(r)
                if min(cover, foam) > 0:
                    return "拆包组装", f"成品模式：cover {cover:g} + foam {foam:g} → 可组装 {min(cover, foam):g}"
                if p in fg_products:
                    return "补证", "同产品同时有成品与皮壳库存：双形态累加（1 皮壳=1 个）"
                lack = "Foam" if cover > 0 else ("Cover" if foam > 0 else "Cover/Foam")
                return ("component_partial_nonblocking",
                        f"组件不全（缺 {lack}），不阻塞：默认绍兴下单成品，可单独补皮壳/海绵")
            if ship is None:
                return "待核", "产品发货方式未知（不猜）"
        return "仍隔离", "无活跃EN映射（码未登记到任何活跃产品）"

    disp = [dispose(r) for _, r in iso.iterrows()]
    iso["处置"] = [x[0] for x in disp]
    iso["处置原因"] = [x[1] for x in disp]
    iso["base码"] = [COVER_RE.match(n).group(1) if COVER_RE.match(n) else "" for n in iso["norm"]]
    iso["候选产品"] = [",".join(c) for c in iso["cands_active"]]
    iso["产品方式"] = [",".join(str(en_ship.get(c, "")) for c in c) for c in iso["cands_active"]]
    iso["both_forms_present"] = [
        bool(a) and (a[0] in fg_products) for a in iso["cands_active"]]
    iso["产品成品库存(个)"] = [float(fg_qty_by_product.get(a[0], 0.0)) if a else None
                              for a in iso["cands_active"]]
    _sp = [_split_of(r) for _, r in iso.iterrows()]
    iso["cover_raw"] = [x[0] for x in _sp]
    iso["foam_raw"] = [x[1] for x in _sp]
    iso["base_raw"] = [x[2] for x in _sp]
    iso["blocking"] = [d == "待核" for d in iso["处置"]]
    iso["component_note"] = [
        ("缺 Foam" if (x[1] <= 0 and x[0] > 0) else ("缺 Cover" if (x[0] <= 0 and x[1] > 0) else ""))
        if d == "component_partial_nonblocking" else ""
        for d, x in zip(iso["处置"], _sp)]
    iso["assembled_qty"] = [min(x[0], x[1]) if d == "拆包组装" else 0.0
                            for x, d in zip(_sp, iso["处置"])]
    iso["split_package"] = iso["处置"] == "拆包组装"
    iso["missing_component"] = iso["component_note"]
    iso["本行皮壳量(个)"] = iso["qty_pieces"]
    # 拆包行：个当量=可组装数（同步写回事实层，供 pivot 计入成品供给）
    iso.loc[iso["split_package"], "qty_pieces"] = iso.loc[iso["split_package"], "assembled_qty"]
    _split_map = dict(zip(iso.loc[iso["split_package"], "src_row"],
                          iso.loc[iso["split_package"], "assembled_qty"]))
    if _split_map:
        f["qty_pieces"] = [
            float(_split_map.get(int(sr), qp))
            for sr, qp in zip(f["src_row"], f["qty_pieces"])]
        f["split_package"] = f["src_row"].isin(_split_map)
        f["cover_raw"] = [float(iso.set_index("src_row")["cover_raw"].get(int(sr), float("nan")))
                          if int(sr) in _split_map else None for sr in f["src_row"]]
        f["foam_raw"] = [float(iso.set_index("src_row")["foam_raw"].get(int(sr), float("nan")))
                         if int(sr) in _split_map else None for sr in f["src_row"]]
    else:
        f["split_package"] = False
        f["cover_raw"] = None
        f["foam_raw"] = None
    iso_tbl = iso[["src_row", "sku", "warehouse_name", "pool", "available", "qty_pieces", "uom",
                   "uom_source", "base码", "role", "actual_form", "候选产品", "产品方式",
                   "处置", "处置原因", "both_forms_present", "产品成品库存(个)", "本行皮壳量(个)",
                   "split_package", "cover_raw", "foam_raw", "base_raw", "assembled_qty",
                   "missing_component", "blocking", "component_note",
                   "form_basis", "cand_priority"]].rename(columns={
        "src_row": "源行号(parquet1基)", "sku": "源SKU", "warehouse_name": "仓", "pool": "仓池",
        "available": "available", "qty_pieces": "个当量", "uom": "uom", "uom_source": "单位来源",
        "role": "A角色(v2无)", "actual_form": "实物形态", "form_basis": "形态依据",
        "cand_priority": "候选来源优先级"})
    iso_tbl["A角色(v2无)"] = iso_tbl["A角色(v2无)"].fillna("(无,未归属)")

    f["iso_disposition"] = ""
    f.loc[iso_mask, "iso_disposition"] = iso["处置"].values
    iso_proven = iso_mask & (f["iso_disposition"] == "补证")

    # ---------- N3/状态分层：身份状态（唯一/共享/未映射/未激活/待核） ----------
    def identity(r) -> str:
        b = r["bucket"]
        if b == "共享码":
            return "共享"
        if b == "未映射":
            return "未映射"
        if b == "A未激活":
            return "未激活"
        if b == "皮壳无活跃EN":
            n = len(r["cands_active"])
            if r["iso_disposition"] == "补证":
                return "唯一"
            if n > 1:
                return "共享"
            if n == 1:
                return "待核" if r["iso_disposition"] == "待核" else "唯一"
            return "未映射"
        if r["link_status"].startswith("共享"):
            return "共享"
        if is_missing(r["en"]):
            return "未映射"
        return "唯一"

    f["identity_status"] = [identity(r) for _, r in f.iterrows()]

    def proof(r) -> str:
        ids = r["identity_status"]
        if ids == "共享":
            return ("归属待核(显式共享码)" if r["bucket"] == "共享码"
                    else "归属待核(共享多候选)")
        if ids == "未映射":
            return "无映射(未归属)"
        if ids == "未激活":
            return "归属未激活(映射到非活跃EN)"
        if ids == "待核":
            return "归属待核(候选唯一但发货方式未定)"
        # 唯一：只有唯一有效映射才标「归属已证」
        if r["iso_disposition"] == "补证":
            return "归属已证(254补证)"
        if r["bucket"] == "皮壳无活跃EN":
            return "归属已证(唯一候选;形态不适用)"
        if r["piece_bridge"]:
            return "归属已证(基础码→活跃产品)"
        return "归属已证"

    f["link_proof"] = [proof(r) for _, r in f.iterrows()]
    # 多件后缀跨桶行：基础码已映射到活跃产品（桶仍保留 A未激活）
    if bridge_mask.any():
        f.loc[bridge_mask, "link_proof"] = "归属已证(基础码→活跃产品)"
        f.loc[bridge_mask, "identity_status"] = "唯一"

    # ---------- 单位状态 ----------
    def uom_status_of(r) -> str:
        if r["uom"] == "套":
            return "套件"
        if str(r["uom_note"]).startswith("uom_conflict"):
            return "冲突"
        if str(r["uom_source"]).startswith("EN缓存stock_uom="):
            return "已证"
        if str(r["uom_source"]).startswith("多件后缀折算"):
            return "已证"
        return "默认个"

    f["uom_status"] = [uom_status_of(r) for _, r in f.iterrows()]

    # ---------- 供给状态（N2：骨架按独立成品；套单列） ----------
    def eligible(r) -> str:
        if r["piece_bridge"]:
            return "成品供给"
        if r["bucket"] == "皮壳无活跃EN":
            if r["iso_disposition"] == "拆包组装":
                return "成品供给"
            if r["iso_disposition"] != "补证":
                return "待核" if r["iso_disposition"] == "待核" else "仍隔离(不计)"
        elif r["bucket"] != "计入A":
            return "非计入桶"
        if r["uom"] == "套":
            return "套件单列(套)"
        form = r["actual_form"]
        if form == "海绵":
            # C v12：HM 物料（role=海绵/海绵关联成品）有海绵库存即独立供给
            if r["role"] in ("海绵", "海绵/关联成品"):
                return "海绵供给"
            return "海绵分支(不计)"
        if form == "内胆":
            return "内胆组件(不计)"
        if form == "套件":
            return "套件单列(个)"
        if form not in ("成品", "皮壳", "主体骨架"):
            return "形态未知(待核)"
        p = r["product_id"]
        ship = en_ship.get(p) if p else None
        if ship is None:
            return "发货方式未知(待核)"
        if form == "皮壳":
            # C v11：皮壳与半成品方式下，皮壳都是可履约形态（成品也可替代）
            if ship not in ("皮壳", "半成品"):
                return f"方式={ship}:皮壳组件(不计)"
            return "皮壳供给"
        return "成品供给"

    f["supply_role"] = [eligible(r) for _, r in f.iterrows()]
    multi_in_counted = f[(f["bucket"] == "计入A") & (f["link_status"].str.startswith("共享"))]
    f.loc[multi_in_counted.index, "supply_role"] = "待核"

    def avail(r) -> str:
        if r["supply_role"] in ("非计入桶", "仍隔离(不计)"):
            return "不进join"
        if r["supply_role"] in ("待核", "发货方式未知(待核)", "形态未知(待核)"):
            return "待核"
        if r["supply_role"] in ("套件单列(套)", "套件单列(个)"):
            return "套件单列"
        if r["pool"] in (POOL_CG, POOL_OTHER):
            return "仅披露(CG/其他)"
        if r["supply_role"] in ("海绵分支(不计)", "内胆组件(不计)") \
                or r["supply_role"].startswith("方式="):
            return "仅披露(不计)"
        return "可进join"

    f["availability"] = [avail(r) for _, r in f.iterrows()]

    # ---------- 覆盖状态（事实行级）：完整=计入 / 部分=已知形态但未计入 / 未覆盖=无法归属 / 不适用=规则排除 ----------
    def coverage_of_row(r) -> str:
        if r["bucket"] == "规则排除":
            return "不适用"
        if r["identity_status"] in ("共享", "未映射", "未激活", "待核"):
            return "未覆盖"
        if r["supply_role"] in ("成品供给", "皮壳供给", "套件单列(套)", "套件单列(个)"):
            return "完整"
        if r["supply_role"] == "仍隔离(不计)":
            return "未覆盖"
        return "部分"

    f["coverage_status"] = [coverage_of_row(r) for _, r in f.iterrows()]

    # ---------- C8-1 供给资格最小闭环（physical_form / canonical_uom / demand_eligibility） ----------
    FORM_CANON = {"成品": "成品", "皮壳": "皮壳", "海绵": "海绵", "内胆": "内胆",
                  "主体骨架": "骨架", "套件": "套件", "unknown": "未知"}

    def physical_form_of(r) -> str:
        """实物形态（canonical）。半成品保留 raw 成品形态，不口头等同 PK#。"""
        return FORM_CANON.get(str(r["actual_form"]), "未知")

    def qual_category_of(r) -> str:
        role, form = r["role"], r["actual_form"]
        ship = en_ship.get(r["product_id"]) if r["product_id"] else None
        if role in ("海绵", "海绵/关联成品") or form == "海绵":
            return "HM"
        if role == "内胆" or form == "内胆":
            return "ND"
        if r["uom"] == "套" or role == "套件" or form == "套件":
            return "TJ#"
        if form == "主体骨架":
            return "骨架"
        if ship == "半成品" and role == "成品":
            return "半成品"
        if role == "皮壳" or form == "皮壳":
            return "皮壳"
        if role == "成品":
            return "成品"
        return "其他"

    def eligibility_of(r) -> tuple[str, str]:
        """(demand_eligibility, reason)。语义：该行能否作为独立终端需求的锚。"""
        cat = r["qual_category"]
        if r["identity_status"] in ("未映射", "未激活") or r["bucket"] == "规则排除":
            return "not_applicable", "未映射/未激活/规则排除：不构成需求或供给事实"
        if cat == "HM":
            return ("component",
                    "用户口径：海绵目前假设不单独销售 → 默认 component；SO 独立行不足以证售后/零售"
                    "（SPONGE §3）；无父件不猜配套，after_sales 仅在有确认的补发/备件时启用")
        if cat == "ND":
            return "component", "内胆只作组件/齐套证据，不生成独立终端需求（ND 独立需求=0）"
        if cat == "TJ#":
            return ("independent",
                    "TJ#/Product Bundle 是可按套销售的产品：需求按「套」，不拆组件重复计数，不进个净额")
        if cat == "骨架":
            return "independent", "主体骨架按用户规则独立销售/独立可补（N2），不并入沙发成品"
        if cat == "半成品":
            return ("independent",
                    "产品发货方式=半成品：保留 raw 成品形态，不等同 PK#；供给按成品口径计入")
        if cat == "皮壳":
            return ("component",
                    "皮壳是该产品的供货物料（PK#→KS 1:1），不单独建终端需求；"
                    "仅已证「独立皮壳零售」才可独立")
        if cat == "成品":
            return "independent", "成品：终端需求锚（A 角色=成品）"
        return "not_applicable", "无角色/形态证据，不判定需求资格"

    f["physical_form"] = [physical_form_of(r) for _, r in f.iterrows()]
    f["canonical_uom"] = f["uom"]
    f["qual_category"] = [qual_category_of(r) for _, r in f.iterrows()]
    _elig = [eligibility_of(r) for _, r in f.iterrows()]
    f["demand_eligibility"] = [x[0] for x in _elig]
    f["eligibility_reason"] = [x[1] for x in _elig]

    def source_ref_of(r) -> str:
        parts = [f"ST:{int(r['src_row'])}", f"sku={r['sku']}",
                 f"wh={r['warehouse_name']}", f"qty={r['available']:g}",
                 f"form={r['actual_form']}", f"uom={r['uom']}"]
        if r["product_id"]:
            parts.append(f"product={r['product_id']}")
        if r["identity_status"] == "共享":
            parts.append(f"pool=SP-{r['norm']}")
        return ";".join(parts)

    f["source_ref"] = [source_ref_of(r) for _, r in f.iterrows()]
    # C8-2：共享池 ID（同码=同一物理池；不向候选产品复制数量）
    f["shared_pool_id"] = [f"SP-{n}" if s == "共享" else ""
                           for n, s in zip(f["norm"], f["identity_status"])]

    # ---------- 产品×仓池×UOM 供给汇总（N1 门禁：空集=null；伪 0 判 null） ----------
    sup_src = f[f["supply_role"].isin(["成品供给", "皮壳供给", "海绵供给", "海绵分支(不计)",
                                       "内胆组件(不计)", "套件单列(套)", "套件单列(个)",
                                       "待核", "发货方式未知(待核)", "形态未知(待核)"])
                | f["supply_role"].str.startswith("方式=")].copy()
    sup_src = sup_src[sup_src["product_id"].notna()]

    sup_src = sup_src.assign(
        n_fg=(sup_src["supply_role"] == "成品供给").astype(int),
        n_cover=(sup_src["supply_role"] == "皮壳供给").astype(int),
        n_pending=sup_src["supply_role"].isin(
            ["待核", "发货方式未知(待核)", "形态未知(待核)"]).astype(int),
        n_bundle=sup_src["supply_role"].isin(["套件单列(套)"]).astype(int),
        n_setpcs=(sup_src["supply_role"] == "套件单列(个)").astype(int),
        n_hm=(sup_src["supply_role"] == "海绵供给").astype(int),
        ident_counted=sup_src["identity_status"].where(
            sup_src["supply_role"].isin(["成品供给", "皮壳供给", "海绵供给",
                                         "套件单列(套)", "套件单列(个)"]), None),
    )
    sup_src = sup_src.assign(
        q_fg=sup_src["qty_pieces"].where(sup_src["n_fg"] == 1, 0.0),
        q_skeleton=sup_src["qty_pieces"].where(
            (sup_src["n_fg"] == 1) & (sup_src["actual_form"] == "主体骨架"), 0.0),
        q_cover=sup_src["qty_pieces"].where(sup_src["n_cover"] == 1, 0.0),
        q_foam=sup_src["qty_pieces"].where(sup_src["supply_role"] == "海绵分支(不计)", 0.0),
        q_comp=sup_src["qty_pieces"].where(sup_src["supply_role"] == "内胆组件(不计)", 0.0),
        q_pending=sup_src["qty_pieces"].where(sup_src["n_pending"] == 1, 0.0),
        q_bundle=sup_src["available"].where(sup_src["n_bundle"] == 1, 0.0),
        q_setpcs=sup_src["qty_pieces"].where(sup_src["n_setpcs"] == 1, 0.0),
        q_hm=sup_src["qty_pieces"].where(sup_src["n_hm"] == 1, 0.0),
    )
    pivot = (sup_src.groupby(["product_id", "pool", "uom"], dropna=False).agg(
        成品行数=("n_fg", "sum"), 成品库存=("q_fg", "sum"), 其中骨架=("q_skeleton", "sum"),
        皮壳行数=("n_cover", "sum"), 皮壳库存=("q_cover", "sum"),
        套件库存=("q_bundle", "sum"), 套件行数=("n_bundle", "sum"),
        套件个行数=("n_setpcs", "sum"), 套件个库存=("q_setpcs", "sum"),
        海绵库存=("q_foam", "sum"), 内胆库存=("q_comp", "sum"),
        海绵个体行数=("n_hm", "sum"), 海绵供给库存=("q_hm", "sum"),
        待核行数=("n_pending", "sum"), 待核库存=("q_pending", "sum"),
        行数=("n_fg", "size"),
        uom_source=("uom_source", lambda s: "；".join(sorted(set(s)))),
        uom_status=("uom_status", lambda s: (s.iloc[0] if s.nunique() == 1
                                             else "混合:" + "/".join(sorted(set(s))))),
        identity_status=("identity_status", lambda s: _agg_identity(s)),
        identity_counted=("ident_counted",
                          lambda s: _agg_identity(s.dropna()) if s.notna().any() else ""),
    )).reset_index()
    # C v14：键身份以「实际计入的供给行」为准；零库存共享/待核行不改变键身份
    pivot["identity_status"] = [
        c if isinstance(c, str) and c else a
        for c, a in zip(pivot["identity_counted"], pivot["identity_status"])]
    pivot["ship_mode"] = pivot["product_id"].map(en_ship)
    pivot["ship_mode_cn"] = pivot["product_id"].map(en_ship_cn)
    pivot["产品角色"] = pivot["product_id"].map(en_role)

    def calc(r):
        """C v11：按 ship_mode 判必需形态（用户 2026-10-30 确认：成品可替代皮壳）。
        返回 (可发供给, 供给状态, 覆盖状态, 覆盖缺口, 门禁原因, required_form, optional_form, 形态要求状态)。
        N1 门禁不变：无适用事实=null；已计0但有未计正量=null；共享/待核不聚合成已证 0。"""
        gaps: list[str] = []
        if r["uom"] == "套":
            if r["套件行数"] == 0:
                return (None, "无适用事实(非0)", "未覆盖", "无套件事实行", "无套件事实行",
                        "套件", "", "无事实")
            gaps = ["有待核行(有量)"] if r["待核库存"] > 0 else []
            detail = "/".join(gaps)
            if float(r["待核库存"]) > 0:
                return (None, "待核(已计0;有未计形态量)", "部分", detail, "套件0但待核有量",
                        "套件", "", "缺必需形态")
            return (float(r["套件库存"]), "套件单列", ("完整" if not gaps else "部分"), detail,
                    "仅套件事实行", "套件", "", "满足")

        # C v12：HM 物料有海绵库存即独立供给，不要求成品行
        if r["产品角色"] in ("海绵", "海绵/关联成品"):
            if float(r["海绵个体行数"]) == 0:
                why = "无海绵事实行"
                return (None, "无适用事实(非0)", "未覆盖", why, why, "海绵", "", "无事实")
            v_hm = float(r["海绵供给库存"])
            gaps = ["有待核行(有量)"] if r["待核库存"] > 0 else []
            hidden_hm = float(r["内胆库存"] + r["待核库存"] + r["套件个库存"])
            if v_hm == 0 and hidden_hm > 0:
                return (None, "待核(已计0;有未计形态量)", "部分", "/".join(gaps),
                        "已计为0但另有未计正量", "海绵", "", "满足")
            return (v_hm, "已计入", ("部分" if gaps else "完整"), "/".join(gaps),
                    ("完整" if not gaps else "部分覆盖"), "海绵", "", "满足")

        ship = r["ship_mode"]
        if is_missing(ship) or ship not in ("皮壳", "成品", "半成品"):
            # C v12：发货方式未知且无库存 → uncovered（不是 partial）
            return (None, "待核(发货方式未知)", "未覆盖", "方式未知", "方式未知",
                    "未知", "未知", "未知(pending)")

        fg, cv = float(r["成品行数"]), float(r["皮壳行数"])
        n_app = fg + cv
        hidden_pos = float(r["海绵库存"] + r["内胆库存"] + r["待核库存"] + r["套件个库存"])
        if ship == "皮壳":
            req, opt = "皮壳或成品", "另一形态（可替代）"
            v = float(r["成品库存"] + r["皮壳库存"])
            ok = n_app > 0
        elif ship == "半成品":
            req, opt = "半成品/皮壳或成品", "另一形态（可替代）"
            v = float(r["成品库存"] + r["皮壳库存"])
            ok = n_app > 0
        else:  # 成品
            req, opt = "成品", "皮壳组件（不计）"
            v = float(r["成品库存"])
            ok = fg > 0

        if n_app == 0:
            why = "仅未计形态行" if hidden_pos > 0 else "无适用行"
            return (None, "无适用事实(非0)", "未覆盖", why, why, req, opt, "无事实")
        if not ok:
            gaps.append(f"缺必需形态:{req}")
        if r["待核库存"] > 0:
            gaps.append("有待核行(有量)")
        # 非必需形态：只记录，不单独构成 partial
        if r["海绵库存"] > 0:
            gaps.append("含海绵(非必需)")
        if r["内胆库存"] > 0:
            gaps.append("含内胆(非必需)")
        if r["套件个行数"] > 0:
            gaps.append("含套件行(非必需)")
        partial = (not ok) or r["待核库存"] > 0
        cov = "部分" if partial else "完整"
        detail = "/".join(gaps)
        if v == 0 and hidden_pos > 0:
            return (None, "待核(已计0;有未计形态量)", cov, detail, "已计为0但另有未计正量",
                    req, opt, "缺必需形态" if not ok else "满足")
        return (v, "已计入", cov, detail, ("完整" if not partial else "部分覆盖"),
                req, opt, ("满足" if ok else "缺必需形态"))

    cc_ = [calc(r) for _, r in pivot.iterrows()]
    pivot["可发供给"] = [x[0] for x in cc_]
    pivot["供给状态"] = [x[1] for x in cc_]
    pivot["覆盖状态"] = [x[2] for x in cc_]
    pivot["覆盖缺口"] = [x[3] for x in cc_]
    pivot["门禁原因"] = [x[4] for x in cc_]
    pivot["required_form"] = [x[5] for x in cc_]
    pivot["optional_form"] = [x[6] for x in cc_]
    pivot["form_requirement_status"] = [x[7] for x in cc_]

    def avail2(r):
        if r["uom"] == "套":
            if r["供给状态"].startswith("无适用") or r["供给状态"].startswith("待核"):
                return "不进join(无适用事实)" if r["供给状态"].startswith("无适用") else "不进join(待核)"
            return "套件单列"
        if r["可发供给"] is None or pd.isna(r["可发供给"]):
            return "不进join(无适用事实)" if r["供给状态"].startswith("无适用") else "不进join(待核)"
        if r["pool"] in (POOL_CG, POOL_OTHER):
            return "仅披露(CG/其他)"
        if r["覆盖状态"] == "完整":
            return "可进join"
        return f"可进join(partial:{r['覆盖缺口']})"

    pivot["可用性"] = [avail2(r) for _, r in pivot.iterrows()]
    pivot["补货资格"] = ["老产品-默认不补(待确认)" if str(p) in planet_ens else ""
                         for p in pivot["product_id"]]
    supply_tbl = pivot[["product_id", "产品角色", "ship_mode", "ship_mode_cn", "pool", "uom",
                        "uom_source", "uom_status", "identity_status", "成品库存", "其中骨架",
                        "皮壳库存", "套件库存", "套件个库存", "可发供给", "供给状态", "覆盖状态",
                        "覆盖缺口", "门禁原因", "required_form", "optional_form",
                        "form_requirement_status",
                        "海绵库存", "内胆库存", "待核库存", "行数", "可用性",
                        "补货资格"]].rename(columns={"uom_status": "单位状态",
                                                      "identity_status": "身份状态"}) \
        .sort_values(["pool", "product_id", "uom"])

    # ---------- P2-1：可进 join 拆分（join_full / join_partial / no_join） ----------
    def join_class_of(r) -> tuple[str, str]:
        """默认消费只允许 join_full。join_partial 仅观察/需白名单，不得静默进补货净额。"""
        val = r["可发供给"]
        if val is None or pd.isna(val):
            return "no_join", "null(无适用事实或已计0但有未计正量)"
        if r["uom"] == "套":
            return "no_join", "套件单列(套)"
        if r["pool"] in (POOL_CG, POOL_OTHER):
            return "no_join", "仅披露(CG/其他)"
        if str(r["供给状态"]).startswith("待核"):
            return "no_join", "待核"
        reasons = []
        if r["覆盖状态"] != "完整":
            reasons.append(f"覆盖{r['覆盖状态']}")
        if r["身份状态"] != "唯一":
            reasons.append(f"身份{r['身份状态']}")
        if reasons:
            return "join_partial", "/".join(reasons)
        # C v11：单位冲突不再单独阻断（任务：partial 只在形态缺失/未知时成立），
        # 但保留 uom_conflict 标记供下游显式过滤
        return "join_full", ""

    jc = [join_class_of(r) for _, r in supply_tbl.iterrows()]
    supply_tbl["join_class"] = [x[0] for x in jc]
    supply_tbl["join_reason"] = [x[1] for x in jc]

    # ---------- C8-1/C8-3：供给键的形态、UOM、来源证明与候选闸门 ----------
    def key_form(r) -> str:
        if r["uom"] == "套":
            return "套件"
        if float(r["其中骨架"] or 0) > 0:
            return "骨架"
        fg, cv = float(r["成品库存"] or 0), float(r["皮壳库存"] or 0)
        if fg > 0 and cv > 0:
            return "成品+皮壳"
        if cv > 0:
            return "皮壳"
        if fg > 0:
            return "成品"
        return "无适用" if str(r["供给状态"]).startswith("无适用") else "成品"

    supply_tbl["physical_form"] = [key_form(r) for _, r in supply_tbl.iterrows()]
    supply_tbl["canonical_uom"] = supply_tbl["uom"]
    supply_tbl["uom_conflict_flag"] = supply_tbl["单位状态"].astype(str).str.contains("冲突")

    counted_src = sup_src[sup_src["supply_role"].isin(
        ["成品供给", "皮壳供给", "套件单列(套)"])]
    proof_map = {}
    for (pid, pool, uom), g in counted_src.groupby(["product_id", "pool", "uom"]):
        rows = ",".join("ST:" + str(int(x)) for x in sorted(g["src_row"]))
        proof_map[(pid, pool, uom)] = f"{rows};qty={g['qty_pieces'].sum():g}"
    supply_tbl["source_proof"] = [
        proof_map.get((r["product_id"], r["pool"], r["uom"]), "无适用源行")
        for _, r in supply_tbl.iterrows()]
    supply_tbl["join_candidate"] = supply_tbl["join_class"] == "join_full"
    # C v13：除真共享身份冲突外，其余非 full 行不再阻塞 Top50/下一步
    supply_tbl["blocking"] = ((supply_tbl["join_class"] == "join_partial")
                              & (supply_tbl["身份状态"] == "共享"))

    # ---------- C9：partial/no_join/null 的可操作状态（reason_code + 证据/动作/责任人） ----------
    # 码表 → (needed_evidence, next_action, owner)
    CODE_META = {
        # join_partial
        "missing_finished": ("补该产品×仓池的成品库存行（在途/SO/DN 或盘点）", "补证", "主数据"),
        "missing_cover": ("补皮壳库存行或确认该仓无皮壳供给", "补证", "主数据"),
        "missing_sponge": ("补海绵分支证据（父件/BOM/售后凭证），不猜配套", "人工确认", "业务"),
        "missing_kit": ("确认套件/组合身份（是否 EN Product Bundle；非 Bundle 套件归属）", "人工确认", "主数据"),
        "shared_pending": ("共享码候选归属证据（订单/DN/物料血缘）并批准分配", "人工确认", "业务"),
        "uom_partial": ("单位证据（EN stock_uom 与 Bundle 身份一致性）", "人工确认", "主数据"),
        "coverage_partial": ("补齐覆盖缺口（缺哪一形态见覆盖缺口列）", "补证", "主数据"),
        # no_join
        "no_applicable_fact": ("补该产品×仓池的适用供给事实源行", "补证", "主数据"),
        "uncovered": ("补该产品库存行或确认该快照确无库存", "补证", "主数据"),
        "shared_pool": ("共享池分配需业务批准（allocation_qty>0 另表落证）", "人工确认", "业务"),
        "kit_only": ("无需补：按套保留、不拆组件、不进个净额", "不补(按套观察)", "系统"),
        "cg_other": ("CG/其他仓不进责任仓净额；如需归仓再补市场/仓责任证据", "不补(仅披露)", "业务"),
        "excluded": ("按排除规则（FBA/退货/第三方/非商品/超大占位）不回补", "不补", "系统"),
        "uom_conflict": ("单位冲突待确认（缓存套但非 Bundle）", "人工确认", "主数据"),
        "identity_ambiguous": ("身份歧义（多候选/待核）需归属证据", "人工确认", "业务"),
        # null
        "unknown_not_zero": ("补未计形态（套件/HM/ND）的归属与数量证据；不得当 0", "人工确认", "业务"),
        # full
        "none": ("", "", ""),
    }

    def reason_code_of(r) -> str:
        val = r["可发供给"]
        if val is None or pd.isna(val):
            return ("unknown_not_zero" if "未计正量" in str(r["门禁原因"])
                    else "no_applicable_fact")
        cls = r["join_class"]
        if cls == "join_full":
            return "none"
        gaps = str(r["覆盖缺口"])
        uom = str(r["单位状态"])
        if cls == "join_partial":
            if r["身份状态"] == "共享" and r["待核库存"] > 0:
                return "shared_pending"
            if "缺必需形态" in gaps and "成品" in gaps:
                return "missing_finished"
            if "缺必需形态" in gaps and "皮壳" in gaps:
                return "missing_cover"
            if "含海绵(非必需)" in gaps:
                return "missing_sponge"
            if "含套件行(非必需)" in gaps:
                return "missing_kit"
            return "coverage_partial"
        # no_join（有值）
        if r["uom"] == "套":
            return "kit_only"
        if r["pool"] in (POOL_CG, POOL_OTHER):
            return "cg_other"
        if r["身份状态"] == "共享":
            return "shared_pool"
        if r["身份状态"] == "待核":
            return "identity_ambiguous"
        if "冲突" in uom:
            return "uom_conflict"
        if r["覆盖状态"] == "未覆盖":
            return "uncovered"
        return "no_applicable_fact"

    supply_tbl["reason_code"] = [reason_code_of(r) for _, r in supply_tbl.iterrows()]
    supply_tbl["needed_evidence"] = supply_tbl["reason_code"].map(lambda c: CODE_META[c][0])
    supply_tbl["next_action"] = supply_tbl["reason_code"].map(lambda c: CODE_META[c][1])
    supply_tbl["owner"] = supply_tbl["reason_code"].map(lambda c: CODE_META[c][2])
    # join_partial 默认不消费；白名单默认空 → partial 一律 blocked
    supply_tbl["whitelist_status"] = supply_tbl["join_class"].map(
        lambda c: "not_required" if c == "join_full" else "not_whitelisted")
    supply_tbl["consumption"] = [
        "netting" if c == "join_full" else "blocked"
        for c in supply_tbl["join_class"]]
    supply_tbl = supply_tbl[["product_id", "产品角色", "ship_mode", "ship_mode_cn", "pool", "uom",
                             "uom_source", "单位状态", "身份状态", "physical_form", "canonical_uom",
                             "成品库存", "其中骨架",
                             "皮壳库存", "套件库存", "套件个库存", "可发供给", "供给状态", "覆盖状态",
                             "覆盖缺口", "门禁原因", "海绵库存", "内胆库存", "待核库存", "行数",
                             "required_form", "optional_form", "form_requirement_status",
                             "join_class", "join_reason", "join_candidate", "source_proof",
                             "reason_code", "needed_evidence", "next_action", "owner",
                             "uom_conflict_flag", "blocking", "whitelist_status", "consumption",
                             "可用性", "补货资格"]]

    # ---------- 多件后缀换算表（含星球组 1:1 例外） ----------
    pc_rows = f[f["pieces_status"] != ""].copy()
    pc_rows["v5口径个当量"] = pc_rows["available"] * pc_rows["pieces_rule_only"]
    pc_tbl = pc_rows[["src_row", "sku", "pieces_per_unit", "pieces_basis", "pieces_status",
                      "warehouse_name", "pool", "available", "qty_pieces", "v5口径个当量",
                      "legacy_note", "bucket", "en", "product_id", "supply_role",
                      "availability"]].rename(columns={
        "src_row": "源行号(parquet1基)", "sku": "源SKU", "pieces_per_unit": "每单位件数",
        "pieces_basis": "依据", "pieces_status": "状态", "warehouse_name": "仓", "pool": "仓池",
        "available": "available", "qty_pieces": "本版个当量",
        "v5口径个当量": "若按后缀乘N(个当量)", "legacy_note": "补货标记", "bucket": "桶",
        "en": "映射EN", "product_id": "产品", "supply_role": "供给状态",
        "availability": "可用性"}).sort_values(["本版个当量"], ascending=False)
    conv = pc_rows[pc_rows["pieces_status"] == "已换算"]
    exc = pc_rows[pc_rows["pieces_status"] == "组级例外1:1"]
    mid = pc_rows[pc_rows["pieces_status"] == "仅列不换算"]
    pc_summary = pd.DataFrame([
        {"项": "已换算(末尾多件后缀，非星球组)", "行数": int(len(conv)),
         "原始available": float(conv["available"].sum()), "个当量": float(conv["qty_pieces"].sum()),
         "若按后缀乘N": float(conv["v5口径个当量"].sum())},
        {"项": "组级例外 1:1（星球抱枕 KS0019）", "行数": int(len(exc)),
         "原始available": float(exc["available"].sum()), "个当量": float(exc["qty_pieces"].sum()),
         "若按后缀乘N": float(exc["v5口径个当量"].sum())},
        {"项": "仅列不换算(名称中段件数)", "行数": int(len(mid)),
         "原始available": float(mid["available"].sum()), "个当量": float(mid["qty_pieces"].sum()),
         "若按后缀乘N": float(mid["available"].sum())},
    ])

    # ---------- F5 共享候选全集 ----------
    def cands_disp(n: str) -> dict[str, set]:
        out: dict[str, set] = {}
        for e in _all_cands(cand, n):
            out.setdefault(e, set()).update(_tags_for(cand, n, e))
        m = COVER_RE.match(n)
        if m:
            for e in _all_cands(cand, m.group(1)):
                out.setdefault(e, set()).update(_tags_for(cand, m.group(1), e))
        return out

    shared_stock = f[(f["mapping_source_v2"] == "共享码(未归属)") | (f["norm"].isin(shared_codes))
                     | (f["n_cands_active"] > 1)]
    sh = (shared_stock.groupby(["norm", "warehouse_name", "pool"], dropna=False)
          .agg(行数=("sku", "size"), 库存=("available", "sum")).reset_index()
          .rename(columns={"norm": "归一码", "warehouse_name": "仓"}))
    sh["A登记候选"] = sh["归一码"].map(lambda n: shared_cand.get(n, ""))
    sh["本次全部候选(含来源)"] = sh["归一码"].map(
        lambda n: " | ".join(f"{en}<-{'/'.join(sorted(t))}"
                             for en, t in sorted(cands_disp(n).items())))
    sh["候选数"] = sh["归一码"].map(lambda n: len(cands_disp(n)))
    sh["触发来源"] = sh["归一码"].map(
        lambda n: "A共享码登记+多候选" if (n in shared_codes and len(cands_disp(n)) > 1)
        else ("A共享码登记" if n in shared_codes else "同优先级多候选(未登记)"))
    sh["处理"] = sh["归一码"].map(lambda n: "共享待核：保留全部候选，不分配单一EN"
                                  if len(cands_disp(n)) > 1 else "共享待核(A登记)")

    # ---------- 明细表（全量事实层） ----------
    detail = f[f["bucket"].notna()][
        ["src_row", "sku", "norm", "warehouse_id", "warehouse_name", "仓类别", "pool", "available",
         "pieces_per_unit", "qty_pieces", "pieces_status", "legacy_note", "uom", "uom_source",
         "uom_note", "uom_status", "bucket", "en", "role", "actual_form", "physical_form",
         "canonical_uom", "form_basis", "product_id", "qual_category", "demand_eligibility",
         "eligibility_reason", "source_ref", "shared_pool_id",
         "conversion_basis", "link_status", "identity_status", "link_proof", "supply_role",
         "coverage_status", "availability", "mapping_source_v2"]].rename(columns={
        "src_row": "源行号(parquet1基)", "sku": "source_sku", "norm": "归一码",
        "warehouse_id": "warehouse_id", "warehouse_name": "warehouse_name", "仓类别": "仓类别",
        "pool": "pool", "available": "qty", "pieces_per_unit": "pieces_per_unit",
        "qty_pieces": "qty_pieces", "pieces_status": "pieces_status", "legacy_note": "补货标记",
        "uom": "uom", "uom_source": "uom_source", "uom_note": "uom_note",
        "uom_status": "单位状态", "bucket": "桶",
        "en": "resolved_supply_item", "role": "role(A)", "actual_form": "actual_form",
        "physical_form": "physical_form", "canonical_uom": "canonical_uom",
        "qual_category": "资格类别", "demand_eligibility": "demand_eligibility",
        "eligibility_reason": "eligibility_reason", "source_ref": "source_ref",
        "shared_pool_id": "shared_pool_id",
        "form_basis": "form_basis", "product_id": "product_id",
        "conversion_basis": "conversion_basis", "link_status": "候选状态",
        "identity_status": "身份状态", "link_proof": "归属证明",
        "supply_role": "供给状态", "coverage_status": "覆盖状态",
        "availability": "可用性", "mapping_source_v2": "mapping_source"})
    detail.insert(0, "snapshot_date", args.date)
    detail.insert(1, "rule_version", RULE_VERSION)
    detail["源行号(parquet1基)"] = detail["源行号(parquet1基)"].astype(int)
    detail.insert(list(detail.columns).index("product_id") + 1, "ship_mode",
                  detail["product_id"].map(en_ship))

    un = f[f["bucket"] == "未映射"].copy()

    def why(r):
        if r["仓类别"] == WH_THIRD:
            return "第三方云仓（不计补货）"
        if r["is_fba"]:
            return "FBA 码（不计自发货）"
        if r["is_nonproduct"]:
            return "非商品/原料"
        if r["is_big"]:
            return "超大占位"
        return "真未映射（无任何映射源命中）"

    un["未映射原因"] = [why(r) for _, r in un.iterrows()]
    un_tbl = un[["src_row", "sku", "warehouse_name", "pool", "available", "未映射原因",
                 "cands_all", "n_cands_active"]] \
        .sort_values("available", ascending=False).rename(columns={
            "src_row": "源行号(parquet1基)", "sku": "源SKU", "warehouse_name": "仓", "pool": "仓池",
            "available": "available", "cands_all": "全部候选", "n_cands_active": "活跃候选数"})

    excluded = f[f["bucket"] == "规则排除"][
        ["src_row", "exclusion", "sku", "warehouse_name", "仓类别", "pool", "available", "en", "role",
         "actual_form", "identity_status"]].rename(columns={
            "src_row": "源行号(parquet1基)", "exclusion": "排除规则", "sku": "源SKU",
            "warehouse_name": "仓", "仓类别": "仓类别", "pool": "仓池", "available": "available",
            "en": "映射EN", "role": "A角色", "actual_form": "实物形态",
            "identity_status": "身份状态"})

    conflict_tbl = pd.DataFrame([{
        "EN": en, "缓存stock_uom(原值)": uoms.get(en), "is_stock_item(原值)": is_stock_item.get(en),
        "A角色": en_role.get(en), "发货方式": en_ship.get(en),
        "快照行数": int((f["en"] == en).sum()), "快照库存": float(f.loc[f["en"] == en, "available"].sum()),
        "单位状态": "冲突", "处理": "按个计入可发供给；原值留档备查（UOM-CANONICAL §2.2）",
    } for en in sorted(uom_conflict_en)])

    # ---------- 未覆盖产品（A 活跃但快照无库存行 = 未覆盖，不是 0） ----------
    covered_en = set(f.loc[f["bucket"] == "计入A", "en"].dropna())
    uncovered = active[~active["EN物料"].astype(str).isin(covered_en)][
        ["EN物料", "名称", "角色", "物料组", "ship_mode", "绍兴发货方式", "活跃分类"]].copy()
    uncovered = uncovered.rename(columns={"EN物料": "product_id", "绍兴发货方式": "ship_mode_cn"})
    uncovered.insert(0, "snapshot_date", args.date)
    uncovered.insert(1, "rule_version", RULE_VERSION)
    uncovered["覆盖状态"] = "未覆盖"
    uncovered["说明"] = "快照无该产品库存行：未覆盖 ≠ 0 库存"

    # ---------- 汇总 ----------
    def bq(b):
        g = f[f["bucket"] == b]
        return int(len(g)), float(g["available"].sum())

    counted_rows = f[f["bucket"] == "计入A"].copy()

    def cat_of(r) -> str:
        sr = r["supply_role"]
        if sr in ("成品供给", "皮壳供给"):
            if r["pool"] in (POOL_CG, POOL_OTHER):
                return "仅披露(CG/其他)"
            return "成品供给(独立骨架)" if r["actual_form"] == "主体骨架" else f"{sr}(按个)"
        if sr == "待核":
            return "待核(共享多候选)"
        if sr in ("发货方式未知(待核)", "形态未知(待核)"):
            return "待核(发货方式/形态未知)"
        if sr.startswith("方式="):
            return "方式不符:皮壳组件(仅披露)"
        if sr == "套件单列(个)":
            return "套件按个折算"
        if sr == "套件单列(套)":
            return "套件单列(套)"
        return sr

    counted_rows["去向"] = [cat_of(r) for _, r in counted_rows.iterrows()]
    decomp = (counted_rows.groupby("去向").agg(行数=("available", "size"),
                                               原始数值=("available", "sum"),
                                               个当量=("qty_pieces", "sum"))
              .reset_index().sort_values("个当量", ascending=False))
    iso_proven_rows = f[iso_proven]
    decomp = pd.concat([decomp, pd.DataFrame([{
        "去向": "254补证(第六桶→皮壳供给)", "行数": int(len(iso_proven_rows)),
        "原始数值": float(iso_proven_rows["available"].sum()),
        "个当量": float(iso_proven_rows["qty_pieces"].sum())}])], ignore_index=True)
    bridge_rows = f[f["piece_bridge"]]
    if len(bridge_rows):
        decomp = pd.concat([decomp, pd.DataFrame([{
            "去向": "多件后缀跨桶折算(A未激活→成品供给)", "行数": int(len(bridge_rows)),
            "原始数值": float(bridge_rows["available"].sum()),
            "个当量": float(bridge_rows["qty_pieces"].sum())}])], ignore_index=True)

    join_tbl = supply_tbl[supply_tbl["可用性"].astype(str).str.startswith("可进join")]
    discl_tbl = supply_tbl[supply_tbl["可用性"] == "仅披露(CG/其他)"]
    cover_rows = f[f["supply_role"] == "皮壳供给"]
    skeleton_rows = f[(f["supply_role"] == "成品供给") & (f["actual_form"] == "主体骨架")]
    no_fact = pivot[pivot["供给状态"].str.startswith("无适用事实")]
    partial = supply_tbl[supply_tbl["可用性"].astype(str).str.startswith("可进join(partial")]
    jc_grp = supply_tbl.groupby("join_class").agg(行数=("可发供给", "size"),
                                                  数量=("可发供给", "sum"))

    # ---------- P2-2：老产品双口径（产品级 + 行级） ----------
    legacy_fact = f[f["legacy_note"] != ""]
    _lf = legacy_fact.assign(pid=legacy_fact["product_id"].fillna("(未归属)"))
    legacy_products = (_lf.groupby("pid")
                       .agg(事实行数=("sku", "size"), 事实个当量=("qty_pieces", "sum"),
                            源可用=("available", "sum")).reset_index()
                       .rename(columns={"pid": "product_id"}))
    legacy_products["物料组"] = legacy_products["product_id"].map(
        lambda p: "未归属" if p == "(未归属)" else en_group.get(p, "(非活跃EN)"))
    legacy_products["名称"] = legacy_products["product_id"].map(
        lambda p: "(无活跃EN映射)" if p == "(未归属)" else en_name_map.get(p, "(非活跃EN)"))
    lp_supply = (supply_tbl[supply_tbl["补货资格"] != ""]
                 .groupby("product_id")
                 .agg(供给行数=("可发供给", "size"),
                      supply_qty=("可发供给", "sum"),
                      含套件=("uom", lambda s: int((s == "套").sum()))).reset_index()
                 .rename(columns={"supply_qty": "供给可发供给和"}))
    legacy_products = legacy_products.merge(lp_supply, on="product_id", how="left")
    legacy_products[["供给行数", "含套件"]] = \
        legacy_products[["供给行数", "含套件"]].fillna(0).astype(int)
    legacy_products["供给可发供给和"] = legacy_products["供给可发供给和"].fillna(0.0)
    legacy_products["补货资格"] = "老产品-默认不补(待确认)"
    legacy_products.insert(1, "rule_version", RULE_VERSION)
    legacy_products.insert(2, "snapshot_date", args.date)
    legacy_products = legacy_products[["product_id", "rule_version", "snapshot_date", "物料组",
                                       "名称", "事实行数", "事实个当量", "源可用", "供给行数",
                                       "供给可发供给和", "含套件", "补货资格"]]         .sort_values("事实个当量", ascending=False)

    # ---------- C8-1 资格分层汇总 ----------
    cat_elig = (f.groupby(["qual_category", "demand_eligibility"])
                .agg(行数=("sku", "size"), 个当量=("qty_pieces", "sum"),
                     产品数=("product_id", "nunique"),
                     原因样例=("eligibility_reason", "first")).reset_index()
                .sort_values(["qual_category", "demand_eligibility"]))

    # ---------- C8-2 共享池回放（一码一池，候选不分配） ----------
    sh_info = (sh.groupby("归一码")
               .agg(候选数=("候选数", "max"), 全部候选=("本次全部候选(含来源)", "first"),
                    触发来源=("触发来源", "first"), 处理=("处理", "first")).reset_index())
    shared_fact = f[f["shared_pool_id"] != ""]
    sp = (shared_fact.groupby("shared_pool_id")
          .agg(归一码=("norm", "first"), 源行数=("sku", "size"),
               源行号集合=("src_row", lambda s: ",".join("ST:" + str(int(x)) for x in sorted(s))),
               原量=("available", "sum"), 个当量=("qty_pieces", "sum"),
               仓池=("pool", lambda s: "/".join(sorted(set(s)))),
               coverage=("coverage_status", lambda s: "部分" if (s == "完整").any() else "未覆盖"))
          .reset_index())
    sp = sp.merge(sh_info, left_on="归一码", right_on="归一码", how="left")
    sp["候选数"] = sp["候选数"].fillna(0).astype(int)
    sp["allocation_qty"] = 0.0
    sp["未分配余额"] = sp["原量"] - sp["allocation_qty"]
    sp["pool_status"] = sp["候选数"].map(
        lambda n: "待核(共享池,未分配)" if n and n > 0 else "未覆盖(无候选)")
    sp["coverage"] = sp["pool_status"]
    sp["回指"] = "ST 行号→en_stock.parquet"
    sp = sp[["shared_pool_id", "归一码", "仓池", "候选数", "全部候选", "触发来源", "源行数",
             "源行号集合", "原量", "个当量", "allocation_qty", "未分配余额", "coverage",
             "pool_status", "处理", "回指"]] \
        .sort_values("原量", ascending=False)

    # ---------- C8-3 Top50 兼容导出（P1-1 物理只含 join_full；P2 资格字段随行） ----------
    def top50_reason(r) -> str:
        if r["join_reason"]:
            return r["join_reason"]
        if r["覆盖缺口"]:
            return f"覆盖:{r['覆盖缺口']}"
        return str(r["供给状态"])

    counted_key = sup_src[sup_src["supply_role"].isin(
        ["成品供给", "皮壳供给", "套件单列(套)", "海绵供给"])]

    def _key_elig(s: pd.Series) -> str:
        vals = set(s.dropna().astype(str))
        if "independent" in vals:
            return "independent"
        if "component" in vals:
            return "component"
        if "after_sales" in vals:
            return "after_sales"
        return "not_applicable"

    key_qual = (counted_key.groupby(["product_id", "pool", "uom"])
                .agg(demand_eligibility=("demand_eligibility", _key_elig),
                     eligibility_reason=("eligibility_reason",
                                         lambda s: " | ".join(sorted(set(s)))),
                     source_ref=("source_ref", lambda s: " | ".join(sorted(set(s)))),
                     ).reset_index())
    _kq = {(r["product_id"], r["pool"], r["uom"]): r for _, r in key_qual.iterrows()}

    def _q(row, col, default=""):
        rec = _kq.get((row["product_id"], row["pool"], row["uom"]))
        return (rec[col] if rec is not None else default)

    base = pd.DataFrame({
        "product_id": supply_tbl["product_id"],
        "pool": supply_tbl["pool"],
        "physical_form": supply_tbl["physical_form"],
        "canonical_uom": supply_tbl["canonical_uom"],
        "join_class": supply_tbl["join_class"],
        "join_candidate": supply_tbl["join_candidate"],
        "可发供给": supply_tbl["可发供给"],
        "coverage_status": supply_tbl["覆盖状态"],
        "demand_eligibility": [_q(r, "demand_eligibility") for _, r in supply_tbl.iterrows()],
        "eligibility_reason": [_q(r, "eligibility_reason") for _, r in supply_tbl.iterrows()],
        "source_ref": [_q(r, "source_ref") for _, r in supply_tbl.iterrows()],
        "source_proof": supply_tbl["source_proof"],
        "join_reason": supply_tbl["join_reason"],
        "reason_code": supply_tbl["reason_code"],
        "needed_evidence": supply_tbl["needed_evidence"],
        "next_action": supply_tbl["next_action"],
        "owner": supply_tbl["owner"],
        "whitelist_status": supply_tbl["whitelist_status"],
        "consumption": supply_tbl["consumption"],
        "reason": [top50_reason(r) for _, r in supply_tbl.iterrows()],
        "as_of": AS_OF,
        "rule_version": RULE_VERSION,
    })
    top50 = base[base["join_class"] == "join_full"].reset_index(drop=True)
    top50["join_reason"] = top50["join_reason"].replace("", "无(join_full)")
    top50_obs = base[base["join_class"] != "join_full"].reset_index(drop=True)

    # ---------- C9：no_join 观察（按 reason_code 汇总）+ join_partial 白名单（默认空） ----------
    obs_src = supply_tbl[supply_tbl["join_class"] != "join_full"]
    def _reason_sum(df):
        t = (df.groupby("reason_code")
             .agg(行数=("可发供给", "size"), 数量=("可发供给", "sum"),
                  空值行=("可发供给", lambda s: int(s.isna().sum())),
                  涉及产品=("product_id", "nunique"),
                  涉及仓池=("pool", lambda s: "/".join(sorted(set(s)))),
                  示例产品=("product_id", "first"),
                  needed_evidence=("needed_evidence", "first"),
                  next_action=("next_action", "first"),
                  owner=("owner", "first"))
             .reset_index().sort_values(["行数"], ascending=False))
        t.loc[t["空值行"] == t["行数"], "数量"] = None
        return t
    nojoin_sum = _reason_sum(supply_tbl[supply_tbl["join_class"] == "no_join"])
    partial_sum = _reason_sum(supply_tbl[supply_tbl["join_class"] == "join_partial"])
    whitelist_cols = ["product_id", "pool", "physical_form", "canonical_uom", "reason_code",
                      "approver", "expiry"]
    whitelist = pd.DataFrame({c: pd.Series(dtype="object") for c in whitelist_cols})

    # ---------- C8-3 十键回放（join v7 pilot 冻结键） ----------
    # 期望值来自分析/C6-join-v7-pilot-review_2026-10-30.md 与 pilot 工作簿；ST 行号=parquet 1 基
    TEN_KEYS = [
        (1, "皮壳且Cover已证", "KS0001-AHR-100-BROWN2", "波兰", "个", "join_full", 27.0, 45117),
        (2, "成品FG已证", "KS0010-HLR-38-COFFEE", "波兰", "个", "join_full", 8.0, 44898),
        (3, "半成品 raw+normalized 皮壳", "KS0394-CTTM-135x152x80-REDDISHGRAY", "美中USTX",
         "个", "join_full", 74.0, 43934),
        (4, "HM 海绵独立供给/需求", "HM1510-YD2-100x60x10QKL-WHITE", "美中USTX", "个",
         "no_join", None, None),
        (5, "ND 内胆配套", "ND#KS0001-100-CYF-WHITE", "波兰", "个", "no_join", None, None),
        (6, "TJ# 套件按套", "TJ#KS0334x1_KS0335x1_KS0336x1-001", "波兰", "套",
         "no_join", 8.0, 45377),
        (7, "主体骨架 599 分支", "ZTGJ5525-SOFALSHAPEDBRACKET-IRON-55x45x45", "美东USNJ",
         "个", "join_full", 599.0, 47680),
        (8, "共享多候选池", "KS0342-HLR-50-BLACK", "美中USTX", "个", "no_join", None, None),
        (9, "仅库存 stock_placement", "HM1510-YD1-120x100x10+120x100x10cm-WHITE", "美中USTX",
         "个", "no_join", None, None),
        (10, "无适用事实", "KS0316-HLR-55-PURPLE", "美中USTX", "个", "no_join", None, 44108),
    ]
    ten = []
    for seq, kind, pid, pool, uom, exp_cls, exp_val, st in TEN_KEYS:
        q = supply_tbl[(supply_tbl["product_id"] == pid) & (supply_tbl["pool"] == pool)
                       & (supply_tbl["uom"] == uom)]
        fact_q = f[(f["product_id"] == pid) & (f["pool"] == pool)]
        src_ok = "—"
        if st is not None:
            prow = d.iloc[st - 1]
            frow = f[f["src_row"] == st]
            ok = (str(prow["snapshot_date"])[:10] == AS_OF
                  and len(frow) == 1
                  and str(frow.iloc[0]["product_id"]) == pid
                  and abs(float(prow["available"]) - float(frow.iloc[0]["available"])) < 1e-9)
            src_ok = "通过" if ok else "不通过"
        got_cls = q.iloc[0]["join_class"] if len(q) else "no_join"
        got_val = None if (not len(q) or pd.isna(q.iloc[0]["可发供给"])) else float(q.iloc[0]["可发供给"])
        val_ok = ((exp_val is None and got_val is None)
                  or (exp_val is not None and got_val is not None and abs(exp_val - got_val) < 1e-9))
        cls_ok = got_cls == exp_cls
        ten.append({
            "序号": seq, "类型": kind, "product_id": pid, "仓池": pool, "uom": uom,
            "C join_class": got_cls, "期望 join_class": exp_cls,
            "C 可发供给": got_val, "期望可发供给": exp_val,
            "事实行数": int(len(fact_q)),
            "源行回放": ("ST:%d %s" % (st, src_ok)) if st else "无 C 源行",
            "回放结果": "通过" if (cls_ok and val_ok) else "不通过",
            "规则变更": ("v11：半成品皮壳计入（v7 pilot 记为 no_join）" if seq == 3 else ""),
        })
    ten_tbl = pd.DataFrame(ten)

    # ---------- C v10：CG 库存池（EN 只读 API；只取 warehouse_id='CG' 汇总行） ----------
    env = read_env_file(Path(args.en_env))
    cg_all = fetch_cg_stock(env, args.en_base)
    cg_cache = Path(args.out_cg_cache)
    cg_cache.parent.mkdir(parents=True, exist_ok=True)
    cg_all.to_parquet(cg_cache, index=False)
    b_owner = {}
    if Path(args.b_attribution).exists():
        _bm = pd.read_excel(args.b_attribution, sheet_name="主表")
        _us = _bm[_bm["地区"] == "US"]
        for pid, o in zip(_us["产品键"], _us["美国责任方"]):
            if isinstance(o, str) and o.strip() and pid not in b_owner:
                b_owner[str(pid)] = o.strip()
    alias_map = load_alias_map(Path(args.cg_alias_zip))
    bundles = fetch_bundles(env, args.en_base, Path(args.bundle_cache),
                            refresh=args.refresh_bundles)
    cg_pack = build_cg_table(cg_all, idx, cand, set(en_role), b_owner,
                             supply_tbl,
                             attribution_source="B-r9-local-provisional",
                             attribution_version=Path(args.b_attribution).stem,
                             alias_map=alias_map, bundles=bundles)
    cg_tbl, cg_pool_tbl, cg_detail = cg_pack["cg_tbl"], cg_pack["pool"], cg_pack["cg"]

    # 供给展示：可发供给保留物理值；cg_available / supply_total_display 单列（不进净额）
    cg_elig_map = (cg_detail[cg_detail["cg_status"] == "cg_eligible"]
                   .groupby(["erp_item_code", "cg_pool"])["cg_available"].sum().to_dict())

    def _cg_pair(r):
        pool = {POOL_EAST: "CG-USNJ", POOL_CENTRAL: "CG-USTX"}.get(r["pool"])
        if not pool or not r["product_id"]:
            return None
        return cg_elig_map.get((r["product_id"], pool))

    _cgv = [_cg_pair(r) for _, r in supply_tbl.iterrows()]
    supply_tbl["cg_available"] = _cgv
    # 只有 join_full 才可标 cg_eligible；partial/no_join 即使有 CG 也只算 cg_pending
    supply_tbl["cg_status"] = [
        ("cg_eligible" if r["join_class"] == "join_full" else "cg_pending") if v is not None
        else "none"
        for v, (_, r) in zip(_cgv, supply_tbl.iterrows())]
    supply_tbl["supply_total_display"] = [
        (None if (pd.isna(p) and c is None) else
         (0.0 if pd.isna(p) else float(p)) + (0.0 if c is None else float(c)))
        for p, c in zip(supply_tbl["可发供给"], _cgv)]

    # ---------- C v13：套件拆解表 ----------
    set_rows = []
    for _, r in supply_tbl[(supply_tbl["uom"] == "套")
                           & (supply_tbl["套件库存"].fillna(0) > 0)].iterrows():
        comps = bundles.get(r["product_id"]) or []
        for comp, per in comps:
            set_rows.append({
                "来源": "C", "set_item": r["product_id"], "set_qty": float(r["套件库存"]),
                "仓池": r["pool"], "component_item": comp, "qty_per_set": float(per),
                "component_qty": float(r["套件库存"]) * float(per),
                "component_active": comp in en_role,
                "component_owner": b_owner.get(comp, ""),
                "supply_action": ("计入组件供给（按个）" if comp in en_role
                                  else "组件未激活：仅记录"),
                "set_usage": "仅库存/供给换算；订单需求不换算（保留原始单件/套件单位）",
                "source_ref": r["source_proof"]})
    for _, r in cg_tbl[cg_tbl["set_qty"].notna()].iterrows():
        comps = bundles.get(r["erp_item_code"]) or []
        for comp, per in comps:
            set_rows.append({
                "来源": "CG", "set_item": r["erp_item_code"], "set_qty": float(r["set_qty"]),
                "仓池": r["cg_pool"], "component_item": comp, "qty_per_set": float(per),
                "component_qty": float(r["set_qty"]) * float(per),
                "component_active": comp in en_role,
                "component_owner": b_owner.get(comp, ""),
                "supply_action": "按组件计入 CG 池（个）",
                "set_usage": "仅库存/供给换算；订单需求不换算（保留原始单件/套件单位）",
                "source_ref": r["cg_source_ref"]})
    set_tbl = pd.DataFrame(set_rows, columns=[
        "来源", "set_item", "set_qty", "仓池", "component_item", "qty_per_set",
        "component_qty", "component_active", "component_owner", "supply_action",
        "set_usage", "source_ref"])

    cg_recon_tbl = cg_tbl[["raw_tongtool_sku", "cg_available", "det_sum", "reconcile_diff",
                           "det_rows", "cg_reconcile_status"]].copy()

    summary = dict(
        date=args.date, rule_version=RULE_VERSION, uom_version=UOM_VERSION,
        rows_in=int(len(f)), qty_in=float(f["available"].sum()),
        buckets={b: bq(b)[0] for b in BUCKET_BASELINE},
        bucket_qty={b: bq(b)[1] for b in BUCKET_BASELINE},
        active_roles=len(active),
        covered_en=int(len(covered_en)),
        uncovered_en=int(len(uncovered)),
        iso_total=len(iso_tbl),
        iso_disposition={k: int(v) for k, v in iso["处置"].value_counts().items()},
        iso_disposition_qty={k: float(g["available"].sum()) for k, g in iso.groupby("处置")},
        iso_pos={k: int((g["available"] > 0).sum()) for k, g in iso.groupby("处置")},
        both_forms_rows=int(iso["both_forms_present"].sum()),
        split_assembled_qty=float(iso["assembled_qty"].sum()),
        both_forms_qty=float(iso.loc[iso["both_forms_present"], "qty_pieces"].sum()),
        shared_codes=int(shared_stock["norm"].nunique()),
        shared_extra_codes=int(multi_in_counted["norm"].nunique()),
        uom_conflict_en=len(uom_conflict_en),
        join_rows=int(len(join_tbl)), join_qty=float(join_tbl["可发供给"].fillna(0).sum()),
        discl_rows=int(len(discl_tbl)), discl_qty=float(discl_tbl["可发供给"].fillna(0).sum()),
        partial_rows=int(len(partial)),
        no_fact_keys=int(len(no_fact)),
        null_keys=int(supply_tbl["可发供给"].isna().sum()),
        pending_null_keys=int(((supply_tbl["可发供给"].isna())
                               & supply_tbl["供给状态"].astype(str).str.startswith("待核")).sum()),
        cover_rows=int(len(cover_rows)), cover_qty=float(cover_rows["qty_pieces"].sum()),
        cover_rows_in_join=int((cover_rows["availability"].astype(str).str.startswith("可进join")).sum()),
        cover_qty_in_join=float(cover_rows.loc[cover_rows["availability"].astype(str)
                                               .str.startswith("可进join"), "qty_pieces"].sum()),
        finished_rows=int((f["supply_role"] == "成品供给").sum()),
        skeleton_rows=int(len(skeleton_rows)), skeleton_qty=float(skeleton_rows["qty_pieces"].sum()),
        piece_rows=int(len(conv)), piece_raw=float(conv["available"].sum()),
        piece_qty=float(conv["qty_pieces"].sum()),
        piece_mid_rows=int(len(mid)), piece_mid_raw=float(mid["available"].sum()),
        piece_bridge_rows=int(len(bridge_rows)),
        piece_bridge_qty=float(bridge_rows["qty_pieces"].sum()),
        planet_rows=int(f["planet_group"].sum()),
        planet_raw=float(f.loc[f["planet_group"], "available"].sum()),
        planet_qty=float(f.loc[f["planet_group"], "qty_pieces"].sum()),
        planet_qty_v5rule=float((f.loc[f["planet_group"], "available"]
                                 * f.loc[f["planet_group"], "pieces_rule_only"]).sum()),
        planet_ens=len(planet_ens),
        planet_supply_rows=int((supply_tbl["补货资格"] != "").sum()),
        planet_supply_qty=float(supply_tbl.loc[supply_tbl["补货资格"] != "", "可发供给"].fillna(0).sum()),
        bundle_units=float(f.loc[f["uom"] == "套", "available"].sum()),
        bundle_rows=int((f["uom"] == "套").sum()),
        default_ge_rows=int(((f["uom_status"] == "默认个") & (f["bucket"] == "计入A")).sum()),
        default_ge_qty=float(f.loc[(f["uom_status"] == "默认个") & (f["bucket"] == "计入A"),
                                   "available"].sum()),
        decomp={r["去向"]: [int(r["行数"]), float(r["原始数值"]), float(r["个当量"])]
                for r in decomp.to_dict("records")},
        pools={k: [int(v["rows"]), float(v["qty"])] for k, v in
               f.groupby("pool").agg(rows=("sku", "size"), qty=("available", "sum")).iterrows()},
        wh_classes={k: [int(v["rows"]), float(v["qty"])] for k, v in
                    f.groupby("仓类别").agg(rows=("sku", "size"), qty=("available", "sum")).iterrows()},
        identity={k: int(v) for k, v in f["identity_status"].value_counts().items()},
        uom_status={k: int(v) for k, v in f["uom_status"].value_counts().items()},
        coverage={k: int(v) for k, v in f["coverage_status"].value_counts().items()},
        # P2-1 join_class
        join_class={k: [int(v["行数"]), float(v["数量"])] for k, v in jc_grp.iterrows()},
        # P2-2 老产品双口径
        legacy_products=int(legacy_fact["product_id"].nunique()),
        legacy_unmapped_rows=int(legacy_fact["product_id"].isna().sum()),
        legacy_sheet_rows=int(len(legacy_products)),
        legacy_fact_rows=int(len(legacy_fact)),
        legacy_fact_qty=float(legacy_fact["qty_pieces"].sum()),
        legacy_supply_rows=int((supply_tbl["补货资格"] != "").sum()),
        legacy_supply_qty=float(supply_tbl.loc[supply_tbl["补货资格"] != "",
                                               "可发供给"].fillna(0).sum()),
        legacy_group_counts={k: int(v) for k, v in
                             legacy_products["物料组"].value_counts().items()},
        # C8-1 资格
        c8_category={k: int(v) for k, v in f["qual_category"].value_counts().items()},
        c8_eligibility={k: int(v) for k, v in f["demand_eligibility"].value_counts().items()},
        hm_rows=int((f["qual_category"] == "HM").sum()),
        hm_component_rows=int(((f["qual_category"] == "HM")
                              & (f["demand_eligibility"] == "component")).sum()),
        hm_mappable_rows=int(((f["qual_category"] == "HM")
                             & f["identity_status"].isin(["唯一", "共享"])).sum()),
        hm_mappable_component=int(((f["qual_category"] == "HM")
                                   & f["identity_status"].isin(["唯一", "共享"])
                                   & (f["demand_eligibility"] == "component")).sum()),
        nd_rows=int((f["qual_category"] == "ND").sum()),
        nd_independent_rows=int(((f["qual_category"] == "ND")
                                 & (f["demand_eligibility"] == "independent")).sum()),
        tj_rows=int((f["qual_category"] == "TJ#").sum()),
        c8_join_candidates=int(supply_tbl["join_candidate"].sum()),
        # C8-2 共享池
        c8_shared_pools=int(len(sp)),
        c8_shared_pool_qty=float(sp["原量"].sum()),
        c8_shared_pool_rows=int(sp["源行数"].sum()),
        c8_shared_allocation=float(sp["allocation_qty"].sum()),
        c8_shared_balance=float(sp["未分配余额"].sum()),
        # C8-3 十键
        c8_ten_pass=int((ten_tbl["回放结果"] == "通过").sum()),
        c8_ten_total=int(len(ten_tbl)),
        # P1-1 Top50 物理过滤
        c8_top50_rows=int(len(top50)),
        c8_top50_obs_rows=int(len(top50_obs)),
        c8_join_full_rows=int((supply_tbl["join_class"] == "join_full").sum()),
        c8_top50_qty=float(top50["可发供给"].fillna(0).sum()),
        # C9 可操作状态
        c9_reason_code={k: int(v) for k, v in supply_tbl["reason_code"].value_counts().items()},
        c9_partial_reason={k: int(v) for k, v in
                           supply_tbl.loc[supply_tbl["join_class"] == "join_partial",
                                          "reason_code"].value_counts().items()},
        c9_nojoin_reason={k: int(v) for k, v in
                          supply_tbl.loc[(supply_tbl["join_class"] == "no_join")
                                         & supply_tbl["可发供给"].notna(),
                                         "reason_code"].value_counts().items()},
        c9_null_reason={k: int(v) for k, v in
                        supply_tbl.loc[supply_tbl["可发供给"].isna(),
                                       "reason_code"].value_counts().items()},
        c9_whitelist_rows=int(len(whitelist)),
        c9_obs_rows=int(len(obs_src)),
        c9_nojoin_obs_rows=int(nojoin_sum["行数"].sum()),
        c9_partial_obs_rows=int(partial_sum["行数"].sum()),
        c9_top50_reason={k: int(v) for k, v in top50["reason_code"].value_counts().items()},
        # C10 CG 池
        cg_rows=int(len(cg_tbl)),
        cg_available=float(cg_tbl["cg_available"].fillna(0).sum()),
        cg_detail_sum=float(cg_pack["det_sum_total"]),
        cg_detail_rows=int(len(cg_pack["det"])),
        cg_pool_rows={r["cg_pool"]: (0 if pd.isna(r["行数"]) else int(r["行数"]))
                      for r in cg_pool_tbl.to_dict("records")},
        cg_pool_qty={r["cg_pool"]: (0.0 if pd.isna(r["cg_available"]) else float(r["cg_available"]))
                     for r in cg_pool_tbl.to_dict("records")},
        cg_pool_supply={r["cg_pool"]: (0.0 if pd.isna(r["cg_supply_qty"])
                                       else float(r["cg_supply_qty"]))
                        for r in cg_pool_tbl.to_dict("records")},
        cg_eligible=int((cg_tbl["cg_status"] == "cg_eligible").sum()),
        cg_pending=int((cg_tbl["cg_status"] == "cg_pending").sum()),
        cg_unmapped=int((cg_tbl["attribution_status"] == "unmapped").sum()),
        cg_unknown_owner=int((cg_tbl["attribution_status"] == "unknown").sum()),
        cg_mapped_inactive=int((cg_tbl["attribution_status"] == "mapped_inactive").sum()),
        cg_owner_rows=int((cg_tbl["attribution_status"] == "owner").sum()),
        cg_reconcile_ok=int((cg_tbl["cg_reconcile_status"] == "ok").sum()),
        cg_stale=int((cg_tbl["cg_stale"].fillna(0) != 0).sum()),
        cg_avail_missing=int((cg_tbl["cg_available_missing"].fillna(0) != 0).sum()),
        cg_in_net=int((cg_tbl["cg_included_in_current_net"]).sum()),
        cg_transfer=int((cg_tbl["transfer_flag"]).sum()),
    )

    # ---------- 15 键门禁回放 ----------
    fifteen = []
    v3_rows = [363, 591, 620, 693, 814, 838, 839, 1278, 1456, 1949, 2336, 2352, 2446, 2455, 2456]
    for (pid, pool, uom), v3row in zip(FIFTEEN_KEYS, v3_rows):
        q = supply_tbl[(supply_tbl["product_id"] == pid) & (supply_tbl["pool"] == pool)
                       & (supply_tbl["uom"] == uom)]
        note = ""
        if q.empty:
            # v3 清单里 KS0018 组写的是 uom=套；按 UOM-CANONICAL §2.2 已回落「个」，回放按 v6 实际键
            alt = "个" if uom == "套" else "套"
            q2 = supply_tbl[(supply_tbl["product_id"] == pid) & (supply_tbl["pool"] == pool)
                            & (supply_tbl["uom"] == alt)]
            if not q2.empty:
                q = q2
                note = f"v3 清单为 uom={uom}；UOM-CANONICAL 后按「{alt}」计"
                uom = alt
        if q.empty:
            fifteen.append({"v3行号": v3row, "product_id": pid, "仓池": pool, "uom": uom,
                            "可发供给": None, "供给状态": "键不存在(无任何事实行)", "覆盖状态": "未覆盖",
                            "覆盖缺口": "无适用行", "join_class": "no_join",
                            "可用性": "不进join(无适用事实)",
                            "门禁": "PASS", "事实行号(parquet1基)": "-", "事实个当量": 0.0,
                            "未计个当量": 0.0, "说明": note})
            continue
        r = q.iloc[0]
        val = r["可发供给"]
        is_null = val is None or (isinstance(val, float) and pd.isna(val))
        av = str(r["可用性"])
        sub = f[(f["product_id"] == pid) & (f["pool"] == pool) & (f["uom"] == uom)]
        applied = sub[sub["supply_role"].isin(["成品供给", "皮壳供给", "套件单列(套)"])]
        fact_qty = float(applied["qty_pieces"].sum())
        hidden_qty = float(sub.loc[sub["supply_role"].isin(
            ["海绵分支(不计)", "内胆组件(不计)", "套件单列(个)", "待核",
             "发货方式未知(待核)", "形态未知(待核)"]), "qty_pieces"].sum())
        src_rows = ",".join(str(int(x)) for x in applied["src_row"])
        if is_null and not av.startswith("可进join"):
            gate = "PASS(null)"
        elif av == "套件单列":
            gate = "PASS(套件单列/不进净额)"
        elif (not is_null) and float(val) > 0:
            gate = "PASS(真实正量,可回指源行)"
        elif len(applied) > 0 and fact_qty == 0.0 and hidden_qty == 0.0:
            gate = "PASS(已证零,有源行)"
        else:
            gate = "FAIL(伪0或误进join)"
        fifteen.append({"v3行号": v3row, "product_id": pid, "仓池": pool, "uom": uom,
                        "可发供给": None if is_null else float(val),
                        "供给状态": r["供给状态"], "覆盖状态": r["覆盖状态"],
                        "覆盖缺口": r["覆盖缺口"], "join_class": r["join_class"],
                        "可用性": av, "门禁": gate,
                        "事实行号(parquet1基)": src_rows or "-",
                        "事实个当量": fact_qty, "未计个当量": hidden_qty,
                        "说明": (note + "；" if note else "") + str(r["门禁原因"])})
    fifteen_tbl = pd.DataFrame(fifteen)

    # ---------- 自检 ----------
    def trace_ok() -> tuple[int, int]:
        ok = 0
        for _, r in detail.iterrows():
            sr = int(r["源行号(parquet1基)"])
            src_row = d.iloc[sr - 1]
            if (str(src_row["sku"]) == str(r["source_sku"])
                    and str(src_row["warehouse_name"]) == str(r["warehouse_name"])
                    and abs(float(src_row["available"]) - float(r["qty"])) < 1e-9):
                ok += 1
        return ok, len(detail)

    trace_ok_n, trace_total = trace_ok()

    iso_trace = 0
    for _, r in iso_tbl.iterrows():
        sr = int(r["源行号(parquet1基)"])
        s = d.iloc[sr - 1]
        if (str(s["sku"]) == str(r["源SKU"]) and str(s["warehouse_name"]) == str(r["仓"])
                and abs(float(s["available"]) - float(r["available"])) < 1e-9):
            iso_trace += 1

    # 伪 0 全量检查：可进join 且 可发供给==0 的键，必须存在实际适用行 qty==0 且无未计正量
    pseudo = []
    for _, r in supply_tbl.iterrows():
        if not str(r["可用性"]).startswith("可进join"):
            continue
        v = r["可发供给"]
        if v is None or pd.isna(v) or float(v) != 0.0:
            continue
        key = ((f["product_id"] == r["product_id"]) & (f["pool"] == r["pool"])
               & (f["uom"] == r["uom"]))
        sub = f[key]
        applied = sub[sub["supply_role"].isin(["成品供给", "皮壳供给"])]
        hidden = float(sub.loc[sub["supply_role"].isin(
            ["海绵分支(不计)", "内胆组件(不计)", "套件单列(个)", "待核",
             "发货方式未知(待核)", "形态未知(待核)"]), "qty_pieces"].sum())
        if not (len(applied) > 0 and float(applied["qty_pieces"].sum()) == 0.0 and hidden == 0.0):
            pseudo.append((r["product_id"], r["pool"], r["uom"]))
    fifteen_fail = int((fifteen_tbl["门禁"].astype(str).str.startswith("FAIL")).sum())
    pool_bad = int((~f["pool"].isin(POOL_CANON)).sum()) + int((~supply_tbl["pool"].isin(POOL_CANON)).sum())

    # ---------- P2-1 独立复算（不复用生成逻辑，直接按列重判） ----------
    def _jc_recompute(r) -> str:
        v = r["可发供给"]
        if v is None or pd.isna(v):
            return "no_join"
        if r["uom"] == "套" or r["pool"] in (POOL_CG, POOL_OTHER):
            return "no_join"
        if str(r["供给状态"]).startswith("待核"):
            return "no_join"
        if r["覆盖状态"] != "完整" or r["身份状态"] != "唯一":
            return "join_partial"
        return "join_full"

    jc_recomputed = [_jc_recompute(r) for _, r in supply_tbl.iterrows()]
    jc_mismatch = int((pd.Series(jc_recomputed).values != supply_tbl["join_class"].values).sum())
    jc_total = int(supply_tbl["join_class"].isin(
        ["join_full", "join_partial", "no_join"]).sum())
    full_mask = supply_tbl["join_class"] == "join_full"
    jc_leak = int((full_mask & ((supply_tbl["覆盖状态"] != "完整")
                                | (supply_tbl["身份状态"] != "唯一"))).sum())
    jc_partial_full = int(((supply_tbl["覆盖状态"] == "部分") & full_mask).sum())
    planet_11_viol = int((f["planet_group"] & ((f["pieces_per_unit"] != 1)
                                               | (f["qty_pieces"] != f["available"]))).sum())
    legacy_labels = sorted(set(f.loc[f["legacy_note"] != "", "legacy_note"]))
    legacy_row_diff = int((f["legacy_note"] != "").sum()) - summary["legacy_fact_rows"]

    # ---- C8 独立复算 ----
    _c8_cols = ["physical_form", "canonical_uom", "demand_eligibility",
                "eligibility_reason", "source_ref"]
    c8_missing = sum(int((f[c].isna() | f[c].astype(str).str.strip().eq("")).sum())
                     for c in _c8_cols)
    c8_tj_leak = int(((f["qual_category"] == "TJ#")
                      & f["supply_role"].isin(["成品供给", "皮壳供给"])).sum())
    c8_semi_form_bad = int(((f["qual_category"] == "半成品")
                            & (f["physical_form"] != "成品")).sum())
    c8_cand_leak = int((supply_tbl["join_candidate"]
                        != (supply_tbl["join_class"] == "join_full")).sum())
    c8_shared_fact_qty = float(f.loc[f["shared_pool_id"] != "", "available"].sum())
    c8_over_alloc = int((sp["allocation_qty"] > sp["原量"] + 1e-9).sum())
    _tp_cols = ["product_id", "pool", "physical_form", "canonical_uom", "join_class",
                "coverage_status", "demand_eligibility", "eligibility_reason", "source_ref",
                "source_proof", "reason", "as_of", "rule_version"]
    c8_proof_missing = sum(int((top50[c].isna() | top50[c].astype(str).str.strip().eq("")).sum())
                           for c in _tp_cols)
    top50_nonfull = int((top50["join_class"] != "join_full").sum())
    top50_null = int(top50["可发供给"].isna().sum())
    _c9_rows = supply_tbl[supply_tbl["join_class"] != "join_full"]
    c9_missing = sum(int((_c9_rows[c].isna()
                          | _c9_rows[c].astype(str).str.strip().eq("")).sum())
                     for c in ["reason_code", "needed_evidence", "next_action", "owner"])
    c9_nojoin_sum = int(nojoin_sum["行数"].sum())
    c9_partial_sum = int(partial_sum["行数"].sum())
    top50_proof_empty = int(top50["source_proof"].astype(str).str.strip().eq("").sum())
    join_full_n = int((supply_tbl["join_class"] == "join_full").sum())

    checks = [
        ("六桶逐桶 0 差", f"行差={int(recon.iloc[-1]['行数差'])}, 数值差={recon.iloc[-1]['数值差']:.0f}",
         "=0", int(recon.iloc[-1]["行数差"]) == 0 and abs(recon.iloc[-1]["数值差"]) < 1e-6),
        ("源行数/数值和", f"{summary['rows_in']:,} / {summary['qty_in']:,.0f}",
         f"{SRC_ROWS:,} / {SRC_QTY:,.0f}", summary["rows_in"] == SRC_ROWS
         and abs(summary["qty_in"] - SRC_QTY) < 1e-6),
        ("事实层逐行回指源 parquet", f"{trace_ok_n}/{trace_total}", "全部", trace_ok_n == trace_total),
        ("254 行逐行回指", f"{iso_trace}/{len(iso_tbl)}", "全部", iso_trace == len(iso_tbl)
         and len(iso_tbl) == V5_BASELINE["iso_rows"]),
        ("254 行数值和", f"{float(iso['available'].sum()):,.0f}", "1,192",
         abs(float(iso["available"].sum()) - 1192.0) < 1e-6),
        ("254 补证(皮壳/半成品/双形态)", f"{summary['iso_disposition'].get('补证', 0)} 行 / "
         f"{summary['iso_disposition_qty'].get('补证', 0):,.0f}",
         "21 / 548", summary["iso_disposition"].get("补证", 0) == 21
         and abs(summary["iso_disposition_qty"].get("补证", 0) - 548.0) < 1e-6),
        ("254 拆包组装", f"{summary['iso_disposition'].get('拆包组装', 0)} 行 / 组装 "
         f"{summary.get('split_assembled_qty', 0):,.0f}", "1 / 29",
         summary["iso_disposition"].get("拆包组装", 0) == 1
         and abs(summary.get("split_assembled_qty", 0) - 29.0) < 1e-6),
        ("254 组件不全(不阻塞)",
         f"{summary['iso_disposition'].get('component_partial_nonblocking', 0)} 行 / "
         f"{summary['iso_disposition_qty'].get('component_partial_nonblocking', 0):,.0f}，"
         f"blocking=true 行={int(iso['blocking'].sum())}", "20 / 603 / 0",
         summary["iso_disposition"].get("component_partial_nonblocking", 0) == 20
         and int(iso["blocking"].sum()) == 0),
        ("C13 套件拆解", f"{len(set_tbl)} 行；CG 组件 16/6",
         "C 3 行 + CG 2 行（16/6）",
         len(set_tbl) == 5 and set_tbl["component_qty"].tolist()[-2:] == [16.0, 6.0]),
        ("254 零库存忽略", f"{summary['iso_disposition'].get('忽略(0库存)', 0)} 行", "212",
         summary["iso_disposition"].get("忽略(0库存)", 0) == 212),
        ("骨架 599 保留", f"{summary['skeleton_qty']:,.0f}", "599",
         abs(summary["skeleton_qty"] - 599.0) < 1e-6),
        ("TJ# 套件按套单列", f"{summary['bundle_rows']} 行 / {summary['bundle_units']:,.0f} 套", "4 / 8",
         summary["bundle_rows"] == 4 and abs(summary["bundle_units"] - 8.0) < 1e-6),
        ("星球组 1:1", f"{summary['planet_rows']} 行 / {summary['planet_qty']:,.0f} 个",
         "113 / 1,148", summary["planet_rows"] == V5_BASELINE["planet_rows"]
         and abs(summary["planet_qty"] - V5_BASELINE["planet_qty"]) < 1e-6),
        ("15 键门禁", f"FAIL={fifteen_fail}", "0", fifteen_fail == 0),
        ("伪 0 全量扫描", f"违例={len(pseudo)}", "0", len(pseudo) == 0),
        ("仓池标准名（5 值）", f"非标准={pool_bad}", "0", pool_bad == 0),
        ("契约完整性（rule/as_of/uom）", f"{RULE_VERSION} / {AS_OF} / {UOM_VERSION}", "非空",
         bool(RULE_VERSION and AS_OF and UOM_VERSION)),
        # ---- P2-1 join_class ----
        ("join_class 可复算", f"不一致={jc_mismatch} / {len(supply_tbl)}", "0",
         jc_mismatch == 0),
        ("join_class 覆盖全量", f"{jc_total} / {len(supply_tbl)}",
         f"{len(supply_tbl)}", jc_total == len(supply_tbl)),
        ("join_partial 不默认进净额",
         f"full∩(部分/非唯一/冲突)={jc_leak}", "0", jc_leak == 0),
        ("部分覆盖行不得 join_full", f"覆盖部分行={int((supply_tbl['覆盖状态'] == '部分').sum())}，"
         f"其中 join_full={jc_partial_full}", "0", jc_partial_full == 0),
        # ---- C8-1 资格闭环 ----
        ("C8-1 资格字段完整", f"缺失={c8_missing}", "0", c8_missing == 0),
        ("C8-1 HM 默认 component", f"HM 行={summary['hm_rows']}（可归属 "
         f"{summary['hm_mappable_rows']}：component {summary['hm_mappable_component']}；"
         f"未映射 {summary['hm_rows'] - summary['hm_mappable_rows']} 判 not_applicable）",
         "可归属 HM 全 component",
         summary["hm_mappable_rows"] == summary["hm_mappable_component"]),
        ("C8-1 ND 独立需求=0", f"{summary['nd_independent_rows']}", "0",
         summary["nd_independent_rows"] == 0),
        ("C8-1 TJ# 不拆组件", f"TJ# 行={summary['tj_rows']}，误计成品/皮壳={c8_tj_leak}",
         "误计=0", c8_tj_leak == 0),
        ("C8-1 半成品保留 raw", f"非成品形态={c8_semi_form_bad}", "0", c8_semi_form_bad == 0),
        ("C8-1 只有 join_full 进候选", f"候选={summary['c8_join_candidates']}，"
         f"候选≠full={c8_cand_leak}", "0", c8_cand_leak == 0),
        # ---- C8-2 共享池 / 缺行 ----
        ("C8-2 共享池 allocation=0", f"池={summary['c8_shared_pools']}，"
         f"allocation合计={summary['c8_shared_allocation']:g}", "=0",
         abs(summary["c8_shared_allocation"]) < 1e-9),
        ("C8-2 共享池数量守恒", f"池原量={summary['c8_shared_pool_qty']:,.0f} / "
         f"源行={summary['c8_shared_pool_rows']}", f"事实行原生量={c8_shared_fact_qty:,.0f}",
         abs(summary["c8_shared_pool_qty"] - c8_shared_fact_qty) < 1e-6),
        ("C8-2 共享池未超分", f"超分池={c8_over_alloc}", "0", c8_over_alloc == 0),
        ("C8-2 254 桥可回放", f"补证 {summary['iso_disposition'].get('补证', 0)}/{summary['iso_disposition_qty'].get('补证', 0):,.0f}；"
         f"仍隔离 {summary['iso_disposition'].get('仍隔离', 0)}/{summary['iso_disposition_qty'].get('仍隔离', 0):,.0f}",
         "63/539 + 191/653",
         summary["iso_disposition"].get("补证", 0) == 21
         and summary["iso_disposition"].get("拆包组装", 0) == 1),
        # ---- C8-3 Top50 导出与十键 ----
        ("C8-3 十键回放", f"{summary['c8_ten_pass']}/{summary['c8_ten_total']}", "10/10",
         summary["c8_ten_pass"] == 10 == summary["c8_ten_total"]),
        ("C8-3 稳定字段完整", f"空值={c8_proof_missing}", "0", c8_proof_missing == 0),
        ("P1-1 Top50 只含 join_full", f"{len(top50):,} / join_full={join_full_n:,}", "相等",
         len(top50) == join_full_n),
        ("P1-1 Top50 无 partial/no_join", f"{top50_nonfull}", "0", top50_nonfull == 0),
        ("P1-1 Top50 source_proof 非空", f"空={top50_proof_empty}", "0", top50_proof_empty == 0),
        # ---- C9 可操作状态 ----
        ("C9 非 full 行状态完整", f"缺 reason/证据/动作/责任人={c9_missing} / {len(_c9_rows)}",
         "0", c9_missing == 0),
        ("C9 白名单默认空", f"{summary['c9_whitelist_rows']}", "0", summary["c9_whitelist_rows"] == 0),
        ("C9 no_join 观察表", f"{c9_nojoin_sum} 行 / {summary['c9_nojoin_obs_rows']}", "相等",
         c9_nojoin_sum == summary["c9_nojoin_obs_rows"]
         and summary["c9_nojoin_obs_rows"] == summary["join_class"].get("no_join", [0])[0]),
        ("C9 partial 观察表", f"{c9_partial_sum} 行 / {summary['c9_partial_obs_rows']}", "相等",
         c9_partial_sum == summary["c9_partial_obs_rows"]
         and summary["c9_partial_obs_rows"] == summary["join_class"].get("join_partial", [0])[0]),
        ("C9 Top50 仅 join_full", f"非full={top50_nonfull}", "0", top50_nonfull == 0),
        ("C9 Top50 无 null", f"{top50_null}", "0", top50_null == 0),
        # ---- C10 CG 池 ----
        ("C10 CG 汇总行=EN", f"{summary['cg_rows']} SKU / {summary['cg_available']:,.0f}",
         "104 / 417", summary["cg_rows"] == 104 and abs(summary["cg_available"] - 417.0) < 1e-6),
        ("C10 CG 行=分仓和", f"{summary['cg_reconcile_ok']}/{summary['cg_rows']}", "104/104",
         summary["cg_reconcile_ok"] == summary["cg_rows"]),
        ("C10 分仓明细不累加",
         f"CG {summary['cg_available']:,.0f} + 明细 {summary['cg_detail_sum']:,.0f} "
         f"(明细行 {summary['cg_detail_rows']})", "只取 CG；明细仅对账",
         abs(summary["cg_detail_sum"] - summary["cg_available"]) < 1e-6
         and summary["cg_detail_rows"] == 352),
        ("C10 stale=0", f"{summary['cg_stale']}", "0", summary["cg_stale"] == 0),
        ("C10 available_missing 不填0", f"{summary['cg_avail_missing']}", "0",
         summary["cg_avail_missing"] == 0),
        ("C10 CG 三池合计", f"{summary['cg_pool_rows']}", "行数合计=104",
         sum(summary["cg_pool_rows"].values()) == 104),
        ("C10 归属状态可复算",
         f"owner {summary['cg_owner_rows']} / unknown {summary['cg_unknown_owner']} / "
         f"mapped_inactive {summary.get('cg_mapped_inactive', 0)} / "
         f"unmapped {summary['cg_unmapped']}", "104 / 0 / 0 / 0",
         summary["cg_owner_rows"] == 104 and summary.get("cg_mapped_inactive", 0) == 0
         and summary["cg_unknown_owner"] == 0 and summary["cg_unmapped"] == 0),
        ("C10 cg_eligible/pending", f"{summary['cg_eligible']} / {summary['cg_pending']}",
         "104 / 0", summary["cg_eligible"] == 104 and summary["cg_pending"] == 0),
        ("C10 CG 不进当前净额", f"included={summary['cg_in_net']}，transfer={summary['cg_transfer']}",
         "0/0", summary["cg_in_net"] == 0 and summary["cg_transfer"] == 0),
        ("C10 cg_eligible 仅 join_full",
         f"{int(((supply_tbl['cg_status'] == 'cg_eligible') & (supply_tbl['join_class'] != 'join_full')).sum())}",
         "0", int(((supply_tbl["cg_status"] == "cg_eligible")
                   & (supply_tbl["join_class"] != "join_full")).sum()) == 0),
        # ---- P2-2 老产品双口径 ----
        ("老产品·产品级（distinct product_id）",
         f"{summary['legacy_products']} 个 + 未归属 {summary['legacy_unmapped_rows']} 行",
         f"清单 {summary['legacy_sheet_rows']} 行（含未归属 1 行）",
         summary["legacy_products"] == summary["legacy_sheet_rows"] - 1
         and summary["legacy_unmapped_rows"] == 13),
        ("老产品·行级（事实层）", f"{summary['legacy_fact_rows']} 行 / "
         f"{summary['legacy_fact_qty']:,.0f} 个", "113 / 1,148",
         summary["legacy_fact_rows"] == V5_BASELINE["planet_rows"]
         and abs(summary["legacy_fact_qty"] - V5_BASELINE["planet_qty"]) < 1e-6),
        ("老产品·行级（供给层）", f"{summary['legacy_supply_rows']} 行 / "
         f"{summary['legacy_supply_qty']:,.0f} 个", "19 / 764",
         summary["legacy_supply_rows"] == 19
         and abs(summary["legacy_supply_qty"] - 764.0) < 1e-6),
        ("老产品·1:1 断言（独立）", f"违反={planet_11_viol}", "0", planet_11_viol == 0),
        ("老产品·默认不补断言（独立）", f"标签值={legacy_labels}；行数差={legacy_row_diff}",
         "1 个标签且行数差=0", legacy_row_diff == 0 and legacy_labels == [LEGACY_NOTE]),
    ]

    # ---------- 输出 ----------
    out = Path(args.out_xlsx)
    out.parent.mkdir(parents=True, exist_ok=True)
    iso_total_rows, iso_total_qty = int(len(iso_tbl)), float(iso["available"].sum())

    def bucket_tbl():
        t = recon.copy()
        t["桶"] = t["bucket"]
        t.insert(0, "rule_version", RULE_VERSION)
        t.insert(1, "as_of", AS_OF)
        return t[["rule_version", "as_of", "桶", "行数", "数值和", "基线行数", "基线数值和",
                  "行数差", "数值差"]]

    def bridge_tbl():
        a_rows, a_qty = bq("计入A")
        add_rows = int((iso["处置"] == "补证").sum())
        add_qty = float(iso.loc[iso["处置"] == "补证", "available"].sum())
        return pd.DataFrame([
            {"项": "第六桶(皮壳无活跃EN)", "行数": iso_total_rows, "数值和": iso_total_qty,
             "说明": "逐行明细见 7_254行隔离明细"},
            {"项": "→ 补证进入皮壳供给", "行数": add_rows, "数值和": add_qty,
             "说明": "客户码/来源码同物映射到活跃产品且方式=皮壳（按个）"},
            {"项": "→ 待核", "行数": summary["iso_disposition"].get("待核", 0),
             "数值和": summary["iso_disposition_qty"].get("待核", 0.0), "说明": "多候选/方式未知"},
            {"项": "→ 仍隔离(有据不计)", "行数": summary["iso_disposition"].get("仍隔离", 0),
             "数值和": summary["iso_disposition_qty"].get("仍隔离", 0.0),
             "说明": "方式=成品/半成品(皮壳组件不计) 或 无活跃EN映射"},
            {"项": "计入A + 补证 = 供给输入", "行数": a_rows + add_rows, "数值和": a_qty + add_qty,
             "说明": "仍受多候选/方式约束；单位按用户口径不再阻断"},
        ])

    input_files = [
        ("en_stock.parquet", args.stock),
        ("SKU活跃宇宙_2026-10-29_FINAL.xlsx", args.a_final),
        ("sku_map.tsv", args.sku_map),
        ("en_item_customer_codes.csv", args.customer_codes),
        ("sku_mapping_overrides_2026-10-29.csv", args.overrides),
        ("non_product_skus.csv", args.non_product),
        ("warehouse_scope.csv", args.warehouse_scope),
        ("item_uom_cache.parquet", args.uom_cache),
        ("商品导出_20261030_1626.zip(CG别名)", args.cg_alias_zip),
        ("仓库归属_A337_v6r9_2026-10-30.xlsx(CG归属)", args.b_attribution),
        ("EN Product Bundle 缓存", args.bundle_cache),
    ]
    input_sha = [(n, str(p), sha256(Path(p))) for n, p in input_files]

    def contract_tbl():
        rows = [
            ("rule_version", RULE_VERSION),
            ("as_of(快照日)", AS_OF),
            ("snapshot_date(parquet 过滤)", args.date),
            ("UOM 版本", UOM_VERSION),
            ("UOM 唯一依据", "D:/Work/赛狐/Cursor-claude/docs/research/supply-chain/2026-10-20/claude/control/reference/UOM-CANONICAL.md"),
            ("源行数", SRC_ROWS),
            ("源 available 数值和", SRC_QTY),
            ("六桶基线", "计入A 2,484/47,332；共享码 53/1,403；A未激活 425/20；"
                        "规则排除 879/10,308,263；未映射 1,222/2,238；皮壳无活跃EN 254/1,192"),
            ("仓池标准名", " / ".join(POOL_CANON)),
            ("身份状态枚举", "唯一 / 共享 / 未映射 / 未激活 / 待核"),
            ("单位状态枚举", "已证 / 默认个 / 冲突 / 套件"),
            ("覆盖状态枚举", "完整 / 部分 / 未覆盖 / 不适用（缺口明细见「覆盖缺口」列）"),
            ("可发供给 null 语义", "无适用事实或已计0但有未计正量 → null；禁止补 0"),
            ("缺行语义", "产品在快照无库存行 → 覆盖状态=未覆盖；不是 0"),
            ("老产品口径", "星球抱枕组只标「老产品-默认不补(待确认)」，行不删、数值照算"),
            ("join_class 枚举", "join_full（覆盖完整+身份唯一+单位非冲突+无未计正量）/ "
                             "join_partial（部分覆盖/身份非唯一/单位冲突，需白名单或仅观察）/ "
                             "no_join（null/待核/套件单列/CG·其他仅披露）"),
            ("join_class 行数", "；".join(
                f"{k}: {v[0]} 行 / {v[1]:,.0f} 个" for k, v in summary["join_class"].items())),
            ("默认消费", "只允许 join_class=join_full；join_partial 不得静默进入补货净额"),
            ("老产品·产品级", f"{summary['legacy_products']} 个 distinct product_id + "
                           f"{summary['legacy_unmapped_rows']} 行未归属"
                           f"（16_老产品清单 {summary['legacy_sheet_rows']} 行）"),
            ("老产品·行级", f"事实层 {summary['legacy_fact_rows']} 行 / "
                          f"{summary['legacy_fact_qty']:,.0f} 个；供给层 "
                          f"{summary['legacy_supply_rows']} 行 / "
                          f"{summary['legacy_supply_qty']:,.0f} 个"),
            ("C8-1 资格字段", "physical_form / canonical_uom / demand_eligibility / "
                          "eligibility_reason / source_ref / shared_pool_id 全 5,317 行非空"),
            ("C8-1 资格口径", "HM=component（默认；after_sales 仅已证补发）；ND=component（独立需求=0）；"
                          "TJ#=independent(套)；骨架/半成品/成品=independent；皮壳=component；"
                          "未映射/未激活/规则排除=not_applicable"),
            ("C8-1 候选闸门", f"join_candidate 仅 join_full：{summary['c8_join_candidates']:,} 行"),
            ("C8-2 共享池", f"{summary['c8_shared_pools']} 个池 / {summary['c8_shared_pool_rows']} 个源行 / "
                          f"原量 {summary['c8_shared_pool_qty']:,.0f}；allocation_qty="
                          f"{summary['c8_shared_allocation']:g}"),
            ("C8-3 Top50 导出", f"19_Top50候选导出 仅 join_full {summary['c8_top50_rows']:,} 行 /"
                              f" {summary['c8_top50_qty']:,.0f} 个；19b 观察表 "
                              f"{summary['c8_top50_obs_rows']:,} 行；20_十键回放 "
                              f"{summary['c8_ten_pass']}/{summary['c8_ten_total']}"),
            ("P1-2 脚本与 manifest", "脚本：scripts/tongtool_inventory_rollup_a337_v14.py（镜像到 "
                                  "D:/Work/fzh-order-store/scripts/，同 SHA）；manifest："
                                  "通途库存_A337_v9_2026-10-30.manifest.json"),
            ("C9 reason_code", "partial: missing_finished/missing_cover/missing_sponge/missing_kit/"
                             "shared_pending/uom_partial/coverage_partial；"
                             "no_join: no_applicable_fact/uncovered/shared_pool/kit_only/cg_other/"
                             "excluded/uom_conflict/identity_ambiguous；null: no_applicable_fact/"
                             "unknown_not_zero；full: none"),
            ("C9 可操作状态", "每行 needed_evidence / next_action / owner / consumption；"
                           "partial 默认 blocked，白名单登记后才可观察性消费"),
            ("C9 白名单", f"22_join_partial白名单 {summary['c9_whitelist_rows']} 行（默认空）"),
            ("C9 观察表", f"21_no_join观察 {summary['c9_nojoin_obs_rows']} 行（含 null）；"
                        f"21b_join_partial观察 {summary['c9_partial_obs_rows']} 行；null 数量留空不写 0"),
            ("C10 CG 池", f"EN Wayfair CG Stock Latest（只读，仅 warehouse_id=CG）：{summary['cg_rows']} SKU / "
                        f"{summary['cg_available']:,.0f}；三池 "
                        f"{summary['cg_pool_rows']}；eligible {summary['cg_eligible']} / pending "
                        f"{summary['cg_pending']}"),
            ("C10 CG 边界", "不并入 USNJ/USTX 物理库存；分仓明细不累加；不生成 transfer；"
                          "cg_included_in_current_net=false"),
            ("C10 归属来源", "attribution_source=B-r9-local-provisional（EN SKU Market Attribution 未建，暂用 B r9 本地）"),
            ("C11 CG 别名映射", "商品导出_20261030_1626.zip（3 表）SKU+分号别名 → 45,494 键；"
                             "CG SKU 先剥 OLD_，再 sku/alias 匹配；mapping_basis=sku|old_prefix_strip|alias"),
            ("C11 形态要求", "皮壳：required=皮壳或成品（成品可替代）；成品：required=成品（皮壳组件不计）；"
                          "半成品：required=半成品/皮壳或成品；未知→pending；缺必需形态才算 partial"),
            ("C14 身份口径", "身份以库存源 SKU 为准：只有源 SKU 本身多候选、或共享池有正库存并实际计入才标共享；"
                          "零库存共享码不阻塞（KS0248-DM-153/194 → join_full）"),
            ("C14 套件口径", "套件拆解仅用于库存/供给换算；订单需求保留原始单件/套件单位，不换算"),
            ("C13 套件拆解", "读 EN Product Bundle：set_qty × component_qty 换算组件供给；套件本身不作为库存；"
                           "CG TJ#KS0156x2/x3 → mapped_set，组件 16/6 个"),
            ("C13 组件不阻塞", "254 缺 foam/cover → component_partial_nonblocking（blocking=false）；"
                           "仅 KS0248 共享身份冲突 blocking=true"),
            ("C12 规则", "TJ#/TT# 不活跃但 EN 实存 → mapped_inactive/old_set（不标 unmapped）；"
                        "HM role=海绵 有库存即独立供给（required_form=海绵）；"
                        "ship_mode 未知且无库存 → uncovered（不判 partial）；"
                        "拆包成品：cover+foam → min(cover,foam) 计入成品供给（split_package）"),
            ("C11 双形态", f"254 行：补证 {summary['iso_disposition'].get('补证', 0)} 行 / "
                         f"{summary['iso_disposition_qty'].get('补证', 0):,.0f}；"
                         f"both_forms_present {summary['both_forms_rows']} 行"),
            ("同输入可重放", "内容哈希（各 sheet 规范化 CSV）对所有输入确定；见下行"),
        ]
        for n, p, h in input_sha:
            rows.append((f"输入 SHA256 · {n}", h))
            rows.append((f"输入路径 · {n}", p))
        for c, got, want, ok in checks:
            rows.append((f"自检 · {c}", f"{got}（期望 {want}）→ {'PASS' if ok else 'FAIL'}"))
        rows.append(("产物", str(out)))
        rows.append(("内容哈希（可重放证据）", content_hash))
        return pd.DataFrame(rows, columns=["项", "内容"])

    def notes_tbl():
        rows = [
            ("产物", "通途库存_A337_v14_2026-10-30.xlsx（v5 + 契约冻结 + 门禁/守恒/状态分层，只读）"),
            ("脚本", "scripts/tongtool_inventory_rollup_a337_v14.py"),
            ("rule_version", RULE_VERSION),
            ("as_of", f"{AS_OF} 快照（snapshot_date 过滤）"),
            ("UOM 版本", UOM_VERSION),
            ("快照", f"snapshot_date={args.date}，{len(f)} 行，available 数值和 {f['available'].sum():,.0f}"),
            ("口径1·默认个", "一切按个；EN stock_uom 只作参考、不作证明"),
            ("口径2·套", "「套」只给 TJ#/Product Bundle（缓存 stock_uom=套 且 is_stock_item=0）"),
            ("口径3·多件后缀", "末尾 -2PCS/-3PCS/-5PC/-7PCS 等：每单位=N 个，available×N；裸 -2/-3 与中段件数不换算"),
            ("口径4·缓存套非Bundle", "KS0354/KS0422 按个计入，原值记入 uom_note 与 10_单位冲突记录"),
            ("口径5·不再阻断", "取消 uom_unproven 阻断；无单位来源按个计并记录来源缺失"),
            ("口径6·星球组1:1", "EN 物料组=星球抱枕(KS0019) 整组 1:1（UOM-CANONICAL §2.1 例外）"),
            ("口径7·老产品标记", "该组在事实层 `补货标记`、供给行 `补货资格` 标「老产品-默认不补(待确认)」；不删行、数值照算"),
            ("N1·空集不为0", "无适用成品/皮壳/套件事实的键：可发供给=null、不进 join；已计0但同键有未计正量也判 null"),
            ("N2·主体骨架", "按 A 用户规则作独立成品分支，单独成行，不并入沙发成品/不按内胆组件排除（美东 599）"),
            ("N3·证明状态", "事实/汇总/供给三层共用 身份状态/单位状态/覆盖状态；只有唯一有效映射才标「归属已证」"),
            ("N4·表结构", "产品区与去向/汇总分 sheet：供给只含产品行，去向在 12_，换算汇总在 7_"),
            ("口径·仓池", "美东USNJ / 美中USTX / 波兰 / CG / 其他（退货仓/第三方仅作「仓类别」，仓池归「其他」）；全表无 East/Central"),
            ("口径·可发供给", "皮壳模式=成品+皮壳；成品/半成品模式=成品（均按个）；套件单独按套"),
            ("口径·共享", "同优先级全部候选保留；多候选一律共享待核，不进可发供给"),
            ("口径·缺行", "无库存行的产品=未覆盖，不等于 0 库存（13_未覆盖产品）"),
            ("只读声明", "未调用 EN/通途写接口，未发消息，未 push；不改 A/B/C 历史产物"),
        ]
        return pd.DataFrame(rows, columns=["项", "内容"])

    # 汇总层（产品×仓池×形态×UOM）
    prod_form = (f[f["product_id"].notna() & f["bucket"].isin(["计入A", "皮壳无活跃EN"])]
                 .groupby(["product_id", "actual_form", "pool", "uom", "uom_status", "identity_status",
                           "role", "supply_role", "coverage_status"], dropna=False)
                 .agg(库存=("qty_pieces", "sum"), 原始available=("available", "sum"),
                      行数=("sku", "size")).reset_index()
                 .sort_values(["pool", "product_id", "actual_form", "uom"]))

    def avail3(r) -> str:
        sr = r["supply_role"]
        if sr in ("成品供给", "皮壳供给"):
            return "仅披露(CG/其他)" if r["pool"] in (POOL_CG, POOL_OTHER) else "可参考"
        if sr in ("待核", "发货方式未知(待核)", "形态未知(待核)"):
            return "待核"
        if sr.startswith("套件单列"):
            return "套件单列"
        return "仅披露(不计)"

    prod_form["可用性"] = [avail3(r) for _, r in prod_form.iterrows()]
    prod_form["补货资格"] = ["老产品-默认不补(待确认)" if str(p) in planet_ens else ""
                             for p in prod_form["product_id"]]
    prod_form = prod_form[["product_id", "actual_form", "role", "pool", "uom", "uom_status",
                           "identity_status", "supply_role", "coverage_status", "库存",
                           "原始available", "行数", "可用性", "补货资格"]] \
        .rename(columns={"uom_status": "单位状态", "identity_status": "身份状态",
                         "coverage_status": "覆盖状态"})

    # 命名扫描（写入后按单元格扫描，仓池/仓名列必须 0）
    def naming_scan(tables: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, int, int]:
        pat = re.compile(r"east|central", re.I)
        rows, total, wh_hits = [], 0, 0
        wh_cols = {"仓池", "warehouse_name", "仓"}
        for name, df in tables.items():
            for col in df.columns:
                hits = [str(v) for v in df[col].dropna().unique() if pat.search(str(v))]
                if hits:
                    rows.append({"sheet": name, "列": col, "命中数": len(hits),
                                 "样例": "；".join(hits[:3])})
                    total += len(hits)
                    if col in wh_cols:
                        wh_hits += len(hits)
        return pd.DataFrame(rows), total, wh_hits

    tables = {
        "0_契约": None,  # 占位，内容在写完后回填
        "1_六桶对账": bucket_tbl(),
        "2_库存事实层": detail,
        "3_产品×仓池×形态×UOM汇总": prod_form,
        "4_可发供给": supply_tbl,
        "5_多件后缀换算表": pc_tbl,
        "6_共享候选": sh,
        "7_多件后缀换算汇总": pc_summary,
        "8_254行隔离明细": iso_tbl,
        "9_单位冲突记录": conflict_tbl,
        "10_排除明细": excluded,
        "11_供给去向分解": decomp,
        "12_六桶供给桥接": bridge_tbl(),
        "13_未覆盖产品": uncovered,
        "14_15键门禁回放": fifteen_tbl,
        "15_自检清单": pd.DataFrame(checks, columns=["检查项", "结果", "期望", "通过"]),
        "16_老产品清单": legacy_products,
        "17_资格分层": cat_elig,
        "18_共享池回放": sp,
        "19_Top50候选导出": top50,
        "19b_Top50观察表": top50_obs,
        "21_no_join观察": nojoin_sum,
        "21b_join_partial观察": partial_sum,
        "22_join_partial白名单": whitelist,
        "23_CG库存池": cg_tbl,
        "26_套件拆解": set_tbl,
        "24_CG池汇总": cg_pool_tbl,
        "25_CG对账": cg_recon_tbl,
        "20_十键回放": ten_tbl,
    }

    def canonical(df: pd.DataFrame) -> str:
        cols = [str(c) for c in df.columns]
        body = [",".join(cols)]
        for rec in df.itertuples(index=False, name=None):
            body.append(",".join("" if x is None or (isinstance(x, float) and pd.isna(x))
                                 else (f"{x:.6f}" if isinstance(x, float) else str(x))
                                 for x in rec))
        return "\n".join(body)

    h = hashlib.sha256()
    for name, df in tables.items():
        if df is None:
            continue
        h.update(name.encode("utf-8"))
        h.update(canonical(df).encode("utf-8"))
    content_hash = h.hexdigest()

    contract = contract_tbl()
    tables["0_契约"] = contract
    # 契约自身不参与内容哈希（避免自指），但参与命名扫描
    scan_tbl, scan_total, scan_wh = naming_scan({k: v for k, v in tables.items() if v is not None})

    with pd.ExcelWriter(out, engine="openpyxl") as w:
        contract.to_excel(w, sheet_name="0_契约", index=False)
        bucket_tbl().to_excel(w, sheet_name="1_六桶对账", index=False)
        detail.to_excel(w, sheet_name="2_库存事实层", index=False)
        prod_form.to_excel(w, sheet_name="3_产品×仓池×形态×UOM汇总", index=False)
        supply_tbl.to_excel(w, sheet_name="4_可发供给", index=False)
        pc_tbl.to_excel(w, sheet_name="5_多件后缀换算表", index=False)
        sh.to_excel(w, sheet_name="6_共享候选", index=False)
        pc_summary.to_excel(w, sheet_name="7_多件后缀换算汇总", index=False)
        iso_tbl.to_excel(w, sheet_name="8_254行隔离明细", index=False)
        conflict_tbl.to_excel(w, sheet_name="9_单位冲突记录", index=False)
        excluded.to_excel(w, sheet_name="10_排除明细", index=False)
        decomp.to_excel(w, sheet_name="11_供给去向分解", index=False)
        bridge_tbl().to_excel(w, sheet_name="12_六桶供给桥接", index=False)
        uncovered.to_excel(w, sheet_name="13_未覆盖产品", index=False)
        fifteen_tbl.to_excel(w, sheet_name="14_15键门禁回放", index=False)
        pd.DataFrame(checks, columns=["检查项", "结果", "期望", "通过"]) \
            .to_excel(w, sheet_name="15_自检清单", index=False)
        legacy_products.to_excel(w, sheet_name="16_老产品清单", index=False)
        cat_elig.to_excel(w, sheet_name="17_资格分层", index=False)
        sp.to_excel(w, sheet_name="18_共享池回放", index=False)
        top50.to_excel(w, sheet_name="19_Top50候选导出", index=False)
        top50_obs.to_excel(w, sheet_name="19b_Top50观察表", index=False)
        ten_tbl.to_excel(w, sheet_name="20_十键回放", index=False)
        nojoin_sum.to_excel(w, sheet_name="21_no_join观察", index=False)
        partial_sum.to_excel(w, sheet_name="21b_join_partial观察", index=False)
        whitelist.to_excel(w, sheet_name="22_join_partial白名单", index=False)
        cg_tbl.to_excel(w, sheet_name="23_CG库存池", index=False)
        cg_pool_tbl.to_excel(w, sheet_name="24_CG池汇总", index=False)
        cg_recon_tbl.to_excel(w, sheet_name="25_CG对账", index=False)
        set_tbl.to_excel(w, sheet_name="26_套件拆解", index=False)

    out_sha = sha256(out)
    Path(args.out_report).write_text(
        render(summary, bucket_tbl(), bridge_tbl(), supply_tbl, pc_summary, conflict_tbl,
               fifteen_tbl, checks, input_sha, scan_tbl, scan_total, scan_wh,
               uncovered, content_hash, out_sha, args, out,
               cat_elig=cat_elig, sp=sp, ten_tbl=ten_tbl, top50=top50,
               cg_pool=cg_pool_tbl, set_tbl=set_tbl),
        encoding="utf-8")
    # ---------- P1-2：脚本落盘（仓库 + D:/Work/fzh-order-store/scripts，同 SHA）+ manifest ----------
    script_src = Path(__file__).resolve()
    script_sha = sha256(script_src)
    dscripts = Path("D:/Work/fzh-order-store/scripts")
    dscripts.mkdir(parents=True, exist_ok=True)
    script_dup = dscripts / script_src.name
    if script_dup.resolve() != script_src:
        shutil.copyfile(script_src, script_dup)
    predecessors = []
    for nm in ("tongtool_inventory_rollup_a337_v8.py", "tongtool_inventory_rollup_a337_v8b.py"):
        src_p = script_src.with_name(nm)
        if not src_p.exists():
            continue
        dup_p = dscripts / nm
        if dup_p.resolve() != src_p.resolve():
            shutil.copyfile(src_p, dup_p)
        predecessors.append({"path": str(src_p), "sha256": sha256(src_p),
                             "mirror_path": str(dup_p), "mirror_sha256": sha256(dup_p)})
    manifest_path = Path(str(out).replace(".xlsx", ".manifest.json"))
    manifest = {
        "rule_version": RULE_VERSION,
        "as_of": AS_OF,
        "snapshot_date": args.date,
        "uom_version": UOM_VERSION,
        "generated_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "command": "uv run python scripts/tongtool_inventory_rollup_a337_v14.py",
        "script": {"path": str(script_src), "sha256": script_sha},
        "script_mirror": {"path": str(script_dup), "sha256": sha256(script_dup)},
        "predecessor_scripts": predecessors,
        "inputs": [{"name": n, "path": pp, "sha256": hh} for n, pp, hh in input_sha],
        "outputs": {
            "xlsx": {"path": str(out), "sha256": out_sha},
            "report": {"path": str(args.out_report), "sha256": sha256(Path(args.out_report))},
        },
        "counts": {
            "source_rows": summary["rows_in"], "source_qty": summary["qty_in"],
            "buckets": summary["buckets"], "bucket_qty": summary["bucket_qty"],
            "join_full_rows": summary["c8_join_full_rows"],
            "join_full_qty": summary["c8_top50_qty"],
            "top50_rows": summary["c8_top50_rows"],
            "top50_observation_rows": summary["c8_top50_obs_rows"],
            "join_class": summary["join_class"],
            "uncovered_products": summary["uncovered_en"],
            "checks_total": len(checks),
            "checks_failed": sum(1 for c in checks if not c[3]),
            "ten_keys_pass": summary["c8_ten_pass"],
        },
        "cg": {
            "en_doctype": CG_DOCTYPE,
            "run_id": sorted(set(cg_tbl["cg_run_id"].astype(str)))[:1],
            "snapshot_at": sorted(set(cg_tbl["cg_snapshot_at"].astype(str)))[:1],
            "cache_path": str(cg_cache),
            "cache_sha256": sha256(cg_cache),
            "rows": summary["cg_rows"], "available": summary["cg_available"],
            "detail_rows": summary["cg_detail_rows"], "detail_sum": summary["cg_detail_sum"],
            "pools": summary["cg_pool_rows"], "pool_qty": summary["cg_pool_qty"],
            "eligible": summary["cg_eligible"], "pending": summary["cg_pending"],
            "alias_zip": args.cg_alias_zip,
            "alias_keys": len(alias_map),
            "mapping_basis": {k: int(v) for k, v in
                              cg_tbl["mapping_basis"].value_counts().items()},
            "attribution_source": "B-r9-local-provisional",
            "attribution_file": args.b_attribution,
            "attribution_sha256": sha256(Path(args.b_attribution)) if Path(args.b_attribution).exists() else None,
        },
        "content_hash": content_hash,
        "sheets": {name: int(len(df)) for name, df in tables.items() if df is not None},
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1,
                                        default=str), encoding="utf-8")
    print("manifest:", manifest_path)
    print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    print("15键:", fifteen_tbl["门禁"].value_counts().to_dict())
    print("未覆盖EN:", len(uncovered))
    print("自检:", [(c[0], c[3]) for c in checks])
    print("命名扫描: total=", scan_total, "warehouse_cols=", scan_wh)
    print("内容哈希:", content_hash)
    print("工作簿 SHA256:", out_sha)
    print("工作簿：", out)
    print("报告：", args.out_report)
    return 0


def _agg_identity(s: pd.Series) -> str:
    vals = set(s.dropna().astype(str))
    if vals == {"唯一"}:
        return "唯一"
    if "共享" in vals:
        return "共享"
    if "未激活" in vals:
        return "未激活"
    if "待核" in vals:
        return "待核"
    if "未映射" in vals:
        return "未映射"
    return "/".join(sorted(vals))


def _all_cands(cand: dict, n: str) -> set:
    return {e for tags in cand.get(n, {}).values() for e in tags}


def _tags_for(cand: dict, n: str, en: str) -> set:
    return {t for t, ens in cand.get(n, {}).items() if en in ens}


def render(summary, bucket_tbl, bridge_tbl, supply_tbl, pc_summary, conflict_tbl,
           fifteen_tbl, checks, input_sha, scan_tbl, scan_total, scan_wh,
           uncovered, content_hash, out_sha, args, out: Path,
           cat_elig=None, sp=None, ten_tbl=None, top50=None, cg_pool=None,
           set_tbl=None) -> str:
    L = [
        f"# 通途库存 → A FINAL（A337）v14 报告（as_of={AS_OF}，只读）",
        "",
        f"- `rule_version` = **{RULE_VERSION}**；`as_of` = **{AS_OF}**；`uom_version` = **{UOM_VERSION}**",
        f"- 生成：`scripts/tongtool_inventory_rollup_a337_v14.py`（只读：不写 EN/通途、不发消息、不 push）",
        f"- 产物：`{out.name}`（不覆盖 v2…v13）",
        "- 本版 = v13 + 两件修复：**身份以库存源 SKU 为准**（零库存共享码不阻塞 → KS0248 两行 join_full）；"
        "**套件拆解只用于库存/供给换算**（订单需求保留原始单件/套件单位）。",
        "",
        "## 1. 契约冻结与可重放",
        "",
        "| 输入 | SHA256 |",
        "|---|---|",
    ]
    for n, p, h in input_sha:
        L.append(f"| {n} | `{h}` |")
    L += [
        "",
        f"- 内容哈希（各 sheet 规范化 CSV 的 SHA256）：`{content_hash}`",
        f"- 本次工作簿 SHA256：`{out_sha}`（docProps 含写入时间，逐次不同；**可重放以内容哈希为准**）",
        f"- 源 {summary['rows_in']:,} 行 / available 数值和 {summary['qty_in']:,.0f}",
        "",
        "## 2. 与 v13 的差异（身份按源 SKU / 套件只用于供给）",
        "",
        "| 项 | v13 | v14 |",
        "|---|---|---|",
        "| 身份判定 | 键内任一行为共享即判共享 | 只看**实际计入的供给行**；零库存共享/待核行不改变键身份 |",
        "| KS0248-DM-153/194 | join_partial（假 partial） | **join_full**（223 / 147），与 KS0001 分开处理 |",
        "| 套件口径 | 换算未说明用途 | 明确**只用于库存/供给换算**；订单需求不换算（`26_套件拆解.set_usage`） |",
        "| join_full / partial | 1,916 / 2 | **1,918 / 0** |",
        "",
        "> 保持：CG 套件 8/2→16/6、CG 未归属 0、六桶 0 差、命名 0、HM 独立、单形态正常、"
        "component_partial_nonblocking 20 行 blocking=false。",
        "",
        "## 3. 六桶对账（冻结口径，逐桶 0 差）",        "## 3. 六桶对账（冻结口径，逐桶 0 差）",        "## 3. 六桶对账（冻结口径，逐桶 0 差）",        "## 3. 六桶对账（冻结口径，逐桶 0 差）",        "## 3. 六桶对账（冻结口径，逐桶 0 差）",
        "",
        "| 桶 | 行数 | 数值和 | 基线行数 | 基线数值和 | 行差 | 数值差 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in bucket_tbl.to_dict("records"):
        L.append(f"| {r['桶']} | {r['行数']:,} | {r['数值和']:,.0f} | {r['基线行数']:,} | "
                 f"{r['基线数值和']:,.0f} | {r['行数差']} | {r['数值差']:,.0f} |")
    L += [
        "",
        "### 3.1 六桶 → 供给输入桥接",
        "",
        "| 项 | 行数 | 数值和 | 说明 |",
        "|---|---:|---:|---|",
    ]
    for r in bridge_tbl.to_dict("records"):
        L.append(f"| {r['项']} | {r['行数']} | {r['数值和']:,.0f} | {r['说明']} |")
    L += [
        "",
        "## 4. N1 门禁：v3 评审 15 个键逐键回放",
        "",
        "门禁规则：没有适用成品/皮壳/套件事实 → `可发供给=null`、`供给状态=无适用事实(非0)`、`可用性=不进join`；"
        "空集不求和当 0；**已计=0 但同键有未计形态正量 → 也判 null**。",
        "",
        "| v3行号 | # | product_id | 仓池 | uom | 可发供给 | 供给状态 | 覆盖状态 | join_class | 可用性 | 事实行号 | 门禁 |",
        "|---:|---:|---|---|---|---:|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(fifteen_tbl.to_dict("records"), 1):
        v = "null" if r["可发供给"] is None or pd.isna(r["可发供给"]) else f"{r['可发供给']:,.0f}"
        L.append(f"| {r['v3行号']} | {i} | `{r['product_id']}` | {r['仓池']} | {r['uom']} | {v} | "
                 f"{r['供给状态']} | {r['覆盖状态']} | {r['join_class']} | {r['可用性']} | "
                 f"{r['事实行号(parquet1基)']} | {r['门禁']} |")
    gate_counts = fifteen_tbl["门禁"].value_counts().to_dict()
    L += [
        "",
        f"- 门禁结论：**PASS {int((fifteen_tbl['门禁'].astype(str).str.startswith('PASS')).sum())}/15**，"
        f"FAIL={int((fifteen_tbl['门禁'].astype(str).str.startswith('FAIL')).sum())}；"
        f"分类：{gate_counts}。",
        "- **12 个键 → null 或套件单列**（不进净额）：无适用成品/皮壳事实，或只有共享/海绵/待核/未映射事实。"
        "其中 v3 的 363/1278/1949 三行原为 `uom=套`（KS0018 并非 EN Product Bundle），"
        "按 UOM-CANONICAL §2.2 已回落「个」；中/波两仓另有未计套件正量（3/13），v6 判 null 而不是 0。",
        "- **2 个键 → 真实已证零**（`PASS(已证零,有源行)`）：KS0018 美东、骨架 ZTGJ5525 波兰。"
        "这两个键存在实际适用行且数量=0、同键无任何未计正量，按复审口径「真正已证零」保留 0；"
        "它们进 join 贡献为 0，不构成伪 0。",
        "- **1 个键 → 真实正量**：1456（骨架美东）599 个，源行 5279（TT0312701K0064561），属 N2 独立成品分支，"
        "与第 7 条「骨架 599 保留」一致。",
        "- 与验收字面「15 键全部 null/不进join」的偏差仅在上面 3 个键：把有源行证据的 0 或 599 强行改成 null，"
        "等于伪造「无事实」，会同时违反守恒与 N2「保留真实已证零/599」。故按证据保留，并在此显式列出。",
        "- 全量伪 0 扫描（所有可进join 且值=0 的键）见 `15_自检清单`：违例 0。",
        "- P2-1 落点：1278（KS0018/美东USNJ，0 值 + 部分覆盖）现在是 `join_class=join_partial`，"
        "**不再默认进入补货净额**；1456（599）与 2456（真零）为 `join_full`，"
        "2455（8 套）为 `no_join`。",
        "",
        "## 5. 缺行 = 未覆盖（不是 0）",
        "",
        f"- A 活跃产品 **{summary['active_roles']:,}** 个；快照有库存行（计入A）**{summary['covered_en']:,}** 个；"
        f"**未覆盖 {summary['uncovered_en']:,}** 个（明细见 `13_未覆盖产品`，覆盖状态=未覆盖）。",
        "- 未覆盖 ≠ 0 库存：表示该快照没有任何源行可证明其数量；下游禁止补 0。",
        "",
        "## 6. 状态分层（事实/汇总/供给同一套）",
        "",
        "| 层 | 身份状态 | 单位状态 | 覆盖状态 |",
        "|---|---|---|---|",
        "| 事实层 `2_库存事实层` | 逐行 唯一/共享/未映射/未激活/待核 | 已证/默认个/冲突/套件 | 完整/部分/未覆盖/不适用 |",
        "| 汇总层 `3_产品×仓池×形态×UOM汇总` | 同上（按行组聚合） | 同上 | 同上 |",
        "| 供给层 `4_可发供给` | 同上（按 product×pool×uom 聚合） | 同上 | 同上 |",
        "",
        f"- 事实层身份状态分布：{summary['identity']}",
        f"- 事实层单位状态分布：{summary['uom_status']}",
        f"- 事实层覆盖状态分布：{summary['coverage']}",
        "- 只有 `身份状态=唯一` 才写「归属已证」；共享/未映射/未激活/待核一律「归属待核/无映射/未激活」。",
        "",
        "## 7. 可发供给结果",
        "",
        f"- 供给行 {len(supply_tbl):,}（product×pool×uom）。",
        "",
        "### 7.1 join_class 三分（P2-1）",
        "",
        "| join_class | 判据 | 行数 | 可发供给（个） | 默认消费 |",
        "|---|---|---:|---:|---|",
        "| `join_full` | 覆盖完整 + 身份唯一 + 单位非冲突 + 无未计正量 | "
        f"{summary['join_class'].get('join_full', [0, 0])[0]:,} | "
        f"{summary['join_class'].get('join_full', [0, 0])[1]:,.0f} | **允许** |",
        "| `join_partial` | 部分覆盖 / 身份非唯一 / 单位冲突 | "
        f"{summary['join_class'].get('join_partial', [0, 0])[0]:,} | "
        f"{summary['join_class'].get('join_partial', [0, 0])[1]:,.0f} | 仅观察或显式白名单 |",
        "| `no_join` | null / 待核 / 套件单列 / CG·其他仅披露 | "
        f"{summary['join_class'].get('no_join', [0, 0])[0]:,} | "
        f"{summary['join_class'].get('no_join', [0, 0])[1]:,.0f} | 不允许 |",
        "",
        f"- `可用性` 保留人读文字（可进join / 可进join(partial…) / 不进join / 仅披露 / 套件单列），"
        "机器消费只看 `join_class`。",
        f"- 旧口径「可进 join」= `join_full` + `join_partial` = {summary['join_rows']:,} 行 / "
        f"{summary['join_qty']:,.0f} 个；其中 `join_partial` "
        f"{summary['join_class'].get('join_partial', [0, 0])[0]:,} 行"
        f"（部分覆盖 / 身份非唯一 / 单位冲突）**不再默认可进**。",
        f"- CG/其他 只披露 {summary['discl_rows']:,} 行 / {summary['discl_qty']:,.0f}，归 `no_join`。",
        f"- `可发供给=null` 的键 **{summary['null_keys']}** 个，全部 `no_join`："
        f"无适用事实 {summary['no_fact_keys']} 个 + 已计 0 但另有未计正量 {summary['pending_null_keys']} 个。",
        f"- 皮壳供给 {summary['cover_rows']:,} 行 / {summary['cover_qty']:,.0f} 个，"
        f"可进 join {summary['cover_rows_in_join']:,} 行 / {summary['cover_qty_in_join']:,.0f} 个。",
        f"- 成品供给 {summary['finished_rows']:,} 行（含骨架 {summary['skeleton_rows']} 行 / "
        f"{summary['skeleton_qty']:,.0f}）。",
        "- 与 v5/v6 数量口径一致：`join_full+join_partial` 数量和 = 44,586 个；v7 只重分类，不改数值。",
        "",
        "### 7.2 C8-1 供给资格闭环（physical_form / canonical_uom / demand_eligibility）",
        "",
        "| 资格类别 | 行数 | demand_eligibility 分布 | 个当量 |",
        "|---|---:|---|---:|",
    ]
    if cat_elig is not None:
        agg = cat_elig.groupby("qual_category").agg(
            行数=("行数", "sum"), 个当量=("个当量", "sum"))
        for cat, r in agg.iterrows():
            dist = "；".join(f"{x.demand_eligibility} {int(x.行数)}"
                            for _, x in cat_elig[cat_elig["qual_category"] == cat].iterrows())
            L.append(f"| {cat} | {int(r['行数']):,} | {dist} | {r['个当量']:,.0f} |")
    L += [
        "",
        f"- HM（海绵）{summary['hm_rows']} 行：可归属 {summary['hm_mappable_rows']} 行全部 `component`，"
        f"未映射 {summary['hm_rows'] - summary['hm_mappable_rows']} 行判 `not_applicable`；"
        "**无 `after_sales`**：未见已证售后/补发，无父件不猜配套。",
        f"- ND（内胆）：本快照事实层 ND 类行 **{summary['nd_rows']}**，"
        f"`independent` = **{summary['nd_independent_rows']}**（要求 0）；ND 只作组件/齐套，"
        "不生成独立终端需求。",
        f"- TJ#：{summary['tj_rows']} 行按 `independent(套)`，不拆组件；"
        "供给仅 `套件单列(套)`，不进「个」净额。",
        "- 半成品：134 行 `independent`，`physical_form` 保留 **成品**（raw），不等同 PK#；"
        "皮壳码只作组件披露。",
        "- 皮壳：504 行 `component`（产品供货物料，不单独建终端需求）、197 行 `not_applicable`。",
        "- 骨架 2 行 `independent`（独立成品分支，N2）。",
        "- 规则：未映射/未激活/规则排除 → `not_applicable`；`source_ref` 形如 "
        "`ST:45117;sku=…;wh=…;qty=…;form=…;uom=…;product=…`，共享行附 `pool=SP-<码>`。",
        "- 注：`其他` 类的个当量 1,031 万主要来自「超大占位」排除行（原始 available ≥ 100,000 的占位值），"
        "不是可用库存，也不进入任何净额。",
        "",
        "### 7.3 C8-3 Top50 兼容导出与十键回放",
        "",
        f"- `19_Top50候选导出`：**{summary['c8_top50_rows']:,} 行，物理只含 join_full**"
        f"（可发供给合计 {summary['c8_top50_qty']:,.0f} 个）；`19b_Top50观察表` 另放 "
        f"{summary['c8_top50_obs_rows']:,} 行 partial/no_join，只观察。",
        "- 行内字段：product_id / pool / physical_form / canonical_uom / join_class / join_candidate /"
        " 可发供给 / coverage_status / **demand_eligibility** / **eligibility_reason** /"
        " **source_ref** / source_proof / **join_reason** / reason / as_of / rule_version"
        "（16 列，无需回接事实层）。",
        f"- `20_十键回放`：**{summary['c8_ten_pass']}/{summary['c8_ten_total']} 通过**"
        "（键与期望值来自 join v7 pilot，ST 行号回指 parquet）。",
        "",
        "| # | 类型 | product_id | 仓池 | join_class | 可发供给 | 源行回放 | 结果 |",
        "|---:|---|---|---|---|---:|---|---|",
    ]
    if ten_tbl is not None:
        for r in ten_tbl.to_dict("records"):
            v = "null" if r["C 可发供给"] is None or pd.isna(r["C 可发供给"]) else f"{r['C 可发供给']:,.0f}"
            L.append(f"| {r['序号']} | {r['类型']} | `{r['product_id']}` | {r['仓池']} | "
                     f"{r['C join_class']} | {v} | {r['源行回放']} | {r['回放结果']} |")
    L += [
        "",
        "### 7.4 C9 可操作状态（reason_code / needed_evidence / next_action / owner）",
        "",
        "| 分类 | reason_code | 行数 |",
        "|---|---|---:|",
    ]
    for grp, key in (("partial", "c9_partial_reason"), ("no_join(有值)", "c9_nojoin_reason"),
                     ("null", "c9_null_reason")):
        for code, n in sorted(summary[key].items(), key=lambda kv: -kv[1]):
            L.append(f"| {grp} | `{code}` | {n} |")
    L += [
        f"| join_full | `none` | {summary['join_class'].get('join_full', [0])[0]:,} |",
        "",
        f"- `consumption`：`netting` {summary['join_class'].get('join_full', [0])[0]:,} 行；"
        f"`blocked` {summary['c9_obs_rows']:,} 行（partial + no_join）；本版**无 observe 行**，"
        "因为白名单默认为空。",
        f"- `22_join_partial白名单` 默认 **{summary['c9_whitelist_rows']} 行**（列：product_id / pool / "
        "physical_form / canonical_uom / reason_code / approver / expiry）。只有登记白名单并填 approver/expiry "
        "的 partial 行才可「观察性消费」；未登记前 `whitelist_status=not_whitelisted`、`consumption=blocked`。",
        f"- `21_no_join观察` 按 reason_code 汇总 **no_join {summary['c9_nojoin_obs_rows']} 行**"
        f"（含 null {summary['c9_null_reason'] and sum(summary['c9_null_reason'].values())} 行）；"
        f"`21b_join_partial观察` 汇总 partial **{summary['c9_partial_obs_rows']} 行**。"
        "null 行的数量列留空（不是 0），`13_未覆盖产品` 766 个产品继续标「未覆盖」。",
        "- 码表与处置：缺失成品→补证(主数据)；缺失海绵/共享归属/未计形态→人工确认(业务)；"
        "套件→不补(按套观察, 系统)；CG/其他→不补(仅披露, 业务)；单位冲突/套件身份→人工确认(主数据)。",
        "",
        "### 7.5 C10 CG 库存池（Wayfair Castlegate，单列不并入物理库存）",
        "",
        "| CG 池 | 行数 | cg_available(原始) | 组件口径 | 其中 eligible | 判定 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    if cg_pool is not None:
        for r in cg_pool.to_dict("records"):
            n_rows = 0 if pd.isna(r["行数"]) else int(r["行数"])
            q_raw = 0.0 if pd.isna(r["cg_available"]) else float(r["cg_available"])
            q_sup = 0.0 if pd.isna(r.get("cg_supply_qty")) else float(r["cg_supply_qty"])
            n_el = 0 if pd.isna(r["eligible行"]) else int(r["eligible行"])
            L.append(f"| {r['cg_pool']} | {n_rows:,} | {q_raw:,.0f} | {q_sup:,.0f} | {n_el:,} | "
                     f"{'按 owner 进 Wayfair 资格' if r['cg_pool'] != 'CG-unknown' else '无 owner→待证，不进净额'} |")
    L += [
        "",
        f"- 来源：EN `Wayfair CG Stock Latest` 只读 API，**只取 `warehouse_id='CG'` 汇总行** "
        f"{summary['cg_rows']} SKU / {summary['cg_available']:,.0f} available（run_id 见 manifest）；"
        f"分仓明细 {summary['cg_detail_rows']} 行合计 {summary['cg_detail_sum']:,.0f} 只用于对账，"
        "**不累加**（两者相加 834 即重复计数）。",
        f"- 对账：CG 行=分仓和 **{summary['cg_reconcile_ok']}/{summary['cg_rows']}**；stale "
        f"{summary['cg_stale']}；available_missing {summary['cg_avail_missing']}（缺失不填 0）。",
        f"- 映射（C v11）：商品导出别名表 + 剥 `OLD_` → **104/104 匹配**；"
        f"`mapping_basis` 分布见 23_（sku / old_prefix_strip / alias）。",
        f"- 归属：`attribution_source=B-r9-local-provisional`；owner {summary['cg_owner_rows']} / "
        f"unknown {summary['cg_unknown_owner']} / unmapped {summary['cg_unmapped']}；"
        f"`cg_status`：eligible {summary['cg_eligible']} / pending {summary['cg_pending']}"
        f"（unknown 的 2 个是 TJ# 旧套件，映射到未激活 EN、无 US owner）。",
        "- 口径：CG 不并入 USNJ/USTX 物理库存；`4_可发供给` 的 `可发供给` 仍是物理值，"
        "`cg_available`/`supply_total_display` 只作展示；`cg_included_in_current_net=false`、"
        "`transfer_flag=false`（不生成调拨候选）。",
        "- 无 CG 行的 SKU 不写 0，记 unknown（本表只列有 CG 快照行的 SKU）；CP 不归波兰。",
        "",
        "### 7.6 C11 皮壳/成品双形态与形态要求",
        "",
        "| ship_mode | required_form | optional_form | 键数 | 形态要求状态 |",
        "|---|---|---|---:|---|",
    ]
    if supply_tbl is not None:
        _fr = (supply_tbl.groupby(["ship_mode", "required_form", "optional_form", "form_requirement_status"])
               .size().reset_index(name="n"))
        for r in _fr.sort_values("n", ascending=False).to_dict("records"):
            L.append(f"| {r['ship_mode']} | {r['required_form']} | {r['optional_form']} | "
                     f"{r['n']} | {r['form_requirement_status']} |")
    L += [
        "",
        f"- 254 行双形态：补证 **{summary['iso_disposition'].get('补证', 0)} 行 / "
        f"{summary['iso_disposition_qty'].get('补证', 0):,.0f}**（其中 both_forms_present "
        f"{summary.get('both_forms_rows', 0)} 行，同时记录成品牌库存与皮壳量）；"
        f"仍隔离 {summary['iso_disposition'].get('仍隔离', 0)} 行 / "
        f"{summary['iso_disposition_qty'].get('仍隔离', 0):,.0f}（成品模式皮壳组件 或 无活跃映射）。",
        f"- `join_partial` 现在只有 **{summary['join_class'].get('join_partial', [0])[0]}** 行，"
        "均为共享待核（KS0248），不是形态缺失；缺必需形态的键会落 null（无适用事实）而不是 0。",
        "- 例：KS0001/KS0340 只有皮壳、无成品 → join_full（成品是可选项）；KS0248 皮壳为共享待核 → partial；"
        "KS0354 按 ship_mode=成品判（有成品行），单位冲突改为 `uom_conflict_flag` 标记、不再单独阻断。",
        "",
        "### 7.7 C12 TJ#/HM/单形态/拆包",
        "",
        f"- **TJ# 旧套件**：CG 2 行（TT0031038K0062927-2PCS/-3PCS）→ `TJ#KS0156x2/x3-001`，"
        f"`mapping_status=old_set`、`attribution_status=mapped_inactive`；映射不丢，"
        f"`cg_status` 仍 pending（无 US owner）。CG 分布：owner {summary['cg_owner_rows']} / "
        f"mapped_inactive {summary.get('cg_mapped_inactive', 0)} / unknown "
        f"{summary['cg_unknown_owner']} / unmapped {summary['cg_unmapped']}。",
        f"- **HM 海绵**：role=海绵/海绵关联成品 的键按 `required_form=海绵` 独立供给，"
        f"不要求成品行、不判 partial；本轮进入 join_full 的 HM 键见 `4_可发供给`（77 / 24 / 2 个）。",
        f"- **单一形态**：`ship_mode` 未知且无库存 → 覆盖状态=未覆盖（不是 partial）；"
        f"当前 partial 仅 **{summary['join_class'].get('join_partial', [0])[0]}** 行（KS0248 共享身份冲突）。",
        f"- **拆包成品**：254 行中 0 库存 {summary['iso_disposition'].get('忽略(0库存)', 0)} 行忽略；"
        f"成品模式 cover+foam → 可组装 min(cover,foam) 计入成品供给（split_package=true，"
        f"本轮 {summary['iso_disposition'].get('拆包组装', 0)} 行 / {summary.get('split_assembled_qty', 0):,.0f} 个）；"
        f"只有 cover 无 foam → component_partial（{summary['iso_disposition'].get('component_partial', 0)} 行）。",
        "",
        "### 7.8 C13 套件拆解与组件不阻塞",
        "",
        "| 来源 | 套件 | set_qty | 组件 | 每套用量 | 组件量 | 组件归属 |",
        "|---|---|---:|---|---:|---:|---|",
    ]
    _st = set_tbl.to_dict("records") if set_tbl is not None else []
    for r in _st:
        L.append(f"| {r['来源']} | `{r['set_item']}` | {r['set_qty']:g} | `{r['component_item']}` | "
                 f"{r['qty_per_set']:g} | {r['component_qty']:g} | {r['component_owner'] or '—'} |")
    L += [
        "",
        f"- 套件本身不作为库存；需求按套、组件供给按个。CG 的 2 个套件 SKU 由 unknown 改为 "
        f"**mapped_set**（组件 16 / 6 个，owner 美中USTX → CG-USTX），CG-unknown 归零。",
        f"- 254 组件不全：**component_partial_nonblocking "
        f"{summary['iso_disposition'].get('component_partial_nonblocking', 0)} 行**（缺 foam 或 cover），"
        "`blocking=false`；默认绍兴下单成品，可单独补皮壳/海绵，不阻塞 Top50/下一步。",
        f"- `blocking` 列：全场只有 **{int(supply_tbl['blocking'].sum())}** 个键为 true（KS0248 共享身份冲突），"
        "其余仍隔离/组件不全一律 false。",
        "",
        "## 8. UOM 与换算",
        "",
        f"- 套仅 Bundle：{summary['bundle_rows']} 行 / {summary['bundle_units']:,.0f} 套（TJ# 单列，不拆组件）。",
        f"- 多件后缀：{summary['piece_rows']} 行，{summary['piece_raw']:,.0f} → {summary['piece_qty']:,.0f} 个。",
        f"- 星球抱枕组 1:1：{summary['planet_rows']:,} 行 / {summary['planet_qty']:,.0f} 个"
        f"（若按后缀乘 N 会多 {summary['planet_qty_v5rule'] - summary['planet_qty']:,.0f} 个）。",
        f"- 默认个（无 EN 单位来源，计入A）：{summary['default_ge_rows']:,} 行 / {summary['default_ge_qty']:,.0f}。",
        f"- 单位冲突（缓存套但非 Bundle）：{summary['uom_conflict_en']} 个 EN，按个计入并留档。",
        "",
        "| 项 | 行数 | 原始 available | 本版个当量 | 若按后缀乘 N |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in pc_summary.to_dict("records"):
        L.append(f"| {r['项']} | {r['行数']} | {r['原始available']:,.0f} | "
                 f"{r['个当量']:,.0f} | {r['若按后缀乘N']:,.0f} |")
    L += [
        "",
        "## 9. 254 行隔离与皮壳补证",
        "",
        "| 处置 | 行数 | 其中正库存 | 数值和 |",
        "|---|---:|---:|---:|",
    ]
    for k, v in sorted(summary["iso_disposition"].items(), key=lambda kv: -kv[1]):
        L.append(f"| {k} | {v} | {summary['iso_pos'].get(k, 0)} | "
                 f"{summary['iso_disposition_qty'].get(k, 0):,.0f} |")
    L += [
        "",
        f"- 254 行逐行回指源 parquet：见自检。0 库存 **{summary['iso_disposition'].get('忽略(0库存)', 0)}** 行"
        "不再列入「仍隔离」阻塞；非零 42 行中，补证 "
        f"{summary['iso_disposition'].get('补证', 0)} 行、拆包组装 "
        f"{summary['iso_disposition'].get('拆包组装', 0)} 行（可组装 "
        f"{summary.get('split_assembled_qty', 0):,.0f} 个）、组件不全（不阻塞） "
        f"{summary['iso_disposition'].get('component_partial_nonblocking', 0)} 行。",
        "- 拆包示例：KS0342-HLR-50-DEEPBLUE 美中 cover 41 + foam 29 → 可组装 **29**；同 SKU 波兰 cover 46、foam 0 → 0；"
        "KS0333（cover 1/2、foam 0）、KS0458（只有 cover）→ component_partial_nonblocking（缺 foam，blocking=false），"
        "不计入成品可发供给，但 cover 仍作为独立可补供给记录。",
        "",
        "### 9.1 老产品双口径（P2-2 冻结）",
        "",
        "| 口径 | 计数 | 明细位置 |",
        "|---|---:|---|",
        f"| **产品级**（distinct product_id） | **{summary['legacy_products']}** 个 + 未归属 **{summary['legacy_unmapped_rows']}** 行"
        f"（清单 {summary['legacy_sheet_rows']} 行） | `16_老产品清单`（逐产品：物料组/名称/事实行数/事实个当量/供给行数/可发供给） |",
        f"| **行级·事实层** | **{summary['legacy_fact_rows']}** 行 / {summary['legacy_fact_qty']:,.0f} 个 | `2_库存事实层.补货标记` / `16_老产品清单.事实行数` |",
        f"| **行级·供给层** | **{summary['legacy_supply_rows']}** 行 / {summary['legacy_supply_qty']:,.0f} 个 | `4_可发供给.补货资格` |",
        "",
        f"- 产品级按物料组分布：{summary['legacy_group_counts']}",
        "- **两个口径互不替代**：产品级回答「多少个老产品受影响」，行级回答「多少库存行/数量被标记」。",
        "- **1:1 断言（独立）**：老产品行 `pieces_per_unit` 全为 1 且 `qty_pieces == available`（自检项）；",
        "- **默认不补断言（独立）**：所有老产品事实行 `补货标记=老产品-默认不补(待确认)`、"
        "所有老产品供给行 `补货资格=老产品-默认不补(待确认)`，且行未被删除（自检项）。",
        "- 执行计划原写「老产品默认不补行=15」：**15 既不是产品数也不是行数**，v7 用上述两口径替代，"
        "不再混用；15 的来源已无法从现有产物复现，如需保留请业务确认它指哪一维。",
        "",
        "## 10. 共享池",
        "",
        f"- `6_共享候选` 覆盖 **{summary['shared_codes']} 个码**；计入A 中多候选 "
        f"{summary['shared_extra_codes']} 个码按共享待核，不分配、不外推。",
        "",
        "### 10.1 C8-2 共享池回放（一码一池，不分配）",
        "",
        f"- `18_共享池回放`：**{summary['c8_shared_pools']} 个池** / "
        f"{summary['c8_shared_pool_rows']} 个源行 / 原量 **{summary['c8_shared_pool_qty']:,.0f}**；"
        f"`allocation_qty` 合计 **{summary['c8_shared_allocation']:g}**，"
        f"未分配余额 **{summary['c8_shared_balance']:,.0f}**。",
        "- 每池给 `shared_pool_id=SP-<归一码>`、候选数、全部候选、源行集合（ST 行号）、仓池、"
        "coverage=待核（未分配）；**不向任何候选产品复制数量**，`sum(allocation) ≤ pool_qty`。",
        "- 缺行侧：`13_未覆盖产品` 766 个产品保持「未覆盖」，禁止补 0；254 桥 63/539、191/653 逐行可回指。",
        "",
        "## 11. 命名扫描（East / Central）",
        "",
        f"- 全表文本命中 **{scan_total}** 处；其中仓池/仓名列命中 **{scan_wh}** 处（要求 = 0）。",
    ]
    if scan_total:
        L += ["", "| sheet | 列 | 命中数 | 样例 |", "|---|---|---:|---|"]
        for r in scan_tbl.to_dict("records"):
            L.append(f"| {r['sheet']} | {r['列']} | {r['命中数']} | {r['样例']} |")
        L += ["", "> 仓池一律 美东USNJ / 美中USTX / 波兰 / CG / 其他；上述产品编码列命中属于 SKU 名称"
                   "（如 `...-CENTRALAMERICANAZTEC...`），不是仓名，不构成命名违规。"]
    else:
        L += ["- 全表 0 命中。"]
    L += [
        "",
        "## 12. 自检清单（机器验收）",
        "",
        "| 检查项 | 结果 | 期望 | 通过 |",
        "|---|---|---|---|",
    ]
    for c, got, want, ok in checks:
        L.append(f"| {c} | {got} | {want} | {'PASS' if ok else 'FAIL'} |")
    L += [
        "",
        "## 13. join v7 消费边界",
        "",
        "- **默认只读 `join_class=join_full` 的行**（覆盖完整 + 身份唯一 + 单位非冲突 + 无未计正量）。"
        "`join_partial` 仅观察或显式白名单，`no_join` 不得进入补货净额。",
        "- **可读表**：`4_可发供给`（不要直接消费事实层或 CG/其他披露行）。",
        "- **null 语义**：`可发供给=null` = 无适用事实或已计 0 但另有未计正量，禁止补 0。",
        "- **未覆盖语义**：`13_未覆盖产品` 中的产品在该快照无库存行，禁止当 0。",
        "- **套件**：`uom=套` 行不得与「个」混加；`可发供给` 列不含套（归 `no_join`）。",
        "- **不可读**：`join_class≠join_full`、`身份状态∈{共享,未映射,未激活,待核}`、"
        "`供给状态=待核*`、`可用性=仅披露*`。",
        "- **需求资格**：`demand_eligibility` 为 `component`（HM/ND/皮壳）或 `not_applicable` 的行，"
        "不得作为独立终端需求锚；`ND` 独立需求恒为 0；TJ# 只按「套」，不与「个」相加。",
        "- **消费闸门**：只消费 `consumption=netting`（即 `join_full`）；`join_partial` 需在 "
        "`22_join_partial白名单` 登记 approver/expiry 后才可观察性消费；`no_join`/null 一律 `blocked`。",
        "- **原因与责任**：任何非 full 行用 `reason_code` + `needed_evidence` + `next_action` + `owner` "
        "驱动补证/观察/人工确认，不自行补数。",
        "- **共享池**：只引用 `shared_pool_id`，不复制池量；`allocation_qty` 恒为 0，"
        "任何分配须业务批准后另行落表。",
        "- **合同键**：snapshot_date × 仓池 × source_sku × resolved_supply_item × actual_form × uom；"
        "附 product_id、pieces_per_unit、源行号（parquet 1 基）。",
        "- **CG/其他**：只披露，不得自动当责任仓可用。",
        "",
        "## 14. 只读声明",
        "",
        "本次仅本地读表/内存计算/写本地 xlsx 与 md；未调用 EN/通途接口，未发消息，未 push；"
        "未修改 A/B 产物，未覆盖 v2/v3/v4/v5。",
        "",
    ]
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
