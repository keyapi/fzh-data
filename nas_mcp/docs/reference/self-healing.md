---
okf: v0.1
type: Reference
title: nas_mcp 自愈方案（探活 / 自动重启）
description: 2026-11-03 假活故障的真实根因（synology_api 类级共享会话）、修复与已上线状态；探活频率结论（30 分钟推荐）与实施脚本
tags: [nas, mcp, self-healing, healthcheck, watchdog, docker, systemd, synology-api]
timestamp: 2026-11-03
---

# nas_mcp 自愈方案

> 状态：**已实施并验证**（2026-11-03）。代码修复 + 镜像 `nas-mcp:0.1.1` + 30 分钟探活定时器。

## 1. 故障复盘

**现象**：容器活着，端口在，Bearer 鉴权正常，`tools/list` 返回 200 + 15 个工具；
但所有真实 NAS 操作返回 DSM 错误码 **119 `Invalid session / SID not found.`**。
ChatGPT 连接器显示「已连接」，一查文件就报错。

**两次复现**：

- 老容器连续运行 42 天：10-04 最后一次使用，闲置 29 天后（11-02）开始失败。
- 重启后 **仅 3 小时又失败**：03:38 建立会话，05:46 首次调用即 `Session timeout`（闲置约 2 小时）。

→ 因此不是「跑久了进程腐化」，而是**只要 DSM 会话过期一次，进程内重登就救不回来**。

**真实根因**：`synology_api` 把 `Authentication` 缓存在**类级属性** `BaseApi.shared_session` 上。
`BaseApi.__init__` 的逻辑是：

```python
if BaseApi.shared_session:
    self.session = BaseApi.shared_session      # ← 直接复用，不重新登录
else:
    ... 新建 Authentication 并 login() ...
    BaseApi.shared_session = self.session
```

所以 `nas_client(relogin=True)` 里 `new FileStation(...)` **并没有登录**，
日志里的「DSM 会话重建」是假象 —— 实际仍带着那个已失效的 SID，于是永远 119。

**验证**（容器内，同一份库）：

1. 正常调用成功 → 在服务端强制 `logout`（客户端仍持有旧 SID）。
2. 旧代码：`tool_health` 返回 `available: false`（重登无效）。
3. 修复：重建前把 `BaseApi.shared_session = None` → 拿到新 SID，调用成功。

## 2. 修复内容（server.py）

| 改动 | 说明 |
|---|---|
| `nas_client()` 重建前清 `BaseApi.shared_session` | 根因修复：确保 `relogin=True` 真正重新登录 |
| 新增 `retry_on_session(fn)` | 会话失效（105/106/107/119）→ 真重登后重试一次；用于 search / folder_size / md5 / archive |
| `tool_list_shares()` 改为重试循环 | 原先 `fetch()` 闭包绑定旧客户端，`globals()["_nas"]=None` 后仍用旧 `c` |
| `tool_thumbnail()` 走 `retry_on_session` | 原裸 requests 拿旧 `_sid`，失效后不会自愈 |

**回归测试**：`tests/test_smoke.py` 第 15 节 —— 服务端强制登出后，
`nas_health` 与 `nas_list_shares` 都必须自动恢复。旧代码必挂，新代码通过。

## 3. 运行时兜底：30 分钟探活

即使代码能自愈，仍需要兜底（NAS 重启、网络中断、进程卡死等情况）。

- 脚本：`/usr/local/bin/nas-mcp-healthcheck.sh`
- 定时器：`nas-mcp-healthcheck.timer`（`OnUnitActiveSec=30min`）
- 策略：**连续 2 次** `nas_health` 不可用才 `docker restart nas-mcp`；
  若返回是 `LoginError` / `ConnectionError`（上游/凭证问题）则**只记日志、不重启**，避免重启风暴。

> ⚠️ 探针必须解析 JSON，不能 grep 字符串：MCP 响应的内层 JSON 是**转义字符串**
> （`\"available\": true`），直接 grep `"available": true` 永远匹配不上 —— 第一版脚本就踩了这个坑。

## 4. 探活频率：10 分钟没必要

实测 DSM 会话闲置超时约 **2 小时**（03:38 登录 → 05:46 报 `Session timeout`）。

| 间隔 | 每天次数 | 最长发现延迟 | 评价 |
|---|---|---|---|
| 10 分钟 | 144 | 10 分钟 | 没必要（超时是小时级） |
| **30 分钟** | **48** | 30 分钟（连续 2 次失败 → 约 60 分钟） | **已采用** |
| 1 小时 | 24 | 1 小时（→ 约 2 小时） | 可接受，余量只剩 2× |

30 分钟相对 2 小时超时是 4× 余量，即使偶尔漏一次也不会过期；1 小时也安全但余量更小。
负载可忽略：每次只列 1 项目录。

## 5. 失败分类（别盲目重启）

| 类型 | 表现 | 正确动作 |
|---|---|---|
| 进程崩溃 | 容器退出 | `restart=unless-stopped` 已覆盖 |
| 假活（本模块） | 进程在、HTTP 200，但功能全废 | 代码自愈 + 探活重启 |
| 上游故障 | 登录都失败 / 连不上 NAS | **不要重启**，告警（脚本已区分） |

## 6. 更标准的演进方向

- **Docker `HEALTHCHECK` + `willfarrell/autoheal`**：标准化「假活」自愈，但要额外跑一个 autoheal 容器。
- **Kubernetes `livenessProbe`**：探针失败由 kubelet 自动重启，是当前最标准的做法；单机小服务上 K8s 过重。
- **应用内 watchdog 线程**：不依赖外部组件，但进程整体损坏时线程也可能失效。
- 当前选择 systemd timer：成本最低，**同时保活会话**，且能区分上游故障。

## 7. 验证记录（2026-11-03）

- 外部 HTTPS 真实调用：`nas_health` available=true、`nas_list_shares` 2 个共享、`nas_list_folder` 正常。
- 强制登出回归：`nas_health` / `nas_list_shares` 均自动恢复。
- 故障演练：`docker stop nas-mcp` → 第 1 次探活计 x1 → 第 2 次触发 `restarting nas-mcp` → 容器自动拉起、健康恢复。
- 定时器：`systemctl list-timers` 显示下一次 30 分钟后执行。
