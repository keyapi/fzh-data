# Copyright (c) 2024, delivery_plan contributors
# For license information, please see license.txt

"""销售出库单(Delivery Note) → 通途采购单。

业务规则（2026-09-16 与业务方确认）：

* 只处理三个客户：CENTRADE(美东)、DANEEY(美中)、波兰公司。其余（含 FBA）不处理。
* 明细行只处理两类：
    - 成品：Item 上直接登记了客户物料号
    - 皮壳（item_code 以 ``PK#`` 开头）：去掉前缀找对应成品，再取成品的客户物料号
* 客户物料号按**公司**选客户组：CENTRADE/DANEEY → 美国公司；波兰公司 → 欧洲公司。
* 皮壳与成品都取**基码**（不带 ``-Cover`` / ``-Foam`` 后缀的那条）。
* 海绵暂不处理（后期再说）；内胆/扣子/套件# 等一律跳过。
* 采购单参数（采购员/仓库/供应商/币种）从 ``Tongtool Settings`` 的多行文本字段读，
  不新增单据：每行 ``名称=通途ID``。

通途客户端复用 ``tongtool_integration.api.client``（凭证在 Tongtool Settings）。
限流提醒：同商户所有 App 共享 5 次/分钟，且客户端用 ``time.sleep()`` 退避，
所以能缓存的必须缓存；未授权的接口会按网络异常重试 3 次，可能卡十几分钟。
"""

from typing import Dict, List, Optional, Tuple

import frappe
from frappe import _
from frappe.utils import flt, now

from tongtool_integration.api.client import TongToolClient, get_tongtool_client

# ── 业务常量 ────────────────────────────────────────────────────────────

# DN 的 customer → 客户物料号上登记的「客户组」
COMPANY_CUSTOMER_GROUP = {
    "CENTRADE": "美国公司",
    "DANEEY": "美国公司",
    "波兰公司": "欧洲公司",
}

# 皮壳物料编码前缀
COVER_ITEM_PREFIX = "PK#"

# 视为「形态变体码」的后缀——皮壳/成品都取基码，所以要排掉这些
VARIANT_CODE_SUFFIXES = ("-Cover", "-Foam")

# 成品所在物料组的祖先（白名单根）
PRODUCT_GROUP_ROOT = "产品"

# 采购参数配置（放在 tongtool_integration 的 Tongtool Settings 上，不新增单据）
SETTINGS_SINGLE = "Tongtool Settings"
CONFIG_FIELDS = {
    "purchase_users": "custom_purchase_users",
    "warehouses": "custom_purchase_warehouses",
    "suppliers": "custom_purchase_suppliers",
}
CURRENCY_FIELD = "custom_purchase_currency"

# goodsQuery 的 skus 每批最多 10 个
GOODS_SKU_BATCH_SIZE = 10

PURCHASE_ORDER_FIELD = "custom_tongtool_purchase_order"
PURCHASE_ORDER_TIME_FIELD = "custom_tongtool_po_created_on"


def as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes")


# ── 配置读取 ────────────────────────────────────────────────────────────

def _parse_options(raw: str) -> List[Dict]:
    """解析 ``Tongtool Settings`` 里的多行配置：每行 ``名称=通途ID``。

    空行与 ``#`` 开头的注释行忽略；缺 ``=`` 或任一侧为空的行跳过。
    """
    out: List[Dict] = []
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        label, _sep, value = line.partition("=")
        label, value = label.strip(), value.strip()
        if label and value:
            out.append({"label": label, "value": value})
    return out


