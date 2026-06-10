# DAM Prototype Phase 3b — 讨论记录与里程碑

> 日期: 2026-06-09 ~ 2026-06-10 | 状态: Phase 3b 实现完成，待用户验收

---

## 1. 讨论过程与阶段性共识

### 阶段 1: 基础方向确认 (2026-06-09)

**问题**: Collection 编辑器用什么 UI 外壳？侧边栏 vs 弹窗 vs 替换视图？

**共识**: 需要先研究行业方案再决定。

### 阶段 2: 行业调研 (2026-06-09)

**搜索范围**: AEM、Shopify、Amazon、WordPress、IPV Curator、StreamYard、Cloudinary、FotoWare、Bynder、Orange Logic、TESSA DAM

**关键发现**:

| 系统 | Collection 概念 | UI 模式 |
|------|----------------|---------|
| AEM | 资产的虚拟引用层（不存文件），解耦物理存储 | 替换视图（点击进入子目录） |
| Shopify | 产品图片排序 | Grid 拖拽，位置=顺序 |
| Amazon | Inventory Template (多 SKU，多列 URL) | Excel 批量上传 |
| ERPNext File | tabFile 通用附件表 (attached_to_doctype, attached_to_name) | 通用 FK 对 |

### 阶段 3: 核心设计澄清 (2026-06-09 ~ 2026-06-10)

**用户提出的关键问题**:

1. **Collection 应该关联到什么颗粒度？** — 单品 SKU？Item Group？Campaign？太灵活像 tag？
2. **"每个人是否允许不一样"** — Private Collection 是什么意思？
3. **当前导出只有 1 行（单 SKU）vs 实际需要多 SKU 多行**

**共识**: 参考 AEM 三层模型和 ERPNext File 通用 FK 模式：

- **AEM 三层**: Folder(WHERE) / Tag(WHAT) / Collection(WHICH/WHY)
- **Tag** = 描述资产本身的属性（白色、枕头、正面）
- **Collection** = 描述资产的用途（6月上贴、夏季 Campaign）
- **type 枚举约束灵活度** + context JSON 按 type 有固定 schema
- **ERPNext File 模式**: (doctype, docname) 通用 FK 对，灵活但有结构

**确认的设计方向**:
1. Collection 用 `type` 枚举约束灵活度（listing/campaign/catalog/custom）
2. Context schema 按 type 固定（listing → {skus, channel, marketplace}）
3. 不做到 ERPNext 单据关联（以后可在 context 里加 erpnext_doctype + erpnext_docname）
4. Phase 3b 默认 Public，Private 以后再说
5. 导出多行 Excel（N SKU × M 列）
6. AEM 替换视图编辑器（点击 Collection → 主区域切换）

### 阶段 4: Collection 点击交互修复 (2026-06-10)

**用户发现**: 点击 Collection 弹出 `prompt()` 对话框要求输入 "open" / "export" / "delete"

**分析**: 没有现代 DAM 或 Web 应用使用 `prompt()` 做导航。这是旧代码残留——编辑器实现前的临时占位符。

**修复**: 
- **单击 Collection** → 直接打开编辑器（AEM、Shopify、Google Drive 都是这样）
- **右键 Collection** → 上下文菜单（快速导出/删除，不用进入编辑器）
- 导出按钮在编辑器工具栏里也有

---

## 2. 实现里程碑

### 实现内容 (4 commits, 4 files, ~1246 lines)

| Commit | 文件 | 内容 |
|--------|------|------|
| `bba73f1` | `export.py` | 多 SKU 多行 Excel 导出。按 asset.product_links 分组 SKU，每 SKU 一行。 |
| `920fe43` | `export.py` | 修复 N+1 查询（用 item.asset 代替 query），修复列字母计算，未知平台警告 |
| `afa6911` | `main.py` | PATCH `/api/collections/{id}/items` 增量 API（add/remove/reorder/set_role），`_coll_to_dict` 输出 SKU |
| `6327116` | `index.html` | Collection 编辑器 UI：CSS + HTML 模板 + Vue computed/methods + SortableJS |
| `59b9de1` | `index.html` | UX 修复：去掉 prompt() 弹窗，单击直接打开编辑器，右键上下文菜单 |

