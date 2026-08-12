---
okf: v0.1
type: Index
module: sellfox_shipping
created: 2026-08-07
updated: 2026-08-11
---

# sellfox_shipping — 已解决问题索引

## 2026-08

- [tongtool-order-mark-2026-08-12.md](tongtool-order-mark-2026-08-12.md) — 通途订单标记：美东100.xls 参考编号 → EN Tongtool Package → Amazon 订单号 → 本地包裹匹配 → is_tongtool 持久化 + Transactions 过滤（114/114 匹配）
- [send-to-sellfox-trackno-writeback-2026-08-11.md](send-to-sellfox-trackno-writeback-2026-08-11.md) — 赛狐 Amazon FBM 追踪号写回问题反馈（可发送给赛狐表单）：submitToPlatform/quickOutbound 均写不进 trackNo + quickOutbound shipmentType=1 疑似触发订单变已发货
- [sellfox-trackno-writeback-test-2026-08-10.md](sellfox-trackno-writeback-test-2026-08-10.md) — P2BAA9T735007 写回测试详细记录（请求/响应/问题/待赛狐确认）
- [upsert-package-dims-pk-fk-bug-2026-08-10.md](upsert-package-dims-pk-fk-bug-2026-08-10.md) — 面单创建报 "No dimensions available"：`upsert_package_dims` 用 `session.get` 按主键 id 查外键 package_id，写错别家行导致目标包裹尺寸永不落库
- [tiktok-exclude-shops-2026-08-07.md](tiktok-exclude-shops-2026-08-07.md) — TikTok 排除店铺：赛狐 API 核实真实 shop_name + `exclude_shops` 单点配置驱动列表过滤与路由建议
- [reliability-hardening-and-lizard-chain-2026-08-06.md](reliability-hardening-and-lizard-chain-2026-08-06.md) — 可靠性收口与蜴国际面单链路：分页count、resume并发、证据化结案、蜴国际API、报价展示、赛狐回写、批量面单、async阻塞、参考号重复（含 2026-08-07 CENTRADE ca_zone 遗留修复）

## 2026-07

- [chatgpt-ups-fedex-analysis-reference-2026-07-22.md](chatgpt-ups-fedex-analysis-reference-2026-07-22.md) — ChatGPT 通途 UPS/FedEx 承运商分析参考
