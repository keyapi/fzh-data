"""EN「订单侧输入」纯函数层：合并键 / 件数 / 补发判据。

只做纯计算，不访问 EN、不写任何业务数据。规则出处：
`docs/solutions/conventions/tongtu-order-suffix-and-merge-criteria.md`
（通途订单号后缀语义与「该不该合并」判据；件数=Σ皮壳行数量；TikTok 跨前缀按数字主体合并）。

口径：**子单口径** —— 每张 `_N` 子单各算一件订单，不合并订单边界；
对"源头就没有原始单"的订单（通途只落了 `_N`）天然适用。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# 补发后缀：`<base>_N-M####` 或 `<base>-M####`
_SUPP_RE = re.compile(r"[-_]M\d+$")
# 同前缀拆单后缀：仅 1–2 位数字（`_1 _2` / `-1 -2`）；订单号本体（如 `OS-474530280`）不剥
_SPLIT_RE = re.compile(r"[_-]\d{1,2}$")
# 皮壳行：SKU 以 `-Cover`（可带 1 位序号）结尾，或产品名含「皮壳」
_COVER_RE = re.compile(r"-Cover\d*$", re.I)
# 明确的后缀部件码
_PART_SUFFIX_RE = re.compile(r"-(?:Cover\d*|Foam)$", re.I)
# 部件词（产品名）
_PART_NAME_RE = re.compile(r"海绵块|主体骨架|铁架|框架|内胆|支架|骨架")


def order_base(order_id: str) -> str:
    """同前缀合并键：剥补发后缀 + 剥 1–2 位拆单后缀。

    仅剥 1–2 位，避免把订单号本体（如 `OS-474530280` 的 9 位数字）当"包裹序号"吃掉。
    """
    oid = (order_id or "").strip()
    oid = _SUPP_RE.sub("", oid)
    return _SPLIT_RE.sub("", oid)


def platform_body(order_id: str) -> str:
    """平台单号数字主体（跨前缀合并用）。

    TikTok 在通途不让拆单，拆包裹时手动新建销售平台账号补另一半，
    于是同一单的数字主体散落在不同前缀（`TTDaneeyUS-…` / `TTBNKC-…`）。
    仅按数字主体即可把两半对上。
    """
    return re.sub(r"\D", "", order_base(order_id))


def is_supplementary(order_id: str, flag: str | None = None) -> bool:
    """是否补发单。优先用通途 `是否补发货` 列（'是'），退化到 `-M####` 结构后缀。

    不要用「SKU 含 Cotton/棉包」判补发——`Curve-Pillow-50-PPCotton` 是 PP棉内胆（正常填充物）。
    """
    if flag is not None and str(flag).strip() == "是":
        return True
    return bool(_SUPP_RE.search((order_id or "").strip()))


def is_cover(sku: str | None, name: str | None = None) -> bool:
    return bool(_COVER_RE.search(sku or "")) or ("皮壳" in (name or ""))


def is_part(sku: str | None, name: str | None = None) -> bool:
    return bool(_PART_SUFFIX_RE.search(sku or "")) or bool(_PART_NAME_RE.search(name or ""))


@dataclass(frozen=True)
class Item:
    sku: str
    quantity: int
    shipping_method: str = ""


def count_pieces(items: list[Item]) -> tuple[int, str]:
    """件数 = Σ(皮壳行 quantity)；无皮壳行时兜底 `max(各行 quantity)` 并打标记。

    三级兜底（必须给数，绝不空）：
    1. 有 `-Cover` 行 → Σ(皮壳行 quantity)
    2. 无皮壳但来源有兄弟（跨前缀）→ 由调用方先合并兄弟再走第 1 步
    3. 仍无皮壳 → `max(各行 quantity)` + 标记「无皮壳·待复核」

    Returns (件数, 口径标记)。
    """
    covers = [i for i in items if is_cover(i.sku)]
    if covers:
        return sum(max(int(i.quantity), 0) for i in covers), "皮壳口径"
    if not items:
        return 0, "空"
    return max(int(i.quantity) for i in items), "无皮壳·待复核"
