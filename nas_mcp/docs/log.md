---
okf: v0.1
type: Log
title: nas_mcp 变更日志
description: nas_mcp 变更历史
tags: [nas, mcp, log]
---

# 变更日志

## 2026-09-21

- **初始化 OKF bundle**：新建 `nas_mcp/` 模块并实现服务。
  **起因**：FAC（ERPNext）与赛狐 MCP 之后，问「群晖 NAS 能不能接 ChatGPT」；调研结论是
  **部署在 VPS 而非 NAS**（NAS 公网 443 被联通封），且**静态令牌路线已实测可用**。
- **实现**: [server.py](../server.py) — 薄 MCP 服务（stdlib 传输 + 复用 `NAS_API/synology.py`）。
  - **只读四工具**：`nas_health` / `nas_list_folder` / `nas_file_info` / `nas_read_text`。
    **刻意不接出** `NAS_API` 里的 `create_folder` / `create_subfolders` / **`delete_folder`**。
  - **路径护栏 `safe_path()`**：规范化后强制落在 `NAS_ROOT_FOLDER` 内；越界抛 `PathDenied`。
  - **`nas_read_text` 双保险**：只允许文本类扩展名 + 硬上限 256 KiB，超限只给元数据；
    非 UTF-8 一律拒绝（避免把乱码灌进上下文）。
  - **Bearer 鉴权**：与 2026-09-21 在 ChatGPT 实测通过的「访问令牌/持有者」路线一致。
  - **默认只绑 `127.0.0.1:8402`**，由宿主 nginx 反代（与 `sellfox-api-proxy` 同一模式）。
- **测试**: [tests/test_smoke.py](../tests/test_smoke.py) — **真连 NAS 的只读冒烟测试，13/13 通过**。
  含路径越界（4 种）、目录不可被读、非文本扩展名被拒、工具清单无写删。另单独验证了
  MCP 传输（initialize / tools/list / 无令牌 401）。
- **部署**: [docs/reference/deploy.md](reference/deploy.md) — 上海 VPS 上 Docker + nginx 路径块，
  含**备份 / `nginx -t` / `reload` / 回滚**步骤；端口选 8402（避开已占用的 8400 等）。
- **安全约束**：真正权限边界是 **NAS 侧 `<MCP 专用账号>` 这个受限账号的文件夹权限**，路径护栏是第二道；
  凭证只在环境变量 / `.env`（600）里，**不写进仓库与镜像**。
- **部署**: 已上上海 VPS（容器 `nas-mcp` @ `127.0.0.1:8402`）+ nginx 反代 `https://api.vilavi.cn/nas/mcp`。
  端到端验证：办公网与美国 VPS 均通；无令牌 401；真实调用返回 NAS 数据。**已有 5 个容器与关键端口未受影响。**
- **修复（实测暴露）**: **支持多个允许的根目录**（新增 `NAS_ALLOWED_ROOTS`）。
  ChatGPT 列 `/FZH共享文件夹` 正常，但访问 `/产品信息` 被拒 —— 根因是 **DSM 上各共享文件夹是彼此独立的顶层目录**，
  而路径护栏原先写死单根。改后可列多个根；**仍不放松**：`/FZH共享文件夹X`、`/产品信息X/x` 这类前缀混淆仍拒。
  测试 16/16。**教训**：给账号加 DSM 权限之后，**还必须把该目录加进 `NAS_ALLOWED_ROOTS` 并重启容器**，否则仍被护栏拒。
- **未决**: 尚无写入能力（刻意）；per-user 权限（现为单账号单 token）待评估。
