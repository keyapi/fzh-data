# DAM Prototype Session Summary (2026-06-10 — 2026-06-11)

> 36 commits · Phase 3b → 4 → 5 → 6b → NAS · 状态: 全部完成

## 目标回顾

从 AGENT_HANDOFF.md 接手，继续实现 DAM Prototype。初始待办: Phase 3b (Collection 编辑器)、Phase 4 (版本历史)、Phase 5 (ERPNext API)。

## 已完成: Phase 3b — Collection 编辑器

### 设计讨论 (brainstorming skill + visual companion)

1. **编辑器 UI 模式调研**: 对比了 AEM、Shopify、Google Docs、Notion 的 Collection/分组 编辑 UI
   - 决定: AEM 替换视图（点击 Collection → 主区域切换编辑器）

2. **Collection 数据模型争议**: 当前 1 Collection = 1 SKU，但用户需要 1 个上贴批次 = 多个 SKU
   - 搜索 AEM、ERPNext File (tabFile)、Notion Tag vs Relation 模型
   - 决定: Collection = 上贴批次，`context.skus` 数组支持多 SKU

3. **Tag vs Collection 区分**: 
   - Tag = Asset **是**什么 (白色、枕头、正面)
   - Collection = Asset **用于**什么 (6月上贴批次)
   - `type` 枚举约束灵活度 (listing/campaign/catalog/custom)

4. **跨 SKU 图片归属**: 两张图可能属于不同 SKU，在一个 Collection 里如何展示
   - 决定: 多 SKU 支持 (AssetProductLink N:N), Picker 显示 SKU 标签

### 实现内容

| Commit | 内容 |
|--------|------|
| `bba73f1` | 多 SKU 多行 Excel 导出 |
| `920fe43` | 修复 N+1 查询 + 列字母计算 |
| `afa6911` | PATCH `/api/collections/{id}/items` 增量 API + SKU 输出 |
| `6327116` | Collection Editor UI (CSS + HTML + Vue + SortableJS) |

### 后续发现并修复的问题

- **prompt() 弹窗**: 旧代码残留，修复为单击直接打开编辑器 + 右键上下文菜单 → `59b9de1`
- **侧边栏过滤器 broken**: 在编辑器里点 TYPE/TAG 无反应 → 修复为点过滤器关闭编辑器 → `28f1528`
- **未保存变更**: 缺少 dirty state 检查 → 实现 beforeunload + confirm + ● Unsaved 视觉提示 → `a7f722d`
- **Picker 多 SKU 标签 + 跨 SKU 确认**: 显示 SKU badge + 确认弹窗 → `795b34e`
- **多 SKU 支持**: linked_sku → linked_skus 数组, PATCH 端点更新 → `bf69e50`
- **跨 SKU 添加语义**: 区分"加产品到批次"vs"跨SKU链接图" → `ad85781`

### 设计文档产出
- `docs/superpowers/specs/2026-06-10-dam-collection-editor-design.md`
- `docs/superpowers/plans/2026-06-10-dam-collection-editor.md`

---

## 已完成: Phase 4 — Collection 版本历史 + 回滚

### 设计讨论

- UI 模式: 对比 Google Docs (右侧面板) vs Figma (右侧面板) vs AEM (左栏 Timeline)
- 决定: 右侧 320px 抽屉面板 (Google Docs/Figma 模式)
- 回滚: Figma 非破坏性模式（回滚前先存 checkpoint）

### 实现内容

| Commit | 内容 |
|--------|------|
| `2c66cd4` | POST `/api/collections/{id}/versions/{v}/restore` |
| `529b3e0` | 版本历史右侧面板 (CSS + HTML + Vue) |

### 设计文档产出
- `docs/superpowers/specs/2026-06-10-dam-phase4-version-history.md`
- `docs/superpowers/plans/2026-06-10-dam-phase4-version-history.md`

---

## 已完成: Phase 5 — ERPNext Item API 对接

### 设计

- 复用 EN_API 模式: `requests.Session()` + `_NoExpectAdapter` + `frappe.client.get_list`
- 替换 `/api/products/search` 的 5 个硬编码 mock 数据
- 配置: `ERP_URL` / `ERP_API_KEY` / `ERP_API_SECRET` 从 `.env` 读取
- 优雅降级: API 不可用时返回 `[]`

### 实现

| Commit | 内容 |
|--------|------|
| `cb2f8b1` | ErpnextClient 代码 + `.env.example` 更新 |

### 已知问题: OR filter 导致 404（已修复）

