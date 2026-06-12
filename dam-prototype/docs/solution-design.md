# DAM 方案设计

> 基于行业最佳实践 + 8 轮用户访谈 + AI 最新能力
> 设计日期: 2026-06-09

---

## 1. 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                    前端 (Vue 3 SPA)                          │
│  DAM Workspace (原型 v2) + AssetCollection 编辑器            │
│  + 上传工作台 + AI 审核面板 + 导出面板                         │
├─────────────────────────────────────────────────────────────┤
│                    FastAPI 后端                              │
│  REST API + 文件处理 + AI 管线 + Excel 导出                  │
├─────────────────────────────────────────────────────────────┤
│                   数据层                                     │
│  SQLite (原型) / MariaDB (生产) + NAS 文件存储 + Redis 缓存   │
├─────────────────────────────────────────────────────────────┤
│                    外部系统                                   │
│  ERPNext REST API (Item/BOM/Item Group) + Claude API (AI)   │
└─────────────────────────────────────────────────────────────┘
```

## 2. 核心数据模型

### 2.1 Asset（资产）— 核心实体

```
Asset:
  id: UUID
  filename: str                    # 原始文件名
  stored_path: str                 # NAS 上的实际路径
  asset_type: enum(image|video|document)
  file_size: int
  width: int, height: int
  content_hash: str                # SHA256, 去重
  thumbnail_path: str              # 缩略图路径
  
  # 元数据
  title: str (nullable)
  alt_text: str (nullable)
  tags: [str]                      # ["pillow", "white", "front-view"]
  ai_tags: [str] (nullable)        # AI 建议的标签 (待确认)
  ai_tags_confirmed: bool
  
  # 业务属性 (从 ERPNext 枚举值)
  style: str (nullable)            # 款式 → Item Group.custom_model_id
  fabric: str (nullable)           # 面料
  size: str (nullable)             # 尺寸
  color: str (nullable)            # 颜色
  
  # 图片角色
  image_role: enum(main|alternate|lifestyle|detail|size_chart|packaging|a_plus|other)
  
  # 合规
  compliance_status: enum(pending|passed|failed|not_applicable)
  compliance_detail: JSON (nullable)  # 各平台检查结果
  
  # 状态与版本
  status: enum(draft|pending_review|approved|rejected|archived)
  version: int                      # 同 content_hash 递增
  parent_asset_id: UUID (nullable)  # 上一版本
  
  # 时间戳
  uploaded_at: datetime
  uploaded_by: str
  updated_at: datetime
```

### 2.2 AssetProductLink（资产-产品关联）— 多对多

```
AssetProductLink:
  asset_id: UUID (FK → Asset)
  product_sku: str                   # ERPNext Item.item_code
  match_level: enum(exact|style|style_fabric|style_fabric_size)
  # exact: 4属性全匹配, style: 仅款式, style_fabric: 款式+面料
  is_primary: bool                   # 是否主图
```

**关键设计**: `match_level` 允许运营查询"这个图片适用于哪些产品变体？"

### 2.3 AssetCollection（虚拟分组 + 上贴快照）— 核心抽象

```
AssetCollection:
  id: UUID
  name: str                          # "KS0001 Amazon US 上贴 v3"
  type: enum(listing|campaign|social_post|catalog|custom)
  
  # 上下文 (按 type 不同)
  context: JSON
    # listing: {product_sku, channel, marketplace}
    # campaign: {campaign_name, season, platforms}
    # custom: {description}
  
  # 有序资产列表
  images: [
    {asset_id, position: 0, role: "main"},
    {asset_id, position: 1, role: "alternate"},
    {asset_id, position: 2, role: "lifestyle"},
    ...
  ]
  
  version: int                       # 每次修改递增
  status: enum(draft|active|archived)
  
  created_at, updated_at, created_by
```

**AssetCollectionVersion** (历史快照):
```
AssetCollectionVersion:
  collection_id: UUID (FK)
  version: int
  images: [...]                      # 该版本的完整 images 快照
  created_at, created_by
