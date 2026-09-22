# nas_mcp — Agent 交接

> **只读把群晖 NAS 暴露给 MCP（含 ChatGPT 连接器）**
> 人读：[README.md](README.md) ｜ OKF：[docs/index.md](docs/index.md) ｜ 部署：[docs/reference/deploy.md](docs/reference/deploy.md)

## 这是什么

一个 **Python 薄 MCP 服务**：复用 `NAS_API/synology.py`（已验证的 DSM 客户端）把 NAS 的
几个共享文件夹**只读**暴露给 MCP 客户端。

跑在**上海 EN 测试服务器 VPS**（`8.133.254.66` / `api.vilavi.cn`），由现有 nginx 反代出去。

## 何时用

- 要给 ChatGPT / Claude 等接 NAS 文件 → 本模块
- 要改部署/加工具 → 先读 [docs/reference/deploy.md](docs/reference/deploy.md)
- 要判断「为什么部署在 VPS 而不是 NAS」「为什么不用第三方」→ 读
  [../docs/research/2026-09-21-nas-mcp-chatgpt-feasibility.md](../docs/research/2026-09-21-nas-mcp-chatgpt-feasibility.md)

## 四条铁律（改动前必读）

1. **只读**。`TOOLS` / `TOOL_IMPL` 里**只允许只读工具**。不要加 `create`/`move`/`upload`/`delete` ——
   `NAS_API` 里有 `delete_folder`，**绝不要接出来**。
2. **路径必须过 `safe_path()`**。任何新工具读文件前都要走它；不要自己拼路径。
3. **凭证只在环境变量里**。`NAS_MCP_TOKEN` 与 NAS 账号密码**不写进仓库、不写进镜像**。
   例：`NAS_API/.env` 是 gitignore 的；本模块没有自己的凭证文件。
4. **NAS 侧权限才是真限制**。路径护栏是第二道；第一道是**这个 DSM 账号本身的文件夹权限**。
   换账号 = 改权限范围，代码不用动。

## 当前状态（2026-09-21）

| 项 | 状态 |
|---|---|
| 工具数 | **15 个，全部只读**（清单见 [docs/index.md](docs/index.md)） |
| 本机只读冒烟测试（真连 NAS） | ⚠️ **45 通过 / 2 失败**，两个失败都是**本地环境**问题：venv 缺 `python-docx`/`python-pptx`；`nas_folder_size` 撞上 DSM「目录统计」任务被回收（该 API 已知不稳） |
| MCP 传输（initialize / tools-list / 401） | ✅ 本机通过 |
| 部署到 VPS | ✅ 已上（容器 `nas-mcp` @ `127.0.0.1:8402`，nginx 反代 `https://api.vilavi.cn/nas/mcp`） |
| 接进 ChatGPT | ✅ 已通（Bearer 静态令牌路线；已在 ChatGPT 里实际调用 NAS 工具） |

## 已知坑

- **Windows / git-bash 下本地跑**：`NAS_ROOT_FOLDER` 会被 MSYS 转成 `C:/Program Files/Git/...`。
  这是本地测试环境的问题，**Linux 上不会**。要在 Windows 上干净地测，请从 Python 里设 `os.environ` 再拉起服务。
- **凭证在父仓库**：worktree 里通常没有 `NAS_API/.env`；`tests/test_smoke.py` 会自动往上找父仓库。
- **`NAS_URL` 用哪个域名**：仓库里 `NAS_API/.env` 用的是 `fzh.myds.me:11024`；
  从 VPS 走 `nas.vilavi.cn:11024` 也可（已实测 VPS→NAS 通）。
- **File Station 深链格式不要自己编**：照抄 EN 现成实现 —— 双层 URL 编码
  （`quote(quote(path))`）+ `?launchApp=SYNO.SDS.App.FileStation3.Instance&launchParam=openfile%3D<second>`。
  见 `nas_mcp/server.py::filestation_link()`；测试用真实样例钉住逐字一致。
  **EN 侧的 NAS 代码主要在两处**：`vilavi_pim`（产品物料库：`api/nas.py`、`public/js/item_group_nas.js`）
  与 `work_order_task` 的 `item_groups_nas_path.py::encode_filestation_link()`。
- **会话失效错误码**：DSM 报 **`[105, 106, 107]`** 都算会话过期（EN 口径）—— **不要只判 106/107**。
- **DSM Thumb 的 `path` 要加双引号**（EN 注释：spec 要求）。实测加不加都通，加上更稳（防路径带逗号等特殊字符）。
- **加了 DSM 文件夹权限还不够**：还要把该目录加进 `NAS_ALLOWED_ROOTS` 并重启容器，否则仍被路径护栏拒。