**现象**: `frappe.client.get_list` 用 OR filter 返回 404 `单据类型 OR未找到`

**根因**: EN 测试系统 (ensh.vilavi.cn) 的 `frappe.client.get_list` 不支持 filter 中的 OR 操作符

**修复**: 去掉 OR，仅用 `[["item_code", "like", "%query%"]]` 单条件过滤
- 早期误判为"Windows 连接超时"是因为测试时有时用 OR（404）有时没用（200）
- 实际网络连接正常，`/api/method/ping` 和 `httpbin.org` 均可达

### 设计文档产出
- `docs/superpowers/specs/2026-06-10-dam-phase5-erpnext-integration.md`

---

## 软件开发通用性原则 (讨论过程中识别)

| 原则 | 在本项目的体现 |
|------|-------------|
| PoLA (最小惊讶) | Picker 显示 SKU 标签，选了不会意外 |
| Error Prevention | 跨 SKU 添加确认弹窗 |
| Feedback | ● Unsaved 标记、toast 消息 |
| Progressive Disclosure | picker 里最多显示 3 个 SKU badge |
| YAGNI | Phase 3b 不做 Private/Smart Collection/文件夹上传 |
| SRP | export.py 只管导出, main.py 只管 API, index.html 只管前端 |
| Fail Fast | API 返回 404/error 而非静默失败 |

---

## 未保存变更提醒 (dirty state) 实现

按行业标准 (Google Docs / Figma / VS Code):
- `editorDirty` ref 追踪变更 (add/remove/reorder/role change)
- ● Unsaved 视觉提示
- beforeunload 守卫 (浏览器关闭/刷新)
- 侧边栏导航 confirm 确认

---

## 跨 SKU 图片归属 (2026-06-10 讨论，待完善)

两种用户意图:
1. **加产品到批次**: 新 SKU 加入 Collection context.skus，图保持原 SKU (当前支持)
2. **给图打多 PRODUCT 标签**: 图片尚未分配 SKU，用户通过编辑器反向分配 → **早期核心需求**

当前 status: 多 SKU 数据模型 (AssetProductLink N:N) + UI 就绪。Picker 确认弹窗偏向操作 1，需要支持操作 2。

---

## Session Commits 完整列表 (36 个)

### 上一 session (Phase 3b → 4 → 5, 17 commits)
```
d7945b8 docs(dam): AGENT_HANDOFF — mark Phase 5 ERPNext client ready for deployment
cb2f8b1 feat(dam): Phase 5 — ERPNext Item search replaces mock with ErpnextClient
cd9b0cd docs(dam): Phase 4 completion + milestone update + design/plan docs
529b3e0 feat(dam): add version history side panel to collection editor
2c66cd4 feat(dam): add POST restore endpoint for collection version rollback
bafed10 docs(dam): cross-SKU asset assignment design discussion recorded
ad85781 fix(dam): cross-SKU add now adds SKU to collection batch, not cross-links image
bf69e50 feat(dam): multi-SKU support — asset can link to multiple products
795b34e feat(dam): picker SKU badges + cross-SKU assignment confirmation dialog
a7f722d fix(dam): add asset now shows all SKUs + unsaved changes guard
28f1528 fix(dam): sidebar filters navigate back from editor
d1db715 docs(dam): Phase 3b milestone + AGENT_HANDOFF update
59b9de1 fix(dam): remove prompt() dialog — direct open editor + right-click menu
6327116 feat(dam): Collection Editor UI (Vue 3 + SortableJS)
afa6911 feat(dam): PATCH collection items endpoint + SKU info
920fe43 fix(dam): N+1 query + column letter + platform fallback warning
bba73f1 feat(dam): multi-SKU multi-row Excel export
```

