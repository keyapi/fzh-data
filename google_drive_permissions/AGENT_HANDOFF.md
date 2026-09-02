# Agent Handoff — Google Drive 权限管理

> 给 Agent（Claude Code / Codex）快速上手用。**不含任何员工邮箱/账号明文的硬编码**（一律从 Google Sheet 台账读）。

## 1. 凭证（在父仓库，不在 git）

| 凭证 | 怎么找 | 用场 |
|------|--------|------|
| 服务账号私钥 | `GSPREAD_SERVICE_ACCOUNT_FILE`，默认 `secrets/gsheets-service-account.json` | 只读/改显式共享给它的文件 |
| 用户 OAuth | `GSPREAD_USER_OAUTH_FILE`，默认 `secrets/gsheets-user-oauth.json` | 全局审计 |
| Desktop client_secret | 本机 Google Cloud OAuth 客户端 JSON（勿提交、勿写死路径） | 重新授权用户 OAuth |

> worktree 里通常没有这些文件。从仓库根运行：`uv run python google_drive_permissions/scripts/<script>.py`（`uv run` 会把仓库根加进 sys.path）。
> 加载用户 OAuth：`Credentials.from_authorized_user_file(user_oauth_path())` + `refresh(Request())`。

## 2. Google Sheet 台账（权威源）

- **sheet_id**: `1TTVVHQOe5VCmdLZynGFAKXSPUVIvtlB6kOOqgszIqD0`
- 链接: https://docs.google.com/spreadsheets/d/1TTVVHQOe5VCmdLZynGFAKXSPUVIvtlB6kOOqgszIqD0
- **账号主清单** worksheet 列：`状态 | 账号 | 识别/备注 | 处理方式 | 当前文件数`（状态=自己/SA/在职/离职/待确认；处理方式=不取消/保留/**清理**/已清理/已清(遗留)）
- **现状明细** worksheet 列：`类别 | 文件名称 | 文件ID | 属主 | 链接 | 账户 | 角色`（类别=电子表格/Colab）
- 打开/读取用 gspread：`gc.open_by_key(SHEET_ID)`（SA 或用户凭证均可，账号主清单已含 SA editor）

> **数据源约定**：所有账号邮箱（离职名单、现任/前任财务、在职保留等）**一律从本台账读**（见 `scripts/sheet_ledger.py`），脚本内**不硬编码任何邮箱**（PII 治理）。用「识别/备注」列找现任财务负责人等语义账号。

## 3. 脚本（google_drive_permissions/scripts/）

优先从**仓库根**运行：`uv run python google_drive_permissions/scripts/<script>.py`。
运行需 SA 环境变量或用户 OAuth token 文件（见上表）。变更脚本默认 dry-run，加 `--apply` 才写。

| 脚本 | 用途 | 凭证 | 幂等 | CSV 产物 |
|------|------|------|------|---------|
| `audit_gsheet_permissions.py` | 只读盘点 spreadsheet 权限（Drive files.list 一次拉全，快） | SA | 只读 | gsheet_permission_audit.csv |
| `audit_drive_permissions.py` | 用户级全量盘点 spreadsheet+Colab 权限 | 用户OAuth | 只读 | drive_permission_ledger.csv + colab_permission_ledger.csv |
| `cleanup_gsheet_permissions.py` | 补现任财务到含前任财务的表 + 移除离职账号（**仅 SA 可见文件**） | SA | dry-run 默认；Phase1 失败则中止删除 | — |
| `add_sa_to_business_colab.py` | 给业务 Colab 补 SA writer（幂等） | 用户OAuth | 是 | — |
| `check_oauth_token.py` | 验证用户 OAuth token 可 refresh + Drive about | 用户OAuth | 只读 | — |
| `check_colab_capabilities.py` | 用 **SA token** 检查 Colab canShare/canEdit | SA | 只读 | — |
| `share_tongtu_order_editor.py` | 给 12 张通途订单表加编辑权限（无参则从台账取现任财务） | SA | dry-run 默认 | — |
| `list_colab_and_public.py` | 收集全部 Colab 状态 + 公开链接表 | 用户OAuth | 只读 | — |
| `auth_gsheets_user.py` | 一次性授权：浏览器登录后把 refresh token 存到 secrets | 用户 | — | — |
| `sheet_ledger.py` | **共享模块**：从台账读账号列表（removed/kept/all） | SA | 只读 | — |
| `build_accounts_master.py` | **对账式刷新「账号主清单」**：Drive 现状 vs 台账，新增标待确认、刷新文件数，不覆盖人工填的列 | 用户OAuth | dry-run 默认 | — |
| `create_permissions_ledger_sheet.py` | **扫描 Drive 现状刷新「现状明细」**：扫描失败/空结果拒绝 --apply | 用户OAuth | dry-run 默认 | — |

> **数据以台账为准**：账号主清单的「离职/在职 + 姓名备注」由人工/Agent 直接在 Google Sheet 台账填（Drive 推导不出姓名）；`build_accounts_master.py` 只做对账（新增=待确认、刷新文件数），`create_permissions_ledger_sheet.py` 只刷新现状明细，都不覆盖人工填的状态/备注列。

## 4. API 机制

- **加/删共享**（与 mimeType 无关）：`POST /drive/v3/files/{id}/permissions`、`DELETE /drive/v3/files/{id}/permissions/{permId}`。
  加用 `sendNotificationEmail=false` 可静默；权限 body `{role, type:"user", emailAddress}`。
- **批量审计快径**：`files.list` 带 `permissions(id,emailAddress,role,type)` 字段，一次拿全（避免逐表 list_permissions 的几百次调用）。
- **改内容**才分：spreadsheet→Sheets API(gspread)；.ipynb→Drive files.get/update。
- **限流**：429/500/503 需退避重试（本项目脚本 `api()` 已实现 4 次指数退避）。

## 5. 边界与坑

- **查 SA 能否操作**：必须用 **SA 凭证** 调 `files.get` 看 `capabilities.canShare`；用属主凭证查永远 true，会误判。
- **「仅属主可改共享」开关** = `writersCanShare`（`files.update` 顶层布尔）。`capabilities.canShare` 只是调用者能否共享，别混淆。
- **Testing 状态 refresh token 7 天过期**（external app 请求 drive scope）；服务账号私钥永不过期；access token 约 1 小时。改消息别一概而论。
- **invalid_scope**：refresh token 只授权过 `drive` 时，再请求 `drive+spreadsheets` 会报错。gspread 用 `drive` scope 即可，或重新授权两个 scope。
- **PII**：所有含员工邮箱的明细都只放 Google Sheet 台账，**绝不入仓**。脚本 CSV 产物已被 .gitignore 排除。
- **凭证不入仓**：`secrets/*.json`、client_secret、refresh token 均由 .gitignore 保护。

## 6. 离职账号名单 & 在职保留

不在文档里硬编码（PII）。以 **Google Sheet 台账「账号主清单」** 为准：待删填 `清理`；做完改 `已清理` / `已清(遗留)`。`保留` / `不取消` 即使状态=离职也不删。执行前先读该 worksheet。
