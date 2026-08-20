---
okf: v0.1
type: Reference
title: 赛狐皮壳共享库存代理
description: 单 SKU 沙盒审计脚本的运行入口。
---

# 赛狐皮壳共享库存代理

该模块为三角类皮壳共享库存方案提供文档和只读沙盒审计。决策依据见 [canonical 记录](../docs/solutions/conventions/sellfox-cover-shared-inventory-transition.md)。

先复制并修改 `sandbox.example.json`，配置只允许一个映射：

```json
{
  "warehouse_name": "CENTRADE",
  "tongtool_base_sku": "TT123",
  "tongtool_cover_sku": "TT123-Cover",
  "sellfox_bottom_sku": "KS0001-DM-194-GREY",
  "sellfox_cover_sku": "PK#KS0001-DM-194-GREY",
  "listing_msku": "example-cover-msku",
  "shop_name": "example-shop"
}
```

```powershell
uv run python sellfox_cover_inventory/audit_sandbox.py --config path/to/sandbox.json
uv run python sellfox_cover_inventory/audit_sandbox.py --config path/to/sandbox.json --live
```

第一条只校验配置并输出计划；第二条读取赛狐仓库和商品。两者都不会创建商品、配对 Listing 或调整库存。报告写入 `sellfox_cover_inventory/out/`。
