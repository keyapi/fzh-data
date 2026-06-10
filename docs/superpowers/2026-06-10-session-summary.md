# DAM Prototype Session Summary (2026-06-10)

> 20 commits · Phase 3b → 4 → 5 · 状态: Phase 3b+4+5 全部完成

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

## Session Commits 完整列表 (18个)

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
f01606c fix(dam): Phase 5 ERPNext search — remove OR filter, verified working
df585dc fix(dam): use or_filters for ERPNext Item search (code + name)
```

## 待完成

- [x] Phase 5: ERPNext Item API — 已验证通过 (详见下方"Phase 5 调试记录")
- [ ] Phase 6: a.vilavi.cn 替换 (OSS 防关联分发)
- [ ] Phase 6b: 文件夹上传保留本地结构
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

## 关键文件

| 文件 | 用途 |
|------|------|
| `dam-prototype/AGENT_HANDOFF.md` | Agent 交接说明 (已更新) |
| `dam-prototype/main.py` | FastAPI 后端 (含 ErpnextClient) |
| `dam-prototype/models.py` | 数据模型 |
| `dam-prototype/static/index.html` | Vue 3 SPA 前端 |
| `dam-prototype/export.py` | Excel 导出 |
| `dam-prototype/.env` | 本地配置 (gitignored) |
| `dam-prototype/.env.example` | 配置模板 |
| `docs/superpowers/2026-06-10-dam-phase-3b-milestone.md` | 全过程里程碑 |
| `docs/superpowers/2026-06-10-session-summary.md` | 本文档 |
