---
okf: v0.1
type: HowTo
title: Wayfair Sandbox 测试（解锁生产权限）
description: 用 Sandbox Access Token 跑通 CastleGate Inventory On-Hand，解锁 read:inventory_visibility
tags: [wayfair, sandbox, permissions, castlegate]
---

# Wayfair Sandbox 测试（解锁生产权限）

## 先厘清

- Sandbox 测试是**按应用（client_id）+ 按 API** 记录的，与领星等第三方是否使用无关。
- 领星以前做过的是它需要的 API；CastleGate Inventory On-Hand 没做，所以我们的应用
  现在仍然没有 `read:inventory_visibility` 生产权限。
- 这个测试不需要写 ERP 代码，只需要用 Sandbox Access Token 向沙盒地址发一次
  `inventorySummaryList` 查询。

## 需要谁做

sandbox token 只能在 Developer Portal 生成，登录需要 Partner Home 的 API 角色。
两种方式，任选其一：

1. **最省事**：管理员（YTQ）在 Partner Home → User Management 给操作人加上
   **API access role**，之后操作人自己登录 `developer.wayfair.io`。
2. **不共享账号**：管理员自己生成 sandbox token，交给操作人，或直接由管理员在本机/美国
   VPS 跑下面的脚本。

不需要把 Partner Home 密码给任何人。

> 已实测：用 **Sandbox 应用自己的 client_id/secret** 向 `sso.auth.wayfair.com` 换 token，
> 也能直接请求沙箱 URL 并通过 sandbox 测试；不一定需要手工生成 Sandbox Access Token。
> 前提仍然是登录 Portal 拿到 Sandbox 应用的凭证。

## 操作步骤

1. 登录 `https://developer.wayfair.io`，进入 **Application Management**。
2. 找到持有当前 `client_id` 的应用，确认这是 Centrade 的应用。
3. 进入 **Overview**，选择 **CastleGate Inventory On-Hand API**，点 **Test in Sandbox**，
   复制 Sandbox URL（应为 `https://api.wayfair.io/sandbox/v1/supplier-order-api/graphql`）。
4. 生成 **Sandbox Access Token**。
5. 用真实 parent supplier ID 和至少一个真实 CastleGate SKU 跑脚本（从美国 VPS 执行）：

```bash
# token 只放受控文件，0600；测完删除
install -m 600 deploy/sandbox.env.example /etc/wayfair-api-proxy/sandbox.env
# 编辑该文件填入 token / supplier id / SKU 后：
ssh us-ubuntu-proxy 'set -a; . /etc/wayfair-api-proxy/sandbox.env; set +a; python3 -' \
  < wayfair-api-proxy/scripts/sandbox_test.py
```

`WAYFAIR_SUPPLIER_ID` 是 Partner Home 里的 **parent supplier ID**，不是 CG 子仓 ID
（PO 数据里的 `supplierId` 实际是 NJ/CA 等 CastleGate 仓库的子供应商 ID，两者不同）。

输出 `SANDBOX OK` 即请求成功。若报错：

- `401`：token 过期或不是 sandbox token。
- `not authorized`：选错了应用/API，或 sandbox token 不属于该应用。
- 空 `edges`：supplier ID 或 SKU 与沙盒数据不匹配，换真实 CG SKU。

6. 约 30 秒后刷新 **Sandbox Testing** 页面，对应 API 应从 `Not Started` 变为 `Done`。
7. 回到 **Application Management → Permissions**，确认生产环境里
   `read:inventory_visibility` 已解锁并勾选。生产权限是「逐步解锁 + 默认勾选」，
   若未自动勾选则手动勾上。

## 通过之后我们这边做什么

```bash
# 用生产 token 复测
WAYFAIR_CONFIG=/etc/wayfair-api-proxy/config.yaml \
WAYFAIR_DATABASE=/srv/wayfair-api-proxy/data/wayfair.db \
uv run python wayfair-api-proxy/snapshot.py --account centrade
```

- `snapshot_runs` 出现 `status=success`，`upstream_count == written_count`。
- 用同一个 SKU 在 Partner Home / snapshot / live 三方对账。
- 对账通过后才把 `inventory_snapshot` 或 `inventory_live` 改为 `true`。

## 安全

- sandbox token 也只放环境变量，不写文档、不进 Git、不发群。
- 脚本只打印状态码、错误信息、节点数与字段名，不打印 token、SKU 列表或完整 payload。
- 不要为了测试另建应用或换 client_id；沿用现有应用，保持账号一致性。