def get_purchase_settings() -> Dict:
    """采购单参数。

    * 采购员 / 仓库 / 币种：读自 ``Tongtool Settings`` 的多行文本字段
      （采购员**无法**用 API 查——员工类接口全部 524 无权限，只能人工维护）
    * 供应商：**从通途实时拉取**（带缓存）。供应商不固定，且 ``supplierQuery`` 有权限，
      没必要在配置里手工维护几百行。
    """
    settings = frappe.get_single(SETTINGS_SINGLE)
    suppliers = _fetch_suppliers()
    if not suppliers:
        # 通途拉取失败时退回配置里的兜底值，至少别让弹窗开不出来
        suppliers = _parse_options(settings.get(CONFIG_FIELDS["suppliers"]))
    return {
        "purchase_users": _parse_options(settings.get(CONFIG_FIELDS["purchase_users"])),
        "warehouses": _parse_options(settings.get(CONFIG_FIELDS["warehouses"])),
        "suppliers": suppliers,
        "currency": (settings.get(CURRENCY_FIELD) or "USD").strip() or "USD",
    }


SUPPLIER_CACHE_KEY = "purchase_supplier_options"
SUPPLIER_MAX_PAGES = 10


def _fetch_suppliers() -> List[Dict]:
    """从通途拉供应商列表 → [{label, value}]，结果按客户端 TTL 缓存。"""
    try:
        client = get_tongtool_client()
        cache_key = client.get_cache_key(SUPPLIER_CACHE_KEY)
        cached = client.get_cached_data(cache_key)
        if cached:
            return cached

        out: List[Dict] = []
        for page in range(1, SUPPLIER_MAX_PAGES + 1):
            response = client.request(
                "POST", "/openapi/tongtool/supplierQuery", {"pageNo": page, "pageSize": 100}
            )
            rows = (response.get("datas") or {}).get("array") or []
            for s in rows:
                if not s.get("supplierId"):
                    continue
                out.append({
                    "label": s.get("corporationFullname") or s.get("supplierCode") or s.get("supplierId"),
                    "value": s.get("supplierId"),
                })
            if len(rows) < 100:
                break

        if out:
            client.set_cached_data(cache_key, out)
        return out
    except Exception as e:
        frappe.log_error(f"拉取通途供应商列表失败: {e}", "tongtool_purchase")
        return []


# ── 物料组白名单 ────────────────────────────────────────────────────────

def _item_group_parent_map() -> Dict[str, Optional[str]]:
    rows = frappe.db.sql(
        "SELECT name, parent_item_group FROM `tabItem Group`", as_dict=True
    )
    return {r["name"]: r["parent_item_group"] or None for r in rows}


def is_under_product_group(item_group: str) -> bool:
    """物料组是否属于「产品」的后代（含自身）。用于排除海绵/套件#等。"""
    if not item_group:
        return False
    parents = _item_group_parent_map()
    seen = set()
    name = item_group
    while name and name not in seen:
        if name == PRODUCT_GROUP_ROOT:
            return True
        seen.add(name)
        name = parents.get(name)
    return False


def is_cover_item(item_code: str) -> bool:
    return bool(item_code) and item_code.startswith(COVER_ITEM_PREFIX)


def _is_variant_code(ref_code: str) -> bool:
    code = (ref_code or "").strip()
    return any(code.lower().endswith(s.lower()) for s in VARIANT_CODE_SUFFIXES)


# ── 客户物料号解析 ──────────────────────────────────────────────────────

def _ref_code_for(item_code: str, customer_group: str) -> Optional[str]:
    """取某物料在指定客户组下的**基码**客户物料号。

    只认目标客户组；该组没有登记就返回 None（**不退回别的客户组**，避免采购错货）。
    组内若同时有基码和 -Cover/-Foam 码，取基码。
    """
    rows = frappe.db.sql(
        """
        SELECT ref_code, customer_group
        FROM `tabItem Customer Detail`
        WHERE parent = %s
          AND ref_code IS NOT NULL AND ref_code != ''
        ORDER BY idx
        """,
        item_code,
        as_dict=True,
    )
    if not rows:
        return None

    pool = [r["ref_code"] for r in rows if (r.get("customer_group") or "") == customer_group]
    if not pool:
        return None

    base = [c for c in pool if not _is_variant_code(c)]
    return (base or pool)[0]


