# 双面板资源浏览器 — 设计研究报告

> 研究日期: 2026-06-11 | 方法: 行业方案分析 + 领域知识 + 已有文档交叉验证
> 回答: Assets ⇄ Collection 双面板应该怎么做？删除引用应该怎么操作？

---

## 1. 双面板设计的三种行业模式

### 模式 A: 对称独立面板（Windows 资源管理器 / Mac Finder）

```
┌── Left Pane ──────┐  ┌── Right Pane ──────┐
│ 🔍 Search...       │  │ 🔍 Search...       │
├────────────────────┤  ├────────────────────┤
│ 📁 Folder Tree     │  │ 📁 Folder Tree     │
│  ├─ NAS/产品图     │  │  ├─ Collections    │
│  ├─ NAS/营销素材   │  │  ├─ Amazon Listing │
│  └─ ...            │  │  └─ ...            │
├────────────────────┤  ├────────────────────┤
│ [Grid: thumbnails] │  │ [Grid: thumbnails] │
│ 🖼️ 🖼️ 🖼️ 🖼️     │  │ 🖼️ 🖼️ 🖼️ 🖼️     │
│ 🖼️ 🖼️ 🖼️ 🖼️     │  │ 🖼️ 🖼️ 🖼️ 🖼️     │
└────────────────────┘  └────────────────────┘
```

**特征**:
- 两个面板功能完全对称 — 各自有文件夹树 + 网格视图 + 搜索
- 文件夹树独立导航、互不影响
- 拖拽语义由源/目标决定（不是面板决定）
- 用户心智模型：两个"窗口"并排

**典型案例**: Total Commander, Double Commander, Forklift (Mac), Windows 11 文件资源管理器（多标签）

### 模式 B: 源→目标面板（Adobe Lightroom / AEM Touch UI）

```
┌── Source (Assets) ──┐  ┌── Target (Collection) ──┐
│ 🔍 Global Search     │  │ 📋 Collection: "KS0001  │
├──────────────────────┤  │    Amazon Listing"       │
│ Filters:             │  ├──────────────────────────┤
│  □ Images  □ Videos  │  │ #1 🖼️ main       [✕]   │
│  Tags:               │  │ #2 🖼️ alternate  [✕]   │
│   □ front □ back     │  │ #3 🖼️ lifestyle  [✕]   │
├──────────────────────┤  │ #4 🖼️ detail     [✕]   │
│ [Grid: all assets]   │  │                          │
│ 🖼️ 🖼️ 🖼️ 🖼️      │  │  ┌─ Drop Zone ─┐       │
│ 🖼️ 🖼️ 🖼️ 🖼️      │  │  │ Drop assets  │       │
│                       │  │  │ here →       │       │
└──────────────────────┘  │  └──────────────┘       │
                           └──────────────────────────┘
```

**特征**:
- 左右不对称 — 源是浏览器，目标是编辑器
- 右面板显示 Collection 的有序列表（不是文件夹树）
- 拖拽方向单向：源 → 目标
- 用户心智模型：从库存里"挑选"到购物车

**典型案例**: Lightroom Collections, AEM Touch UI, Shopify 产品图片管理

### 模式 C: 混合面板（Bynder / ResourceSpace）

```
┌── Left (Browse) ──────┐  ┌── Right (Collection) ──┐
│ 🔍 Search...           │  │ 📁 Collections         │
├────────────────────────┤  │  ├─ 📋 KS0001 Amazon   │
│ 📁 Folder Tree         │  │  │   ├─ #1 🖼️         │
│  ├─ Product Photos     │  │  │   └─ #2 🖼️         │
│  └─ Marketing          │  │  ├─ 📋 KS0002 Wayfair  │
├────────────────────────┤  │  │   └─ #1 🖼️         │
│ [Grid: filtered]       │  │  └─ 📋 Campaign Q2     │
│ 🖼️ 🖼️ 🖼️ 🖼️        │  │                        │
│ 🖼️ 🖼️ 🖼️ 🖼️        │  │  [展开 SKU 显示图片]   │
└────────────────────────┘  └────────────────────────┘
```

