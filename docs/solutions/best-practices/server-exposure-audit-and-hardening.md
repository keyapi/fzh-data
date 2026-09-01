---
title: 服务器暴露面审计与安全加固（数据库远程 root、端口瘦身、凭证轮换）
date: 2026-09-01
category: best-practices
module: infrastructure
problem_type: best_practice
component: database
severity: high
applies_when:
  - 公开仓库曾出现硬编码数据库/API 凭证，需要全面评估泄露影响
  - 新服务器上线、或凭证泄露后需要做暴露面安全审计
  - 需要清理数据库远程超级账号（root@%），避免远程 root 死账户
  - 需要判断哪些公网端口该放行、哪些该封
tags: [security, hardening, mariadb, mysql, root-remote, port-exposure, credential-rotation, firewall]
related_components: [database, tooling]
---

# 服务器暴露面审计与安全加固

## Context

一次 PR 审核发现 new-api 部署脚本硬编码了生产 MySQL root 密码并提交到**公开 GitHub 仓库**（阻断红线）。修复脚本硬编码的同时，触发了一次完整的服务器暴露面安全审计——结果发现比"脚本密码泄露"更严重的问题：**ERPNext 的 MariaDB 存在 `root@%`（允许任意 IP 远程连接的数据库超级账号），且 3306 端口曾公网可达**。

本学习记录这套可复用的审计方法 + 加固动作，供之后新开对话或任何 Agent 接手时直接参考。

## Guidance

### 1. 凭证入公开仓库 = 按已泄露处理

- 密码一旦进入公开 git 历史，**删除文件无法撤回**（fork 副本、旧 commit 永久保留）
- 不要纠结"是否真能被利用"（端口是否暴露、是否需要 SSH）——**统一按已泄露处理，轮换凭证**
- 检查 git 历史：`git log --all -S "<secret>" -- <path>`
- 确认仓库可见性：`gh repo view --json visibility`

### 2. 凭证不硬编码在脚本/文档

脚本从环境变量或服务器 gitignored 的 `.secrets.env` 读取：

```bash
# .secrets.env (chmod 600, gitignored)
MYSQL_ROOT_PASSWORD=...
DINGTALK_APP_KEY=...
DINGTALK_APP_SECRET=...
```

Python 脚本读取模式（MySQL 密码经 `docker exec -e MYSQL_PWD=` 传入容器，不经命令行参数）：

```python
def _mysql_password():
    pwd = os.environ.get("MYSQL_ROOT_PASSWORD", "").strip()
    if pwd:
        return pwd
    # 回退到服务器 .secrets.env
    if SECRETS_FILE.is_file():
        for line in SECRETS_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("MYSQL_ROOT_PASSWORD="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("MYSQL_ROOT_PASSWORD 未配置")
```

### 3. 数据库账号最小化：删除远程 root（`root@%`）

MariaDB/MySQL 的 `root@%` 是允许任意 IP 远程连接的超管账号，**绝大多数场景是多余的死账户**：

| 账号 | 含义 | 是否该存在 |
|------|------|-----------|
| `root@localhost` | 仅本机连接（应用、socket 认证） | ✅ 保留 |
| `root@%` | 任意 IP 远程连接 | ❌ 通常删除 |

**检测它是否被使用（万分检测清单）**：
```sql
-- 当前连接来源（应全为 localhost）
SELECT user, host, db FROM information_schema.processlist;
-- 历史是否有过远程连接（0 = 从无远程连接）
SELECT COUNT(*) FROM performance_schema.host_cache;
-- 应用实际连接配置（应 host=localhost）
cat /path/frappe-bench/sites/*/site_config.json
```

**删除前记录授权（供救火）**：
```sql
SHOW GRANTS FOR 'root'@'%';
```

**删除**：
```sql
DROP USER IF EXISTS 'root'@'%';
FLUSH PRIVILEGES;
```

**救火（完全可逆，root@localhost 有 WITH GRANT OPTION）**：
```sql
CREATE USER 'root'@'%' IDENTIFIED BY PASSWORD '<原 hash>';
GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' WITH GRANT OPTION;
FLUSH PRIVILEGES;
```

