---
okf: v0.1
type: HowTo
title: 运维手册
description: Wayfair API Proxy 的部署、secret 轮换、验收、备份与回滚
tags: [wayfair, operations, deployment, secrets, rollback]
---

# 运维手册

## 前置闸门（未满足不得部署）

1. 用户明确授权本次共享 VPS 操作。
2. Wayfair secret 只写入 `/etc/wayfair-api-proxy/env`（`0600`，root 所有），
   不进 Git、不进聊天、不进日志。用户已决定不轮换现有 secret。
3. 认证环境完成最小只读探测：token 获取、库存 operation、字段、分页、限流。
   已完成，见 [contract.md](contract.md)。
4. 应用获得生产 `read:inventory_visibility` 权限，并完成至少一个真实 SKU 对账。
5. 只有实测通过的 capability 才可改为 `true`。

## 上游权限开通（Wayfair 侧，需人工）

1. 由拥有 Partner Home API 角色的管理员登录 `developer.wayfair.io`。
2. Application Management → 对应应用 → Permissions，确认 CastleGate Inventory
   On-Hand 相关权限已解锁。
3. 在 Overview 选择 CastleGate Inventory On-Hand API → Test in Sandbox，用
   Sandbox Access Token 跑通一次 `inventorySummaryList`。
4. 生产权限解锁后，把真实 parent supplier ID 写入配置的 `supplier_id`。
5. 回到本机跑 `python snapshot.py --account centrade`，确认 `snapshot_runs` 为 success
   且计数与上游一致。

## 目录约定

```text
/etc/wayfair-api-proxy/config.yaml   非敏感配置，只读挂载
/etc/wayfair-api-proxy/env           secret 环境变量，0600
/srv/wayfair-api-proxy/data/         SQLite（WAL）持久目录
```

## 部署步骤（需授权）

本机实际采用 **venv + systemd**；不要在共享美国 VPS 上安装 Docker，Docker 会改
iptables，可能影响现有 Tailscale/CLIProxyAPI 应急出口。`deploy/docker-compose.yml`
仅作其他环境的备选。

```bash
# 1. 代码与 venv（系统需 python3.12-venv）
install -d -o wayfair -g wayfair /opt/wayfair-api-proxy
tar -xzf wayfair-api-proxy.tar.gz -C /opt/wayfair-api-proxy
python3 -m venv /opt/wayfair-api-proxy/.venv
/opt/wayfair-api-proxy/.venv/bin/pip install -r /opt/wayfair-api-proxy/requirements.txt
chown -R wayfair:wayfair /opt/wayfair-api-proxy

# 2. 配置与 secret
install -d -m 755 /etc/wayfair-api-proxy
install -d -m 750 -o wayfair -g wayfair /srv/wayfair-api-proxy/data
install -m 640 -o root -g wayfair deploy/env.example /etc/wayfair-api-proxy/env
install -m 644 config.example.yaml /etc/wayfair-api-proxy/config.yaml

# 3. systemd
install -m 644 deploy/systemd/wayfair-api-proxy.service /etc/systemd/system/
install -m 644 deploy/systemd/wayfair-snapshot.service /etc/systemd/system/
install -m 644 deploy/systemd/wayfair-snapshot.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now wayfair-api-proxy.service wayfair-snapshot.timer

# 4. Nginx（可选，公网/Tailscale HTTPS 时）：替换占位域名后启用
nginx -t && systemctl reload nginx

# 5. 本机验收
curl -fsS http://127.0.0.1:8410/health
curl -fsS http://127.0.0.1:8410/ready
```

`/ready` 是 503 时先查数据库目录权限与磁盘，不要直接重启。uvicorn 使用
`--no-access-log`，请求日志由应用中间件统一输出，避免 OIDC 回调 query 进入访问日志。

## 防火墙

只保留 SSH（key-only）、80/443、Tailscale。应用端口不对公网开放。
Tailscale 客户端同样走 `https://<域名>`，不直连 `127.0.0.1`。

## 创建与停用 key

```bash
cd /opt/wayfair-api-proxy
set -a; . /etc/wayfair-api-proxy/env; set +a
WAYFAIR_CONFIG=/etc/wayfair-api-proxy/config.yaml \
WAYFAIR_DATABASE=/srv/wayfair-api-proxy/data/wayfair.db \
.venv/bin/python manage.py create --name forecast --owner <dingtalk-sub> \
  --account centrade --operation inventory:snapshot:read
```

