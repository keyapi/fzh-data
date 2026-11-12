---
okf: v0.1
type: Reference
title: 侧台账的行级范围：默认拒绝 + bridge 过滤 + 快照对象不外发
date: 2026-11-12
category: docs/solutions/architecture-patterns/
module: demand_collaboration
problem_type: architecture_pattern
component: api-gateway
severity: high
applies_when:
  - "侧台账（SQLite/文件）挂在 ERPNext 下，多运营共用但需按商品/分公司隔离"
  - "不用 DocType，Frappe 自带权限不生效，需要自己实现行级范围"
  - "发布快照里嵌了全部行，担心一次读取就泄露整个台账"
tags: [row-level-scope, sqlite, frappe, rbac, default-deny, side-ledger]
---

# 侧台账的行级范围：默认拒绝 + bridge 过滤 + 快照对象不外发

## Context

运营需求协同的台账是站点私有目录里的 SQLite，不是 DocType。首版对所有获授角色共享整份台账；README 也自认“尚无按运营商品/分公司的行级隔离”。这在单机演示没问题，但一开放给多个运营，任何 Contributor 都能读到全部 1,513 行基准和所有提案。

## Guidance

### 范围键与事实源

- 范围键用 `(product_id, branch)`，与 D5 的物理商品/分公司一致；`unit`/`physical_form` 是同一商品属性，不单独授权。
- 事实源是站点私有 `demand_scope.json`，由 System Manager 通过 `set_scope` 维护；**默认拒绝**：没有 active assignment 的用户看到 0 行。
- 禁止用历史仓归属、`owner`、`created_by` 或“谁最近改过”推断范围；必须有业务确认的映射。

### 在 bridge 层过滤，core 保持无状态

```python
allowed = None if scope.all_scope(roles) else scope.keys_for(assignments, user)
state = scope.filter_state(store.state(), allowed)
```

- `allowed=None` 表示 Reviewer / System Manager 全量；其余用户只保留范围内的 baseline rows、proposals、audit。
- `submit` 二次校验：`row_id` 必须在 allowed 集合里；未知行/范围外行一律 **403**，不要落到 core 的 404/422。
- **publication 对象必须对 scoped 用户整体隐藏**：一个快照嵌了全部 rows，过滤 rows 但保留对象仍会泄露。运营端返回 `publications: []`，发布/下载只给 Reviewer/SM。
- 过滤后给前端 `coverage`（可见行数/基准总行数），避免把“部分覆盖”当成“全量”。

### 发布与角色

- Reviewer 建议全量，才能裁决跨运营冲突；若某 Reviewer 也有 assignment，不要允许其发布全局快照（或明确标 coverage）。
- 范围文件变更写一条 ledger audit（`scope_updated`）；范围文件不要进 git。

## Why This Matters

Frappe 的 DocType 权限对侧台账完全不起作用；bridge 是唯一闸门。最危险的泄露不是 rows，而是 **publication 对象**：它每次发布都复制全部行，任何能读 `/api/publications/{id}` 的角色都等于拿到整份基准。范围过滤必须同时覆盖 rows、proposals、audit 和快照对象。

## When to Apply

- 任何“EN 登录 + 独立服务/文件台账”的多人协作工具。
- 任何在 API 层返回“发布快照/整表导出”的接口。
- 不适用于纯单用户本地工具（此时用服务端配置的固定身份即可）。

## Examples

```python
def filter_state(state, allowed):
    if allowed is None:
        return state
    rows = [r for r in state['baseline']['rows']
            if (r['product_id'], r['branch']) in allowed]
    ids = {r['id'] for r in rows}
    return {**state,
            'baseline': {**state['baseline'], 'rows': rows},
            'proposals': [p for p in state['proposals'] if p['row_id'] in ids],
            'publications': [],   # 快照嵌全量行，整体隐藏
            'coverage': {'visible_rows': len(rows),
                         'baseline_rows': len(state['baseline']['rows']),
                         'scope': 'assigned'}}
```

## Related

- `demand_collaboration/scope.py`、`demand_collaboration/frappe_bridge.py`
- `integration-issues/frappe-desk-page-iframe-rpc-bridge.md` — EN 入口与 bridge
- `demand_collaboration/docs/review-2026-11-12.md` — 跨范围提交/快照读取均 403
