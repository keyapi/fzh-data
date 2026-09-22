---
okf: v0.1
type: Log
title: 集成问题 — 变更日志
---

# 变更日志

| 日期 | 操作 | 文档 | 说明 |
|------|------|------|------|
| 2026-09-22 | 新增 | [carrier-label-batch-field-length-limits.md](carrier-label-batch-field-length-limits.md) | UPS Reference 1~5 **各 35 字符、超了整批被拒**（`Invalid Package Reference Value`）；FedEx 批量模板 `Available headers` 里 `poNumber=String(30)`、`itemDescription=String(450)`、`reference=String(30)`。两个可复用做法：**上限从官方模板自带的字段定义表读**（FedEx 那张表就在本地模板 xlsx 里）、**用「承运商已接受历史文件的最长值」交叉验证**（实测 UPS Reference 2 最长 30 / FedEx poNumber 最长 29，都贴着上限 ⇒ 没出事只是还没撞上多 SKU 订单）。关键认知：拼接串变长是模板从「每包裹一行」改「每货品一行」**新引入**的风险，旧模板下合并是空操作（最长 32）。 |
| 2026-09-22 | 新增 | [sku-name-backfill-via-en-customer-code.md](sku-name-backfill-via-en-customer-code.md) | 背贴品名为空时怎么补：查名键 = 通途导出 `Reference 2` 原样字符串，表是 `US SKU Name` sheet。**通途SKU 在 EN 存于 `Item.customer_code` / `customer_items[].ref_code`，不在 `item_languages.tt_sku`**（后者只存 `-Cover` 成品码，海绵件干脆为空）。三个访问性坑：`Item Language` **子表不能 list**（403，但可逐 Item 读）、`commodity_sku` **不能当过滤字段**、`Item.name` 是物料编码搜不到 TT 号。PIM API `pim_api.get_sku_item_itemgroup_mapping` 可映射，**但必须先做假阳性测试**（丢不存在的 SKU 应返回 `not_found`）并横验同族自洽。尺寸↔序号**不成顺序**（153→4183、160→4182）必须逐条读。另记：同一个件在通途=直角 / EN PIM=方格 / 同包裹皮壳=菱形时，说明它是**跨款式中性件**，别硬选一个款式名。 |
| 2026-09-21 | 新增 | [sellfox-amazon-settlement-plug-only.md](sellfox-amazon-settlement-plug-only.md) | Amazon 账期报表（Transaction / Summary PDF）在赛狐侧**只有「插件获取报告」一条路**，该接口纯读、**API 无法触发抓取**（旁证：`创建报告任务` 只支持 `PRODUCT_SALE_REPORT`；`亚马逊原报告` 类型枚举无账期）。`fileUrls` 为 **1 小时有效的腾讯 COS 预签名 URL**，不能存链接只能即取即下。实测 90 店仅 39 店有数据、只覆盖 6/7 月 ⇒ **51 店需运营在插件侧补抓**。另留档一个**已被否决**的替代方案（`monthProfit/shopSummary` 服务端销售额、覆盖全店但属赛狐自算口径），以免将来重复提议。 |
| 2026-09-20 | 修复 | [dingtalk-sso-new-api-oidc-bridge.md](dingtalk-sso-new-api-oidc-bridge.md) | 修正指向 `us_openai_api_proxy/`、`new-api-deployment/` 的失效相对链接（少退一级，`../../` → `../../../`） |
| 2026-09-08 | 新增 | [cliproxyapi-auth-unavailable-oauth-recovery.md](cliproxyapi-auth-unavailable-oauth-recovery.md) | CLIProxyAPI `503 auth_unavailable`：区分进程健康与上游授权可用性，固化升级、浏览器 OAuth、失效认证记录隔离和目标模型真实请求验收；全程使用占位符。 |
| 2026-09-08 | 更新 | [dingtalk-offboarding-hardening.md](dingtalk-offboarding-hardening.md) | 补「生产部署与实测」：上海生产已上线双通道（每日 cron 0 3 * * * + 实时 bridge 重建），实测 3 名离职者自动封号 status=2；bridge 容器需挂 proxy DB volume + PROXY_DB_PATH，否则 disable_proxy_keys 抛错致 STATUS_LATER 无限重投；proxy 关 key 链路容器内函数级实测通过 |
| 2026-09-08 | 新增 | [dingtalk-offboarding-hardening.md](dingtalk-offboarding-hardening.md) | new-api/sellfox-proxy 离职自动封号加固：60121 判离职替代 active、本地 identity_map(unionId↔userId)、provider slug 解析、proxy 失败 proxy_pending 次日补关、offboarding_audit 心跳/明细、--dry-run；真实离职场景之前会漏(移出组织→[SKIP])会误伤(在职未激活) |
| 2026-09-01 | 新增 | [cursor-state-vscdb-synology-cdrive-backup.md](cursor-state-vscdb-synology-cdrive-backup.md) | Cursor state.vscdb 膨胀 + Synology 连续备份吃 C 盘：根因、诊断方法、GC 局限、预防；附 `scripts/check_cursor_cdrive_health.py` |
| 2026-08-31 | 更新 | [nas-multi-domain-access-openwrt-quickconnect.md](nas-multi-domain-access-openwrt-quickconnect.md) | 路径 A/B（OpenWrt 自定义域 vs QC/myds）；DSM 外部访问 DDNS 不能改 QC 目标；勿删 myds |
| 2026-08-28 | 新增 | [nas-multi-domain-access-openwrt-quickconnect.md](nas-multi-domain-access-openwrt-quickconnect.md) | NAS 多域名（daneey/vilavi）、OpenWrt ACME+反代、QC 直连/中继、联通 443 与深圳未决 |
| 2026-08-13 | 新增 | [tongtool-erp2-mcp-shared-rate-limit.md](tongtool-erp2-mcp-shared-rate-limit.md) | 通途 ERP2 MCP 接入、细粒度授权探测和双 App 共享五次每分钟限流验证 |
| 2026-08-05 | 新增 | [chatgpt-edu-cliproxyapi-429-rate-limit.md](chatgpt-edu-cliproxyapi-429-rate-limit.md) | ChatGPT Edu 单账号 CLIProxyAPI 429 限流调研，含限流机制分析、事件还原、定价确认、缓解方案 |
| 2026-06-26 | 新增 | [dingtalk-sso-new-api-oidc-bridge.md](dingtalk-sso-new-api-oidc-bridge.md) | 钉钉 SSO + OIDC Bridge 桥接 new-api 方案 |