明文 key 只在终端打印一次，立即写入调用方的 secret 管理。人员离职或 key 泄露时用
`python manage.py deactivate --id <id>`；按人批量停用用管理入口
`POST /admin/api/owners/{owner}/deactivate`。

### 管理员入口（可选）

启用条件：

- `config.yaml` 有 `oidc` 段，且 `admin_identities` 填入了管理员的 OIDC `sub`；
- `/etc/wayfair-api-proxy/env` 设置了 `WAYFAIR_ADMIN_SESSION_SECRET`
  （`openssl rand -hex 32`）与 OIDC client 凭证。

之后访问 `https://<域名>/admin/oidc-login` 登录，再用 JSON 接口管理 key。
会话 cookie 为 HttpOnly + SameSite=Lax；`oidc.cookie_secure` 默认 `true`，
仅本机 HTTP 调试时改为 `false`。非白名单身份登录返回 403，不会自动获得任何 key。

管理员动作同样写入 `audit_events`（operation 为 `admin:keys:*`）。

## 快照 worker

```bash
systemctl start wayfair-snapshot.service      # 手工跑一次
systemctl list-timers wayfair-snapshot.timer  # 查看下次运行
journalctl -u wayfair-snapshot.service --since today
```

默认 timer：**每天 23:00 UTC = 北京 07:00**，带 60 秒抖动，`Persistent=true`。
一次全量约 13 页、3 秒、1255 个仓位，对 1C2G 无感。若业务需要更高新鲜度，可在
`OnCalendar` 增加 13:00/19:00/01:00（北京时间），否则日常一次足够，临时查用 live。

**EN 每日拉取**建议排在快照之后，例如北京 **07:20**：调用
`GET /v1/accounts/centrade/inventory/snapshot` 取整份快照，写 `stock_latest` 等价表
并追加 parquet/JSONL。EN 若直读 live API，则不受此时间限制。

## 验收清单

1. `localhost` health/ready 正常。
2. Tailscale 客户端用最小权限 key 查询快照。
3. 公网 HTTPS 客户端执行相同查询；验证 401、403（账号/operation 越权）、429。
4. 手工跑 worker，核对上游 N 行与写入/跳过/失败总数；制造一次失败确认旧快照仍在。
5. 等待 timer 自动运行一次，检查 run 记录与 freshness。
6. 用 Centrade CastleGate 已知 SKU 做 Portal / snapshot / live 三方对账。
7. 重启本服务，确认现有 CLIProxyAPI 不受影响；检查 CPU、内存、磁盘、监听端口。
8. `uv run python scripts/check_secrets.py` 零输出，根索引已同步。

## 备份与恢复

```bash
# 一致性备份（WAL 模式）
sqlite3 /srv/wayfair-api-proxy/data/wayfair.db ".backup '/backup/wayfair-$(date +%F).db'"
```

恢复：`systemctl stop wayfair-api-proxy.service wayfair-snapshot.timer` → 用备份替换
`wayfair.db`（删除同目录 `-wal`/`-shm`）→ `systemctl start wayfair-api-proxy.service
wayfair-snapshot.timer` → 查 `/ready`。

## 回滚

1. `systemctl stop wayfair-api-proxy.service wayfair-snapshot.timer`。
2. 恢复上一版 `/opt/wayfair-api-proxy` 代码与 venv（或整目录备份）及 Nginx 配置备份。
3. `nginx -t && systemctl reload nginx`。
4. `systemctl daemon-reload && systemctl start wayfair-api-proxy.service wayfair-snapshot.timer`。
5. 数据不回滚，除非确认新快照写坏；失败 run 本身不会覆盖成功快照。

## secret 轮换

1. 在 Wayfair Portal 生成新 secret 并撤销旧值。
2. 更新 `/etc/wayfair-api-proxy/env`（保持 `640 root:wayfair`，不要世界可读）。
3. `systemctl restart wayfair-api-proxy.service` 使新 secret 生效。
4. `systemctl start wayfair-snapshot.service` 手工跑一次，确认 worker 与 live 查询仍鉴权成功；
   失败时恢复旧 env 文件并重启。

## 日志

- 应用按 request id 记录方法、路径、状态、耗时；不记录 header/body。
- Nginx access log 使用 `$uri`（不含查询串），uvicorn 关闭 access log。
- 审计事件在 `audit_events` 表，可按 `account`、`operation`、`status_code` 查询。

## 尚未实现

- worker 重叠防护：真实采集落地时增加文件锁或数据库租约。
- 数据库版本化迁移。
- 管理入口只有 JSON API，没有 HTML 页面。
