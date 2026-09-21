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
- **修复（实测暴露，两个 bug）**: ChatGPT 报 `/产品信息` 为「0 项，文件夹是空的」，但 DSM 侧实测该目录有 **355 项**。
  - **根因① 静默吞异常**：`NAS_API.get_file_list` 在失败时 `return []`，把 **`Session timeout`（DSM 会话过期）伪装成「文件夹是空的」**。
    容器日志一行 `[nas] list error: Session timeout` 是唯一线索。
  - **根因② 不处理会话过期**：DSM 会因空闲回收会话，客户端不重登。
  - **改法**：本模块自带**严格数据层**（`list_strict` / `download_strict`）—— **出错抛 `NasError`，绝不转成空结果**；
    会话失效（`session`/`timeout`/code 106/107）**自动重登并重试一次**。
    不再走 `NAS_API.get_file_list`（其吞异常行为对**所有**上层调用者都是隐患，已在文档标注）。
  - **顺带**：`nas_list_folder` 增报 `total` 与翻页 `note`（避免把「一页」当成「总共就这些」）；新增 `offset`。
  - **顺带修**: `_is_session_error()` 对异常对象做 `json.dumps` 会 `TypeError`，反而盖住真实错误 —— 已修。
  - **测试 19/19**，新增回归护栏：**不存在的目录必须抛错，不得返回空**（正是本次 bug 的核心）。
- **新增（用户反馈驱动）**: **`nas_read_image` —— 返回 MCP 原生 `image` 内容块**，模型可真正看图。
  背景：ChatGPT 能定位到 `3.jpg` 却看不到像素，只能列目录/读文本，**对产品图场景等于没用**。
  实现：按 DSM `SYNO.FileStation.Download` 取字节 → Pillow 校验 → 超长边自动等比缩小 + 重编码 JPEG。
  实测：2000×2000 / 1.14 MB 原图 → **1280×1280 / 287 KiB**。
  - **顺带又修一个上游 bug**：`FileStation.get_file(mode='download')` 是**往磁盘写文件并返回 None** 的，
    所以 `NAS_API.download_file()` **永远返回 None**（还会偷偷在磁盘建文件）。改为直接用 `requests`
    打同一个 API 拿响应体。
- **新增**: **放开模式 `NAS_ALLOWED_ROOTS=*`（现已设为默认）** —— **权限完全交给 DSM 账号**，
  MCP 只拦 `..` 逃逸。用户明确要求「权限按用户（NAS 账号）走」，加目录不该还要改服务。
  显式列表模式保留，供需要收紧时用。
- **新增（按「功能面盘点」一次补齐，不再等用户点菜）**: 对着开源方案的**工具清单**和 DSM 的 19 个 API 族盘了一遍，
  补上三项高价值只读工具（工具数 5 → 8）：
  - **`nas_read_pdf`** —— **把 PDF 渲染成图片**返回（模型可直接看图），并附每页抽出的文字。
    用 PyMuPDF；默认只渲染第 1 页，`pages` 可指定（如 `2-4`），`max_edge` 控分辨率。
    实测：设计稿第 1 页 → 640 KiB PNG + 抽出「产品名称/编号/面料/规格」等文字。
  - **`nas_search`** —— DSM 索引搜索（按名字/扩展名/大小/时间）。实测 `extension=pdf` → **517 个**、`name=靠枕` → **426 个**。
  - **`nas_folder_size`** —— 递归目录大小。实测「设计稿」219 KiB、「图片」**1.7 TiB**。
- **又踩两个上游坑**（都修了）：
  1. `search_start` / `start_dir_size_calc` 在默认 `interactive_output=True` 时**返回一句字符串**而不是 dict →
     需自行解析 taskid。新增 `_task_id()` 兼容两种返回。
  2. `get_search_list` 要求 taskid **带双引号**（库自己的报错里才写明白）。
  3. `get_dir_status` 对已缓存路径会给出**已被回收的任务 id**（`No such task`）→ 加**多次重启重试**，
     最终仍失败时给可读的中文解释而非裸异常。
- **容器依赖**：新增 `pymupdf`（镜像再 +~30MB）。
- **测试 32/32**（新增：search 有结果、folder_size 有值、PDF 渲染出图 + 抽出文字）。
- **新增（B+C，用户点选）**: 三个只读工具，工具数 8 → **11**：
  - **`nas_thumbnail`** —— DSM Thumb API 的廉价缩略图。⚠️ **实测发现 DSM 对 small/medium 返回的是 BMP（未压缩）**
    （250x250 就 183 KiB！），所以本工具拿回来**自己转 JPEG** —— 同样 250x250 转完 **10.8 KiB，省 17 倍**。
  - **`nas_file_md5`** —— MD5 **不下载文件**（`start_md5_calc` + `get_md5_status` + 轮询）。
    实测：`a3270f8f17ab6f06b6ec6a93966af928`。
  - **`nas_read_doc`** —— 抽 **Word(.docx) / Excel(.xlsx) / PPT(.pptx) 的文字**（不渲染版式）。
    实测：docx 抽出完整需求（含天猫参考链接）；xlsx 抽出 A+ 图需表（型号/尺寸/文案）。
    老式二进制 .doc/.xls/.ppt 不支持。
  - 容器依赖新增 `openpyxl` / `python-docx` / `python-pptx`。
- **已知不稳**: `nas_folder_size` 偶尔失败 —— DSM 的 DirSize 任务会被回收（`No such task`）。
  已加多次重启重试 + 可读中文解释；**测试里表现为间歇性**（连跑两次：一次 35/1、一次 36/0）。
- **未决**: 尚无写入能力（刻意）；per-user 权限（现为单账号单 token）待评估。
