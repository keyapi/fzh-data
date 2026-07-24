# DAM Collection 编辑器设计

> 状态: 待用户审阅 | 日期: 2026-06-10 | 基于: 8轮用户访谈 + AEM/Shopify/ERPNext 行业调研

## 1. 背景与问题

DAM 原型已实现 Phase 1-3 基础功能（资产上传、AI标签、Collection CRUD），但存在两个根本性问题：

1. **Collection 模型不匹配实际工作流**: 当前 1 个 Collection = 1 个 SKU 的图片组。但运营实际使用 Amazon Inventory Template，一次上贴几十个 SKU，每个 SKU 一行图片 URL。Collection 应该是"上贴批次"而非"单产品图片组"。

2. **缺少 Collection 编辑 UI**: 当前只有 `prompt()` 弹窗操作，无法拖拽排序、添加/删除资产、设置角色。

## 2. 行业调研结论

### 2.1 AEM: 三层模型

| 维度 | Folders | Tags | Collections |
|------|---------|------|-------------|
| 回答 | WHERE 资产在哪 | WHAT 资产是什么 | WHICH/WHY 用于什么 |
| 结构 | 层次树 | 命名空间+分类法 | 扁平引用列表 |
| 关系 | 1:1 | N:N | N:N |
| 生命周期 | 永久 | 持久(受控) | 临时/项目级 |
| 谁操作 | 管理员 | 管理员维护,所有人用 | 任何人 |

**核心区别**: Tag 描述资产本身的属性（白色、枕头、正面），Collection 描述资产的用途（6月上贴、夏季Campaign）。Collection 存引用不存文件，删除 Collection ≠ 删除资产。

### 2.2 ERPNext File: 通用附件 FK

`tabFile` 表用 `(attached_to_doctype, attached_to_name)` 作为通用外键对。同一文件可附加到多个不同 DocType 的不同单据。灵活但有结构——引用的必须是真实存在的单据。

### 2.3 Shopify/Amazon: Listing 图片管理

- Grid 拖拽排序，显式保存按钮（非自动保存）
- Position = 导出顺序，第1张=主图
- Amazon: 每 SKU 最多 9 张图片 URL（1 主图 + 8 副图）
- Wayfair: 每 SKU 6-7 张
- 图片角色绑定到位置，而非标签

### 2.4 Notion: Tag vs Relation

- Select/Multi-select = 简单分类（标签是终点）
- Relation = 关联到独立数据库行（标签有自己的故事/属性）
- 选择标准: "标签本身是否有额外信息需要存储？"

## 3. 设计决策

### 3.1 Collection 模型: type 枚举约束灵活度

```python
# 现有模型 (models.py AssetCollection) 基本正确，需微调 context
AssetCollection:
  type: enum(listing|campaign|social_post|catalog|custom)
  context: JSON  # 按 type 不同有不同的 schema

# type="listing" 的 context schema (Phase 3b 实现):
context = {
    "skus": ["KS0001", "KS0002", ...],        # 变为数组
    "channel": "amazon",                        # amazon|wayfair|shopify|home24
    "marketplace": "US",                        # 站点
}

# 未来扩展 (Phase 5+):
# type="campaign" → {campaign_name, season, platforms}
# context 还可以加 erpnext_doctype + erpnext_docname 做 ERPNext 关联
```

**为什么不用更灵活的自由关联**: type 枚举给出"用途骨架"，每种 type 有固定 context schema。既不像 tag 一样随意（因为没有 schema 约束），也不像硬编码一样死板（可扩展新 type）。

### 3.2 Collection vs Tag 的分工

| | Tag | Collection |
|---|---|---|
| 什么意思 | Asset **是**什么 | Asset **用于**什么 |
| 例子 | pillow, white, front-view | 6月 Amazon US 上贴 |
| 能否自由创建 | 是(受 category 约束) | 是(受 type 约束) |
| 谁创建 | 任何人 | 任何人(默认 Public) |
| 删除影响 | 标签消失,资产还在 | Collection 消失,资产和标签都在 |

### 3.3 UI 模式: AEM 替换视图

搜索确认 AEM 打开 Collection 后主视图切换为编辑器（非侧边栏、非弹窗）:
- 点击 Collection → 导航进入 → 主区域变为 Collection 编辑器
- 搜索范围限定在 Collection 内
- 顶部有面包屑可返回资产浏览

对我们的映射:
- 点击 Collection → 主网格区域切换为编辑器
- 左侧 Collection 列表折叠/变窄
- 右侧是编辑器: 上方 Collection 信息 + 下方 SKU 列表每行可展开编辑图片

### 3.4 访问控制: 默认 Public

- Phase 3b 全部 Public，不需要 Private
- Collection 列表可按创建者过滤
- 以后如需按渠道/账号隔离，用 context.channel 过滤即可

## 4. 数据模型变更

### 4.1 Collection 中的 items 结构不变

```python
# AssetCollectionItem 不变:
# collection_id, asset_id, position, role
# position 在 collection 内全局排序

# 但需要在 context 中存储 SKU → images 的映射关系:
# 方案: 每个 Asset 本身已通过 AssetProductLink 关联了 SKU
# Collection 只需列出它包含的 assets，SKU 归属由 asset.product_links 决定
# 导出时聚合: 按 asset.product_links[0].product_sku 分组
```

### 4.2 替代方案: 直接在 CollectionItem 上加 SKU