```

### 2.4 Tag（标签体系）

```
Tag:
  id: UUID
  name: str                          # "pillow"
  category: enum(color|angle|style|fabric|size|role|scene|season|custom)
  usage_count: int                   # 去重计数
```

### 2.5 PlatformPreset（平台输出定义）

```
PlatformPreset:
  code: str                          # "amazon-main"
  label: str                         # "Amazon 主图"
  platform: enum(amazon|wayfair|shopify|home24)
  role: enum(main|alternate|a_plus)
  
  # 输出规格
  width: int                         # 2000
  height: int (nullable)             # null = 正方形
  format: enum(jpeg|png|webp)
  quality: int                       # 85
  colorspace: enum(sRGB|AdobeRGB)
  max_file_size_mb: int
  
  # 合规规则
  rules: JSON
    # {background: "pure_white", product_fill_pct: 85, no_text: true, no_logo: true}
```

### 2.6 实体关系图

```
Asset ──N:M── AssetProductLink ──N:M── ERPNext Item
  │                                        │
  ├── Tag (N:M)                            │
  ├── PlatformPreset (引用)                 │
  │                                        │
  └── AssetCollectionItem ──N:1── AssetCollection
                                      │
                                      ├── AssetCollectionVersion (1:N)
                                      └── 导出 → Excel
```

---

## 3. REST API 设计

### 3.1 资产管理

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/assets` | GET | 列表 (筛选: type, tags, style, status, search) |
| `/api/assets/{id}` | GET | 详情 + 版本历史 |
| `/api/assets` | POST | 上传 (multipart, 自动生成缩略图) |
| `/api/assets/{id}` | PATCH | 更新元数据 (标签、业务属性、产品关联) |
| `/api/assets/{id}/versions` | GET | 版本列表 |
| `/api/assets/{id}/versions/{v}` | POST | 回滚到指定版本 |
| `/api/assets/batch` | PATCH | 批量标签/属性/状态编辑 |

### 3.2 AI 管线

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/assets/{id}/ai/tag` | POST | 触发 AI 自动标签 (返回建议标签、不自动保存) |
| `/api/assets/{id}/ai/compliance` | POST | 触发 AI 合规检查 (返回各平台通过/失败明细) |
| `/api/assets/batch/ai` | POST | 批量 AI 处理 (支持最多 50 张) |
| `/api/assets/{id}/ai/confirm` | POST | 确认 AI 建议标签 |

### 3.3 AssetCollection

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/collections` | GET | 列表 (筛选: type, product_sku, channel, status) |
| `/api/collections/{id}` | GET | 详情 + 当前 images 顺序 |
| `/api/collections` | POST | 创建 |
| `/api/collections/{id}` | PUT | 更新 (触发版本快照) |
| `/api/collections/{id}/versions` | GET | 版本历史 |
| `/api/collections/{id}/versions/{v}/restore` | POST | 恢复到历史版本 |
| `/api/collections/{id}/export` | GET | 导出 Excel (可选参数: platform, format) |

### 3.4 产品 & 搜索

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/products/search` | GET | 搜索 ERPNext Item (SKU/名称) |
| `/api/products/{sku}/assets` | GET | 某产品的所有可用资产 (含继承) |
| `/api/tags` | GET | 标签列表 (含使用计数) |
| `/api/tags` | POST | 创建/合并标签 |
| `/api/tags/{id}` | DELETE | 删除标签 (零使用检查) |
| `/api/platforms/presets` | GET | 平台输出预设列表 |

---

## 4. 核心交互流程

### 4.1 上传 + AI + 产品关联

```
运营拖入图片
  │
  ▼
Step 1: 自动处理
  - 生成缩略图
  - 提取文件元数据 (尺寸/格式/大小)
  - SHA256 去重检查 (如果已有相同文件 → 提示)
  │
  ▼
Step 2: AI 管线 (异步后台)
  Claude Haiku → {
    color: "white",
    angle: "front-view",
    category: "pillow",
    background: "pure_white",
    has_text: false,
    product_fill_pct: 90
  }
  │
  ▼
