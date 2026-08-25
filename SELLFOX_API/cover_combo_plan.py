# -*- coding: utf-8 -*-
"""Pure planning for Sellfox PK# → KS x1 cover inventory aliases.

Not EN Product Bundle / TJ# sync. No network I/O.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

FAMILIES: tuple[dict[str, str], ...] = (
    {
        "spu": "KS0001",
        "product_template": "KS0001",
        "cover_template": "PK#KS0001",
        "product_group": "三角靠枕",
        "cover_name_prefix": "皮壳#三角靠枕",
    },
    {
        "spu": "KS0248",
        "product_template": "KS0248",
        "cover_template": "PK#KS0248",
        "product_group": "三角靠枕无扣",
        "cover_name_prefix": "皮壳#三角靠枕无扣",
    },
)

SPU_PREFIXES = tuple(f["spu"] for f in FAMILIES)


@dataclass(frozen=True)
class BomCost:
    cover_cost: float | None
    freights: dict[str, float]
    freight_avg: float | None
    purchase_cost: float | None
    cost_missing: bool
    mode: str = ""


@dataclass(frozen=True)
class EnItemBrief:
    item_code: str
    item_name: str
    disabled: bool = False


@dataclass(frozen=True)
class SellfoxSkuBrief:
    sku: str
    name: str = ""
    is_group: str = ""
    full_cid: str = ""
    child_skus: tuple[tuple[str, int], ...] = ()
    id: str = ""


@dataclass
class CoverPlanRow:
    ks_sku: str
    pk_sku: str
    action: str
    reason: str
    spu: str = ""
    suffix: str = ""
    en_pk_name: str = ""
    sellfox_ks_name: str = ""
    sellfox_ks_id: str = ""
    full_cid: str = ""
    cost_missing: bool = False
    purchase_cost: float | None = None
    cover_cost: float | None = None
    freight_avg: float | None = None
    freights: dict[str, float] = field(default_factory=dict)
    remark: str = ""
    existing_pk_is_group: str = ""
    existing_pk_children: list[list[Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def family_for_ks(ks_sku: str) -> dict[str, str] | None:
    for fam in FAMILIES:
        tmpl = fam["product_template"]
        if ks_sku == tmpl or ks_sku.startswith(tmpl + "-"):
            return fam
    return None


def suffix_of(code: str, template: str) -> str | None:
    prefix = template + "-"
    if code.startswith(prefix):
        return code[len(prefix) :]
    if code == template:
        return ""
    return None


def pk_sku_for_ks(ks_sku: str) -> str | None:
    fam = family_for_ks(ks_sku)
    if not fam:
        return None
    suffix = suffix_of(ks_sku, fam["product_template"])
    if suffix is None:
        return None
    if suffix == "":
        return fam["cover_template"]
    return f"{fam['cover_template']}-{suffix}"


def is_group_flag(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true"}


def is_ordinary_finished(row: Mapping[str, Any]) -> bool:
    """Ordinary Sellfox SKU (not combo/process/aux)."""
    raw = row.get("isGroup")
    if raw is None or str(raw).strip() == "":
        return True
    return str(raw).strip() in {"0", "false", "False"}


def parse_children(child_skus: Any) -> tuple[tuple[str, int], ...]:
    rows: list[tuple[str, int]] = []
    for child in child_skus or []:
        if isinstance(child, Mapping):
            sku = str(child.get("sku") or "")
            num = int(child.get("num") or 0)
        else:
            sku, num = str(child[0]), int(child[1])
        if sku:
            rows.append((sku, num))
    return tuple(rows)


def format_cost_remark(bom: BomCost) -> str:
    if bom.cost_missing or bom.cover_cost is None or bom.freight_avg is None:
        return ""
    freights = bom.freights
    usnj = freights.get("USNJ")
    ustx = freights.get("USTX")
    pl = freights.get("PL")
    if usnj is None or ustx is None or pl is None:
        return ""
    return (
        f"绍兴皮壳成本{bom.cover_cost} + 分公司皮壳头程平均值{bom.freight_avg} "
        f"(USNJ{{{usnj}}} + USTX{{{ustx}}} + PL{{{pl}}}) / 3"
    )


def build_bom_cost(
    *,
    cover_cost: Any,
    usnj: Any,
    ustx: Any,
    pl: Any,
    mode: str = "",
) -> BomCost:
    def _num(v: Any) -> float | None:
        if v is None:
            return None
        try:
            if isinstance(v, float) and v != v:  # NaN
                return None
            s = str(v).strip()
            if s == "" or s.lower() == "nan":
                return None
            return float(s)
        except (TypeError, ValueError):
            return None

    c = _num(cover_cost)
    freights = {
        "USNJ": _num(usnj),
        "USTX": _num(ustx),
        "PL": _num(pl),
    }
    ready = c is not None and all(v is not None for v in freights.values())
    if not ready:
        partial = {k: float(v) for k, v in freights.items() if v is not None}
        return BomCost(
            cover_cost=c,
            freights=partial,
            freight_avg=None,
            purchase_cost=None,
            cost_missing=True,
            mode=mode,
        )
    avg = round(
        (float(freights["USNJ"]) + float(freights["USTX"]) + float(freights["PL"])) / 3,
        4,
    )
    purchase = round(float(c) + avg, 4)
    return BomCost(
        cover_cost=float(c),
        freights={k: float(v) for k, v in freights.items()},
        freight_avg=avg,
        purchase_cost=purchase,
        cost_missing=False,
        mode=mode,
    )


def plan_one(
    *,
    ks: SellfoxSkuBrief,
    en_product: EnItemBrief | None,
    en_cover: EnItemBrief | None,
    existing_pk: SellfoxSkuBrief | None,
    bom: BomCost | None,
) -> CoverPlanRow:
    fam = family_for_ks(ks.sku)
    if not fam:
        return CoverPlanRow(
            ks_sku=ks.sku,
            pk_sku="",
            action="unmatched",
            reason="not_triangle_family",
            sellfox_ks_name=ks.name,
            sellfox_ks_id=ks.id,
            full_cid=ks.full_cid,
        )

    suffix = suffix_of(ks.sku, fam["product_template"]) or ""
    pk = pk_sku_for_ks(ks.sku) or ""
    cost = bom or BomCost(
        cover_cost=None,
        freights={},
        freight_avg=None,
        purchase_cost=None,
        cost_missing=True,
    )
    remark = format_cost_remark(cost)
    base_kwargs = dict(
        ks_sku=ks.sku,
        pk_sku=pk,
        spu=fam["spu"],
        suffix=suffix,
        en_pk_name=(en_cover.item_name if en_cover else ""),
        sellfox_ks_name=ks.name,
        sellfox_ks_id=ks.id,
        full_cid=ks.full_cid,
        cost_missing=cost.cost_missing,
        purchase_cost=cost.purchase_cost,
        cover_cost=cost.cover_cost,
        freight_avg=cost.freight_avg,
        freights=dict(cost.freights),
        remark=remark,
    )

    if not is_ordinary_finished({"isGroup": ks.is_group}):
        return CoverPlanRow(
            **base_kwargs,
            action="unmatched",
            reason="ks_not_ordinary_finished",
        )

    # Sellfox finished KS is source of truth. EN disabled products still get a
    # PK# alias. Missing EN cover is reported but does not block create.
    if en_cover is not None:
        base_kwargs["en_pk_name"] = en_cover.item_name
    elif not base_kwargs["en_pk_name"]:
        ks_name = ks.name or (en_product.item_name if en_product else ks.sku)
        if ks_name.startswith("皮壳#"):
            base_kwargs["en_pk_name"] = ks_name
        else:
            base_kwargs["en_pk_name"] = f"皮壳#{ks_name}"

    if existing_pk is None:
        return CoverPlanRow(
            **base_kwargs,
            action="create",
            reason="pk_missing_on_sellfox",
        )

    children = existing_pk.child_skus
    expected = ((ks.sku, 1),)
    base_kwargs["existing_pk_is_group"] = existing_pk.is_group
    base_kwargs["existing_pk_children"] = [[c, n] for c, n in children]

    if not is_group_flag(existing_pk.is_group):
        return CoverPlanRow(
            **base_kwargs,
            action="mismatch",
            reason="pk_exists_but_not_combo",
        )

    if tuple(sorted(children)) != tuple(sorted(expected)):
        return CoverPlanRow(
            **base_kwargs,
            action="mismatch",
            reason="pk_combo_children_differ",
        )

    return CoverPlanRow(
        **base_kwargs,
        action="ok",
        reason="pk_combo_matches_ks_x1",
    )


def plan_cover_combos(
    *,
    sellfox_ks_rows: Sequence[SellfoxSkuBrief],
    en_products: Mapping[str, EnItemBrief],
    en_covers: Mapping[str, EnItemBrief],
    sellfox_pk_rows: Mapping[str, SellfoxSkuBrief],
    bom_by_ks: Mapping[str, BomCost],
) -> list[CoverPlanRow]:
    rows: list[CoverPlanRow] = []
    for ks in sellfox_ks_rows:
        pk = pk_sku_for_ks(ks.sku)
        en_p = en_products.get(ks.sku)
        en_c = en_covers.get(pk) if pk else None
        existing = sellfox_pk_rows.get(pk) if pk else None
        bom = bom_by_ks.get(ks.sku)
        rows.append(
            plan_one(
                ks=ks,
                en_product=en_p,
                en_cover=en_c,
                existing_pk=existing,
                bom=bom,
            )
        )
    return rows


def summarize_plan(rows: Sequence[CoverPlanRow]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    cost_missing = 0
    for row in rows:
        counts[row.action] = counts.get(row.action, 0) + 1
        if row.cost_missing:
            cost_missing += 1
    unmatched = [r.to_dict() for r in rows if r.action not in {"ok", "create"}]
    return {
        "input_ks": len(rows),
        "output_rows": len(rows),
        "counts": counts,
        "cost_missing": cost_missing,
        "unmatched": unmatched,
    }
