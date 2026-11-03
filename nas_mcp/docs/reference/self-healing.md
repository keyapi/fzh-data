---
okf: v0.1
type: Reference
title: nas_mcp 自愈方案（探活 / 自动重启）
description: 2026-11-03 假活故障复盘；进程崩溃、假活、上游故障三类失败的区别；A/B/C 三方案对比；探活频率（10 分钟不必要，30 分钟推荐，1 小时可接受）与实施草图
tags: [nas, mcp, self-healing, healthcheck, watchdog, docker, systemd]
timestamp: 2026-11-03
---

# nas_mcp 自愈方案

## 1. 故障复盘（2026-11-03）

**现象**：容器 `nas-mcp` 活着，端口在，Bearer 鉴权正常，`tools/list` 返回 200 + 15 个工具；
但所有真实 NAS 操作返回 DSM 错误码 **119 `Invalid session / SID not found.`**。
ChatGPT 连接器显示「已连接」，一查文件就报错。

**时间线（容器日志）**：

| 时间 (UTC) | 事件 |
|---|---|
| 2026-10-04 23:58 | 最后一次正常调用 |
| —— | **闲置 29 天** |
| 2026-11-02 00:00 | 调用 → 会话失效 → 进程内重登 → 重试**成功** |
| 2026-11-02 00:00 | `nas_list_shares` 失败（该工具的重试路径有闭包 bug，见 §5） |
| 2026-11-03 03:18 起 | 重登后调用**仍** 119；反复重登无效 |
| 2026-11-03 03:38 | `docker restart nas-mcp` → 全部恢复 |

**已排除**：容器内代码与仓库 sha256 一致；容器 env 与 `/opt/nas-mcp/.env` 一致（密码哈希相同）；
DNS 稳定单 IP；同一凭据在**新进程**里登录、列目录、列共享文件夹全部正常；线程内调用正常。

**结论**：不是网络/凭证/NAS 侧问题，是**长时间运行的进程状态坏了**（库的会话重建路径在进程内失效）。
闲置导致的 DSM 会话过期是触发条件之一，但不是唯一原因 —— 11-02 重登还能救回来，11-03 就不行了。
**重启进程即可恢复**；容器没有 healthcheck，所以「活着但不可用」不会被发现。

## 2. 三类失败要分开处理

| 类型 | 表现 | 正确动作 |
|---|---|---|
| **进程崩溃** | 容器退出 | Docker `restart=unless-stopped` 已覆盖，无需额外处理 |
| **假活（liveness）** | 进程在、HTTP 200，但功能全废 | 探针 + 自动重启 |
| **上游故障** | DSM/NAS 不可达，或**登录就失败** | **不要重启**（重启无用且会风暴），应告警 |

> 关键判据：**能登录但调用全失败 → 本地状态坏了 → 重启**；**连登录都失败 → 上游问题 → 告警**。

## 3. 三个方案

| | A. 定时探活 + 重启 | B. HEALTHCHECK + autoheal | C. 进程内 watchdog |
|---|---|---|---|
| 检测 | 外部定时器（systemd timer / cron） | Docker 健康检查 | 服务内部线程 |
| 恢复 | 脚本 `docker restart` | `willfarrell/autoheal` 监听 unhealthy 并重启 | 重建全部客户端状态 |
| 依赖 | systemd + curl | 额外跑一个 autoheal 容器 | 无外部依赖 |
| 成本 | 低（约 20 行） | 中（多一个常驻容器 + 重建镜像） | 中（改代码、需重新构建部署） |
| 优点 | 最小改动；顺带保活会话 | 标准化，所有「假活」都能兜 | 不依赖外部组件，最接近 let-it-crash |
| 缺点 | 只管这台容器 | Docker 的 HEALTHCHECK **本身不会重启容器**，必须有 autoheal | 进程整体损坏（如本例）时线程本身可能也失效 |

**推荐 A**：成本最低，且探活本身就让 DSM 会话保持热，把「闲置过期」这个触发条件一起消掉。
等 MCP 服务变多、或迁到编排平台（K8s livenessProbe 会自动重启）再升级。

## 4. 探活频率：10 分钟没必要

探针有两个作用：**检测延迟** 和 **会话保活**。

