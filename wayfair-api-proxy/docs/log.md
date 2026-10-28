---
okf: v0.1
type: Log
title: 变更日志
description: Wayfair API Proxy 的时序变更记录
tags: [wayfair, api-proxy, changelog]
---

# 变更日志

## 2026-10-28

- 建立模块骨架：FastAPI 固定业务路由、账号 + operation 授权、SHA-256 key 存储。
- 快照库实现事务发布：成功 run 原子切换 `current_snapshots`，失败 run 不覆盖旧快照。
- 增加审计事件（request id、key、账号、operation、状态码、耗时、结果数、错误分类）与 key 用量计数。
- 限流改为 token bucket，小数速率按真实间隔生效（`0.2` = 每 5 秒 1 次）。
- 新增 `/ready`、inbound 查询入口（未验证时 501）、手动快照入口（未验证时 501）。
- 新增 `manage.py`（key 创建/列出/启停）与 `smoke_test.py`（localhost/公网双路径）。
- 新增钉钉 OIDC 管理员入口（JSON API）：仅白名单身份可用，登录不自动授权、不自动建 key。
- `api_keys` 增加 `owner`（含轻量列迁移），支持按人批量停用。
- **上游实测**：从美国 VPS 确认 OAuth token 可用（`expires_in=86400`），
  `inventorySummaryList` operation 与 CastleGate 字段正确；当前应用缺
  `read:inventory_visibility` 生产权限。记录见 [contract.md](contract.md)。
- `wayfair_client.py` 实现真实查询、分页、token 刷新与错误归类；capability 仍关闭。
- 新增 sandbox 测试脚本与步骤（`scripts/sandbox_test.py`、`docs/sandbox-test.md`），
  用于解锁生产 `read:inventory_visibility`。
- 实测 CastleGate 其他只读 operation：`getCastleGatePurchaseOrders`、
  `getCastleGateWarehouseShippingAdvice`、`inboundStockPurchaseOrderStats`。
  PO/WSA 生产可直接读（头级/运单级），SKU 级在途仍未确认，详见 [contract.md](contract.md)。
- 探测写操作边界：CG 库存由 Wayfair 管理，不需要 inventory feed；WSA/PO acknowledge、
  ship 等写能力留到对应工作流落地时再开。
- 改用新建的专用 Sandbox/Production 应用（不再使用 Lingxing 命名应用）。用 Sandbox
  client 凭证换取 token 跑通 sandbox；用 Production 凭证按真实 CG SKU 查询
  `inventorySummaryList` 成功返回在库/可售/不可售与分仓数据。capability 仍关闭，
  待真实快照对账后开启。
- **部署（2026-10-28）**：美国 Vultr 上以 Python venv + systemd 运行，仅监听
  `127.0.0.1:8410`；未安装 Docker，避免其 iptables 规则影响 Tailscale/CLIProxyAPI
  应急出口。smoke 全绿；首快照 1255 个仓位、1007 个 supplier part、11 个仓库。
  `inventory_snapshot=true`，`inventory_live` / `inbound_live` 仍为 false。
- 实时与快照同 SKU 逐仓对比一致；启用 `inventory_live`（只读，0.2 rps）。
- 新增整份快照导出 `GET /v1/accounts/{account}/inventory/snapshot`，供 EN 每日拉取；
  VPS 仅保留 `snapshot_retention_days`（默认 7 天），长期历史归 EN/parquet。
- Sandbox 内省确认：`inventoryAdjustmentList` 生产可读（变动流水）；
  CGF `inboundOrder` 有 SKU 级在途/里程碑字段但当前为空；写 mutation 仅 acknowledge，
  无创建补货货件能力。
- 新增库存变动接口 `POST /v1/accounts/{account}/inventory/transactions/query`
  （`inventory:transactions:read`），返回带符号数量、仓、类型、描述；
  实测某 SKU 6 条记录。注意上游 `page` 从 0 开始。
- 启用每日快照 timer：23:00 UTC = 北京 07:00；EN 拉取建议排在北京 07:20。
- 新增 EN 接入建议 `docs/en-integration.md`：CG 不进 ERPNext DocType，先原始 JSONL
  + DuckDB `cg_stock_*`，后续再建 `cg_sku_map` / `cg_warehouse_dim` / `inventory_unified`。
- 访问路径：公网 HTTPS 主用（待子域名/证书/UFW 443），Tailscale Serve 备线已启用
  `http://vultr.alpines-grouper.ts.net:8080`，SSH 隧道应急。
- Nginx 1.24 已安装但保持 disabled；实际模板用自签证书 `nginx -t` 通过，
  `/health` 200、`/admin` 与 `/ready` 404；公网 443 尚未开放。
- 核对通途 `stock_latest`：确有 WayfairCG-Cranbury/Perris/Romeoville 三个仓，但覆盖
  仅 92/4/2 个 SKU；Cranbury 与 Wayfair 交集 76，45 个完全一致，存在最大 +104 的偏差。
  结论：CG 以 Wayfair 为准，通途 CG 行不并入合计，只作交叉校验。
- 新增 Docker Compose、Nginx、systemd service/timer 示例，全部使用占位符。
- Wayfair 上游客户端保持安全闸门：任何未验证 operation 返回 `capability_unavailable`。
