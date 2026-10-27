# -*- coding: utf-8 -*-
"""口径常量与仓库范围判定。

仓库只做「有证据的」分类，不按文件名/店铺名猜：
- FBA：仓库名含 ``FBA``（或 EN ``order_type == "FBA"``）。
- 第三方/代发：仓库名含 ``代发``，或属于 ``THIRD_PARTY_WAREHOUSES`` 显式清单
  （``WayfairCG-*`` 依据 supply_timeline ``warehouse_map`` v3 的 3pl/assumed）。
- 自营海外分公司仓：仓库名含 ``CENTRADE`` / ``DANEEY`` / ``POLAND`` / ``FZHPoland``，
  或属于 ``OWN_WAREHOUSES`` 显式清单。
- 其余：``unknown``（保留，不并入自发货，也不猜）。

对 EN 订单：``order_type`` 本身就是源系统的口径，``order_type=自发货`` 且仓库不在
FBA/第三方清单内 → ``self_fulfilled_candidate``（候选，不等于已核实的自营仓）。
对 GS 历史行：没有 ``order_type``，仓库未映射 → ``unknown``。
"""

from __future__ import annotations

import re

# fulfillment_scope 四分类（不要新增第五类；未映射一律 unknown）
SCOPE_SELF = "self_fulfilled_candidate"
SCOPE_FBA = "fba"
SCOPE_THIRD_PARTY = "third_party_or_dropship"
SCOPE_UNKNOWN = "unknown"

ALL_SCOPES = (SCOPE_SELF, SCOPE_FBA, SCOPE_THIRD_PARTY, SCOPE_UNKNOWN)

# 需求口径：发货方式决定这条行代表成品还是组件，不能混算。
DSHIP_FINISHED = "finished_good"
DSHIP_COVER = "cover"
DSHIP_SEMI = "semi_finished"
DSHIP_EMBEDDED = "embedded_component"  # is_deliver_good=0：随单发出的组件，不算成品需求
DSHIP_UNKNOWN = "unknown"

SHIPPING_METHOD_TO_KIND = {
    "成品": DSHIP_FINISHED,
    "皮壳": DSHIP_COVER,
    "半成品": DSHIP_SEMI,
}

# 明确第三方运营/代发的仓（证据写在 evidence 里）
THIRD_PARTY_WAREHOUSES = {
    "WayfairCG-Cranbury仓": "warehouse_map v3: warehouse_scope=3pl (assumed)",
}
THIRD_PARTY_PATTERN = re.compile(r"代发")

# 明确的海外分公司自营仓（名字族，含旧名）
OWN_WAREHOUSE_PATTERN = re.compile(r"CENTRADE|DANEEY|POLAND|FZHPoland", re.IGNORECASE)
OWN_WAREHOUSES = {
    "美东-CENTRADE",
    "美中-FZH-DANEEY",
    "波兰-FZHPoland-covers",
}

FBA_PATTERN = re.compile(r"FBA", re.IGNORECASE)

# 名字看起来是外部仓但缺独立证据：保留为 unknown，不猜归属。
UNMAPPED_WAREHOUSES = {
    "星链海外仓",
    "北美之路-NJ02",
    "大件云仓",
    "多渠道仓库",
    "休斯顿1号仓",
    "休斯顿1号备用仓库",
    "海外仓美西仓库备用仓",
    "海外仓美中仓库备用仓",
    "扬州仓库",
}

WAREHOUSE_SCOPE_VERSION = "v1_2026-10-27"

# EN 读取字段（只读）
ORDER_HEAD_FIELDS = [
    "name",
    "order_id_code",
    "platform_order_id",
    "order_type",
    "order_status",
    "invalid",
    "suspended",
    "sale_time",
    "paid_time",
    "despatch_complete_time",
    "updated_time",
    "last_sync_time",
    "modified",
    "creation",
    "warehouse_name",
    "package_id",
    "tracking_number",
    "merchant_carrier_shortname",
    "channel",
    "account",
    "sale_account",
    "platform_code",
    "channel_account_en",
    "order_amount",
    "order_amount_currency",
    "raw_data",
]

ORDER_ITEM_FIELDS = [
    "idx",
    "platform_sku",
    "tongtool_sku",
    "erp_item_code",
    "quantity",
    "is_deliver_good",
    "goods_detail_id",
    "web_store_item_id",
    "shipping_method",
    "match_status",
    "asin",
    "transaction_price",
    "calc_price_rmb",
    "item_cost",
]

ORDER_PACKAGE_FIELDS = [
    "package",
    "tracking_number",
    "allocated_fee",
    "currency",
    "allocated_carrier_fee",
    "carrier_currency",
]

# 历史 GS 月表覆盖到 2026-09-30；10 月起用 EN 增量。
DEFAULT_LEGACY_CUTOVER = "2026-10-01"