- **会话保活**：只要间隔显著小于 DSM 闲置超时即可。本次实测闲置 **29 天**才过期，
  说明 DSM 的超时是「小时～天」量级，不是分钟级。**10 分钟属于过度设计。**
- **检测延迟**：决定坏了多久被发现。内部只读工具，30 分钟完全够；1 小时也可接受。

| 间隔 | 每天次数 | 最长发现延迟 | 评价 |
|---|---|---|---|
| 10 分钟 | 144 | 10 分钟 | 没必要 |
| **30 分钟** | **48** | **30 分钟（或 60 分钟，若要求连续 2 次失败才重启）** | **推荐** |
| 1 小时 | 24 | 1 小时（或 2 小时） | 可接受，更安静 |

补充：每次探活只是列 1 项目录，负载可忽略；真正的取舍是**恢复延迟 vs 抖动容忍**。
建议 **30 分钟间隔 + 连续 2 次失败才重启**：偶发一次 NAS 抖动不会误重启，真挂了最长约 1 小时恢复。

## 5. 实施草图（方案 A）

**探活脚本**（放在 VPS，例如 `/usr/local/bin/nas-mcp-healthcheck.sh`）：

```bash
#!/usr/bin/env bash
set -euo pipefail
set -a; . /opt/nas-mcp/.env; set +a          # 只取 NAS_MCP_TOKEN 等
STATE=/run/nas-mcp-health.fail

resp=$(curl -sS -m 60 -X POST http://127.0.0.1:8402/mcp \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $NAS_MCP_TOKEN" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"nas_health","arguments":{}}}' || true)

if printf '%s' "$resp" | grep -q '"available": true'; then
  rm -f "$STATE"
  exit 0
fi

n=$(( $(cat "$STATE" 2>/dev/null || echo 0) + 1 ))
echo "$n" > "$STATE"
if [ "$n" -ge 2 ]; then
  logger -t nas-mcp-health "unavailable x$n, restarting"
  docker restart nas-mcp
  rm -f "$STATE"
fi
```

**systemd timer**：

```ini
# /etc/systemd/system/nas-mcp-healthcheck.service
[Unit]
Description=nas_mcp healthcheck
[Service]
Type=oneshot
ExecStart=/usr/local/bin/nas-mcp-healthcheck.sh

# /etc/systemd/system/nas-mcp-healthcheck.timer
[Unit]
Description=Run nas_mcp healthcheck every 30 minutes
[Timer]
OnBootSec=5min
OnUnitActiveSec=30min
[Install]
WantedBy=timers.target
```

启用：`systemctl daemon-reload && systemctl enable --now nas-mcp-healthcheck.timer`。

> 注意：探针必须是**真实 NAS 调用**（`nas_health`），不能只探 HTTP 200 —— 本次故障 HTTP 层一直是好的。
> 另外脚本里 `docker restart` 前应能区分「登录失败」：若日志是 `LoginError` / 连接错误，说明上游坏了，
> 此时重启无用，应只告警。（当前简化版未区分，必要时再加。）

## 6. 顺带发现的代码问题（未修，待评估）

`tool_list_shares()` 里 `fetch()` 闭包绑定了旧的 `c`，`globals()["_nas"] = None` 后重试**仍在用旧客户端**：

```python
c = nas_client()
def fetch():
    r = c.get_list_share(...)      # 闭包捕获旧的 c
try:
    return fetch()
except NasError:
    globals()["_nas"] = None
    out = fetch()                   # 还是旧的 c，换汤不换药
```

这解释了 11-02 00:00 `nas_list_shares` 在别的工具已重登成功后仍然失败。**但这不是 11-03 全挂的原因**
（`nas_health` 走 `list_strict`，重登逻辑是正确的，同样失败）。属于独立的小 bug，可另开单修。

## 7. 验证

1. 手动跑一次探活脚本，确认返回 `available: true` 时退出码 0、不重启。
2. 临时把脚本里的判断反向或停掉 NAS 可达性，确认连续 2 次失败后触发重启。
3. `systemctl list-timers | grep nas-mcp` 确认定时器生效。
4. 观察一周日志，确认无 `Invalid session`。
