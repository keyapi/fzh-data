# -*- coding: utf-8 -*-
"""批量翻译：属性值表 / 物料组 的中文名 → 对应翻译字段（腾讯云 TMT）。

凭证读站点单 `Tencent TMT Settings` + `utils/tmt_translate.py`（服务端，无需外部密钥）。

已接入（--target 三选一）：
  - foam-size : Item Attribute Value All Foam Size.attribute_value → foam_size_translation（海绵尺寸）
  - fabric    : Item Attribute Value All Fabric.attribute_value    → fabric_translation（面料）
  - item-group: Item Group.item_group_name（「产品」子树叶子/LGKS） → item_group_translation（物料组）

设计要点（用户要求）：
  - **已有译文一律跳过**，绝不覆盖 → 同一个中文值永远对应同一个译文；
  - **译文规范化**：命中 `TERM_OVERRIDES` 的中文值直接用批准的英文；其余统一句首大写
    （避免 TMT 对同一中文词给出 combination/combined、Arc/Curved、大小写参差等措辞波动）；
  - 海绵尺寸：中文名末尾的尺寸（「（153cm）」「153cm」「153x60x10cm」）先剥掉再翻，
    尺寸数字由报关导出侧用编码里的尺寸另拼，避免重复/口径不一；
  - 失败不阻断整批，记 Error Log 并在返回值里回报；逐条限速（TMT 5 次/秒）。

调用（REST）：
  POST /api/method/delivery_plan.api.translate_api.batch_translate_foam_sizes?dry_run=1
  POST /api/method/delivery_plan.api.translate_api.batch_translate_fabrics?dry_run=1
  POST /api/method/delivery_plan.api.translate_api.batch_translate_item_groups?dry_run=1
  POST /api/method/delivery_plan.api.translate_api.renormalize_foam_sizes?dry_run=1
"""
from __future__ import annotations

import re
import time

import frappe

from delivery_plan.utils.tmt_translate import translate_text_zh_en

# 与 EN_API/translate_item_group_names.py 的 strip_trailing_size 保持一致
_SIZE_TAIL_RE = re.compile(
    r"(?:"
    r"[（(][^（()）]*\d[^（()）]*[)）]"
    r"|\d+(?:\.\d+)?(?:[xX×*]\d+(?:\.\d+)?)+(?:cm|CM)?"
    r"|\d+(?:\.\d+)?(?:cm|CM)"
    r")\s*$"
)

FOAM_DT = "Item Attribute Value All Foam Size"
FOAM_ZH_FIELD = "attribute_value"
FOAM_EN_FIELD = "foam_size_translation"

FABRIC_DT = "Item Attribute Value All Fabric"
FABRIC_ZH_FIELD = "attribute_value"
FABRIC_EN_FIELD = "fabric_translation"

ITEM_GROUP_DT = "Item Group"
ITEM_GROUP_ZH_FIELD = "item_group_name"
ITEM_GROUP_EN_FIELD = "item_group_translation"

TMT_QPS_SLEEP = 0.25  # 5 次/秒

# 规范大小写时永不小写化的词（品牌/专有名词）；新款品牌词在此追加。
# 注意：这里**不要**放 "Foam" —— 物料词由 WORD_RULES 在大小写之后产出，自然保住大写；
# 若放进来，TMT 对「泡沫」等其它词偶然给出的 "Foam" 也会被保住，句中大写就不一致了。
CASE_KEEP = {"BBL", "BetterRest", "DoubleLoop"}

