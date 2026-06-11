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

### 已知问题 (待修复)

1. **NAS 左侧树不显示**: 最后 commit `546d8e6` 后 Vue 树面板不渲染。之前版本正常。
2. **NAS 图片预览未完整实现**: vilavi_pim 有灯箱预览（`get_thumbnail` API），我们的 API 已实现但前端可能未正确调用。
3. **文件夹树深度硬编码 4 级**: 模板非递归，深层嵌套不显示。
4. **ERPNext Item 搜索仅 item_code+item_name**: 使用 `or_filters` 正确修复后支持双字段 like 搜索。

### 待完成

- [ ] Phase 6: a.vilavi.cn 替换 (OSS 防关联分发)
- [ ] NAS 浏览器完善: 修复树显示 + 图片预览 + 文件类型图标
- [ ] Phase 7: 运营接入试用 + 反馈迭代

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
├── static/index.html ← Vue 3 SPA 前端 (单文件, ~900 行)
├── .env             ← 真实凭证 (gitignored)
├── .env.example     ← 配置模板
├── dam.db           ← SQLite 数据库
└── mock_storage/    ← 本地文件存储 (files/ + thumbnails/)
```

### 开发流程 (已更新)

按 `CONTRIBUTING.md` 新规: **分支 → PR → 审批 → merge**。当前工作在 `feature/dam-folder-upload` 分支。

PR #4: https://github.com/keyapi/fzh-data/pull/4

## 9. 关联系统

- **ERPNext** (ensh.vilavi.cn): REST API, FAC MCP 工具
- **vilavi_pim** (private repo `keyapi/vilavi_pim`): Browse NAS 参考实现
  - `vilavi_pim/api/nas.py` → SynologyNAS 类 (已移植)
  - `vilavi_pim/public/js/item_group_nas.js` → NASBrowser 前端 (待完整移植)
- **a.vilavi.cn**: 老系统 OSS 分发，需被 DAM 接管
- **EN_API**: 图片上传参考 (ErpnextClient 模式)
- **dfp_external_storage**: 开源 Frappe S3 集成 (生产存储备选)
- **NAS**: 共享文件存储，DAM 资产物理存放位置
