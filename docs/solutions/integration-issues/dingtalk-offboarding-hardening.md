---
title: new-api/sellfox-proxy 离职自动封号不可靠 —— 双通道检测加固
date: 2026-09-08
category: integration-issues
module: new-api-deployment
problem_type: integration_issue
component: authentication
severity: high
symptoms:
  - 已从钉钉组织移出的员工：每日兜底 getbyunionid 报错被当 [SKIP]，永不封号（最普遍离职路径漏网）
  - 每日兜底用 user/get 的 active=false 作封号信号，误伤未激活/长期未登钉钉的在职员工
  - user_leave_org 事件到达时若员工已被移除，实时通道反查不到 unionId → 静默 continue 不封
  - offboarding-check.py 硬编码 provider_id=1、proxy DB 路径不一致 → 静默空转或 0 行
  - 仓库无 cron 工件、无审计日志，无法证明离职封号真正执行过
root_cause: logic_error
resolution_type: code_fix
tags:
  - dingtalk
  - offboarding
  - new-api
  - sellfox-proxy
  - user_leave_org
  - identity-map
  - audit
related_components: [new-api-dingtalk-oidc, sellfox-api-proxy]
---

# new-api/sellfox-proxy 离职自动封号不可靠 —— 双通道检测加固

## Problem

员工离职后应自动封禁其在两套系统的访问：new-api（大模型网关，`users.status=2`）与
sellfox-api-proxy（赛狐 API 代理，每个员工一枚 `api_keys`，`is_active=0`）。代码里已有
「实时 Stream `user_leave_org`」与「每日 cron 兜底」双通道，但审查发现**真实离职场景反而
会漏**、且会误伤在职员工。用一个真实离职前同事（姓名不记录于本库）作验收对象，确认机制
是否真能把他自动封掉——结论是需要加固。

## Symptoms

- `offboarding-check.py` 每日兜底对每个 unionId 调 `getbyunionid`：员工若已被**移出组织**
  （离职最常见处理），该接口报错 → 函数返回 `None` → main 打印 `[SKIP]`，**不封号**。
- 兜底判断用 `user/get` 的 `active` 字段：`active=false` 只表示「未激活钉钉」，不是离职。
  未激活新员工、30 天未登钉钉的在职员工都会被误封。
- 实时 `user_leave_org` 事件只携带钉钉数字 userId，而两套系统都以 unionId 关联账号；
  员工已被移除后 DingTalk 不再解析 userId→unionId，事件处理 `continue`，**同样不封**。
- 其它静默故障：`provider_id=1` 硬编码（stream_listener 用 slug 子查询，若生产 provider
  id≠1 每日检查扫到 0 人打印假 OK）；proxy DB 默认路径与脚本不一致 → 关 key 静默 0 行。
- 仓库没有任何 cron 工件，也没有一次真实执行日志——「离职自动封号 [x]」是文档自述，
  无法证明跑过、封过谁。

## What Didn't Work

- **以 `active==false` 判定离职**：字段语义是「是否激活钉钉」，与在职状态无关，既有假阳
  （误封在职未激活员工）又漏真（活跃到被移除为止的离职者）。
- **靠实时查询钉钉确认「还在不在组织」**：反向解析在员工被移出组织后必然失败，而离职的
  普遍处理恰恰是移出组织——需要的是**离职前就沉淀下来的本地映射**，不是离职后再问钉钉。
- **对 proxy 封号静默容错**：`disable_proxy_keys` 路径错时 catch 后返回 0 只打 WARN，
  真实效果是 new-api 已封但 proxy key 仍活着且无报警。

## Solution

核心原则：**只用权威离职信号封号，其余一律 skip+留痕**；在用户仍可解析时把
unionId↔数字userId 映射沉淀到本地，事件通道优先走本地映射。

1. **每日兜底 `classify_employment` 重写**（`new-api-deployment/offboarding-check.py`）：
   - `getbyunionid` 返回 **60121（未找到对应员工）→ DEPARTED → 封号**；
   - 其余 errcode / 网络错 → RETRY → 本次跳过（绝不含糊禁用）；
   - 成功 → 员工仍在组织 → OK，不封，并 `upsert_identity_map` 回填映射。
   - **废弃 `active` 作为封号依据**。