def resolve_line_sku(item_code: str, customer_group: str) -> Tuple[Optional[str], Optional[str]]:
    """把一条 DN 明细翻译成通途 SKU。

    返回 ``(sku, reason)``：成功时 reason 为 None；失败时 sku 为 None 并给出原因。
    """
    if is_cover_item(item_code):
        # 皮壳：去掉 PK# 找对应成品
        finished_good = item_code[len(COVER_ITEM_PREFIX):]
        if not frappe.db.exists("Item", finished_good):
            return None, _("皮壳 {0} 找不到对应成品 {1}").format(item_code, finished_good)
        target = finished_good
        origin = _("皮壳，取自成品 {0}").format(finished_good)
    else:
        target = item_code
        origin = ""

    group = frappe.db.get_value("Item", target, "item_group")
    if not is_under_product_group(group):
        # 海绵(填充材料)、套件#、配件等：不在范围内
        return None, _("物料组 {0} 不在采购范围内（仅成品/皮壳）").format(group or "-")

    ref_code = _ref_code_for(target, customer_group)
    if not ref_code:
        return None, _("物料 {0} 在客户组「{1}」下没有客户物料号").format(target, customer_group)

    return ref_code, origin or None


# ── 通途货品映射 ────────────────────────────────────────────────────────

def goods_cache_key(client: TongToolClient, sku: str) -> str:
    """货品缓存键。SKU 大小写归一，否则永不命中。"""
    return client.get_cache_key(f"goods_detail_{sku.strip().lower()}")


class PurchaseAPI:
    """通途采购相关接口封装。"""

    def __init__(self, client: TongToolClient = None):
        self.client = client or get_tongtool_client()

    def get_goods_detail_map(self, skus: List[str]) -> Dict[str, Dict]:
        """通途 SKU 列表 → {SKU: {goodsDetailId, goodsSku, ...}}，命中缓存的跳过。"""
        unique_skus = [s for s in dict.fromkeys(skus) if s]
        result: Dict[str, Dict] = {}
        missing: List[str] = []

        for sku in unique_skus:
            cached = self.client.get_cached_data(goods_cache_key(self.client, sku))
            if cached:
                result[sku] = cached
            else:
                missing.append(sku)

        for start in range(0, len(missing), GOODS_SKU_BATCH_SIZE):
            batch = missing[start: start + GOODS_SKU_BATCH_SIZE]
            # productType 必填：0=普通销售 1=变参 2=捆绑 3=组装。
            # 2026-09-15 实测本商户货品只在 productType=0 下查得到。
            response = self.client.request(
                "POST",
                "/openapi/tongtool/goodsQuery",
                {"productType": "0", "skus": batch, "pageNo": 1, "pageSize": len(batch)},
            )
            products = (response.get("datas") or {}).get("array") or []

            for product in products:
                for detail in product.get("goodsDetail") or []:
                    goods_sku = detail.get("goodsSku")
                    if not goods_sku:
                        continue
                    record = {
                        "goodsDetailId": detail.get("goodsDetailId"),
                        "goodsSku": goods_sku,
                    }
                    self.client.set_cached_data(goods_cache_key(self.client, goods_sku), record)
                    for requested in batch:
                        if requested.lower() == goods_sku.lower():
                            result[requested] = record

        return result


# ── 预览（只读） ────────────────────────────────────────────────────────

def supported_customers() -> List[str]:
    return sorted(COMPANY_CUSTOMER_GROUP.keys())