Step 3: 运营确认 (前端面板)
  - AI 建议标签以黄色药丸显示
  - 手动选择: 款式/面料 (下拉框, 关联 ERPNext)
  - 手动选择: 图片角色 (主图/场景图/细节图...)
  - 手动关联 SKU (可选)
  - 点击 "确认 AI 标签" → 转为正式标签
  │
  ▼
Step 4: 自动产品关联
  系统根据 款式+面料+尺寸+颜色 → 匹配 ERPNext Item
  AssetProductLink 自动创建
```

### 4.2 创建 AssetCollection (上贴/Campaign)

```
1. 点击 "+ 新建 Collection"
2. 选择 type: "listing" → 输入 product_sku + channel
   或 type: "campaign" → 输入 campaign_name
3. 系统展示该产品所有可用资产:
   - 独有资产 (4属性匹配)
   - 共享资产 (3属性 / 2属性 / 1属性匹配)
   - 按 image_role 分组
4. 运营拖拽资产到 Collection 的 images 列表:
   [0] 白底主图 (asset_01)
   [1] 场景图 (asset_05)  
   [2] 细节图 (asset_03)
   ...
5. 实时预览: 缩略图网格 + 排序
6. 保存 → AssetCollection v1 创建
```

### 4.3 导出 Excel

```
1. 打开 AssetCollection
2. 点击 "导出 Excel"
3. 选择目标平台 (Amazon / Wayfair / Shopify)
4. 系统:
   - 对每张图应用 PlatformPreset (按需生成渲染版)
   - 生成图片 URL
   - 按 position 顺序填入 Excel 对应列:
     main_image_url = images[0].url
     other_image_url1 = images[1].url
     other_image_url2 = images[2].url
     ...
