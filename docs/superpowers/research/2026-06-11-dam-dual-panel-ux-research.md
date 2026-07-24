# DAM 双面板拖拽 UX 研究 (2026-06-11)

> 搜索 + 分析 + 对比。为双面板通用资源管理器的大方向讨论提供依据。
> 遵循 "先搜再造" 原则。网络搜索受限区，综合 SortableJS 官方文档 + 现有代码 + 已知产品模式。

---

## 1. 用户需求重新理解

用户原话：
> "2边都像 Windows Mac 资源管理器的全功能（文件夹树也可以允许搜索）"

关键拆解：
- **两侧对等**: 不是"左主右辅"，两侧都是完整的资源浏览器
- **独立导航**: 各自有文件夹树、搜索、筛选
- **双向拖拽**: Assets ↔ Collection 互相拖，NAS → Assets/Collection
- **搜索**: 每个面板独立搜索框
- **文件夹树**: 类似 Windows 资源管理器左侧树，可展开折叠

---

## 2. 现有产品 UX 模式分析

### 2.1 Windows 资源管理器（双窗口模式）

| 特征 | 描述 |
|------|------|
| 模式 | 开 2 个独立窗口，手动并排 |
| 导航 | 各自有地址栏 + 左侧树 + 右侧内容 |
| 拖拽 | 跨窗口 Move（同盘）/ Copy（跨盘） |
| 搜索 | 右上角搜索框，实时过滤 |
| 视图 | 缩略图/列表/详情/内容 四种 |
| 优点 | 完全独立，灵活强大 |
| 缺点 | 非内置双面板，需手动排列窗口 |

**借鉴**: 对等独立 → 两个面板各自有完整上下文

### 2.2 Total Commander / Double Commander (对称双面板)

| 特征 | 描述 |
|------|------|
| 模式 | 内置对称双面板，Tab 切换 |
| 导航 | 各自有驱动器列表 + 路径 + 文件列表 |
| 拖拽 | F5 复制 / F6 移动 到对侧 |
| 搜索 | Alt+F7 独立搜索对话框 |
| 视图 | 简表 / 详细 / 缩略图 |
| 优点 | 效率极高，键盘流，老牌成熟 |
| 缺点 | UI 陈旧，无现代缩略图网格 |

**借鉴**: 对称布局 + 快捷键操作 + 底栏状态

### 2.3 Adobe Bridge（资源浏览器）

| 特征 | 描述 |
|------|------|
| 模式 | 单面板 + 左侧文件夹树 + 右侧预览 |
| 导航 | 左侧树 + 路径面包屑 + 收藏夹 |
| 拖拽 | 拖到左侧文件夹 = 移动/复制 |
| 搜索 | 右上角搜索 + 高级筛选面板 |
| 视图 | 缩略图网格 + 可调大小滑块 |
| 优点 | 媒体专用，预览强，元数据面板 |
| 缺点 | 非双面板，拖到左侧树不便 |

**借鉴**: 缩略图大小滑块（底部）、文件夹树、面包屑

### 2.4 AEM Assets (Adobe Experience Manager)

| 特征 | 描述 |
|------|------|
| 模式 | 左侧树 + 中间卡片/列表视图 + 右侧 Timeline |
| 导航 | 文件夹树 + 标签筛选 + 智能集合 |
| 拖拽 | 拖到文件夹 = 移动，拖到 Collection = 引用 |
| 搜索 | 顶栏 Omnisearch + Filters 面板 |
| 视图 | 卡片/列表/列 三种 |
| 优点 | Collection 逻辑成熟，权限/版本一体化 |
| 缺点 | 重企业级，非双面板 |

**借鉴**: Collection 与文件夹并列在树中、Omnisearch

### 2.5 Lightroom Classic（图片管理）

| 特征 | 描述 |
|------|------|
| 模式 | 左侧目录树 + 中间网格 + 右侧元数据 |
| 导航 | 文件夹 + Collection + 智能Collection 都在左栏 |
| 拖拽 | 拖图片到 Collection = 添加到集合（不移动文件） |
| 搜索 | 顶栏 Text/Attribute/Metadata 三段式过滤 |
| 视图 | Grid / Loupe / Compare / Survey |
| 优点 | 非破坏性 Collection 模型，与 DAM 高度一致 |
| 缺点 | 非双面板 |

**借鉴**: 文件夹和 Collection 并列在左侧树中，拖入 = 引用而非移动

### 2.6 业界 DAM 产品共性