def build_preview(delivery_note: str) -> Dict:
    """DN 明细 → 通途采购货品。纯只读，不写任何数据。"""
    dn = frappe.get_doc("Delivery Note", delivery_note)
    customer = (dn.customer or "").strip()
    customer_group = COMPANY_CUSTOMER_GROUP.get(customer)

    base = {
        "delivery_note": dn.name,
        "customer": customer,
        "customer_group": customer_group,
        "supported": bool(customer_group),
        "existing_purchase_order": get_existing_purchase_order(dn),
        "logistic_number": dn.get("logistic_number"),
        "logistic_cost": dn.get("logistic_cost"),
    }

    if not customer_group:
        base.update({
            "lines": [], "unmatched": [],
            "message": _("客户 {0} 不在采购范围内（仅 CENTRADE / DANEEY / 波兰公司）").format(customer or "-"),
        })
        return base

    if not dn.items:
        frappe.throw(_("销售出库单没有明细行"))

    lines: List[Dict] = []
    unmatched: List[Dict] = []

    for row in dn.items:
        sku, note = resolve_line_sku(row.item_code, customer_group)
        if not sku:
            # 不在范围内的（内胆/扣子等）静默跳过；范围内容错要显式报出来
            if note and "不在采购范围内" in note:
                continue
            unmatched.append({
                "item_code": row.item_code, "item_name": row.item_name,
                "qty": row.qty, "reason": note or _("无法解析"),
            })
            continue
        lines.append({
            "item_code": row.item_code,
            "item_name": row.item_name,
            "tt_sku": sku,
            "qty": row.qty,
            "note": note,          # 皮壳行会标注取自哪个成品
        })

    # 批量换 goodsDetailId
    goods_map = PurchaseAPI().get_goods_detail_map([l["tt_sku"] for l in lines])
    resolved_lines = []
    for line in lines:
        goods = goods_map.get(line["tt_sku"])
        if not goods or not goods.get("goodsDetailId"):
            unmatched.append({
                "item_code": line["item_code"], "item_name": line["item_name"],
                "qty": line["qty"],
                "reason": _("通途 goodsQuery 查不到 SKU {0}").format(line["tt_sku"]),
            })
            continue
        line["goodsDetailId"] = goods["goodsDetailId"]
        resolved_lines.append(line)

    # 合并后的实际采购内容（同一货品累加）
    merged: Dict[str, Dict] = {}
    for line in resolved_lines:
        gid = line["goodsDetailId"]
        if gid in merged:
            merged[gid]["qty"] += flt(line["qty"])
        else:
            merged[gid] = {"tt_sku": line["tt_sku"], "goodsDetailId": gid,
                           "qty": flt(line["qty"])}

    base.update({"lines": resolved_lines, "unmatched": unmatched,
                 "merged": list(merged.values())})
    return base


# ── 数量校验 ────────────────────────────────────────────────────────────

def purchase_qty(value, label: str) -> int:
    """通途采购数量只收正整数。向下取整会静默改数量，所以宁可报错。"""
    qty = flt(value or 0)
    if qty <= 0:
        frappe.throw(_("{0} 的数量为 {1}，不能创建采购单").format(label, value))
    if qty != int(qty):
        frappe.throw(
            _("{0} 的数量为 {1}，不是整数。通途采购数量只支持整数，请先拆分该行").format(label, value)
        )
    return int(qty)


# ── 创建 ────────────────────────────────────────────────────────────────

def get_existing_purchase_order(dn) -> Optional[str]:
    if not frappe.db.has_column("Delivery Note", PURCHASE_ORDER_FIELD):
        return None
    return frappe.db.get_value("Delivery Note", dn.name, PURCHASE_ORDER_FIELD)


# 通途采购单状态：0 等待到货 / 1 部分到货等待剩余 / 2 部分到货不等待剩余 / 3 全部到货 / 4 作废
PURCHASE_ORDER_VOID_STATUS = "4"