# 同一中文词的固定英文写法（人工审过）。键 = 去尾部尺寸后的中文值。
# 只放「TMT 措辞会漂移」或「明显误译且已确认」的条目，其余走 normalize_case。
TERM_OVERRIDES: dict[str, dict[str, str]] = {
    "foam-size": {
        # 靠枕 → headrest（TMT 对「床头靠枕」会给 pillow）
        "悬挂式床头靠枕": "Hanging bedside headrest",
        "分段式床头靠枕": "Segmented bedside headrest",
        # 组合 → combination；可组合 → modular
        "组合侧睡枕": "Combination side sleeping pillow",
        "组合趴睡枕": "Combination sleeping pillow",
        "瑜伽组合沙发": "Yoga combination sofa",
        "儿童泡沫攀岩块-组合小山丘": "Children's foam rock climbing block-combination hill",
        "梯形单元组合沙发（坐垫）": "Trapezoidal unit combination sofa (cushion)",
        "梯形单元组合沙发（靠背）": "Trapezoidal unit combination sofa (backrest)",
        "可组合扶手沙发（靠背）": "Modular armrest sofa (backrest)",
        "可组合扶手沙发（扶手）": "Modular armrest sofa (armrest)",
        # 弧形 → arc
        "带半圆柱弧形海绵靠枕": "Semi-cylindrical arc Foam headrest",
        "弧形靠枕优化版": "Arc headrest optimized version",
        # 坐墩 → seat
        "几何坐墩椭圆形": "Geometric seat ellipse",
        "几何坐墩梯形": "Geometric seat trapezoid",
        "坐墩三角款": "Triangular seat",
        # 组合 → combination（TMT 对这条给了 assembly）
        "床头软装组合-靠背": "Bedhead soft combination-backrest",
        # 折叠沙发床 → folding sofa bed（TMT 单条给过 pullout sofabed）
        "折叠沙发床": "Folding sofa bed",
        # 嗅闻趴趴垫 → snuffle mat（TMT 把「趴趴」误读成 party）
        "宠物嗅闻趴趴垫": "Pet snuffle mat",
    },
    "fabric": {},
    "item-group": {
        # TMT 会把「海绵」翻成 sponge，业务要 Foam（与海关导出的物料组口径一致）
        "海绵": "Foam",
    },
}

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'’\-]*")

# 中文含某词时，把英文里的固定写法替换掉。在大小写规范化**之后**执行，所以保持给定大小写。
# 顺序敏感：更具体的词必须排在前面（如「可组合」含「组合」）。
# 规则要能自愈（把 TMT 的各种同义写法都列进正则），否则第二遍 normalize_case 后就回不去，
# 回刷会不幂等。
WORD_RULES: dict[str, tuple[tuple[str, str, str], ...]] = {
    "foam-size": (
        ("可组合", r"\b(?:composable|combined|combination|assembly)\b", "modular"),
        ("组合", r"\b(?:composable|combined|combination|assembly)\b", "combination"),
        ("靠枕", r"\b(?:pillow|cushion)\b", "headrest"),
        ("弧形", r"\b(?:curved|arc-shaped)\b", "arc"),
        ("坐墩", r"\babutment\b", "seat"),
        # 描述里的「海绵」与物料组前缀 Foam 统一（TMT 会给 sponge）
        ("海绵", r"\b(?:sponge|foam)\b", "Foam"),
    ),
    "fabric": (),
    "item-group": (),
}


def strip_trailing_size(zh: str) -> str:
    """去掉中文名末尾的尺寸（带括号或裸尾缀），只留描述部分。"""
    return _SIZE_TAIL_RE.sub("", (zh or "").strip()).strip()


def _cap_first(s: str) -> str:
    """把第一个字母大写（句首）。"""
    m = re.search(r"[A-Za-z]", s or "")
    if not m:
        return s or ""
    i = m.start()
    return s[:i] + s[i].upper() + s[i + 1:]


def normalize_case(en: str) -> str:
    """统一为句首大写（sentence case）：其余字母小写，仅保留缩写与 CASE_KEEP 中的词。

    'carambola multifunctional headrest' → 'Carambola multifunctional headrest'
    "Children's Foam Rock Climbing Block-Arch Bridge Set"
        → "Children's foam rock climbing block-arch bridge set"
    'U-lock sofa' → 'U-lock sofa'（首词）
    """
    def _fix(m: re.Match) -> str:
        tok = m.group(0)
        core = tok.strip("'’-")
        if core in CASE_KEEP or (len(core) > 1 and core.isupper()):
            return tok
        return tok.lower()

    return _cap_first(_TOKEN_RE.sub(_fix, en or ""))


def _finalize(en: str, zh: str, target: str) -> str:
    """TMT 结果 → 最终入库值。**顺序敏感**：术语表 → 大小写 → 词形规则 → 补句首大写。

    词形规则写的是小写规范词（组合→combination），放在大小写之后，最后再补一次句首大写；
    这样「海绵→Foam」能保住大写，而 TMT 对别的词偶然给的句中 "Foam" 会被压成小写（一致）。
    """
    en = (en or "").strip()
    if not en:
        return ""
    en = normalize_case(TERM_OVERRIDES.get(target, {}).get(zh) or en)
    for kw, pat, repl in WORD_RULES.get(target, ()):
        if kw in (zh or ""):
            en = re.sub(pat, repl, en, flags=re.IGNORECASE)
    return _cap_first(en)