5. 下载 Excel / 保存到 NAS
```

### 4.4 版本管理与回滚

```
1. 打开 AssetCollection v3
2. 拖入新场景图替换 position[2]
3. 保存 → 自动创建 v4 (images 快照)
4. 如果新场景图被拒 → 打开版本历史
5. 点击 v3 → 恢复到 v3 的 images 组合
6. 系统创建 v5 = v3 的 images 组合 (不覆盖 v4)
```

---

## 5. AI 集成管线详细设计

### 5.1 管线架构

```
┌──────────────────────────────────────────────────┐
│                    上传事件                       │
│              (asset.created webhook)              │
├──────────────────────────────────────────────────┤
│              AI Pipeline (后台异步)                │
│                                                   │
│  Stage 1: Claude Haiku 3.5 (快速 + 便宜)          │
│    ├── 颜色识别: {color, color_confidence}        │
│    ├── 角度识别: {angle, angle_confidence}        │
│    ├── 品类识别: {category, category_confidence}  │
│    └── 合规检查: {bg_pure_white, fill_85pct, ...} │
│                                                   │
│  Stage 2: 结果写入 Asset                           │
│    ├── ai_tags ← 低置信度标记为 yellow            │
│    └── compliance_detail ← 各平台检查结果          │
│                                                   │
│  Stage 3: 人工确认 (前端 UI)                      │
│    ├── 确认 AI 标签 → tags += ai_tags             │
│    ├── 手动补充款式/面料                           │
│    └── 点击"通过" → status = approved              │
└──────────────────────────────────────────────────┘
```

### 5.2 AI Prompts 模板

**标签提取 prompt**:
```
Analyze this ecommerce product image for home textiles (pillow/cushion category).
Return JSON:
{
  "color": "white|black|red|blue|gray|beige|navy|green|brown|multi|other",
  "angle": "front|back|side|top|detail|45degree|lifestyle|other",
  "category": "pillow|cushion|sofa_cover|floor_pillow|other",
  "view_type": "product_only|studio|bedroom|living_room|outdoor|packaging",
  "background": "pure_white|off_white|colored|scene|lifestyle",
  "product_fill_pct": 90,      // estimated percentage of frame filled by product
  "has_text_overlay": false,   // any text, logos, watermarks
  "has_human": false,          // human body parts visible (Wayfair check)
  "is_amazon_main_ready": true, // meets Amazon main image requirements
  "alt_text": "White memory foam pillow front view on pure white background"
}
```

**合规检查 prompt (per platform)**:
```
Check if this image meets {platform} requirements:
- Background: must be pure white (#FFFFFF)
- Product must fill 85%+ of frame
- No text, logos, watermarks
- No human body parts (Wayfair only)
- No shadows or reflections (Wayfair only)
- sRGB color profile

Return JSON: {platform, passed: bool, issues: [string]}
```

### 5.3 成本控制

| 策略 | 实现 |
|------|------|
| **去重缓存** | 同 content_hash 的图片不重复 AI 处理 |
| **效果缓存** | 同 prompt + 相似图片 → 复用结果 (Redis, TTL 24h) |
| **分级模型** | Haiku 做 90% 的工作 ($0.001/张), Sonnet 用于疑难案例 |
| **批量处理** | 非高峰时段跑批量 AI (凌晨 2点) |

---

## 6. Excel 导出详细设计

### 6.1 导出流程

```
AssetCollection (images 有序列表)
  │
  ▼
对每个 position:
  asset → 查找 PlatformPreset → 生成/获取 Rendition URL
  │
  ▼
构建 Excel (openpyxl):
  | SKU | main_image_url | other_image_url1 | other_image_url2 | ... | other_image_url8 |
  |-----|---------------|-----------------|-----------------|-----|-----------------|
  | KS0001 | url_0 | url_1 | url_2 | ... | "" |
  │
  ▼
保存到 out/ + 返回下载
```

### 6.2 多平台导出

同一 AssetCollection 可对 Amazon / Wayfair / Shopify 分别导出：
- Amazon: 主图 2000px JPEG sRGB 纯白底
- Wayfair: 主图 2000px JPEG sRGB 纯白底 无真人
- Shopify: 主图 2048px WebP 不限背景

每平台一个独立的 PlatformPreset，自动应用。

---

## 7. 实施计划

### Phase 1: 核心 DAM (当前 → 第2周)
- [x] DESIGN.md 设计令牌
- [x] DAM 原型 v2
- [ ] SQLite 数据模型 (Asset, Tag, Product 表)
- [ ] 上传 API + 缩略图生成
- [ ] 基础 CRUD 前端对接

### Phase 2: AssetCollection + AI (第3-4周)
- [ ] AssetCollection 数据模型 + API
- [ ] AssetCollection 前端编辑器 (拖拽排序)
- [ ] AI 管线 Stage 1 (Haiku 自动标签)
- [ ] AI 管线 Stage 2 (合规检查)
- [ ] 人工确认 AI 结果 UI

### Phase 3: 导出 + 版本 (第5-6周)
- [ ] PlatformPreset 定义
- [ ] Excel 导出 (单平台 + 多平台)
- [ ] AssetCollection 版本历史 + 回滚
- [ ] ERPNext Item API 对接

### Phase 4: 运营接入 (第7-8周)
- [ ] 运营同事试用 + 反馈
- [ ] a.vilavi.cn 替换方案 (图片 URL 分发)
- [ ] 批量导入历史资产

---

## 8. 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| **核心抽象** | AssetCollection (非 ListingImageSet) | 通用，不绑定 Listing。支持 Campaign/Social/Catalog |
| **产品关联** | AssetProductLink + match_level | 支持 4属性精确 → 1属性宽泛的灵活匹配 |
| **版本** | Asset 级 + AssetCollection 级双层 | 资产版本独立于组合版本 |
| **AI 管线** | Write-time 提取 (非 query-time) | 行业共识，成本低 100 倍 |
| **AI 模型** | Claude Haiku (标签+合规) + Manual (款式+面料) | 低成本高精度组合 |
| **导出** | PlatformPreset 驱动 | 平台规则变数据非代码 |
| **标签** | 受控分类法 (category 枚举) + 自由标签 | 两者兼顾 |

---

**创建日期**: 2026-06-09
**状态**: 待用户确认