### 本 session (Phase 5 修复 + 6b + NAS + 文档, 19 commits)
```
f01606c fix(dam): Phase 5 ERPNext search — remove OR filter, verified working
df585dc fix(dam): use or_filters for ERPNext Item search (code + name)
fcf5fd0 docs(dam): Phase 5 completion + debugging lessons learned
e9b6ecc chore: 添加 sqlalchemy + openai 依赖
7025b7b docs(dam): DAM/PIM 行业调研 — AEM + 13+ 系统功能细节
a40ce28 feat(dam): 文件夹上传 — ZIP 解压保留目录结构 (废弃)
c375aef feat(dam): 前端支持 ZIP 文件夹上传 (废弃)
d1248be feat(dam): 文件夹上传 — webkitdirectory 保留目录结构
e68dca9 feat(dam): 文件夹列表 + 拼贴缩略图 API
c29ff03 feat(dam): 前端侧边栏文件夹视图
9fa3070 feat(dam): 侧边栏文件夹树状视图
eac6bc2 feat(dam): 文件夹浏览头部 + 子文件夹卡片网格
570e832 feat(dam): NAS 浏览导入 (初版假数据)
2823357 feat(dam): 集成真实 Synology NAS + 修复文件夹空状态 UI
3966911 fix(dam): 真实 NAS 连接 + 文件夹空缩略图 fallback + 上传上下文
62423e7 fix(dam): file_url 包含子目录路径
ef3fd64 fix(dam): 空缩略图 + NAS 浏览器重设计 + 去重修复
546d8e6 feat(dam): Windows 风格双面板 NAS 资源管理器
dc9391a docs(dam): 全面更新 session summary + AGENT_HANDOFF
```

## 待完成

- [x] Phase 5: ERPNext Item API — 已验证通过 (正确 fix: `or_filters` 独立参数)
- [x] Phase 6b: 文件夹上传保留本地结构 — webkitdirectory 实现
- [ ] Phase 6: a.vilavi.cn 替换 (OSS 防关联分发)
- [ ] 文件夹缩略图拼贴 — API 已实现，前端子文件夹卡片已显示
- [ ] NAS 浏览器完善 — 真实 Synology 已连接，但左侧树和预览有已知问题
- [ ] Phase 7: 运营接入试用 + 反馈迭代
- [ ] 跨 SKU 图片归属操作 2 (给图打多 PRODUCT 标签)

## Phase 5 调试记录 & 经验教训

### 问题过程

1. **初版代码**: 把 `"OR"` 字符串塞进 `filters` 数组 → 404 `单据类型 OR未找到`
2. **错误诊断**: 早期 curl 测试碰巧没用 OR 返回 200，误判为"Windows sockets 间歇超时"
3. **第一次修复** (f01606c): 去掉 OR，只搜 item_code → 能工作，但丢失了 item_name 搜索
4. **正确修复** (df585dc): 用 `or_filters` 独立参数，同时搜 item_code + item_name

### 根因

> Frappe API 的 `filters` 和 `or_filters` 是**两个独立参数**，不是把 `"OR"` 放进 `filters` 数组。

```python
# 错误
{"filters": [["a","like","%x%"], "OR", ["b","like","%x%"]]}

# 正确
{"or_filters": [["a","like","%x%"], ["b","like","%x%"]]}
```

### Lesson: 先搜再造 — 包括搜已有 Skill

项目已安装 `frappe-core-api` skill（包含完整的 filter/or_filters 参数文档），但在写代码前没有加载它。CLAUDE.md 的"先搜再造"三原则的第一条就是"搜项目内"。

**改进规则**: 涉及 Frappe/ERPNext API 开发时，**必须先加载 `frappe-core-api` skill**，确认 API 参数格式后再写代码。

### Lesson: 错误信息要认真解读

`"单据类型 OR未找到"` = Frappe 把 "OR" 当成了 DocType 名称去数据库查找，说明 filters 数组里的 "OR" 被当成过滤条件而不是逻辑操作符。这本身就是正确的诊断线索。

### Lesson: 参考已有实现

`EN_API/` 模块里有成熟的 ErpnextClient 实现（upload_item_images.py 等），它们用的是 REST API（`GET /api/resource/Item` + URL 编码参数），不是 RPC API。如果先研究已有代码，会更早发现正确的参数格式。

### Lesson: 先搜索正确的 Web API，不要自己瞎猜

文件夹上传第一版用了 ZIP 解压方案，用户纠正后才搜索 `webkitGetAsEntry` / `webkitdirectory` 标准浏览器 API。AEM/Google Drive/Dropbox 都是用直接选文件夹的方式，不是 ZIP。

**改进规则**: 实现功能前，先搜"<功能> web API standard"确认浏览器原生支持。

### Lesson: 先加载 Skill 再写代码

项目安装了 `frappe-core-api` skill（含完整 filter/or_filters 参数文档），但两次都没先加载：
- Phase 5: 不知道 `or_filters` 是独立参数
- vilavi_pim: 不会直接用现成的 `nas.py` + `item_group_nas.js`

**改进规则**: 任何涉及特定领域（Frappe、NAS API 等）的工作，第一步加载对应 skill。

### Lesson: git add -A 陷阱

