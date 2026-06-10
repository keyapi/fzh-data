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

## 8. 当前状态 (2026-06-10)

### 已完成

- [x] 市场调研 + 行业对标 (docs/research.md, docs/industry-research.md)
- [x] 用户访谈 8 轮 (docs/ux-workflow.md 记录)
- [x] DESIGN.md 设计令牌
- [x] DAM 原型 v2 (Vue 3 CDN, 浏览器验证通过)
- [x] 方案设计文档 (docs/solution-design.md)
- [x] Phase 1: SQLite 数据模型 (7 实体) + 上传 API + 缩略图 + 去重 + 前端 CRUD
- [x] Phase 2: AI 自动标签 + 合规检查 (OpenRouter free VL / Aliyun Bailian)
- [x] Phase 3: AssetCollection CRUD API + 版本快照 + Excel 导出模块 + 前端 Collection 面板
- [x] Phase 3b: Collection 编辑器 (AEM 替换视图) + 多 SKU 多行 Excel 导出 + SortableJS 拖拽 + 角色设置 + Asset Picker + 右键菜单
  - 设计文档: `docs/superpowers/specs/2026-06-10-dam-collection-editor-design.md`
  - 实施计划: `docs/superpowers/plans/2026-06-10-dam-collection-editor.md`
  - 讨论记录: `docs/superpowers/2026-06-10-dam-phase-3b-milestone.md`

- [x] Phase 4: Collection 版本历史 + 回滚 (右侧抽屉面板, Google Docs/Figma 非破坏性模式)
  - 设计文档: `docs/superpowers/specs/2026-06-10-dam-phase4-version-history.md`
  - 实施计划: `docs/superpowers/plans/2026-06-10-dam-phase4-version-history.md`
- [x] 多 SKU 支持: AssetProductLink N:N, linked_skus 数组, Picker SKU 标签, 跨 SKU 确认
- [x] 未保存变更守卫: beforeunload + 页内 confirm + ● Unsaved 视觉提示
- [x] 侧边栏过滤器导航: TYPE/TAG/PRODUCT 点选关闭编辑器回到资产浏览

### 待完成

- [x] Phase 5: ERPNext Item API — 已验证通过，产品搜索对接 EN 测试系统正常
  - 设计文档: `docs/superpowers/specs/2026-06-10-dam-phase5-erpnext-integration.md`
  - **已知限制**: `frappe.client.get_list` 不支持 OR filter，仅按 `item_code` like 搜索
- [ ] Phase 6: a.vilavi.cn 替换 (OSS 防关联分发)
- [ ] Phase 6b: 文件夹上传保留本地结构
- [ ] Phase 7: 运营接入试用 + 反馈迭代

### 关键配置

- `.env`: AI_API_KEY (OpenRouter sk-or-v1-...), AI_MODEL (nvidia/nemotron-nano-12b-v2-vl:free)
- AI 自动切换: key 前缀 `sk-or-v1-` → OpenRouter, 否则 → 阿里百炼
- 服务器: `uv run python main.py --port 8098`
- 数据库: dam-prototype/dam.db (SQLite, 自动创建)
- 存储: mock_storage/ (files/ + thumbnails/)

## 9. 关联系统

- **ERPNext**: REST API (Item/BOM/Item Group)。已有 ErpnextClient 类 (EN_API/)
- **a.vilavi.cn**: 老系统，组ID → FTP 上传 → OSS 防关联分发。同事即将离职。需要被 DAM 接管
- **EN_API**: 图片上传前端 (image_upload_app.py)，可复用 FilePond/SortableJS 模式
- **NAS**: 共享文件存储，DAM 资产物理存放位置