调研 Bynder、Brandfolder、OrangeDAM、Canto 等：
- **主导航**: 左侧文件夹树 / 分类树
- **内容区**: 中央缩略图网格 + 顶部搜索/过滤
- **详情**: 右侧滑出面板
- **拖拽**: 拖到左侧节点 = 归类/添加标签
- **双面板**: 都不是核心功能，多数是单面板

**关键发现**: 市面 DAM 产品**几乎都不做对称双面板**。
对称双面板更多出现在**文件管理器**（Total Commander / ForkLift / Windows 双窗口）而非 DAM。
这意味着我们需要自己设计适合 DAM 场景的双面板模式。

---

## 3. 拖拽交互模式分类

### 3.1 按拖拽方向

| 方向 | 语义 | 类比 |
|------|------|------|
| Assets → Collection | "把这个图加入这个批次" | LR 拖图到 Collection |
| Collection → Assets | "从批次中移除" 或 无操作 | — |
| NAS → Assets | "导入 NAS 文件到本地资产库" | 文件管理器复制 |
| NAS → Collection | "直接把 NAS 文件加入批次" | 快捷操作 |
| Assets 内部 | 重新排序（当前无意义，网格无顺序） | — |
| Collection 内部 | 重新排序（改 position） | 编辑器已有 |

### 3.2 按拖拽语义

| 操作 | 数据变化 | UI 变化 |
|------|---------|---------|
| **Clone**（源保留） | 无变化 | 源不变 |
| **Move**（源删除） | 从源移除 | 源消失 |
| **Reference**（链接） | 添加引用关系 | 两边都显示 |

**对 DAM 场景的建议**:
- Assets → Collection: **Reference**（clone 元素 + API 调用添加）
- Collection → Assets: **无操作**（从 Collection 移出需要通过 UI 按钮）
- NAS → Assets: **Import**（下载 + 入库）
- NAS → Collection: **Import + Add**（下载 + 入库 + 添加引用）

### 3.3 SortableJS 配置对应

```js
// Assets 网格（左面板）
{
  group: { name: 'dam', pull: 'clone', put: false },
  // pull:'clone' → 拖出时克隆（保留原处）
  // put:false → 不接受任何拖入
}

// Collection 面板（右面板）
{
  group: { name: 'dam', pull: false, put: true },
  // pull:false → 不能拖出
  // put:true → 接受来自同 group 的拖入
}
```

**当前代码已经是这样配置的**，问题在于：
1. 布局导致拖拽手柄不可达或视觉错位
2. 双面板模式下 split.js 的容器结构可能阻断了 SortableJS 的拖拽检测

---

## 4. 文件夹树 + 搜索 模式

### 4.1 文件夹树

参考 Windows Explorer / VS Code / Mac Finder：

```
📁 All Assets (12,340)
├── 📁 FZH共享文件夹 (3,200)
│   ├── 📁 2024-Q4 (800)
│   └── 📁 2025-Q1 (1,200)
├── 📁 myFolder (5,600)
│   └── 📁 test_upload (340)
└── 📁 NAS (fzh.myds.me) (3,540)
    ├── 📁 product-photos
    └── 📁 marketing
```

关键交互：
- 点击节点 → 面板内容切换到该文件夹
- 展开/折叠 → 懒加载子节点
- 右键 → 新建文件夹 / 重命名 / 删除
- 拖到节点上 → 移动资产到该文件夹

### 4.2 搜索

每个面板独立搜索：
- 搜索框在面板顶部
- 实时过滤（debounce 300ms）
- 搜索范围 = 当前面板的 source 上下文
- 清空搜索 → 恢复原视图

---

## 5. 当前代码架构问题分析

### 5.1 布局结构

当前 DOM 结构：
```html
<div class="main">
  <aside class="sidebar" />           ← 左侧边栏（folder tree + collections）
  <div class="split-container">        ← split.js 容器
    <div class="left-pane">            ← Assets 网格
    <div class="right-pane">           ← Collection 面板 (v-if)
  </div>
</div>
```

**问题**:
1. `.split-container` 和 `.right-pane` **在 `.main` 内部**，与 `.sidebar` 同级
2. 当 `showRightPane=true` 时，split.js 创建的左右分栏与 `.sidebar` 形成三层结构（sidebar / left / right），不是传统的两栏
3. SortableJS 的拖拽事件可能被 split.js 的事件处理干扰

### 5.2 SortableJS 拖拽断裂

**可能原因**:
1. **split.js 的 gutter 元素**在 `left-pane` 和 `right-pane` 之间，SortableJS 拖拽经过 gutter 时可能丢失目标
2. **CSS `overflow` 裁剪**: 拖拽的 ghost 元素可能被 `overflow: hidden` 或 `overflow-y: auto` 裁剪
3. **forceFallback**: 未设置，在复杂布局中 HTML5 原生拖拽可能不可靠