### 4. 安全组/端口瘦身：只放行必要端口

阿里云安全组默认规则常放行大量端口。用 `ss -tlnp` 看本机实际监听，用公网 IP 自测可达性：

```bash
for port in 22 80 443 3306 143 25 3389; do
  timeout 3 bash -c "echo > /dev/tcp/<公网IP>/$port" 2>/dev/null && echo "$port 可达" || echo "$port 不可达"
done
```

**关键判断**：
- 监听 `127.0.0.1` 的端口（如 ERPNext 8000、redis）公网连不上，即使安全组放行也无实际暴露 → 从安全组清理减暴露面
- 应用用 `localhost` 连数据库 → **数据库端口（3306）完全不需要公网放行**
- 邮件用外部服务器 → 服务器不需要开放 25/143 入站

**只保留 22/80/443**（SSH/网站）。其余从安全组删除。

### 5. 纵深防御：防火墙 + fail2ban

- 安全组是云层防护，**服务器本机防火墙（ufw/firewalld）是第二层**，建议启用
- SSH 禁密码登录（`PasswordAuthentication no`）+ 仅密钥 + fail2ban 防爆破

### 6. 凭证轮换流程

泄露后轮换（以钉钉 AppSecret 为例）：
1. 在钉钉开发者后台生成新 AppSecret（Client ID 不变）
2. 更新服务器 `.secrets.env` + docker-compose 环境变量
3. 重建容器：`docker compose up -d <service>`
4. 验证：用新 secret 调 API 拿 token 成功

## Why This Matters

- **公开仓库凭证泄露无法撤回**，轮换是唯一可靠修复；删除文件不够（git 历史 + fork 副本永久保留）
- **`root@%` 是远程超管死账户**：端口一旦误开（安全组改动/网络变化），死账户立即可用。删掉它 = 少一把"万能钥匙"
- **端口暴露 + 弱密码可被爆破**：fail2ban 默认只护 SSH 不护 MySQL，数据库端口公网暴露是高频攻破点
- **纵深防御**：安全组 + 防火墙双层，单层失效不至于裸奔

## When to Apply

- 任何新服务器上线前，做暴露面审计
- 公开仓库出现凭证后，全面排查影响面
- 接手不熟悉的服务器时，快速评估数据库/端口暴露
- 数据库远程账号清理（`root@%`）、安全组瘦身

## Examples

**实际加固案例（上海阿里云两台服务器，测试 + 生产，共享安全组）**：

| 动作 | 结果 |
|------|------|
| 删 `root@%`（测试 + 生产） | ✅ host_cache=0（从无远程连接），删后 ERPNext/SSH/Agent 全部正常 |
| 封公网 3306/5432/6379/8000/11000/12000/13000/143/25 | ✅ 只留 22/80/443 |
| 轮换钉钉 AppSecret | ✅ 新 secret 验证通过 |
| 修复脚本硬编码密码 | ✅ 改 .secrets.env 读取 |

**审计命令速查**：
```bash
# SSH 配置
sshd -T | grep -E "passwordauthentication|permitrootlogin"
# 监听端口
ss -tlnp
# Docker API 是否暴露
ss -tlnp | grep -E ":(2375|2376)"
# 数据库远程账号
mysql -e "SELECT user, host FROM mysql.user;"
# 历史远程连接
mysql -e "SELECT COUNT(*) FROM performance_schema.host_cache;"
```

## Related

- [new-api 峰谷分时定价自动化](../tooling-decisions/new-api-deepseek-time-based-pricing-automation.md) — new-api 部署脚本（本次审计的起点）
- [钉钉 SSO 登录 new-api](../integration-issues/dingtalk-sso-new-api-oidc-bridge.md) — new-api 部署方案（脚本/凭证模式）
- [ChatGPT Edu CLIProxyAPI 429 限流](../integration-issues/chatgpt-edu-cliproxyapi-429-rate-limit.md) — new-api 网关上下文
