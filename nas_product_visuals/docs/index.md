---
okf: v0.1
type: Index
title: NAS 运维脚本
description: 部署在群晖 /volume1/技术部/ 的 Bash 脚本集合 — 产品目录扫描 + ACL 权限实时修复
tags: [nas, synology, bash, acl, inotify]
---

# NAS 运维脚本

## 脚本清单

| 脚本 | 用途 | 触发方式 |
|------|------|---------|
| `generate_products_visuals.sh` | 扫描 /volume1/产品信息/ 下所有产品文件夹路径 | 定时任务 (每天) |
| `fix_design_permissions.sh` | 实时监控"设计稿"文件夹，自动添加 DENY ACE 移除"视觉需求（读取）"角色权限 | 开机触发 (root) |

## DSM 计划任务命令

```
flock -xn /volume1/技术部/.fix_design.lock -c '/bin/bash /volume1/技术部/fix_design_permissions.sh'
```

## 文档导航

- [AGENT_HANDOFF.md](../AGENT_HANDOFF.md) — 部署详情 + 连接排障 + NAS 注意事项
- [log.md](log.md) — 完整调试记录 + 经验教训 (Bug 1-8 + 问题 A-E)
- [fix_design_permissions.sh](../fix_design_permissions.sh) — 脚本源码

## 新对话速查

1. **连接**: `ssh fzh.nas@192.168.1.5 -p 31022` (局域网) 或 `fzh.myds.me` (外网)，密码需向用户询问
2. **环境**: 先 `uv sync` (不要 `uv add paramiko` — 已在 pyproject.toml)
3. **编码**: Windows 下所有 Python 输出必经 `io.TextIOWrapper(buf, encoding='utf-8')`
4. **部署**: base64 over SSH exec (不用 SFTP)
5. **排障**: `ps aux | grep inotify` 比搜脚本名可靠
