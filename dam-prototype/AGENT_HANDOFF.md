# DAM Prototype — Agent 交接说明

> **给 AI Agent 读的技术文档。人类请读 [README.md](README.md)**

---

## 1. 项目背景

FZH 跨境电商，自有工厂，销售 Amazon/Wayfair/Shopify/Home24。ERPNext 管 Item/BOM，
赛狐/通途为 OMS。NAS 共享文件存储。

**核心痛点**（8 轮用户访谈确认）:
1. 信息孤岛: 图片散落 NAS/钉钉/老系统 a.vilavi.cn
2. 肉眼挑图: 无预览、无对比、无合规检查
3. URL 盲确认: 加密文件名 → 逐一打开浏览器确认
4. 排序靠剪切粘贴: Excel 里剪切粘贴 URL 单元格
5. 无版本管理: 换图后旧记录丢失，同事不存档
6. Excel 版本冲突: 多人编辑互相覆盖
7. 关键人风险: a.vilavi.cn 组ID+FTP 管理同事即将离职
8. 跨平台重复劳动: 每平台独立走一轮流程

详细访谈记录: [docs/ux-workflow.md](docs/ux-workflow.md)
行业调研: [docs/industry-research.md](docs/industry-research.md)
完整方案: [docs/solution-design.md](docs/solution-design.md)

## 2. 系统架构

```
dam-prototype/
├── main.py              # FastAPI 后端 (SQLite + NAS + AI管线)
├── models.py            # SQLAlchemy 数据模型
├── static/index.html    # Vue 3 SPA DAM 工作台
├── DESIGN.md            # 设计令牌 (CSS变量 + 组件规范)
├── .env                 # 环境变量 (gitignored)
├── AGENT_HANDOFF.md     ← 本文件
├── README.md            # 人读
└── docs/
    ├── process.md       # 开发方法论 (四阶段 + ADR)
    ├── research.md      # 市场调研摘要
    ├── ux-workflow.md   # 用户工作流 + 8轮访谈
    ├── industry-research.md  # 行业最佳实践 + AI技术路径
    └── solution-design.md    # 完整方案设计
```

## 3. 核心数据模型

### 实体关系

```
Asset ──N:M── AssetProductLink ──N:M── ERPNext Item
  │
  ├── Tag (N:M)
  │
  └── AssetCollectionItem ──N:1── AssetCollection
        (position, role)          ├── AssetCollectionVersion (1:N)
                                  └── 导出 → Excel
```

### 关键概念

- **Asset**: 图片文件 (NAS 存储, UUID 命名)。带元数据、AI标签、合规检查结果、版本链
- **AssetProductLink**: 资产-产品多对多关联。match_level 区分 4属性精确/3属/2属/1属宽泛匹配
- **AssetCollection** (核心抽象): 一组有序资产的命名快照 + 版本历史。type: listing|campaign|social_post|catalog|custom
- **AssetCollectionVersion**: 每次修改 Collection 自动创建快照，可回滚
- **PlatformPreset**: 平台输出规格定义 (尺寸/格式/质量/合规规则)
- **Tag**: 受控分类法，category 枚举: color|angle|style|fabric|size|role|scene|season|custom