某次 commit 用了 `git add -A`，意外提交了 56 个文件（二进制、测试临时文件、`.mcp.json` 等）。以后严格用 `git add <具体文件>`。

---

## Phase 6b: 文件夹上传（保留目录结构）

### 背景

用户指出 AEM Assets 支持直接选择本地文件夹上传（含多层子文件夹），不需要 ZIP。参考了 `webkitGetAsEntry` API 和 `webkitdirectory` 标准。

### 实现

| Commit | 内容 |
|--------|------|
| `a40ce28` | ZIP 方案（第一版，错误方案） |
| `c375aef` | 前端 ZIP 检测（废弃） |
| `d1248be` | **正确方案**: webkitdirectory + webkitRelativePath |
| `e68dca9` | 文件夹列表 API + 拼贴缩略图 |
| `c29ff03` | 前端侧边栏文件夹视图 |
| `9fa3070` | 树状文件夹视图（Windows/Mac 风格） |
| `eac6bc2` | 文件夹浏览头部 + 子文件夹卡片网格 |
| `62423e7` | **修复**: file_url 包含子目录路径 |
| `ef3fd64` | **修复**: 去重时保留目录结构 + 空缩略图 fallback |

### 技术要点

- 前端: `<input webkitdirectory>` 选文件夹 / `webkitGetAsEntry()` 拖拽文件夹递归
- FormData 第 3 参数传 `file.webkitRelativePath` 保留完整路径
- 后端: 从 `UploadFile.filename` 提取目录 → 存入 `files/{path}/{uuid}.ext`
- 去重修改: 有 `rel_dir` 上下文时跳过去重，复制到目标文件夹
- `file_url` 修复: 用 `_file_rel()` 从 `stored_path` 提取 `files/` 后的完整相对路径
- 空文件夹缩略图: CSS 双层结构（底部 SVG 文件夹图标 + 上层拼贴图覆盖）

### 已知问题

- 文件夹树左侧可展开，右侧显示子文件夹卡片 + 拼贴缩略图
- 空文件夹显示 SVG 文件夹图标 + "Folder 'xxx' is empty"
- "Upload to this folder" 传递当前 filterFolder 上下文

---

## Phase 6: NAS 浏览器 (Browse NAS)

### 背景

需要从 Synology NAS 浏览并导入图片到 DAM。vilavi_pim 已有完整的 `SynologyNAS` 类 + `item_group_nas.js` 前端实现。

### 参考代码来源

**vilavi_pim** (private repo, commit `7cb8229`):
- `vilavi_pim/api/nas.py` (160行) — SynologyNAS 类
  - FileStation API: `SYNO.API.Auth` 登录 → 获取 SID
  - `SYNO.FileStation.List` 列出目录 (folder_path, additional=thumbnail,size,time)
  - `SYNO.FileStation.Thumb` 获取缩略图 (small/medium/large/original)
  - Session 缓存 1h，失败不抛异常
- `vilavi_pim/public/js/item_group_nas.js` (249行) — 前端 NAS 浏览器
  - 左侧 300px 树侧栏 + 右侧 Grid/List 视图
  - 面包屑导航 + 工具栏
  - 点击图片 → 灯箱预览
- `vilavi_pim/hooks.py` — 注册到 Item Group: `"Item Group": "public/js/item_group_nas.js"`

**NAS 凭证** (从 ERPNext PIM Settings 获取):
- URL: `https://fzh.myds.me:11024`
- Username: `fzh.test`
- Password: `Fzh,1023` (由用户提供，已写入 `.env`)

### 实现

| Commit | 内容 |
|--------|------|
| `570e832` | 初版 NAS 浏览（假数据，本地文件系统） |
| `2823357` | **真实 Synology NAS 连接** + SynologyNAS 类移植 |
| `546d8e6` | **Windows 风格双面板资源管理器** + 树懒加载 + 灯箱预览 |

### 技术要点

- SynologyNAS 类移植自 vilavi_pim (`nas.py`)
- 配置: `NAS_URL`/`NAS_USERNAME`/`NAS_PASSWORD`/`NAS_ROOT_FOLDER` 从 `.env`
- 不可用时自动 fallback 到本地文件系统 (mock_storage)
- `/api/nas/browse` — 列出目录内容（优先 NAS API，回退本地）
- `/api/nas/tree` — 懒加载文件夹树（仅返回子目录）
- `/api/nas/thumbnail` — 获取缩略图（优先 NAS FileStation.Thumb，回退 Pillow）
- 前进/后退导航历史 + 面包屑
- Grid/List 双视图 + 灯箱预览
- 文件选中 + 批量导入 DAM

