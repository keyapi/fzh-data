---
okf: v0.1
type: Handoff
title: Wayfair API Proxy — Agent 接手参考
description: 当前实现边界、不可违反的约束、下一步验证清单
tags: [wayfair, handoff, api-proxy, verification]
---

# Wayfair API Proxy — Agent 接手参考

## 一分钟状态

- 下游 API、鉴权、限流、审计、快照库、OIDC 管理入口已完成，`uv run pytest wayfair-api-proxy/tests` 全绿。
- 上游契约已从美国 VPS 实测：token 可用，`inventorySummaryList` operation 与字段正确；
  但应用尚无 `read:inventory_visibility` 生产权限，查询返回 “client is not authorized”。
  详见 [`docs/contract.md`](docs/contract.md)。
- `wayfair_client.py` 已按官方字段实现查询、分页、token 刷新与错误归类；capability 仍全部关闭。
- 已在 US Vultr 部署：Python venv + systemd，仅监听 `127.0.0.1:8410`；
  `inventory_snapshot` / `inventory_live` / `inventory_transactions` 开启，inbound 关闭。
  首快照 1255 仓位 / 1007 parts / 11 仓；每日 23:00 UTC（北京 07:00）timer 已启用。
- 未安装 Docker：Docker 会改 iptables，可能影响该机现有的 Tailscale/CLIProxyAPI
  应急出口；如需容器化，先单独评估网络规则。
- 公网 HTTPS 已上线：`https://wayfair-api.vilavi.cn`（Nginx 443 → 127.0.0.1:8410；
  Let's Encrypt DNS-01，certbot.timer 已启用；公网 /admin 与 /ready 返回 404）。
- Tailscale Serve 备线已启用：`http://vultr.alpines-grouper.ts.net:8080`（仅 tailnet）。
- EN 生产无 Tailscale，但已实测公网拉取整份快照（1255 条）；EN key 在
  `/etc/wayfair-api-proxy/en.key`（`600 root`），只含 snapshot + transactions 读权限。

## 不可违反的约束

1. **不得猜 Wayfair 接口。** 任何新增 operation/字段都必须先只读实测，并更新
   `docs/contract.md` 的脱敏记录。
2. **未验证能力保持关闭。** 下游必须收到 `501 capability_unavailable`，不得把
   “在途未知”写成 `0`。
3. **不做通用代理。** 调用方不能提交任意 path、query 或 GraphQL document。
4. **key 只存哈希。** 不引入可逆加密、reveal API 或明文列。
5. **不记录凭证。** 审计只记录 key id、账号、operation、状态码、耗时、结果数、错误分类。
6. **共享 VPS 操作需授权。** 部署、重启、Nginx/防火墙改动都先问用户。

## 代码地图

| 关注点 | 文件 |
|--------|------|
| 路由与审计中间件 | `main.py` |
| 账号/capability 配置 | `config.py`、`config.example.yaml` |
| 授权矩阵 | `auth.py`、`operations.py` |
| 快照发布/读取 | `db.py` 的 `publish_inventory_snapshot` / `read_inventory` |
| freshness 与 501 语义 | `service.py`、`errors.py` |
| 限流 | `rate_limit.py`（进程内，单 worker 前提） |
| token single-flight | `oauth_cache.py` |
| 快照 worker | `snapshot.py` |
| key 管理 | `manage.py` |

## 解锁生产权限后要做的

1. 在 Developer Portal 完成 CastleGate Inventory On-Hand 的 sandbox 测试（需 Partner
   Home 管理员），解锁生产 `read:inventory_visibility`。
2. 把 `config.yaml` 的 `supplier_id` 填成真实 parent supplier ID。
3. 运行 `python snapshot.py --account centrade`，核对上游行数与写入数；失败不覆盖旧快照。
4. 用已知 SKU 做 Portal / snapshot / live 三方对账，通过后才把 `inventory_snapshot`
   或 `inventory_live` 改为 `true`。
