---
okf: v0.1
type: Reference
title: EN 服务器与环境访问（SSH / REST）
description: 生产与测试两台 ERPNext 服务器的 SSH 别名、bench 目录、REST 凭证来源与常见坑
tags: [erpnext, ssh, rest, access, environment]
timestamp: 2026-09-24
---

# EN 服务器与环境访问

> **先读这条**：SSH 入口以 `~/.ssh/config` 的中文别名为准 —— **不要凭记忆拼 `用户@IP`**，
> 也不要因为默认 key 被拒就断言"主机不可达"（见「常见坑」第 1 条）。

## SSH 入口

| 环境 | 别名（定义在 `~/.ssh/config`） | 主机 | 用户 |
|------|------------------------------|------|------|
| 生产 | `阿里云-FZH-ERPNext-frappe` | `47.116.128.218` | `frappe` |
| 测试 | `上海测试-阿里云-FZH-ERPNext-frappe` | `8.133.254.66` | `frappe` |

```bash
ssh 阿里云-FZH-ERPNext-frappe            # 生产
ssh 上海测试-阿里云-FZH-ERPNext-frappe    # 测试
```

- 两台共用同一把私钥，路径写在 `~/.ssh/config` 的 `IdentityFile` 里（**私钥不进仓库**）
- 测试机 `dev01@8.133.254.66` 也能登（早期 handoff 里写的就是它），但**以别名 / `frappe` 为准**
- bench 都在 `/home/frappe/frappe-bench`；生产 `frappe` 用户有 NOPASSWD sudo

## 改服务器代码后必须重启

```bash
cd /home/frappe/frappe-bench && sudo -u frappe bench restart
```

- 只改 `public/js/*` **不需要**重启（浏览器硬刷新或 `bench clear-cache` 即可）
- ⚠️ 测试机的 bench 里也有一个同名站点 `erpnext.vilavi.cn` —— 别重启错 bench
- `bench restart` 权限不对会**静默失败**，重启后要确认真的生效

## REST API

| 环境 | base | 凭证（`EN_API/.env`） |
|------|------|----------------------|
| 生产 | `https://erpnext.vilavi.cn` | `ERP_API_KEY` / `ERP_API_SECRET`（或 `PROD_ERP_API_KEY` / `PROD_ERP_API_SECRET`） |
| 测试 | `https://ensh.vilavi.cn` | `TEST_ERP_API_KEY` / `TEST_ERP_API_SECRET` |

认证头 `Authorization: token <key>:<secret>`。**两台都是 SSH 与 REST 并存**，不存在"生产只能走 REST"。

## 常见坑

1. **`Permission denied (publickey)` ≠ 主机不可达**
   per-host 配置在 `~/.ssh/config`，不写 `-i` 用默认 key 连会被拒。历史文档里大量
   "生产 SSH 不可达 / 没有 SSH"就是这个误判的产物（2026-09-24 已勘误）。

2. **app 的 Python 依赖在生产可能没装**
   生产部署流程只同步代码 + `bench migrate`，**不跑 `bench setup requirements`** —— 自定义 app
   新增的 pip 依赖不会自动进 bench env，调用时抛 `ModuleNotFoundError`。补装要定向手动做：

   ```bash
   cd /home/frappe/frappe-bench
   env/bin/pip install -i https://mirrors.aliyun.com/pypi/simple/ <包名>   # 生产 pip.conf 指清华源，实测极慢
   env/bin/python -c "import <包名>"                                      # 冒烟
   ```

   代码里 import 写在函数内的，装完**不必重启** bench（失败 import 不入 `sys.modules`）。
   优先对齐仓库 `.venv` 里已验证的版本，别装 latest。

3. **OPS 很长时必须走 POST body**：放 query string 会被 nginx 414。

## 相关

- [`../AGENT_HANDOFF.md`](../AGENT_HANDOFF.md) — EN_API 模块入口
- [`../../../docs/solutions/documentation-gaps/agent-system-access-documentation-gap.md`](../../../docs/solutions/documentation-gaps/agent-system-access-documentation-gap.md)
  — 为什么这些访问事实必须写进文档（两次踩坑：FAC/REST 选错、SSH 入口失传）
