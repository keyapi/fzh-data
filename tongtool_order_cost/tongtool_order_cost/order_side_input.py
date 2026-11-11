"""EN「订单侧输入」纯函数层：合并键 / 件数 / 补发判据。

只做纯计算，不访问 EN、不写任何业务数据。规则出处：
`docs/solutions/conventions/tongtu-order-suffix-and-merge-criteria.md`
（通途订单号后缀语义与「该不该合并」判据；件数=Σ皮壳行数量；TikTok 跨前缀按数字主体合并）。

口径：**子单口径** —— 每张 `_N` 子单各算一件订单，不合并订单边界；
对"源头就没有原始单"的订单（通途只落了 `_N`）天然适用。
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, replace
from typing import Any, Protocol
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter

# 补发后缀：`<base>_N-M####` 或 `<base>-M####`
_SUPP_RE = re.compile(r"[-_]M\d+$")
# 同前缀拆单后缀：仅 1–2 位数字（`_1 _2` / `-1 -2`）；订单号本体（如 `OS-474530280`）不剥
_SPLIT_RE = re.compile(r"[_-]\d{1,2}$")
# 皮壳行：SKU 以 `-Cover`（可带序号）结尾，或产品名含「皮壳」
_COVER_RE = re.compile(r"-Cover\d*$", re.I)
# 填充件：只做内胆/填充，不是成品件本身（PP棉/海绵）
_FILLING_RE = re.compile(r"-(?:Foam\d*|PPCotton\d*)$", re.I)
# 拆包裹部件后缀：`<base>-N`（1–2 位），当 `<base>` 也在同一单时=同一件的第 N 个包裹
_SKU_SPLIT_RE = re.compile(r"^(?P<base>.+?)[-_](?P<n>\d{1,2})$")
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
    """平台单号数字主体（跨前缀候选匹配用）。"""
    return re.sub(r"\D", "", order_base(order_id))


def tiktok_platform_body(order_id: str) -> str:
    """TikTok 跨账号拆包裹键；非 TikTok 或过短数字主体不参与匹配。"""
    base = order_base(order_id)
    prefix = base.split("-", 1)[0].upper()
    body = platform_body(base)
    if not prefix.startswith("TT") or len(body) < 12:
        return ""
    return body


def is_supplementary(order_id: str, flag: str | None = None) -> bool:
    """是否补发单。优先用通途 `是否补发货` 列（'是'），退化到 `-M####` 结构后缀。

    不要用「SKU 含 Cotton/棉包」判补发——`Curve-Pillow-50-PPCotton` 是 PP棉内胆（正常填充物）。
    """
    if flag is not None and str(flag).strip() == "是":
        return True
    return bool(_SUPP_RE.search((order_id or "").strip()))


def is_cover(sku: str | None, name: str | None = None) -> bool:
    return bool(_COVER_RE.search(sku or "")) or ("皮壳" in (name or ""))


def _is_split_part(sku: str, present: set[str]) -> bool:
    """SKU 是否为拆包裹部件：形如 `<base>-N` 且 `<base>` 也在同一单里。"""
    match = _SKU_SPLIT_RE.match(sku)
    return bool(match and match.group("base") in present)


def is_part(sku: str | None, name: str | None = None) -> bool:
    return bool(_PART_SUFFIX_RE.search(sku or "")) or bool(_PART_NAME_RE.search(name or ""))


@dataclass(frozen=True)
class Item:
    sku: str
    quantity: int
    shipping_method: str = ""


@dataclass(frozen=True)
class OrderItem:
    tongtool_sku: str
    platform_sku: str
    erp_item_code: str
    quantity: int
    shipping_method: str
    split_package_cost_factor: float
    cost_fg: float
    cost_sxbzcp: float
    cost_sxbzbcp: float
    sx_shipping_cost: float
    first_freight: float
    bcp_first_freight: float
    pk_first_freight: float
    last_leg_fee: float


@dataclass(frozen=True)
class OrderInput:
    requested_order_id: str
    order_id: str
    base_order_id: str
    platform_order_body: str
    is_child: bool
    original_order_exists: bool | None
    is_supplementary: bool
    warehouse_name: str
    piece_count: int
    piece_rule: str
    shipping_methods: tuple[str, ...]
    items: tuple[OrderItem, ...]
    status: str


@dataclass(frozen=True)
class FetchReport:
    input_count: int
    fetched_count: int
    missing_count: int
    failed_count: int
    empty_shell_count: int
    supplementary_count: int
    parts_only_count: int
    child_only_count: int
    failures: tuple[str, ...]
    missing_order_ids: tuple[str, ...]


class OrderReader(Protocol):
    def get_order(self, order_id: str) -> dict[str, Any] | None: ...


class _NoExpectAdapter(HTTPAdapter):
    def send(self, request, **kwargs):
        request.headers.pop("Expect", None)
        return super().send(request, **kwargs)


class ErpnextOrderClient:
    """ERPNext `Tongtool Order` 只读客户端。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        api_secret: str,
        *,
        timeout: float = 60,
        retries: int = 2,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"token {api_key}:{api_secret}",
                "Accept": "application/json",
            }
        )
        self.session.mount("https://", _NoExpectAdapter())
        self.session.mount("http://", _NoExpectAdapter())

    def get_order(self, order_id: str) -> dict[str, Any] | None:
        doctype = quote("Tongtool Order", safe="")
        name = quote(order_id, safe="")
        url = f"{self.base_url}/api/resource/{doctype}/{name}"
        for attempt in range(self.retries + 1):
            response = self.session.get(url, timeout=self.timeout)
            if response.status_code == 404:
                return None
            if response.status_code in {408, 417, 500, 502, 503, 504} and attempt < self.retries:
                time.sleep(attempt + 1)
                continue
            response.raise_for_status()
            return response.json().get("data") or {}
        return None

    def list_documents(
        self,
        doctype: str,
        fields: list[str],
        *,
        page_size: int = 200,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        url = f"{self.base_url}/api/resource/{quote(doctype, safe='')}"
        rows: list[dict[str, Any]] = []
        offset = 0
        prev_first: str | None = None
        while True:
            query = {
                "fields": json.dumps(fields, ensure_ascii=False),
                "limit_start": offset,
                "limit_page_length": page_size,
                **(params or {}),
            }
            for attempt in range(self.retries + 1):
                response = self.session.get(url, params=query, timeout=self.timeout)
                if response.status_code in {408, 417, 500, 502, 503, 504} and attempt < self.retries:
                    time.sleep(attempt + 1)
                    continue
                response.raise_for_status()
                page = response.json().get("data") or []
                break
            if not page:
                return rows
            first = str(page[0].get("name") or "")
            if first and first == prev_first:
                # 后端未按 limit_start 前进（子表常见）——停止，避免死循环
                return rows
            prev_first = first
            rows.extend(page)
            if len(page) < page_size:
                return rows
            offset += page_size

    def list_order_items(
        self,
        fields: list[str],
        *,
        page_size: int = 200,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return self.list_documents(
            "Tongtool Order Item",
            fields,
            page_size=page_size,
            params={"parent": "Tongtool Order", **(params or {})},
        )

    def list_orders_by_ids(
        self,
        order_ids: list[str],
        *,
        fields: list[str] | None = None,
        chunk_size: int = 100,
    ) -> list[dict[str, Any]]:
        fields = fields or ["name", "warehouse_name", "creation", "modified"]
        rows: list[dict[str, Any]] = []
        for start in range(0, len(order_ids), chunk_size):
            chunk = order_ids[start : start + chunk_size]
            rows.extend(
                self.list_documents(
                    "Tongtool Order",
                    fields,
                    params={"filters": json.dumps([["name", "in", chunk]], ensure_ascii=False)},
                )
            )
        return rows

    def list_order_items_by_order_ids(
        self,
        order_ids: list[str],
        *,
        fields: list[str] | None = None,
        chunk_size: int = 20,
    ) -> list[dict[str, Any]]:
        fields = fields or [
            "name",
            "parent",
            "tongtool_sku",
            "platform_sku",
            "erp_item_code",
            "quantity",
            "shipping_method",
            "split_package_cost_factor",
            "cost_fg",
            "cost_sxbzcp",
            "cost_sxbzbcp",
            "sx_shipping_cost",
            "first_freight",
            "bcp_first_freight",
            "pk_first_freight",
            "last_leg_fee",
        ]
        rows: list[dict[str, Any]] = []
        for start in range(0, len(order_ids), chunk_size):
            chunk = order_ids[start : start + chunk_size]
            rows.extend(
                self.list_order_items(
                    fields,
                    params={"filters": json.dumps([["parent", "in", chunk]], ensure_ascii=False)},
                )
            )
        return rows


def _int(value: Any) -> int:
    if value in (None, ""):
        return 0
    return int(float(value))


def _float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def _normalize_item(raw: dict[str, Any]) -> OrderItem:
    return OrderItem(
        tongtool_sku=str(raw.get("tongtool_sku") or "").strip(),
        platform_sku=str(raw.get("platform_sku") or "").strip(),
        erp_item_code=str(raw.get("erp_item_code") or "").strip(),
        quantity=_int(raw.get("quantity")),
        shipping_method=str(raw.get("shipping_method") or "").strip(),
        split_package_cost_factor=_float(raw.get("split_package_cost_factor")),
        cost_fg=_float(raw.get("cost_fg")),
        cost_sxbzcp=_float(raw.get("cost_sxbzcp")),
        cost_sxbzbcp=_float(raw.get("cost_sxbzbcp")),
        sx_shipping_cost=_float(raw.get("sx_shipping_cost")),
        first_freight=_float(raw.get("first_freight")),
        bcp_first_freight=_float(raw.get("bcp_first_freight")),
        pk_first_freight=_float(raw.get("pk_first_freight")),
        last_leg_fee=_float(raw.get("last_leg_fee")),
    )


def group_order_documents(
    parents: list[dict[str, Any]], children: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    items_by_parent: dict[str, list[dict[str, Any]]] = {}
    for item in children:
        parent = str(item.get("parent") or "").strip()
        if parent:
            items_by_parent.setdefault(parent, []).append(item)
    return [
        {**parent, "order_items": items_by_parent.get(str(parent.get("name") or ""), [])}
        for parent in parents
    ]


def normalize_order_document(
    document: dict[str, Any], requested_order_id: str = ""
) -> OrderInput:
    """把一张 EN `Tongtool Order` 文档转成可审计的订单侧输入。"""
    order_id = str(document.get("name") or document.get("order_id") or requested_order_id).strip()
    items = tuple(_normalize_item(raw) for raw in (document.get("order_items") or []))
    pieces, piece_rule = count_pieces(
        [Item(item.tongtool_sku, item.quantity, item.shipping_method) for item in items]
    )
    shipping_methods = tuple(sorted({item.shipping_method for item in items if item.shipping_method}))
    supplementary_flag = (
        document.get("is_supplementary")
        or document.get("supplementary_flag")
        or document.get("是否补发货")
    )
    supplementary = is_supplementary(order_id, str(supplementary_flag or ""))
    without_supplement = _SUPP_RE.sub("", order_id)
    is_child = bool(_SPLIT_RE.search(without_supplement))
    warehouse_name = str(document.get("warehouse_name") or "").strip()
    if not items:
        status = "empty_shell"
    elif piece_rule == "只发部件·待复核":
        status = "review"
    else:
        status = "ok"
    return OrderInput(
        requested_order_id=requested_order_id or order_id,
        order_id=order_id,
        base_order_id=order_base(order_id),
        platform_order_body=platform_body(order_id),
        is_child=is_child,
        original_order_exists=None,
        is_supplementary=supplementary,
        warehouse_name=warehouse_name,
        piece_count=pieces,
        piece_rule=piece_rule,
        shipping_methods=shipping_methods,
        items=items,
        status=status,
    )


def fetch_order_inputs(
    client: OrderReader, order_ids: list[str]
) -> tuple[list[OrderInput], FetchReport]:
    """逐单读取并返回完整数量对账；缺失与失败不会静默丢弃。"""
    rows: list[OrderInput] = []
    missing: list[str] = []
    failures: list[str] = []
    for order_id in order_ids:
        try:
            document = client.get_order(order_id)
        except Exception as exc:
            failures.append(f"{order_id}: {type(exc).__name__}: {exc}")
            continue
        if document is None:
            missing.append(order_id)
            continue
        rows.append(normalize_order_document(document, requested_order_id=order_id))

    fetched_order_ids = {row.order_id for row in rows}
    requested_order_ids = set(order_ids)
    missing_order_ids = set(missing)
    normalized_rows: list[OrderInput] = []
    for row in rows:
        if not row.is_child:
            normalized_rows.append(row)
            continue
        if row.base_order_id in fetched_order_ids:
            normalized_rows.append(replace(row, original_order_exists=True))
        elif row.base_order_id in requested_order_ids or row.base_order_id in missing_order_ids:
            normalized_rows.append(
                replace(
                    row,
                    original_order_exists=False,
                    status="child_only" if row.status == "ok" else row.status,
                )
            )
        else:
            normalized_rows.append(row)
    rows = normalized_rows
    report = FetchReport(
        input_count=len(order_ids),
        fetched_count=len(rows),
        missing_count=len(missing),
        failed_count=len(failures),
        empty_shell_count=sum(row.status == "empty_shell" for row in rows),
        supplementary_count=sum(row.is_supplementary for row in rows),
        parts_only_count=sum(row.piece_rule == "只发部件·待复核" for row in rows),
        child_only_count=sum(
            row.is_child and row.original_order_exists is False for row in rows
        ),
        failures=tuple(failures),
        missing_order_ids=tuple(missing),
    )
    return rows, report


def count_pieces(items: list[Item]) -> tuple[int, str]:
    """件数 = 一单里「成品件」的数量（子单口径，每 `_N` 子单各算一件订单）。

    口径（对应 `docs/solutions/conventions/tongtu-order-suffix-and-merge-criteria.md`）：
    0. 先剔除**拆包裹部件行**（SKU 形如 `<base>-N`，且 `<base>` 也在同一单）——
       这是同一件的第 N 个包裹（如 `TT0031217K0064032` + `TT0031217K0064032-2`），
       不是第 2 件。空 SKU 是 EN 占位行，同样剔除。
    1. 有明确皮壳行（`-Cover`）→ Σ(皮壳行 quantity)。一件成品的成本被拆成皮壳+填充
       两行时，只有皮壳行代表"件"。`绍兴发货方式`（EN `shipping_method` = 皮壳/半成品/成品）
       只决定成本落在哪、分公司要不要填充压缩，**不改变件数**。
    2. 无皮壳行 → Σ(成品行 quantity)。一单多件不同成品时逐行相加，不能取 max。
    3. 全是填充件（只发 `-Foam`/`-PPCotton`，无成品行）→ `max(quantity)` + 标记「只发部件·待复核」。

    Returns (件数, 口径标记)。
    """
    named = [item for item in items if item.sku.strip()]
    if not named:
        return 0, "空"
    present = {item.sku.strip() for item in named}
    rows = [item for item in named if not _is_split_part(item.sku.strip(), present)]
    if not rows:
        return 0, "空"
    explicit_covers = [item for item in rows if is_cover(item.sku)]
    if explicit_covers:
        return sum(max(int(item.quantity), 0) for item in explicit_covers), "皮壳口径"
    product_rows = [item for item in rows if not _FILLING_RE.search(item.sku)]
    if product_rows:
        return sum(max(int(item.quantity), 0) for item in product_rows), "成品口径"
    return max(int(item.quantity) for item in rows), "只发部件·待复核"