2. **实时通道**（`new-api-dingtalk-oidc/stream_listener.py`）：事件权威、不再回查 active。
   每个 UserId 先查本地 `dingtalk_identity_map.dingtalk_user_id → union_id`，本地无才实时
   兜底并回填；仍解析不到 → `logger.error`（不再静默 continue），靠每日 60121 兜底。
   **new-api 封号无条件先做**；proxy 封号失败抛 `ProxyDisableError` → 整包
   `STATUS_LATER`（DingTalk 重投），不吞错。
3. **本地映射持续刷新**：登录回调（`main.py`）后台线程 `record_login_identity`；每日检查对
   每个 OK 用户 upsert；事件命中回填。三处共用同一 MySQL 表。
4. **一致性修复**：`provider_id=1` 换成 `slug='dingtalk'` 子查询解析，解析不到预检退出非 0；
   proxy DB 路径加 `preflight`，连不上/缺表 → `sys.exit(2)`，不再静默 0 行。
5. **审计与可执行证明**：幂等建表 `dingtalk_identity_map` + `offboarding_audit`
   （表 DDL 由脚本自身 `CREATE TABLE IF NOT EXISTS`）。每次运行写心跳行；每次封号写明细行
   （unionId/userId/username/proxy_key 数/结果）。新增 `--dry-run`（只记不封）、
   `--union-id`（可查已封用户）。

幂等建表 SQL：

```sql
CREATE TABLE IF NOT EXISTS dingtalk_identity_map (
  union_id         VARCHAR(128) PRIMARY KEY,
  dingtalk_user_id VARCHAR(128) NOT NULL,
  display_name     VARCHAR(255),
  last_verified_ts INT NOT NULL,
  created_at       INT NOT NULL,
  KEY idx_dtmap_userid (dingtalk_user_id)
);

CREATE TABLE IF NOT EXISTS offboarding_audit (
  id INT AUTO_INCREMENT PRIMARY KEY,
  ts INT NOT NULL,
  channel ENUM('stream','daily','dryrun','manual') NOT NULL,
  union_id VARCHAR(128),
  new_api_user_id INT,
  username VARCHAR(128),
  dingtalk_user_id VARCHAR(128),
  proxy_keys_disabled INT NOT NULL DEFAULT 0,
  result VARCHAR(32) NOT NULL
);
```

## Why This Works

- 被移出组织的人，`getbyunionid` 返回 60121 —— 这是**权威离职信号**，之前被当成「跳过」，
  现在当成「封号」，正是把判断方向扶正。瞬时错误（-1 系统繁忙/网络）走 RETRY 不误封。
- `user_leave_org` 事件本身权威；本地 unionId↔userId 映射让事件处理不依赖离职后再问钉钉，
  解决「userId 已被移除 → 反查失败」的死结。映射在登录/每日跑批时（人在组织内）持续刷新。
- new-api 封号先于 proxy：即使 proxy DB 暂不可达，最关键的新-api 权限收回已生效，事件重投
  直到 proxy 也封成功——两处都不会静默失败。
- `offboarding_audit` 心跳行让「到底跑没跑」有证明；`--dry-run` 上线前先演练不碰生产。

## Prevention

- **不要用 user/get 的 `active` 字段判断离职**——它只表示是否激活钉钉。权威信号是
  `user_leave_org` 事件与 `getbyunionid` 的 60121。
- 事件处理**先查本地映射再实时兜底**，映射必须在用户仍在组织时持续回填（登录 + 每日）。
- 跨系统封号脚本（本仓库 Python + docker exec）**失败要大声**：provider/DB 预检不过就退出
  非 0，proxy 关不掉就 STATUS_LATER 重投，禁止 catch 后返回 0 静默。
- 每新增一个自动运维 cron，仓库里要能拿出「会跑 + 真跑过」的证据：cron 条目、日志落盘、
  审计心跳行——文档自述的 `[x]` 不算数。
- 单测固定行为（见 `tests/new_api_offboarding/`）：60121→封、瞬时错→不封、本地映射命中仍
  封、proxy 不可达时 new-api 先封+重投。

## Related Issues

- 双通道架构原始方案（含现已过时的「查 active」表述，见下条修正提示）：
  [dingtalk-sso-new-api-oidc-bridge.md](dingtalk-sso-new-api-oidc-bridge.md)
- 测试夹具使用占位名，不涉及真实员工（隐私）。