详细数据模型: [docs/solution-design.md#2](docs/solution-design.md#2-核心数据模型)

## 4. 技术决策

| 决策 | 选择 | ADR 编号 |
|------|------|---------|
| 原型方式 | FastAPI + Vue 3 CDN + SQLite | ADR-002 |
| 前端框架 | Vue 3 (非 React/Next.js) | ADR-003 |
| 设计令牌 | DESIGN.md (CSS变量) | ADR-004 |
| 文件存储 | NAS (UUID命名) | ADR-005 |
| 核心抽象 | AssetCollection (非 ListingImageSet) | §6.1 |
| AI 管线 | Write-time 提取, Claude Haiku | §6.2 |

## 5. 启动

```bash
cd dam-prototype
uv run python main.py --port 8098
```

## 6. API 端点

详见 [docs/solution-design.md#3](docs/solution-design.md#3-rest-api-设计)

| 组 | 关键端点 |
|----|---------|
| 资产管理 | GET/POST `/api/assets`, PATCH `/api/assets/{id}`, POST `/api/assets/batch` |
| AI 管线 | POST `/api/assets/{id}/ai/tag`, POST `/api/assets/{id}/ai/compliance` |
| AssetCollection | CRUD `/api/collections`, GET `/api/collections/{id}/export` |
| 产品搜索 | GET `/api/products/search`, GET `/api/products/{sku}/assets` |

## 7. AI 管线

**当前方案** (2026-06-09 实现):

| 项目 | 详情 |
|------|------|
| 模型 | `nvidia/nemotron-nano-12b-v2-vl` — OpenRouter **免费** |
| 成本 | $0/张 |
| 备用 | `qwen-vl-plus` — 阿里百炼 (~0.0017 元/张) |
| 模块 | `ai_pipeline.py` — 自动检测 API key 前缀切换 Provider |
| 接入 | 上传后后台线程调用, 不阻塞响应 |

**AI 识别能力**:
- 颜色 + 角度 + 品类 + 背景类型 + 文字/Logo/人物检测 + 产品占比
- Amazon/Wayfair 合规检查 (白底/纯色/占比/水印)
- Alt text 自动生成
- 标签返回为 AI 建议 (黄色药丸), 用户确认后合并

**不识别** (Phase 2 评估):
- 款式 (三角靠枕 vs 方形) — 需 Few-shot
- 面料 (PP棉 vs 海绵) — 需训练
- 尺寸 — 无法从图片推理

**已安装的 Skill**: frontend-design, brainstorming, design-md, design-review, ecommerce-image-workflow, superpowers 14件套

## 8. 当前状态 (2026-06-11)

### 已完成

- [x] Phase 1-4: 数据模型 + AI 标签 + Collection CRUD + 编辑器 + 版本历史
- [x] Phase 5: ERPNext Item API — `or_filters` 正确修复，item_code + item_name 双字段搜索
  - 设计: `docs/superpowers/specs/2026-06-10-dam-phase5-erpnext-integration.md`
  - **教训**: `filters` 和 `or_filters` 是 Frappe API 两个独立参数
- [x] Phase 6b: 文件夹上传保留目录结构 (webkitdirectory)
  - 前端: `<input webkitdirectory>` + `webkitGetAsEntry()` 递归拖拽
  - 后端: 从 UploadFile.filename 提取路径 → `files/{path}/{uuid}.ext`
  - `file_url` 修复: `_file_rel()` 提取 `files/` 后的完整路径
  - 去重修复: 有 folder 上下文时跳过去重，复制到目标文件夹
- [x] 侧边栏文件夹树视图 + 子文件夹卡片 + 拼贴缩略图
  - `/api/folders` — 目录树 + 资产计数
  - `/api/folders/{path}/thumbnail` — 前 4 张 2×2 拼贴
  - 空文件夹: CSS 双层 SVG 文件夹图标
- [x] NAS 浏览器 (Synology FileStation API)
  - SynologyNAS 类移植自 vilavi_pim `nas.py`
  - NAS 凭证: `fzh.myds.me:11024` / `fzh.test` (从 `.env` 读取，不硬编码)
  - `/api/nas/browse`, `/api/nas/tree`, `/api/nas/thumbnail`, `/api/nas/import`
  - 真实 NAS 已验证连接成功（38 个根目录文件夹）
  - Windows 风格双面板: 左树 + 右 Grid/List + 面包屑 + 前进后退 + 灯箱预览
- [x] 行业调研文档
  - `docs/superpowers/research/2026-06-10-dam-industry-research.md` (AEM + 13+ 系统)
  - `docs/superpowers/research/2026-06-10-erpnext-file-storage-nas.md` (存储架构)
  - `docs/superpowers/research/2026-06-11-dam-multi-source-architecture.md` (多来源 DAM 架构)
  - `docs/superpowers/reference/2026-06-11-nas-synology-api-reference.md` (NAS API 参考)
  - `docs/superpowers/plans/2026-06-11-dam-phase7-multi-source-architecture.md` (Phase 7 计划)
  - `docs/superpowers/specs/2026-06-11-dam-dual-panel-design.md` (双面板设计)

### 双面板 (Dual Pane) — 2026-06-11 新增

- **功能**: 工具栏 "Dual Pane" 按钮 → 右侧面板显示 Collection 内容（SKU 分组 + 缩略图 + role badge + drop zone）
- **布局库**: split.js CDN (已引入，未启用 resize)
- **当前问题** (3 个):
  1. **布局错误**: 点 Dual Pane 后右面板未显示在右侧，左侧 Assets 被替代
  2. **拖拽不工作**: Assets 网格 ⠿ 手柄在双面板模式下拽不动
  3. **SKU 交互不对**: 用户要类似文件夹树的 flat list，不是 toggle filter
- **设计文档**: `docs/superpowers/specs/2026-06-11-dam-dual-panel-design.md`
- **用户期望**: COLLECTIONS→PRODUCT SKU 像文件夹→子文件夹一样展开，每个 SKU 下列出资产

### 已知问题

| # | 问题 | 状态 | 备注 |
|---|------|------|------|
| 1 | 双面板布局 | ❌ 待修复 | 右侧面板位置错误 |
| 2 | 双面板拖拽 | ❌ 待修复 | ⠿ 手柄无法拖拽 |
| 3 | SKU 展示模式 | ❌ 待修复 | 需改为 flat list 树形 |
| 4 | ~~NAS 树~~ | ✅ 已修复 | `13ffc00` |
| 5 | ~~NAS 缩略图~~ | ✅ 已修复 | `d1c81db` |
| 6 | ~~setup return~~ | ✅ 已修复 | `d1c81db` |

### 待完成

- [ ] 修复双面板 3 个已知问题 (布局/拖拽/SKU 树)
- [ ] Phase 6: a.vilavi.cn 替换 (OSS 防关联分发)
- [ ] Phase 8: Smart Collection (远期)

### 开发铁律: 先搜再造 (Search Before Building)

> **违反此规则是本项目最大的时间浪费来源。每次违反平均浪费 2 小时调试时间。**

#### 规则 1: 第三方 API 开发前必须搜索 4 个来源

| 顺序 | 来源 | 示例 (NAS API) |
|------|------|---------------|
| 1 | **项目内已有实现** | vilavi_pim `nas.py:132` 有完整调用方式 |
| 2 | **官方文档** | Synology File Station API Guide (PDF) |
| 3 | **开源项目** | N4S4/synology-api (332 stars, PyPI) |
| 4 | **社区/StackOverflow** | Python Synology download examples |

**违例案例 (2026-06-11)**:
- 未读 vilavi_pim 代码，2 小时自猜 Synology Download API 参数 → 结果参数格式错误
- 未搜官方 API Guide，不知道 `path` 需要 JSON 数组格式 `["/path"]`
- 未搜 `N4S4/synology-api`，不知道已经有 `get_file()` 封装

#### 规则 2: 前端方案选型前必须搜索对比

| 顺序 | 来源 | 示例 (拖拽方案) |
|------|------|----------------|
| 1 | **业界主流库对比** | SortableJS vs vue-draggable-next vs HTML5 原生 |
| 2 | **CDN 可用性** | jsDelivr/unpkg 上是否有 Vue 3 CDN 版本 |
| 3 | **项目兼容性** | 是否与现有 SortableJS 用法冲突、是否支持 Frappe 移植 |

**违例案例 (2026-06-11)**:
- 未搜索对比，直接用 HTML5 原生 API 实现拖拽 → 与现有 SortableJS 冲突，缺少动画/移动端支持
- 正确方案: `vue-draggable-next` (SortableJS 官方 Vue 3 封装) + `group` 配置

#### 规则 3: 穷尽搜索确认信号

以下信号出现时必须立即停止编码，重新搜索:
- [ ] 网上搜不到 → **扩大搜索词** (英文/中文/技术术语变体)
- [ ] 试了几种方案都不行 → **搜索"已有实现"** (开源项目/GitHub Issues)
- [ ] API 返回错误 → **搜索官方文档 + 开源项目源码**
- [ ] 感觉"应该这样写" → **先搜"<topic> best practice"**

### 经验教训 (Lessons Learned)

**1. Frappe `or_filters` 是独立参数**
> `filters` 和 `or_filters` 是两个独立参数，不能把 `"OR"` 字符串塞进 `filters` 数组。
> ```python
> # 错误: {"filters": [["a","like","%x%"], "OR", ["b","like","%x%"]]}
> # 正确: {"or_filters": [["a","like","%x%"], ["b","like","%x%"]]}
> ```
> 涉及 Frappe API 开发时，**必须先加载 `frappe-core-api` skill**。

**2. 先搜再造 — 搜已有 Skill**
> 项目安装了 `frappe-core-api` skill（含完整 filter/or_filters 参数文档），但 Phase 5 写代码前没有加载它。CLAUDE.md 的"先搜再造"三原则第一条就是"搜项目内"。

**3. 错误信息要认真解读**
> `"单据类型 OR未找到"` = Frappe 把 "OR" 当成了 DocType 名称去数据库查找 → 本身就是正确的诊断线索。

**4. 参考已有实现**
> `EN_API/` 模块有成熟的 ErpnextClient 实现（REST API + URL 参数），如果先研究已有代码会更早发现正确格式。

**5. 先搜索 Web API 标准，不要自己瞎猜**
> 文件夹上传第一版用 ZIP 解压方案（错误），用户纠正后才搜到 `webkitGetAsEntry` / `webkitdirectory` 标准浏览器 API。AEM/Google Drive/Dropbox 都用直接选文件夹方式。

**6. git add -A 陷阱**
> 某次 commit 用了 `git add -A`，意外提交了 56 个文件。以后严格用 `git add <具体文件>`。

**7. `file_url` 需包含子目录路径**
> 上传到 `files/subdir/uuid.jpg` 时，`_file_rel()` 必须从 `stored_path` 提取 `files/` 后的完整相对路径，否则缩略图和预览 404。

**8. Vue 3 CDN setup() return 陷阱**
> `setup()` 中 `const` 声明的变量如果未在 return 中暴露，模板里静默为 `undefined`，**不会报错**。
> `v-for="n in undefined"` → 空输出，`undefined.length` → TypeError。
> 当出现 `.length of undefined` 渲染错误时，优先检查 setup() return 是否遗漏变量。
> 如 `flattenedFolderTree`, `isNasImage`, `nasPreviewFiles` 等 6 个变量漏 return 导致所有渲染失败。

**9. Synology FileStation.Thumb path 必须用双引号包裹**
> ```python
> # 错误: "path": path
> # 正确: "path": f'"{path}"'  # Synology API 要求，FileStation.List 不需要
> ```
> 参考 vilavi_pim `nas.py:132` 注释 "Path must be wrapped in quotes per Synology API spec"。
> **教训**: 任何第三方 API 开发前，先搜项目中是否有现有实现可参考。

**10. Synology `has_thumbnail` 字段不可靠**
> `SYNO.FileStation.List` 返回的 `has_thumbnail` 可能为 false 即使文件支持缩略图。
> 应用层应使用文件扩展名判断是否尝试加载缩略图，用 `@error` fallback 处理失败。
> vilavi_pim `item_group_nas.js:331-332` 有完整的 Synology 支持格式列表（含 RAW: arw/cr2/nef/dng 等）。

### 关键配置

- `.env` (gitignored): AI_API_KEY, ERP_URL/KEY/SECRET, NAS_URL/USERNAME/PASSWORD, DAM_NAS_ROOT
- `.env.example`: 配置模板
- 服务器: `uv run python main.py --port 8098`
- 数据库: dam-prototype/dam.db (SQLite)
- 存储: mock_storage/ (files/ + thumbnails/)
- NAS: Synology `fzh.myds.me:11024` (FileStation API)

### 代码架构

```
dam-prototype/
├── main.py          ← FastAPI (ErpnextClient + SynologyNAS + 文件夹/NAS API)
├── models.py        ← SQLAlchemy 数据模型
├── export.py        ← Excel 导出
├── ai_pipeline.py   ← AI 自动标签
├── static/index.html ← Vue 3 SPA 前端 (单文件, ~1000 行 (双面板重构后 ~93K))
├── .env             ← 真实凭证 (gitignored)
├── .env.example     ← 配置模板
├── dam.db           ← SQLite 数据库
└── mock_storage/    ← 本地文件存储 (files/ + thumbnails/)
```

### 开发流程 (已更新)

按 `CONTRIBUTING.md` 新规: **分支 → PR → 审批 → merge**。当前工作在 `feature/dam-folder-upload` 分支。

PR #4: https://github.com/keyapi/fzh-data/pull/4


## 8.5 双面板 Collection 树浏览器 (2026-06-11)

### 架构

- **左面板**: Assets 网格 + 文件名搜索栏 (leftSearch + leftFiltered)
- **右面板**: Collection 树状浏览器
  - 顶层: 所有 Collection 列表 (可搜索 rpSearch)
  - 展开 Collection → 显示 SKU 子节点 (类似文件夹)
  - 点击 SKU → 展开该 SKU 下的图片缩略图网格
  - 每个 SKU 下方有 drop zone → 从左侧拖入 Assets
  - 图片 hover 显示 x 按钮 → 从 Collection 移除引用 (不删除资产)
- **sidebar**: 保留 Type/Tags/Product/Folders/NAS/Collections 快速导航
- **拖拽**: SortableJS group=dam + forceFallback:true + fallbackOnBody:true
  - Assets (pull:clone, put:false) → Collection drop zones (pull:false, put:true)
  - 不支持反向拖拽 (Collection → Assets), 用 x 按钮移除引用

### 关键状态
- rpExpandedCollections (reactive Set) — 哪些 Collection 展开了
- rpActiveSku (reactive {}) — 每个 Collection 当前选中哪个 SKU
- rpCollectionItems (reactive {}) — 懒加载的 Collection items 缓存

### Git (最新 3 commits)
2c830d5 feat(dam): 左面板文件名搜索 + leftFiltered
5cfeb42 feat(dam): 右面板重构为树状 Collection→SKU 浏览器
b956ca4 fix(dam): CSS 布局修复 + SortableJS forceFallback
## 9. 关联系统

- **ERPNext** (ensh.vilavi.cn): REST API, FAC MCP 工具
- **vilavi_pim** (private repo `keyapi/vilavi_pim`): Browse NAS 参考实现
  - `vilavi_pim/api/nas.py` → SynologyNAS 类 (已移植)
  - `vilavi_pim/public/js/item_group_nas.js` → NASBrowser 前端 (待完整移植)
- **a.vilavi.cn**: 老系统 OSS 分发，需被 DAM 接管
- **EN_API**: 图片上传参考 (ErpnextClient 模式)
- **dfp_external_storage**: 开源 Frappe S3 集成 (生产存储备选)
- **NAS**: 共享文件存储，DAM 资产物理存放位置
