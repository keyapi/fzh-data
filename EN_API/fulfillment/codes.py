"""输入解析：把用户给的字符串拆成 InputEntity，并自动判码型（蓝图 §2.2 / §2.3）。"""
from __future__ import annotations

import re

from .model import EntityResolution, InputEntity

_SEP = re.compile(r"[,,;;\n]+")
# EN 物料码特征：含 '#'（PK#/ND# 皮壳/内胆）或形如 KS0001-…（成品/变体）
_ITEM_LIKE = re.compile(r"^(KS|PK#|ND#|[A-Z]{2,3}#)", re.IGNORECASE)


def classify_code(raw: str) -> str:
    """启发式判码型。拿不准就交给 --entity-type 显式指定。"""
    raw = (raw or "").strip()
    if "#" in raw:
        return "item_code"
    if _ITEM_LIKE.match(raw):
        return "item_code"
    return "customer_code"


def parse_inputs(text: str, default_kind: str = "auto") -> list:
    """把逗号/分号/换行分隔的输入拆成 InputEntity 列表，保序去重。"""
    out, seen = [], set()
    for part in _SEP.split(text or ""):
        raw = part.strip()
        if not raw or raw in seen:
            continue
        seen.add(raw)
        kind = classify_code(raw) if default_kind == "auto" else default_kind
        out.append(InputEntity(raw=raw, kind=kind))
    return out


def resolve_inputs(entities, so_rows, master_by_code):
    """给每个输入算出 命中 SO / 命中订单行 / 登记物料 / 未命中原因。

    命中判定复用引擎口径：物料码精确匹配、客户码子串匹配（大小写不敏感）。
    `master_by_code`: {客户码: [登记物料, ...]}（仅客户码输入用），用于识别
    订单行直接卖「登记物料」的场景。不改 so_rows，只读。
    """
    from item_shipment_status import code_in, item_code_equals  # 引擎口径单一来源

    master_by_code = master_by_code or {}
    resolutions = []
    for e in entities:
        res = EntityResolution(raw=e.raw, kind=e.kind)
        reg_items = [m["name"] for m in master_by_code.get(e.raw, [])]
        hit_lines, hit_so = [], []
        for r in so_rows:
            if e.kind == "item_code":
                matched = item_code_equals(r.get("item_code"), [e.raw])
            else:
                matched = (code_in(r.get("customer_item_code"), [e.raw])
                           or item_code_equals(r.get("item_code"), reg_items))
            if matched:
                hit_lines.append(r)
                hit_so.append(r["so"])
        res.hit_lines = [r["line_id"] for r in hit_lines]
        res.hit_sos = sorted(set(hit_so))
        res.resolved_items = reg_items if e.kind == "customer_code" else (
            [e.raw] if res.hit_lines else [])
        if not res.hit_lines:
            res.miss_reason = ("客户码未在订单行/物料登记命中"
                               if e.kind == "customer_code" else "物料码未在任何订单行命中")
        resolutions.append(res)
    return resolutions