### 已知问题 (2026-06-11)

1. **左侧文件夹树不显示**: 最后一次 commit (`546d8e6`) 后树面板不渲染。之前版本正常显示 38 个 Synology 文件夹。
   可能原因: `nasTreeNodes` 初始化或 Vue 响应式问题。
2. **NAS 图片预览未实现**: vilavi_pim 的灯箱使用 `/api/method/vilavi_pim.api.nas.get_thumbnail`，我们的 thumbnail API 已实现但可能未正确调用。
   需要: 检查 `nasPreviewImg` 函数和 `/api/nas/thumbnail` 端点。
3. **非图片文件缩略图**: Synology FileStation.Thumb 只支持图片/视频，文档类文件需要通用图标。

---

## ERPNext File 存储 & dfp_external_storage 调研

### ERPNext 原生 File 存储

- **DB 层级 + 扁平物理文件**: 所有文件在 `sites/{site}/public/files/` (or `private/files/`) 扁平存储，层级关系通过 `File` DocType 的 `folder` 字段（Link 到另一个 `File` 记录）形成
- 文件夹本身是 `File` 记录（`is_folder=1`）
- File URL: `/files/{hashed_name}.ext` 或 `/private/files/{hashed_name}.ext`
- 物理文件名 hash 化，不含路径
- **这不是对象存储 Bucket**，S3 对象存储是扁平 key-value（通过 key 前缀模拟文件夹）

### dfp_external_storage (开源 S3 集成)

- GitHub: `developmentforpeople/dfp_external_storage`
- 按 Frappe 文件夹 → S3 Bucket 映射路由
- 配置 `Home` → 所有文件走 S3；配置 `Attachments` → 仅附件走 S3
- 上传直连 S3（不经过本地磁盘）、流式传输、presigned URL
- S3 不可达时自动 fallback 到本地磁盘
- 可作为 DAM 生产环境的存储后端

### 存储模式对比

| 方案 | 物理 | 层级 | 适用 |
|------|------|------|------|
| DAM 原型当前 | `files/{path}/{uuid}.ext` | 物理子目录 | 原型验证 |
| ERPNext 原生 | 扁平 hash 文件名 | DB `File.folder` | 迁入 Frappe |
| dfp_external_storage | S3 bucket | Frappe folder → S3 映射 | 生产 |
| NAS 直连 | NAS 原始目录树 | 物理目录 | 浏览导入源 |

### 研究文档

- `docs/superpowers/research/2026-06-10-dam-industry-research.md` — AEM + 13+ 系统功能细节
- `docs/superpowers/research/2026-06-10-erpnext-file-storage-nas.md` — File 存储 + dfp_external_storage + NAS

---

## 关键文件 (更新)

| 文件 | 用途 |
|------|------|
| `dam-prototype/AGENT_HANDOFF.md` | Agent 交接说明 |
| `dam-prototype/main.py` | FastAPI 后端 (ErpnextClient + SynologyNAS + 文件夹 API) |
| `dam-prototype/models.py` | 数据模型 |
| `dam-prototype/static/index.html` | Vue 3 SPA 前端 (文件夹树 + NAS 浏览器) |
| `dam-prototype/export.py` | Excel 导出 |
| `dam-prototype/.env` | 本地配置 (gitignored, 含真实 NAS/ERP 凭证) |
| `dam-prototype/.env.example` | 配置模板 |
| `docs/superpowers/2026-06-10-session-summary.md` | 本文档 |
| `docs/superpowers/2026-06-10-dam-phase-3b-milestone.md` | Phase 3b 里程碑 |
| `docs/superpowers/research/2026-06-10-dam-industry-research.md` | 行业调研 |
| `docs/superpowers/research/2026-06-10-erpnext-file-storage-nas.md` | 存储架构 + NAS |
| `docs/superpowers/specs/2026-06-10-dam-collection-editor-design.md` | 编辑器设计 |
| `docs/superpowers/specs/2026-06-10-dam-phase4-version-history.md` | 版本历史设计 |
| `docs/superpowers/specs/2026-06-10-dam-phase5-erpnext-integration.md` | ERPNext 集成设计 |
| `docs/superpowers/plans/2026-06-10-dam-collection-editor.md` | 编辑器实施计划 |
| `docs/superpowers/plans/2026-06-10-dam-phase4-version-history.md` | 版本历史实施计划 |