**特征**:
- 左面板：传统资源浏览器（文件夹树 + 网格）
- 右面板：Collection 树状浏览器（多个 Collection 像文件夹一样列出）
- Collection 内部按 SKU 分组 → SKU 下展开图片
- 每个面板独立搜索
- 拖拽：Assets → Collection drop zone（Clone 语义）

---

## 2. 关键 UX 决策对比

| 维度 | 模式 A (对称) | 模式 B (源→目标) | 模式 C (混合) |
|------|-------------|-----------------|-------------|
| 文件夹树 | 两边都有 | 仅左边 | 左边有树，右边有 Collection 列表 |
| 搜索 | 每面板独立 | 全局搜索 | 每面板独立 |
| 拖拽方向 | 双向（语义决定） | 单向：左→右 | 单向：左→右 |
| 右面板功能 | 完整浏览器 | 单个 Collection 编辑器 | 多个 Collection 浏览器 |
| 适合场景 | 文件管理、NAS 整理 | 单 Collection 精细编辑 | 多 Collection 概览+快速组织 |
| 学习曲线 | 高（功能多） | 低（概念少） | 中 |
| 代码复杂度 | 高（对称复用） | 低 | 中 |

---

## 3. AEM Collection 引用删除 — 行业标准

### AEM 的做法

AEM 的 Collection 是**虚拟分组**（指针集合），不是物理存储：
- 从 Collection 中删除 → 仅移除引用指针，Asset 不受影响
- 删除整个 Collection → 删除所有指针，Asset 不受影响
- 删除 Asset → 从所有 Collection 中自动移除引用

UI 上的体现：
- Collection 内每张图有 **✕ 按钮** (hover 显示)，点击移除引用
- 无"Delete"字样，用"Remove from Collection"明确语义
- 删除前无确认弹窗（因为是安全操作），但支持 Undo Toast

### 其他系统的做法

| 系统 | 删除引用方式 | 确认弹窗 | Undo |
|------|-------------|---------|------|
| **AEM Assets** | ✕ hover 按钮 | 无 | Toast "Removed" |
| **Bynder** | 右键 → Remove | 无 | Toast |
| **Lightroom** | 右键 → Remove from Collection / Delete键 | 无 | 无 |
| **Google Photos Album** | ✕ hover 按钮 | 无 | Toast + Undo |
| **Figma** | 选中 → Delete键 | 无 | Ctrl+Z |

### 我们的设计

**用户已经在用 DAM prototype，当前实现是合理的**：
- 图片 hover → ✕ 按钮，点击移除引用
- Toast 提示 "Removed from collection"
- 不支持从 Collection 反向拖回 Assets（因为无意义 — 资产本来就在 Assets 里）

**不需要反向拖动（Collection → Assets）**，理由：
1. Collection 里的 Asset 已经是 Assets 中的引用 — 删除引用即可
2. 不存在"把 Collection 里的东西移动到 Assets"的场景 — 它本来就在 Assets
3. AEM/Bynder/Lightroom 都不支持从 Collection 往 Source 拖
4. 会增加用户困惑："拖回去是什么意思？"

---

## 4. 方案 A（对称独立面板）详细设计

用户已确认：**方案 A — 对称独立面板，保留可折叠 sidebar**

### 4.1 左面板：Assets 浏览器

```
┌─ Assets ──────────────────────────────────┐
│ 🔍 Search assets...          [📋 Filters] │
├────────────────┬──────────────────────────┤
│ 📁 Folder Tree │ [Grid: thumbnails]       │
│  ├─ All Assets │ 🖼️ 🖼️ 🖼️ 🖼️          │
│  ├─ 📁 product │ 🖼️ 🖼️ 🖼️ 🖼️          │
│  │  ├─ pillows │ 🖼️ 🖼️ 🖼️ 🖼️          │
│  │  └─ covers  │                          │
│  ├─ 📁 NAS     │                          │
│  └─ ...        │                          │
└────────────────┴──────────────────────────┘
```

- **文件夹树**：本地文件夹 + NAS 文件夹 + Type/Tag 快捷筛选
- **搜索**：实时过滤网格（文件名 + 标签 + SKU）
- **拖拽**：从网格拖出 → 拖入右面板的 Collection/SKU drop zone

### 4.2 右面板：Collection 浏览器