5. inbound 只有在官方文档出现独立 operation 后才实现，否则保持 501。

## 常用命令

```bash
uv run pytest wayfair-api-proxy/tests
uv run python wayfair-api-proxy/manage.py list
uv run python wayfair-api-proxy/snapshot.py --account centrade
WAYFAIR_SMOKE_KEY=... WAYFAIR_SMOKE_SKU=... \
  uv run python wayfair-api-proxy/smoke_test.py --url https://wayfair-api.example.com
```

## 已知缺口

- 生产权限未解锁，真实数据尚未完成对账；字段映射按官方定义实现。
- 管理入口只有 JSON API，没有 HTML 页面；key 管理也可继续用 `manage.py`。
- 快照 worker 的重叠防护（flock/数据库租约）等真实采集落地时再加。
- 数据库只有轻量列迁移（`owner`），无完整版本化。
- TestClient 的 `httpx2` 弃用警告未处理，不影响功能。

## 相关经验（docs/solutions）

- `docs/solutions/integration-issues/wayfair-castlegate-inventory-api.md` — 契约、权限、分页与 null 语义（2026-10-29 补：微秒 ErrorCode 104、transfer 页码 1 索引、仓库名来源、汇总=分仓合计）
- `docs/solutions/architecture-patterns/wayfair-cg-stock-table-and-parquet-grain.md` — EN 库存表为什么把 CG 总计行和分仓行放同一张表、Parquet 为什么按粒度拆文件
- `docs/solutions/developer-experience/erpnext-wayfair-sync-timezone-pitfalls.md` — 本地 naive 时间、MariaDB/DuckDB 时区、Single 默认值、bulk_insert、远程跑 bench 脚本
- `docs/solutions/architecture-patterns/shared-egress-vps-venv-systemd-no-docker.md` — 为什么这台 VPS 不用 Docker
- `docs/solutions/developer-experience/gitignore-sensitive-pattern-hides-source-module.md` — `*token*` 忽略源码的教训

## 契约细节（2026-10-29 实测）

- 变动查询 `from/to` **不能带微秒**：`isoformat(timespec="seconds")`；否则 HTTP 200 但
  GraphQL 返回 `Unexpected failure` / `ErrorCode=104`。
- `inventoryAdjustmentList` 页码 0 索引；`inventoryTransferList` 页码 1 索引（1–1000）。
- 仓库名没有清单查询：`legacySuppliersOrWarehousesByFilters` 实际返回 null 报错；
  仓名只能从调拨/变动记录的 `SupplierWarehouse {warehouseId name}` 汇总。
- 新增 `GET /v1/accounts/{account}/inventory/warehouses`（回看 3 年调拨、缓存 6h、
  复用 `inventory:transactions:read`）。
- `castleGate.onHandQty` 等外层字段 = `warehouses[]` 逐仓合计（1007 part 实测 0 差异）；
  `castleGate=null` 表示无 CG 库存位置，不是 0、不是总计行。

## 同事自助门户

- `/portal`：公司钉钉 OIDC 登录即准入；自助只能领 `inventory:snapshot:read`；
  一人一枚，重建停旧，60 秒冷却/每日 3 次；明细见 `docs/portal.md`
- 启用需 `oidc.portal_redirect_uri` + `WAYFAIR_PORTAL_SESSION_SECRET`；
  不维护 per-user 白名单
- live / transactions 仍由管理员发 key；EN 的 manual key 不受门户影响

## 离职自动撤销

- `POST /v1/offboarding/owners/{owner}/deactivate`，operation `offboarding:deactivate`
- 服务 key `offboarding.key`（VPS 600 root）；new-api 的 offboarding 脚本通过
  `WAYFAIR_OFFBOARDING_URL` / `WAYFAIR_OFFBOARDING_KEY` 调用
- 停用 owner 名下全部 key；失败由 offboarding 脚本记 proxy_pending 次日重试
