---
okf: v0.1
type: Index
title: NAS 运维脚本
description: 部署在群晖 /volume1/技术部/ 的 Bash 脚本集合 — 产品目录扫描 + ACL 权限修复
tags: [nas, synology, bash, acl, inotify]
---

# NAS 运维脚本

## 脚本清单

| 脚本 | 用途 |
|------|------|
| `generate_products_visuals.sh` | 扫描 /volume1/产品信息/ 下所有产品文件夹路径 |
| `fix_design_permissions.sh` | 实时监控"设计稿"文件夹，自动移除"视觉需求（读取）"角色权限 |

## 部署

- 服务器: `fzh.myds.me:31022` (DSM 7)
- 用户: `fzh.nas`
- 部署路径: `/volume1/技术部/`
- 任务计划: DSM 任务计划器 → 开机触发 → root

## 参考

- [AGENT_HANDOFF.md](../AGENT_HANDOFF.md) — generate_products_visuals.sh 详情
- [log.md](log.md) — 变更 + 调试记录