def _item_group_rows() -> list[dict]:
    """「产品」子树下的叶子物料组（is_group=0 的叶子 + is_leaf_group=1 的 LGKS）。"""
    rows = frappe.get_all(
        ITEM_GROUP_DT,
        fields=["name", "item_group_name", "parent_item_group", "is_group",
                "is_leaf_group", ITEM_GROUP_EN_FIELD],
        limit_page_length=0,
    )
    idx = {r["name"]: r for r in rows}
    seen_ok: set[str] = set()

    def _under_product(name: str) -> bool:
        seen: set[str] = set()
        cur = name
        while cur and cur in idx and cur not in seen:
            if cur == "产品":
                return True
            seen.add(cur)
            cur = (idx[cur].get("parent_item_group") or "").strip()
        return False

    out: list[dict] = []
    for r in rows:
        name = r["name"]
        if not name or name == "产品" or not _under_product(name):
            continue
        if int(r.get("is_group") or 0) != 0 and int(r.get("is_leaf_group") or 0) != 1:
            continue
        if name in seen_ok:
            continue
        seen_ok.add(name)
        out.append({
            "name": name,
            "abbr": "",
            "zh": (r.get(ITEM_GROUP_ZH_FIELD) or name),
            "en": r.get(ITEM_GROUP_EN_FIELD) or "",
        })
    return out


def _claim_rows(target: str) -> list[dict[str, str]]:
    """取该目标的行，统一成 {name, abbr, zh, en} 形状。"""
    if target == "item-group":
        return _item_group_rows()

    dt, zh_field, en_field = {
        "foam-size": (FOAM_DT, FOAM_ZH_FIELD, FOAM_EN_FIELD),
        "fabric": (FABRIC_DT, FABRIC_ZH_FIELD, FABRIC_EN_FIELD),
    }[target]

    rows = frappe.get_all(dt, fields=["name", zh_field, "abbr", en_field],
                          limit_page_length=0)
    return [{"name": r["name"], "abbr": r.get("abbr") or "",
             "zh": r.get(zh_field) or "", "en": r.get(en_field) or ""}
            for r in rows]


def _target_dt(target: str) -> str:
    return {"foam-size": FOAM_DT, "fabric": FABRIC_DT, "item-group": ITEM_GROUP_DT}[target]


def _preflight() -> None:
    """整批开跑前的自检：凭证/SDK 不可用时直接抛一次，别逐条刷几百条 Error Log。"""
    s = frappe.get_single("Tencent TMT Settings")
    if not s.get("enabled"):
        frappe.throw("Tencent TMT Settings 未启用")
    if not (s.get("tmt_secret_id") or "").strip() or not s.get_password("tmt_secret_key"):
        frappe.throw("Tencent TMT Settings 未配置 TMT 凭证（SecretId / SecretKey）")
    try:
        import tencentcloud  # noqa: F401
    except ImportError:
        frappe.throw(
            "服务端缺少 tencentcloud SDK："
            "cd /home/frappe/frappe-bench && env/bin/pip install tencentcloud-sdk-python-tmt"
        )