### 5.3 状态管理

当前是**单一全局状态**：
- `assets`、`filtered`、`filterFolder`、`collections` 等是全局 ref
- 两个面板共享同一份数据，但没有独立的导航状态

**目标架构**：每个面板有独立的 `paneContext`（已在 v2 设计文档中规划）

---

## 6. 实现方案对比

### 方案 A：对称独立面板（Total Commander 模式）

```
┌──────────┬──────────────────────┬───┬──────────────────────┐
│ SIDEBAR  │  Pane A              │ █ │  Pane B              │
│ (共享)   │  [来源▾] [搜索...]    │ █ │  [来源▾] [搜索...]   │
│          │  [📁树 / 📋筛选]     │ █ │  [📁树 / 📋筛选]     │
│          │  [img][img][img]     │ █ │  [img][img][img]     │
│          │  [img][img][img]     │ █ │  [img][img][img]     │
│          │  [-]━━━●━━━[+]      │ █ │  [-]━━━●━━━[+]      │
└──────────┴──────────────────────┴───┴──────────────────────┘
```

- 两侧完全对等，各自有 source 下拉 + 搜索 + 树/筛选 + 网格
- 共享左侧 sidebar（可选：折叠到面板内）
- 状态隔离：`leftPane` / `rightPane` 独立 context

### 方案 B：主辅面板（当前方案改进）

```
┌──────────┬──────────────────────┬───┬──────────────────────┐
│ SIDEBAR  │  Pane A (主)         │ █ │  Pane B (辅)         │
│          │  Assets / NAS        │ █ │  Collection 视图     │
│          │  + 搜索 + 筛选       │ █ │  SKU 分组 + 缩略图   │
└──────────┴──────────────────────┴───┴──────────────────────┘
```

- 左侧是主要浏览器，右侧是 Collection
- 简单，但左右不对等

### 方案 C：无侧边栏模式（VS Code 风格）

```
┌──────────────────────┬───┬──────────────────────┐
│  Pane A              │ █ │  Pane B              │
│  [📁树] [内容区]     │ █ │  [📁树] [内容区]     │
│  [搜索]              │ █ │  [搜索]              │
└──────────────────────┴───┴──────────────────────┘
```

- 没有全局侧边栏，树内置在每个面板里
- 最接近 Windows 双窗口体验
- 但失去了统一导航

---

## 7. 推荐方向（待讨论）

### 推荐：**方案 A（对称独立面板）+ 全局侧边栏可折叠**

理由：
1. 用户明确要求"两边都像 Windows Mac 资源管理器"
2. 当前 sidebar（筛选/标签/Collections）作为**快速启动器**保留，但可折叠
3. 每个面板内部有自己的 source 导航（下拉 + 搜索 + 树视图）
4. 拖拽方向：A → B / B → A，语义由 source 类型决定

### 分阶段实施

**P0 — 修正当前布局（short-term）**:
- 修复 split.js + SortableJS 冲突
- 修复右侧面板布局错位
- 实现基本双向拖拽（Assets ↔ Collection）

**P1 — 面板独立化**:
- 每个面板创建 `paneContext`（source/搜索/筛选/视图 独立）
- 右侧面板 source 支持切换（Assets/NAS/Collection）
- 每个面板独立的搜索框

**P2 — 文件夹树内置**:
- 每个面板可选显示左侧树（替代或补充全局 sidebar）
- 树节点 = 本地文件夹 + NAS 根 + Collections

**P3 — 高级功能**:
- 拖拽多选
- Collection 内排序/编辑
- 面板状态持久化（localStorage）

---

## 8. 技术参考

| 库 | 用途 | 链接 |
|----|------|------|
| SortableJS | 拖拽 | https://github.com/SortableJS/Sortable |
| split.js | 面板分隔 | https://github.com/nathancahill/split |
| splitpanes | Vue 3 分隔面板 | https://antoniandre.github.io/splitpanes |

### SortableJS 关键配置要点（从官方文档）

- `forceFallback: true` — 在复杂布局中强制用 fallback 模式（克隆 DOM 元素到 body），避免 overflow 裁剪
- `fallbackOnBody: true` — 克隆元素挂到 body
- `removeCloneOnHide: false` — 拖拽过程保持 clone 可见
- `group.pull: 'clone'` — 源列表克隆
- `group.put: true` — 目标列表接收
- `sort: false` — 目标不排序（直接 onAdd 处理）
- `onMove` 回调可返回 `false` 阻止特定拖拽

---

**版本**: 1.0 | **创建**: 2026-06-11 | **状态**: 等待讨论