### 后端 API 变更

**新增**: `PATCH /api/collections/{id}/items`
```json
{
  "add": [{"asset_id": "uuid", "position": 3, "role": "alternate"}],
  "remove": ["asset_id_1"],
  "reorder": [{"asset_id": "uuid", "position": 0}],
  "set_role": [{"asset_id": "uuid", "role": "main"}]
}
```

**增强**: `GET /api/collections/{id}` — 每个 item 现在返回 `sku` 字段

**增强**: `GET /api/collections/{id}/export` — 多行导出，按 SKU 分组

### 前端功能

- **AEM 替换视图**: 点击 Collection → 主网格切换为编辑器
- **SKU 列表**: 从 items 自动聚合，显示每个 SKU 的图片数
- **图片条**: 按选中 SKU 过滤，拖拽排序，设置角色，删除
- **Asset Picker**: 弹窗从全部资产中选择添加到 Collection
- **右键菜单**: 快速导出/删除
- **显式保存**: Save 按钮创建版本快照

---

## 3. 验证结果

| 测试项 | 状态 | 方法 |
|--------|------|------|
| PATCH API (add/remove/reorder/set_role) | ✅ | curl 调用 + 数据验证 |
| 多 SKU 导出 (.xlsx) | ✅ | 5215 bytes, Content-Type 正确 |
| Vue 无 JS 错误 | ✅ | Console 检查 |
| 资产网格渲染 | ✅ | Snapshot 确认 4 资产显示 |
| Collection 编辑器打开 | ✅ | Snapshot 确认 AEM 替换视图 |
| SKU 列表 + 过滤 | ✅ | KS0001/KS0002 各 2 张图 |
| 角色下拉 + 删除 + 拖拽手柄 | ✅ | 每个图片卡片上都有 |
| 单击直接打开编辑器 | ✅ | 去掉 prompt() 后 Snapshot 确认 |
| 右键菜单 | ✅ | 导出 Amazon/Wayfair/Shopify + 删除 |

---

## 4. 下一步

### Phase 4: Collection 版本历史 + 回滚

- [ ] 版本列表 UI（替换视图内切换版本）
- [ ] 版本对比（diff 当前 vs 历史版本）
- [ ] 回滚按钮 → POST /api/collections/{id}/versions/{v}/restore
- [ ] 后端已有 `AssetCollectionVersion` 表和 version list API，需要前端 UI

### Phase 5: ERPNext Item API 真实对接

- [ ] 替换 `/api/products/search` 的 mock 数据
- [ ] 对接 `ErpnextClient` 类
- [ ] Asset → ERPNext Item 自动 4 属性匹配（style/fabric/size/color）

### Phase 6: 文件夹上传 + NAS 对接

- [ ] 文件夹上传保留本地结构
- [ ] NAS 根目录配置
- [ ] a.vilavi.cn 替换方案（OSS 防关联分发）

### 编辑器增强（Phase 4+）

- [ ] 从编辑器内直接搜索/筛选资产（当前 picker 显示全部资产）
- [ ] 拖拽资产从主网格直接放入编辑器（跨区域拖拽）
- [ ] Collection item 的 SKU 覆盖（方案 B：在 CollectionItem 上设 SKU）
- [ ] Delete collection 的下游确认（当前只是 toast）
- [ ] 编辑器内图片预览放大

---

## 5. 参考文档

- 设计文档: `docs/superpowers/specs/2026-06-10-dam-collection-editor-design.md`
- 实施计划: `docs/superpowers/plans/2026-06-10-dam-collection-editor.md`
- 用户工作流: `dam-prototype/docs/ux-workflow.md`
- 方案设计: `dam-prototype/docs/solution-design.md`
- Agent 交接: `dam-prototype/AGENT_HANDOFF.md`
