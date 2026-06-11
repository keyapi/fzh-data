# DAM 双面板通用资源管理器设计方案 (v2)

> 日期: 2026-06-11 | 状态: 搜索完成 v2，等待讨论确认

## 1. 用户需求 (v2 修正)

**核心概念**: 一个屏幕塞进 2 个资源管理器窗口，分别独立导航，互不依赖，互相可拖拽。

- ❌ ~~右侧是 Collection 面板~~
- ✅ **右侧是第二个通用资源管理器**，和左侧功能对等
- ✅ 每个面板独立导航（各自切换来源/文件夹/筛选/Collection）
- ✅ 支持多种视图 + 可调整缩略图大小
- ✅ 支持一切正常操作（编辑/排序/删除/改角色）
- ✅ 双向拖拽：Assets ↔ Collection，NAS → Assets，NAS → Collection
- ✅ 默认显示上次打开的 Collection（简单实现 first）

## 2. 业界参考

| 产品 | 关键模式 | 借鉴 |
|------|---------|------|
| **Windows 资源管理器** | 开 2 个窗口，各自独立 | 核心概念 |
| **Total Commander** | 对称双面板，Tab 切换，F5/F6 复制移动 | 对称设计 |
| **Webix File Manager** | 双面板 + 多视图 + 可缩放预览 | 视图模式 |
| **DevExtreme FileManager** | 详情/缩略图切换 + 自定义缩略图 | 视图切换 |
| **splitpanes (Vue 3)** | 可拖拽分隔条，min/max，双击最大化 | 分隔面板库 |
| **Vuetify createContext** | 多实例独立 context 隔离 | 架构模式 |

## 3. 架构设计

### 3.1 面板上下文 (Pane Context)

每个面板是独立实例，有自己的上下文状态：

```
Pane A (左):                           Pane B (右):
  source: 'assets'                       source: 'collection'
  filterFolder: 'test_upload'            collectionId: 'd1b7f3fa...'
  filterTag: null                        skuFilter: 'KS0001'
  filterType: 'all'                      viewMode: 'grid'
  viewMode: 'grid'                       thumbSize: 80
  thumbSize: 120                         searchQuery: ''
  searchQuery: ''
```

**source 可切换**:
- `'assets'` — DAM 资产网格（含筛选/搜索）
- `'collection'` — Collection 内容（含 SKU 分组/角色）
- `'nas'` — NAS 浏览器（含树 + 网格）
- `'folder'` — 文件夹浏览（本地资产文件夹）

### 3.2 实现方式

由于是 Vue 3 CDN 单文件（无法用 SFC 组件），使用 **composable 模式**：

```javascript
// 每个面板创建独立的上下文
function createPaneContext(defaults) {
  return {
    source: ref(defaults.source || 'assets'),
    collectionId: ref(defaults.collectionId || null),
    filterFolder: ref(null),
    filterTag: ref(null),
    skuFilter: ref(null),
    viewMode: ref('grid'),
    thumbSize: ref(100),
    searchQuery: ref(''),
    // ... 其他状态
  }
}

const leftPane = createPaneContext({ source: 'assets' })
const rightPane = createPaneContext({ source: 'collection' })
```

面板渲染逻辑根据 `source` 选择不同的子视图：

```html
<template v-if="pane.source === 'assets'">
  <!-- 资产网格 + 筛选 -->
</template>
<template v-else-if="pane.source === 'collection'">
  <!-- Collection 内容 + SKU 分组 -->
</template>
<template v-else-if="pane.source === 'nas'">
  <!-- NAS 浏览器 -->
</template>
```

### 3.3 右侧面板的 Collection 视图

当 source='collection' 时，显示：

```
┌──────────────────────────┐
│ 🔍 Search collections... │  ← 搜索/切换 Collection
│ 📁 KS0001 Amazon  v18   │  ← 当前 Collection
│    listing · 12 assets   │
│                          │
│ ▾ SKU: KS0001  (4)       │  ← SKU 分组，可折叠
│  ┌────┬────┬────┬────┐  │
│  │ 🖼  │ 🖼  │ 🖼  │ 🖼  │  │  ← 缩略图网格
│  │ M   │ P   │ A   │ D   │  │     (M=main, P=packaging, etc.)
│  └────┴────┴────┴────┘  │
│                          │
│ ▸ SKU: KS0002  (3)       │  ← 折叠中
│                          │
│ ▾ _unlinked  (5)         │  ← 未分配 SKU
│  ┌────┬────┬────┬────┬──┐│
│  │ 🖼  │ 🖼  │ 🖼  │ 🖼  │🖼││
│  └────┴────┴────┴────┴──┘│
│                          │
│ ═══════════════════════   │
│ 📁 KS0002 Home24  v5     │  ← 上一个/下一个 Collection
│    campaign · 8 assets   │     (滚动查看更多)
│ ▸ SKU: KS0002  (8)       │
│                          │
├──────────────────────────┤
│ [−] [+] 缩略图大小        │  ← 缩放滑块
│ ☐☐☐ ≡ 视图切换           │  ← Grid/List/Detail
└──────────────────────────┘
```