def get_purchase_order_status(purchase_order_code: str) -> Dict:
    """查通途采购单当前状态 → {found, status, is_voided}。"""
    if not purchase_order_code:
        return {"found": False, "status": None, "is_voided": False}
    response = PurchaseAPI().client.request(
        "POST", "/openapi/tongtool/purchaseOrderQuery",
        {"purchaseOrderCode": purchase_order_code, "pageNo": 1, "pageSize": 1},
    )
    rows = (response.get("datas") or {}).get("array") or []
    if not rows:
        return {"found": False, "status": None, "is_voided": False}
    status = str(rows[0].get("status") or "")
    return {"found": True, "status": status,
            "is_voided": status == PURCHASE_ORDER_VOID_STATUS}


def clear_purchase_order_number(dn) -> Optional[str]:
    """把 DN 上的通途采购单号清空，返回被清掉的单号。"""
    if not frappe.db.has_column("Delivery Note", PURCHASE_ORDER_FIELD):
        return None
    code = get_existing_purchase_order(dn)
    if not code:
        return None
    values = {PURCHASE_ORDER_FIELD: None}
    if frappe.db.has_column("Delivery Note", PURCHASE_ORDER_TIME_FIELD):
        values[PURCHASE_ORDER_TIME_FIELD] = None
    frappe.db.set_value("Delivery Note", dn.name, values)
    frappe.db.commit()
    dn.reload()
    return code


def reset_purchase_order(delivery_note: str) -> Dict:
    """清空销售出库单上的通途采购单号，**仅当通途那边已作废**。

    未作废（等待到货/部分到货/全部到货）一律拒绝，避免把还在执行的采购单弄丢。
    """
    dn = frappe.get_doc("Delivery Note", delivery_note)
    code = get_existing_purchase_order(dn)
    if not code:
        frappe.throw(_("该销售出库单上没有通途采购单号，无需清空"))

    info = get_purchase_order_status(code)
    if not info["found"]:
        frappe.throw(_(
            "通途查不到采购单 {0}，无法确认是否已作废，暂不清空。"
            "请先到通途确认这张单的状态"
        ).format(code))
    if not info["is_voided"]:
        frappe.throw(_(
            "通途采购单 {0} 当前状态为「{1}」，尚未作废，不能清空。"
            "如需重开，请先在通途把它作废"
        ).format(code, info["status"]))

    cleared = clear_purchase_order_number(dn)
    frappe.logger().info("清空通途采购单号: DN=%s 原采购单=%s（通途已作废）" % (dn.name, cleared))
    return {"delivery_note": dn.name, "cleared": cleared}


def write_back_purchase_order(dn, purchase_order_code: str) -> None:
    if not frappe.db.has_column("Delivery Note", PURCHASE_ORDER_FIELD):
        frappe.logger().warning("Delivery Note 缺少 %s 字段，采购单号未回写" % PURCHASE_ORDER_FIELD)
        return
    values = {PURCHASE_ORDER_FIELD: purchase_order_code}
    if frappe.db.has_column("Delivery Note", PURCHASE_ORDER_TIME_FIELD):
        values[PURCHASE_ORDER_TIME_FIELD] = now()
    frappe.db.set_value("Delivery Note", dn.name, values)
    frappe.db.commit()
    dn.reload()