```
┌─ Collections ─────────────────────────────┐
│ 🔍 Search collections...     [+ New Coll] │
├────────────────┬──────────────────────────┤
│ 📁 Collection  │ [Selected: KS0001 Amazon]│
│  Tree          │                          │
│  ├─ 📋 KS0001  │  🖼️ #1 main      [✕]  │
│  │   Amazon    │  🖼️ #2 alternate [✕]  │
│  │   ├─ KS0001 │  🖼️ #3 lifestyle [✕]  │
│  │   └─ KS0002 │  🖼️ #4 detail    [✕]  │
│  ├─ 📋 KS0003  │                          │
│  │   Wayfair   │  ┌── Drop Zone ──────┐  │
│  │   └─ KS0003 │  │  📥 Drop assets   │  │
│  ├─ 📋 Campaign│  │  from left pane    │  │
│  └─ ...        │  └───────────────────┘  │
└────────────────┴──────────────────────────┘
```

- **Collection 树**：显示所有 Collections 列表（像文件夹）
  - 每个 Collection = 一个文件夹节点
  - 展开 → 显示关联的 SKU 列表（子节点）
  - 点击 SKU → 右侧显示该 SKU 在该 Collection 中的图片
- **搜索**：实时过滤 Collection 名（与当前实现一致）
- **Drop Zone**：按 SKU 分区，从左边拖入图片 → Clone 到该 Collection
- **删除引用**：图片 hover → ✕ 按钮（当前已实现）

### 4.3 关于"文件夹树里显示什么"

用户明确：
> 左边是 Assets（之后再说NAS），右边是 Collections，显示多个 Collections 列表像是文件夹，点开显示SKU就像里面的子文件夹，点击SKU右侧显示里面的图片。就像是 Windows 资源管理器。

所以：
- **左面板文件夹树**：本地文件夹层级（当前 filterFolder 已有基础）
- **右面板"文件夹树"**：Collection 列表（非传统文件夹树，而是平面列表 + 展开 SKU）
- 两边都有搜索，各自过滤

### 4.4 拖拽语义

| 方向 | 语义 | 实现 |
|------|------|------|
| Assets → Collection | Clone（保留源，添加引用） | SortableJS group pull:clone |
| Collection 内部重排 | Reorder（调整 position） | SortableJS sort:true |
| Collection → Assets | ❌ 不支持 | 用 ✕ 按钮删除引用代替 |

---

## 5. 与当前实现的差异

| 维度 | 当前实现 (6/11) | 方案 A 目标 |
|------|----------------|-----------|
| 左面板文件夹树 | 仅文件夹下拉选择 | ✅ 完整树状导航 |
| 左面板搜索 | ✅ leftSearch | ✅ 保留 + 增强（标签搜索） |
| 右面板 Collection 树 | ✅ 平面列表 | ✅ 保留 |
| 右面板 SKU 展开 | ✅ rpActiveSku | ✅ 保留 |
| 右面板搜索 | ✅ rpSearch | ✅ 保留 |
| 右面板 drop zone | ✅ 按 SKU | ✅ 保留 |
| 拖拽 Assets→Collection | ✅ SortableJS clone | ✅ 保留 |
| Collection 删除引用 | ✅ ✕ hover 按钮 | ✅ 保留 |
| 面板分割 | split.js (42% 固定) | 改为可拖拽分割条 |
| 布局模式 | 源→目标 (非对称) | 对称独立面板 |

---

## 6. 实施建议

### 改动范围（最小化）

当前实现已经有 80% 的功能。方案 A 的核心改动：

1. **左面板增加文件夹树** — 替代当前的 `filterFolder` 下拉选择
2. **面板宽度可拖拽调整** — split.js 已加载，改 CSS
3. **右面板保留现有 Collection 树 + SKU 搜索** — 不改
4. **拖拽逻辑不变** — 已用 SortableJS group:clone

### 不做的

- ❌ 不从 Collection 反向拖到 Assets
- ❌ 不支持 Collection → Collection 拖拽（v2）
- ❌ 不在右面板做回完整的文件夹树（Collection 列表就够了）
- ❌ 不删除当前 sidebar（保留可折叠）

---

**创建日期**: 2026-06-11 | **状态**: 待用户确认