## 4. 布局

```
┌──────┬─────────────────────┬───┬──────────────────────────┐
│ Side │  Pane A              │ █ │  Pane B                  │
│ bar  │  Source: Assets      │ █ │  Source: Collection      │
│ 220px│  [切换来源 ▾]        │ █ │  [切换来源 ▾] [搜索...]  │
│      │──────────────────────│ █ │──────────────────────────│
│ TYPE │  [筛选栏]            │ █ │  SKU 分组 + 缩略图       │
│ TAGS │                      │ █ │                          │
│      │  [img][img][img]     │ █ │  [🖼][🖼][🖼][🖼]       │
│ Fold │  [img][img][img]     │ █ │  [🖼][🖼][🖼]           │
│      │  [img][img][img]     │ █ │                          │
│      │                      │ █ │  [−]━━●━━━━[+] 缩放     │
│      │  [−]━━━●━━━━[+] 缩放 │ █ │  ☐☐☐ ≡                  │
└──────┴─────────────────────┴───┴──────────────────────────┘
 │←220→│←──── flex: 1 ──────→│█│←──── flex: 1 ──────→│
           可拖拽分隔条
```

## 5. 交互流程

### 5.1 打开/关闭右面板
- 工具栏按钮 "☰ Dual Pane" → 切换右面板
- 快捷键 Ctrl+Shift+D
- 拖分隔条到最右边 = 关闭右面板，拖回 = 重新打开

### 5.2 切换来源
- 每个面板顶部有来源下拉: [Assets ▾ | Collection ▾ | NAS ▾]
- 切换来源 → 面板内容切换到对应视图
- 各自独立，互不影响

### 5.3 拖拽操作
- Pane A → Pane B: 拖资产到 Collection 的某个 SKU 下 → add to Collection
- Pane B → Pane A: 从 Collection 拖出 = 移除（或仅高亮标记）
- 多选拖拽: 后续 P2 实现

### 5.4 缩略图大小调整
- 每个面板底部有缩放滑块 `[−]━━●━━━━[+]`
- 拖动调整该面板的缩略图大小 (60px ~ 200px)
- Windows 资源管理器同款

## 6. 与全屏编辑器的关系

| 模式 | 触发 | 用途 |
|------|------|------|
| **右面板 Collection 视图** | 工具栏按钮 / 快捷键 | 快速浏览 + 拖入资产 |
| **全屏 Collection 编辑器** | 点击 Collection → 或右面板 "Expand" 按钮 | 深度编辑/排序/版本历史 |

两种模式展示**同一份数据**，切换到全屏时右面板状态同步。

## 7. 实施计划

### P0: 基础面板系统
- [ ] 引入 `splitpanes` (Vue 3 CDN)
- [ ] 创建 `leftPane` / `rightPane` 上下文
- [ ] 右侧面板: source='collection' 基础视图 (Collection 列表 + SKU 切换)
- [ ] SortableJS 跨面板拖拽 (Assets → Collection)
- [ ] 工具栏 "Dual Pane" 切换按钮

### P1: 通用化 + 增强
- [ ] 来源切换下拉 (Assets / Collection / NAS)
- [ ] 搜索 Collection (搜索框)
- [ ] SKU 分组折叠/展开
- [ ] 缩略图大小滑块
- [ ] 右侧面板 Collection 内容实时同步 (左边加完右边立即可见)

### P2: 视图 + 编辑
- [ ] Grid/List/Detail 视图切换
- [ ] 右侧面板内直接排序/改角色
- [ ] 多选拖拽
- [ ] "Expand to Full Editor" 按钮

### P3: 扩展
- [ ] NAS 作为 source (右侧面板可直接浏览 NAS)
- [ ] 面板状态缓存 (localStorage 记住上次状态)

## 8. 参考来源

- splitpanes (Vue 3): https://antoniandre.github.io/splitpanes
- split.js: https://github.com/nathancahill/split (fallback)
- Webix File Manager (双面板): https://webix.com/filemanager/
- DevExtreme FileManager (多视图): https://js.devexpress.com/jQuery/Documentation/24_2/Guide/UI_Components/FileManager/Overview/
- Vuetify createContext (多实例隔离): https://0.vuetifyjs.com/guide/fundamentals/core
- Total Commander: https://www.ghisler.com (双面板文件管理器鼻祖)