如果一张图可以关联多个 SKU（通过 AssetProductLink），在 Collection 里它到底算哪个 SKU 的图？这个问题需要在产品层面解决:

**方案 A (推荐)**: Asset.product_links 已经定义了 SKU 关联。Collection 导出时，取每个 asset 的 primary link 的 SKU，按 SKU 分组生成 Excel 行。如果一张图没有 linked SKU，导出时跳过或单独提示。

**方案 B**: CollectionItem 加 `product_sku` 字段，允许在 Collection 内覆盖 SKU 关联。

Phase 3b 先实现方案 A（简单），方案 B 如果用户反馈需要再加。

## 5. 后端 API 变更

### 5.1 修改: PUT /api/collections/{id}

```python
# 当前已支持 images 数组更新, position 排序, 版本快照
# 需要改动: 支持新增/删除单张图片 (当前是整体替换)
# 新增 PATCH /api/collections/{id}/items 做增量操作:

@router.patch("/api/collections/{coll_id}/items")
def update_collection_items(coll_id: str, data: dict):
    """增量编辑 Collection 的 items:
    {
      "add": [{"asset_id": "uuid", "position": 3, "role": "alternate"}],
      "remove": ["asset_id_1", "asset_id_2"],
      "reorder": [{"asset_id": "uuid", "position": 0}, ...]
    }
    """
```

### 5.2 新增: POST /api/collections/{id}/items/batch-add

从资产网格批量添加到 Collection。

### 5.3 修改: GET /api/collections/{id}/export

```python
# 当前导出 1 行 (context.product_sku)
# 改为多行: 遍历所有 item，按 SKU 分组，每个 SKU 一行
# 输出: N 行 × M 列 (M = 平台列数)
```

## 6. 前端 UI 设计

### 6.1 Collection 编辑器布局 (AEM 替换视图)

```
┌─ Toolbar ─────────────────────────────────────────────┐
│ ← Back to Assets | 📋 Softer系列 | listing | 5 SKUs  │
├──────────┬────────────────────────────────────────────┤
│ SKU 列表 │  图片编辑区 (选中 SKU 后显示)              │
│          │                                            │
│ KS0001 ✓ │  [主图] [场景图] [细节图] [A+图] [空槽]   │
│ KS0002   │  ↑ 拖拽排序，设置角色，删除               │
│ KS0015   │  ↓                                        │
│          │  [+ 从资产库添加图片]                      │
│          │                                            │
│ [+ Add   │  [保存] [导出 Excel]                       │
│  SKU]    │                                            │
└──────────┴────────────────────────────────────────────┘
```

### 6.2 交互细节

- **点击 Collection** → 主视图替换为编辑器
- **左侧 SKU 列表** → 显示 SKU + 已分配图片数
- **选中 SKU** → 右侧显示其图片条（横向排列，每张图有缩略图+角色标签）
- **拖拽排序** → SortableJS (已加载)，拖拽手柄⠿
- **添加图片** → 点击 "+ 从资产库添加" → 弹出资产选择抽屉
- **设置角色** → 每张图下方下拉框: main|alternate|lifestyle|detail|size_chart|packaging|a_plus
- **删除** → × 按钮移除引用（不删资产）
- **保存** → 显式按钮，创建版本快照
- **导出 Excel** → 调 GET /api/collections/{id}/export?platform=amazon

### 6.3 导出 Excel 格式

```
| SKU     | main_image_url | other_image_url1 | ... | other_image_url8 |
|---------|----------------|------------------|-----|------------------|
| KS0001  | /files/a.jpg   | /files/b.jpg     | ... |                  |
| KS0002  | /files/c.jpg   | /files/d.jpg     | ... |                  |
| KS0015  | /files/e.jpg   |                  | ... |                  |
```

## 7. Phase 3b 范围

### 包含

- [x] 设计文档 (本文档)
- [ ] 后端: PUT /api/collections/{id} 支持增量 item 操作
- [ ] 后端: GET /api/collections/{id}/export 多 SKU 多行导出
- [ ] 前端: Collection 编辑器（AEM 替换视图）
- [ ] 前端: SKU 列表 + 图片编辑区
- [ ] 前端: 拖拽排序 (SortableJS)
- [ ] 前端: 添加/删除资产到 Collection
- [ ] 前端: 角色设置 per item
- [ ] 前端: 导出 Excel 按钮

### 不包含

- Phase 4: 版本历史查看 + 回滚 UI
- Phase 5: ERPNext Item API 真实对接
- Phase 6: 文件夹上传 (保留本地存储习惯)
- Private Collection
- smart collection (search-based)

## 8. 参考来源

- [Adobe Experience League: Collections](https://experienceleague.adobe.com/en/docs/experience-manager-cloud-service/content/assets/manage/manage-collections)
- [Adobe: Files and Collections](https://experienceleague.adobe.com/en/docs/experience-manager-learn/assets/adobe-asset-link/files-and-collections)
- [Adobe: Taxonomy and Tagging Best Practices](https://experienceleague.adobe.com/en/perspectives/taxonomy-and-tagging-best-practices-for-aem-assets)
- [Frappe File doctype: tabFile schema](https://github.com/frappe/frappe)
- [Shopify Product Image Manager](https://www.fudge.ai/guides/how-to-reorder-product-images-in-shopify/)
- IPV Curator DAM collection reordering
- 用户访谈记录 (docs/ux-workflow.md §6)
