---
okf: v0.1
type: Research
title: 现成开源 NAS MCP 横评 — 该学什么、要不要换掉自建
description: 2026-11 重扫 GitHub 上的群晖 MCP 生态；mrquj 最贴近我们的安全/传输姿态，cmeans 是最成熟的工程范本（vDSM 矩阵测试、单飞重认证、Auto Block 防护）；我们独有的图片/PDF/Office 渲染与中文产品目录场景别人没有。结论：不整体替换，按清单借鉴
tags: [nas, synology, mcp, open-source, research, session, healthcheck]
timestamp: 2026-11-03
---

# 现成开源 NAS MCP 横评（2026-11）

## 一句话结论

**不整体替换，按清单借鉴。** 我们自建的「只读 + 路径边界 + Bearer + 远程 HTTP + 图片/PDF/Office 渲染」
在**产品图/中文共享目录**这个场景上仍是最贴合的；但**工程稳健性**（会话生命周期、健康检查、
API 发现、错误翻译、测试体系）确实不如成熟项目 —— 这正是 2026-11-03 那次「会话假重登」暴露出来的差距。

## 1. 生态横评

| 项目 | 语言/协议 | 活跃度 | 传输 | 范围 | 与我们的关系 |
|---|---|---|---|---|---|
| [mrquj/mcp-server-synology](https://github.com/mrquj/mcp-server-synology) | TypeScript / MIT | 0★，最后 push 2026-07-30 | **Streamable HTTP `POST /mcp` + Bearer**、默认绑 `127.0.0.1:3020` | FileStation / Download Station / Photos / Container / System + 受控通用桥 | ⭐ **姿态最接近**：只读默认、路径白名单、策略下不可行的工具直接隐藏、`/healthz` |
| [cmeans/mcp-synology](https://github.com/cmeans/mcp-synology) | Python / PyPI 包 | **14★，2026-11-03 仍在更新** | **stdio 为主**；Streamable HTTP 明确列为 roadmap | System / FileStation / Photos / Download Station / Storage，READ/WRITE 分级 | ⭐ **工程最成熟**：vDSM 矩阵 CI、codecov、真实 NAS live-test、多客户端实测 |
| [vocweb/synology-mcp-server](https://github.com/vocweb/synology-mcp-server) | TypeScript | 11★，2026-10-04 | stdio + SSE | Synology Office 套件（Drive/Spreadsheet/MailPlus/Calendar） | 不是文件浏览场景；安全默认值可参考 |
| [rafalr100/synology-mcp](https://github.com/rafalr100/synology-mcp) | Python | 8★，最后 push 2026-06 | — | 71 工具，偏监控/管理 | 面太宽，权限面不适合对外接 ChatGPT |
| [vega-llc/dk-synology-mcp](https://github.com/vega-llc/dk-synology-mcp) | Python | 5★，2026-03 | — | 87 工具 / 15 模块 | 同上 |
| [lordraw77/synology-mcp](https://github.com/lordraw77/synology-mcp) | Python | 1★，2026-05 | stdio / HTTP streamable | 71 工具 | 同上 |

> 结论：生态**碎片化且普遍小众**（最高 14★）。没有一个项目同时满足
> 「远程 Streamable HTTP + 只读产品目录 + 图片/PDF/Office 渲染 + 中文路径」这四条 —— 我们自建不是纯重复造轮子。

## 2. 别人比我们强的地方（逐条可借鉴）

### 2.1 会话续期：连 **119** 都要重认证 + 重放

mrquj README 明确写：

> "DSM invalidates sessions on idle timeout, **duplicate login** and reboot.
> The client detects codes **106, 107 and 119**, re-authenticates once and replays the call,
> so this never surfaces as a tool failure."

我们本次故障正是 **119 未被真正恢复**（`_is_session_error` 认了 119，但重登是假重登）。
→ 已修（清 `BaseApi.shared_session`），但**「重认证一次 + 重放」应该作为通用契约**覆盖所有工具，
而不是逐个工具补 `retry_on_session`。

### 2.2 唯一会话名，避免「重复登录」互相踢掉

- cmeans 的会话名是 `MCPSynology_{instance_id}_{uuid8}`（每个实例唯一）。
- mrquj 明确把 **duplicate login** 列为会话失效原因之一。

我们的 `synology_api` 库把 `session` **硬编码为 `webui`**；同一 DSM 账号若有多个进程/容器
（我们调试时就同时跑过 canary + 生产）可能互相顶掉。
→ 建议：每个进程用唯一会话名（子类/补丁覆盖 `login()` 的 `session` 参数）。

> **2026-11-03 实测（本 DSM 不适用）**：自定义 `session` 名（`nasmcp_test_123`、`nasmcp-test-123`）
> 登录均返回 **402**；而 `session='webui'` 连续登录两次，两个 SID **都能正常调用** ——
> **重复登录不会踢掉旧会话**。因此这一项没有采用，保留库默认 `webui`（原因已写进代码注释）。

### 2.3 单飞重认证（single-flight）

cmeans 的 `AuthManager` 用 `asyncio.Lock` 包住 `_re_authenticate()`，并回调通知等待者，
避免并发请求同时重登（重登本身可能又踢掉对方会话）。

我们的 `_nas_lock` 只保护「建客户端」，不保护「重认证语义」；并发调用可能各自触发重建。
→ 建议：重认证走单飞 + 失败退避。

### 2.4 DSM Auto Block 防护

cmeans 的 `LoginRefusals` 专门处理 DSM **Auto Block**（默认 10 次失败登录 / 5 分钟封 IP），
并在反复失败时给出可操作提示。

我们这次调试在容器里做了多次强制登出/登录 —— 如果账号密码配错，很容易把 VPS 出口 IP 封掉。
→ 建议：连续登录失败要**熔断 + 停止重试**，并在 `nas_health` 里体现。

### 2.5 `/healthz` 暴露「策略 + 会话 + 工具数」

mrquj 的 `GET /healthz` 报告存活、活跃会话数、暴露的工具数、**当前生效的安全策略**，
从而「不用读容器 env 就能审计运行时姿态」。

我们的 `nas_health` 只是 MCP 工具，不便于 Docker/监控探针调用。
→ 建议：加一个**不需要令牌的本机** `GET /healthz`（只绑 127.0.0.1），返回
`{ok, dsm_available, tools, readonly, allowed_roots}`。

### 2.6 运行时 API 发现 + 缓存

mrquj 通过 `SYNO.API.Info` 在运行时读取端点路径与版本并缓存，因此同一个构建能跨 DSM 6/7 与 API 迁移。

我们硬编码 `THUMB_PATH="entry.cgi"`、`THUMB_VER="3"`。
→ 建议：至少对自构造的 Thumb/Download 路径做一次 `SYNO.API.Info` 查询 + 缓存。

### 2.7 后台任务：轮询到完成 + 进度通知

mrquj 的 copy/move/delete/compress/extract/folder_size/checksum 都「轮询到完成」并回报部分进度。
cmeans 对 delete/copy/move/restore 发送 MCP progress notification，避免客户端空闲超时。

我们的 `nas_search` / `nas_folder_size` / `nas_file_md5` 是轮询，但没有 progress 通知；
长任务可能被客户端判超时。
→ 建议：长任务发 `notifications/progress`。

### 2.8 错误码分族翻译

DSM 在 HTTP 200 的 body 里返回数字错误码，同一个数字在不同 API 族含义不同。mrquj 按族翻译成可操作句子。

我们现在多半把原始 `FileStationError` 抛给模型。→ 建议：至少给 FileStation 建一张码表。

### 2.9 测试体系

cmeans：CI 在**多个 DSM 版本的虚拟 DSM（vDSM）**上跑每个模块的集成测试，另有真实 NAS 的 live-test；
vocweb：用 MSW mock 做单元测试。
我们：只有一个「真连 NAS」的冒烟脚本（32~40 项），无 CI、无 mock。
→ 建议：把核心逻辑（路径护栏、会话重登、错误分类）抽成可单测的函数，用 mock 客户端跑 CI。

### 2.10 配置与凭据

cmeans：`setup` 向导 + `check` 校验 + 多 NAS + keyring + 2FA device token。
我们：`.env` + 环境变量（对 Agent 足够，对人不友好）。→ 低优先级。

## 3. 我们比它们强的地方（别丢）

- **远程 ChatGPT 直连**：`POST /mcp` + Bearer + nginx 反代已在生产验证；cmeans 的 Streamable HTTP **仍是 roadmap**，mrquj 活跃度低。
- **产品图/文档场景**：`nas_read_image`（原生 image 块）、`nas_read_pdf`（渲染 + 抽文字）、
  `nas_read_doc`（docx/xlsx/pptx 抽文字）、`nas_thumbnail` / `nas_folder_thumbnails`（批量廉价预览）、
  `nas_file_md5`、`nas_list_archive`、**File Station 深链（照抄 EN 的 `encode_filestation_link`，双层 URL 编码）**。
- **cmeans 明确缺** thumbnails / MD5 checksums（其 README 「What's not covered」自述）；mrquj 有 MD5、无 PDF/Office 渲染。
- **中文共享目录**（`/FZH共享文件夹`、`/产品信息`）与中文路径编码已实测。
- **安全姿态**：只读、路径护栏、放不开的根目录、`NAS_ALLOWED_ROOTS=*` 时把边界交给 DSM 账号。

## 4. 建议的借鉴清单（按优先级）

| 优先级 | 事项 | 参考 | 状态（2026-11-03） |
|---|---|---|---|
| P0 | 唯一 DSM 会话名（避免重复登录互踢） | cmeans `_build_session_name` / mrquj 会话失效说明 | ❌ **本 DSM 不适用**（自定义名 402；webui 重复登录不互踢） |
| P0 | 单飞重认证 + 登录失败熔断（Auto Block） | cmeans `AuthManager` / `LoginRefusals` | ✅ 已实现：锁串行 + 连续 3 次失败熔断 15 分钟（单飞时间窗因掩盖外部登出已移除） |
| P0 | 本机 `GET /healthz`（策略 + DSL 可用性 + 工具数） | mrquj `/healthz` | ✅ 已实现（0.1.2，无需令牌、不调 DSM） |
| P1 | 长任务 `notifications/progress` | cmeans / mrquj | ❌ 暂不做：当前 stdlib 传输无 SSE 流，ChatGPT 不依赖；留待需要时评估 |
| P1 | `SYNO.API.Info` 运行时发现 + 缓存 | mrquj | ✅ Thumb API 已实现（实测 `entry.cgi v3`） |
| P1 | FileStation 错误码翻译表 | mrquj / cmeans `docs/error-codes.md` | ✅ 已实现（借用 `synology_api` 自带码表） |
| P2 | mock 客户端单测 + CI；vDSM 集成测试评估 | cmeans CI | ✅ 离线单测 23 项 + GitHub Actions；vDSM 仍待评估 |
| P2 | 面向多客户端的 per-client 会话设计（若将来做共享服务） | cmeans ADR 0001 | ⏸ 未做（当前单客户端，不需要） |
| — | MCP `ping` + 工具并发上限 | 标准 / 自身稳定性 | ✅ 已实现（0.1.3） |

## 5. 要不要换掉自建？

**不换。** 理由：

1. 我们的核心需求（产品图/PDF/Office 渲染 + 中文目录 + ChatGPT 远程）没有现成项目完整覆盖；
2. cmeans 没有生产可用的 Streamable HTTP，mrquj 近半年无更新；
3. 换栈会把已上线的部署、鉴权、反代、探活全部重做，收益低于「按清单补齐」。

**什么时候重新评估**：

- 我们开始做**多用户/多客户端**（需要 per-client 会话、RBAC）—— 参考 cmeans ADR 0001；
- 或者 cmeans 正式支持 Streamable HTTP 且能覆盖缩略图/MD5 —— 那时可评估以它为底。

## 6. 关联

- 本次故障与修复：[`nas_mcp/docs/reference/self-healing.md`](../../nas_mcp/docs/reference/self-healing.md)
- 9 月首次调研（部署位置、鉴权路线、候选方案）：[2026-09-21-nas-mcp-chatgpt-feasibility.md](2026-09-21-nas-mcp-chatgpt-feasibility.md)

## 7. 来源

- [mrquj/mcp-server-synology](https://github.com/mrquj/mcp-server-synology) — README（会话续期 106/107/119、`/healthz`、API 发现、后台任务、安全策略）
- [cmeans/mcp-synology](https://github.com/cmeans/mcp-synology) — README、[ADR 0001 per-client sessions](https://github.com/cmeans/mcp-synology/blob/main/docs/adr/0001-per-client-dsm-sessions.md)、[docs/https.md](https://github.com/cmeans/mcp-synology/blob/main/docs/https.md)、`src/mcp_synology/core/auth.py`
- [vocweb/synology-mcp-server](https://github.com/vocweb/synology-mcp-server) — Office 套件 MCP 的安全默认值
- [rafalr100/synology-mcp](https://github.com/rafalr100/synology-mcp) / [vega-llc/dk-synology-mcp](https://github.com/vega-llc/dk-synology-mcp) / [lordraw77/synology-mcp](https://github.com/lordraw77/synology-mcp) — 广面管理型，权限面过大
- GitHub 搜索：`gh search repos "synology mcp"`（2026-11-03 快照）