def create_purchase_order(
    delivery_note: str,
    supplier_id: str,
    warehouse_id_key: str,
    purchase_user_id: str,
    currency: str = None,
    remark: str = None,
    shipping_fee: float = 0,
    lines=None,
    force: bool = False,
) -> Dict:
    """在通途创建采购单并回写单号。真实写操作。"""
    dn = frappe.get_doc("Delivery Note", delivery_note)

    existing = get_existing_purchase_order(dn)
    if existing and not as_bool(force):
        frappe.throw(_("该销售出库单已创建过通途采购单 {0}，如需重开请先清空该字段").format(existing))

    customer_group = COMPANY_CUSTOMER_GROUP.get((dn.customer or "").strip())
    if not customer_group:
        frappe.throw(_("客户 {0} 不在采购范围内").format(dn.customer or "-"))

    missing = [n for n, v in (("供应商", supplier_id), ("仓库", warehouse_id_key),
                              ("采购员", purchase_user_id)) if not v]
    if missing:
        frappe.throw(_("以下参数必填：{0}").format("、".join(missing)))
    if (supplier_id or "").startswith("TODO") or (purchase_user_id or "").startswith("TODO"):
        frappe.throw(_("通途采购配置里仍有 TODO 占位值，请先在 Tongtool Settings 填真实 ID"))

    goods_detail = build_goods_detail(dn, customer_group, lines)

    payload = {
        "currency": currency or (get_purchase_settings().get("currency") or "USD"),
        "supplierId": supplier_id,
        "warehouseIdKey": warehouse_id_key,
        "purchaseUserId": purchase_user_id,
        "externalNumber": dn.get("logistic_number") or "",   # 外部流水号 = 物流单号
        "goodsDetail": goods_detail,
    }
    if remark:
        payload["remark"] = remark
    if shipping_fee:
        payload["shippingFee"] = flt(shipping_fee)

    response = PurchaseAPI().client.request(
        "POST", "/openapi/tongtool/purchaseOrderCreate", payload
    )

    purchase_order_code = response.get("datas")
    if not purchase_order_code:
        frappe.throw(_("通途未返回采购单号，请到通途界面确认是否已创建"))

    write_back_purchase_order(dn, purchase_order_code)
    frappe.logger().info(
        "通途采购单创建成功: DN=%s 采购单=%s 供应商=%s"
        % (dn.name, purchase_order_code, supplier_id)
    )
    return {
        "purchase_order_code": purchase_order_code,
        "delivery_note": dn.name,
        "line_count": len(goods_detail),
    }


def _merge_goods_detail(goods_detail: List[Dict]) -> List[Dict]:
    """同一 goodsDetailId 的多行合并成一行、数量累加。

    销售出库常把同一物料拆成多行（例如同款不同批次/不同调拨来源），
    通途采购单按货品汇总更合理；不合并会在通途建出一堆重复行。
    """
    merged: Dict[str, Dict] = {}
    order: List[str] = []
    for item in goods_detail:
        gid = item["goodsDetailId"]
        if gid in merged:
            merged[gid]["quantity"] += item["quantity"]
        else:
            merged[gid] = dict(item)
            order.append(gid)
    return [merged[g] for g in order]


def build_goods_detail(dn, customer_group: str, lines=None) -> List[Dict]:
    """组装通途 goodsDetail（已按货品合并数量）。

    前端可传回预览结果（lines），也可不传由后端重新解析（走缓存）。
    """
    if lines:
        parsed = frappe.parse_json(lines) if isinstance(lines, str) else lines
        goods_detail = []
        for line in parsed:
            goods_detail_id = line.get("goodsDetailId")
            if not goods_detail_id:
                continue
            goods_detail.append({
                "goodsDetailId": goods_detail_id,
                "quantity": purchase_qty(line.get("qty"), line.get("item_code") or goods_detail_id),
            })
    else:
        goods_detail = _build_goods_detail_from_dn(dn, customer_group)

    if not goods_detail:
        frappe.throw(_("没有可采购的货品明细，请先预览并确认匹配结果"))
    return _merge_goods_detail(goods_detail)


def _build_goods_detail_from_dn(dn, customer_group: str) -> List[Dict]:
    resolved = []
    for row in dn.items:
        sku, _note = resolve_line_sku(row.item_code, customer_group)
        if sku:
            resolved.append((row, sku))

    goods_map = PurchaseAPI().get_goods_detail_map([sku for _row, sku in resolved])

    goods_detail = []
    for row, sku in resolved:
        goods = goods_map.get(sku)
        if goods and goods.get("goodsDetailId"):
            goods_detail.append({
                "goodsDetailId": goods["goodsDetailId"],
                "quantity": purchase_qty(row.qty, row.item_code),
            })
    return goods_detail