def _translate(target: str, dry_run=0, limit=None, full=0) -> dict:
    """公共批量引擎：空译文才翻、已有译文跳过、失败不阻断、逐条限速。

    full=1 时在返回值里给出**全部**译文（默认只给 12 条样例），配合 dry_run 可先审后写。
    """
    dry = int(dry_run or 0)
    want_full = int(full or 0)
    strip_size = target == "foam-size"
    dt = _target_dt(target)
    en_field = {"foam-size": FOAM_EN_FIELD, "fabric": FABRIC_EN_FIELD,
                "item-group": ITEM_GROUP_EN_FIELD}[target]

    rows = _claim_rows(target)
    todo = [r for r in rows if not (r.get("en") or "").strip()]
    skipped_existing = len(rows) - len(todo)
    if limit:
        todo = todo[: int(limit)]  # 先过滤再截断 → 可分批续跑
    if todo:
        _preflight()

    done = skipped_empty = 0
    failed: list[dict] = []
    samples: list[dict] = []
    results: list[dict] = []
    for i, r in enumerate(todo, 1):
        zh = strip_trailing_size(r.get("zh") or "") if strip_size else (r.get("zh") or "").strip()
        if not zh:
            skipped_empty += 1
            continue
        try:
            en = _finalize(translate_text_zh_en(zh), zh, target)
        except Exception as e:
            failed.append({"name": r["name"], "zh": zh, "error": str(e)[:200]})
            frappe.log_error(frappe.get_traceback(), f"TMT 批量翻译失败 {r['name']}")
            continue
        if not en:
            failed.append({"name": r["name"], "zh": zh, "error": "空译文"})
            continue
        if not dry:
            frappe.db.set_value(dt, r["name"], en_field, en)
        done += 1
        if len(samples) < 12:
            samples.append({"abbr": r.get("abbr"), "zh": zh, "en": en})
        if want_full:
            results.append({"abbr": r.get("abbr"), "zh": zh, "en": en})
        if i < len(todo):
            time.sleep(TMT_QPS_SLEEP)

    if not dry:
        frappe.db.commit()

    return {
        "target": f"{dt}.{en_field}",
        "dry_run": bool(dry),
        "total": len(rows),
        "translated": done,
        "skipped_existing": skipped_existing,
        "skipped_empty": skipped_empty,
        "failed": len(failed),
        "failures": failed[:20],
        "samples": samples,
        "results": results,
    }


@frappe.whitelist()
def batch_translate_foam_sizes(dry_run=0, limit=None, full=0):
    """海绵尺寸：attribute_value（去尾部尺寸）→ foam_size_translation。已有译文跳过。"""
    return _translate("foam-size", dry_run=dry_run, limit=limit, full=full)


@frappe.whitelist()
def batch_translate_fabrics(dry_run=0, limit=None, full=0):
    """面料：attribute_value → fabric_translation。已有译文跳过。"""
    return _translate("fabric", dry_run=dry_run, limit=limit, full=full)


@frappe.whitelist()
def batch_translate_item_groups(dry_run=0, limit=None, full=0):
    """物料组：item_group_name（「产品」子树叶子/LGKS）→ item_group_translation。已有译文跳过。"""
    return _translate("item-group", dry_run=dry_run, limit=limit, full=full)


@frappe.whitelist()
def get_translation_rules():
    """把术语表/大小写规则暴露给本地脚本（EN_API/translate_item_group_names.py）。

    单一来源 = 本模块。本地脚本不再手抄规则，避免两边漂移。
    """
    return {
        "case_keep": sorted(CASE_KEEP),
        "term_overrides": TERM_OVERRIDES,
        "word_rules": {t: [list(r) for r in rules] for t, rules in WORD_RULES.items()},
    }


@frappe.whitelist()
def renormalize_foam_sizes(dry_run=1, limit=None):
    """按术语表 + 句首大写，回刷**已有**的海绵尺寸译文（默认只报差异不写）。

    用于修正历史译文：TMT 对同一中文词的措辞漂移（combination/combined、Arc/Curved）
    与大小写参差。空译文不动，交给 batch_translate_foam_sizes。
    """
    dry = int(dry_run or 1)
    rows = frappe.get_all(
        FOAM_DT,
        fields=["name", "abbr", FOAM_ZH_FIELD, FOAM_EN_FIELD],
        limit_page_length=0,
    )
    changed: list[dict] = []
    for r in rows:
        before = (r.get(FOAM_EN_FIELD) or "").strip()
        if not before:
            continue
        zh = strip_trailing_size(r.get(FOAM_ZH_FIELD) or "")
        after = _finalize(before, zh, "foam-size")
        if after and after != before:
            changed.append({"name": r["name"], "abbr": r.get("abbr"),
                            "zh": zh, "before": before, "after": after})
    if limit:
        changed = changed[: int(limit)]
    if not dry:
        for c in changed:
            frappe.db.set_value(FOAM_DT, c["name"], FOAM_EN_FIELD, c["after"])
        frappe.db.commit()
    return {
        "dry_run": bool(dry),
        "scanned": len(rows),
        "changed": len(changed),
        "changes": changed,
    }
