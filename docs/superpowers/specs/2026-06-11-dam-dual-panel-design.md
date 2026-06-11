# DAM 双面板拖拽设计方案

> 日期: 2026-06-11 | 状态: 搜索完成，等待讨论确认

## 1. 用户需求总结

- **两个独立全功能面板**，各自可以独立浏览/切换内容
- 左侧/中间: Assets 浏览器（含文件夹树/筛选/搜索/NAS 来源）
- 右侧: Collection 视图（迷你版编辑器，含 PRODUCTS 列表 + 资产缩略图 + 角色）
- **可拖拽分隔条**调整面板宽度
- **双向拖拽**: Assets → Collection, Collection → Assets
- **不依赖选中状态**: 两个面板都随时可用，不因为没选中资产就隐藏
- **右侧面板显示缩略图**: 用户需要看到 Collection 里有什么，才能判断拖什么进去
- 类比: Windows 资源管理器同时开 2 个窗口，互相拖文件

## 2. 业界模式调研

### 2.1 Windows 资源管理器 / macOS Finder (双窗口)
- **模式**: 开 2 个独立窗口，各自有完整功能（树/网格/预览）
- **优点**: 两个窗口完全独立，各自可导航到不同位置
- **缺点**: Web 应用中多窗口不现实；需要模拟为单窗口双面板

### 2.2 Total Commander / Forklift (双面板文件管理器)
- **模式**: 单窗口，左右两个完全对称的面板，各有独立的地址栏/文件列表
- **操作**: Tab 切换活跃面板，拖拽从一个面板到另一个
- **关键**: 两个面板**功能完全一致**，只是显示不同目录

### 2.3 Lightroom Classic (双显示器模式)
- **模式**: 主显示器 = Grid 视图，副显示器 = Loupe/Compare/Grid
- **Secondary Window**: 可以是 Grid / Loupe / Compare / Survey 四种模式之一
- **关键洞察**: Secondary Window 是**独立可切换模式**的，不跟主窗口绑定

### 2.4 AEM Assets (左 Rail + 侧面板)
- **模式**: 主区域 = 资产网格/文件夹；左侧 Rail = 可滑出的资产浏览器
- **面板默认隐藏**: 点击才滑出，内容优先
- **不适用于我们的需求**: AEM 的面板不是"独立功能"，只是辅助浏览

### 2.5 Notion Side Peek
- **模式**: 从数据库列表打开条目 → 侧边滑出面板，列表仍可见
- **可切换**: Side Peek ↔ Center Peek ↔ Full Page
- **参考价值**: 保持了"列表不消失"的上下文

### 2.6 VS Code 分屏编辑器
- **模式**: 拖 tab 到右侧 → 自动分屏；拖中间分隔条调整大小
- **每个面板独立**: 可以打开不同文件，独立滚动
- **关键**: 分隔条拖拽→实时调整宽度

## 3. 技术方案对比

### 3.1 可拖拽分隔面板库

| 方案 | 框架 | 大小 | CDN | 选择 |
|------|------|------|-----|------|
| **splitpanes** | Vue 3 | ~30KB | ✅ jsdelivr | ⭐ 推荐 |
| **split.js** | 原生 JS | ~3KB | ✅ | 备选 |
| CSS Grid + JS | 手写 | 0 | — | 也可行 |

**推荐 `splitpanes`**: Vue 3 原生支持，有 min-size/max-size，emit resize 事件，支持双击最大化。CDN: `https://cdn.jsdelivr.net/npm/splitpanes@3.1.5/dist/splitpanes.min.js`

### 3.2 面板宽度设计

| 屏幕宽度 | 左面板 (Assets) | 分隔条 | 右面板 (Collection) |
|---------|----------------|--------|---------------------|
| 1920px (桌面) | 600-900px | 6px | 400-600px |
| 1440px (笔记本) | 500-700px | 6px | 350-500px |
| < 1024px (平板) | 折叠为单面板 | — | 折叠为单面板 |

默认比例: 60/40 (Assets/Collection)，用户可拖拽调整。

## 4. 布局设计

### 4.1 默认布局 (Assets 为主)

```
┌──────┬──────────────────────────┬────────┬────────────────────┐
│ Side │  Assets Toolbar           │   │    │ Collection Panel    │
│ bar  │ [Upload][NAS][Filter...]  │   │    │                    │
│ 220px│──────────────────────────│   │    │ KS0001 Amazon US ▼ │
│      │                          │   │    │ ┌ main      [img]  │
│ TYPE │   Assets Grid             │ █ │    │ ├ packaging [img]  │
│ TAGS │   [img][img][img][img]    │ █ │    │ ├ detail    [img]  │
│ PROD │   [img][img][img][img]    │ █ │    │ └ alternate [拖]   │
│      │   [img][img][img]         │   │    │                    │
│ FOLD │                          │   │    │ KS0002 Home24   ▼  │
│  ER  │                          │   │    │ ┌ alternate [img]  │
│      │                          │   │    │ └ main      [拖]   │
│ COLL │                          │   │    │                    │
│      │                          │   │    │ [+ Add to Batch]   │
└──────┴──────────────────────────┴───┴────┴────────────────────┘
 │←220→│←──────── flex ────────→│█│←──── 320-500px ────→│
       左侧工具栏固定             可拖拽分隔条              右侧 Collection 面板
```

### 4.2 Collection 面板详细设计

```
┌────────────────────┐
│ Collections    [×] │  ← 关闭按钮
│ 🔍 Search coll...  │  ← 搜索 Collection (几百个时必备)
├────────────────────┤
│ 📁 KS0001 Amazon   │  ← Collection 名称 + 平台标签
│    v18 · listing   │  ← 版本 + 类型
│                    │
│ ▾ SKU: KS0001      │  ← SKU 分组 (可折叠)
│   ┌──┬──┬──┐      │
│   │  │  │  │      │  ← 缩略图网格 (小尺寸 ~60px)
│   │🖼│🖼│🖼│      │     每个图显示 role badge
│   │M │P │A │      │     M=main, P=packaging, A=alternate
│   └──┴──┴──┘      │
│   [+ drop zone]    │  ← 拖资产到此处 = 自动设为 alternate
│                    │
│ ▸ SKU: KS0002      │  ← 折叠状态 (点击展开)
│   (3 assets)       │
│                    │
│ ▾ SKU: _unlinked   │  ← 未分配 SKU 的资产
│   ┌──┐            │
│   │🖼│            │
│   │? │            │
│   └──┘            │
│                    │
├────────────────────┤
│ [Export] [Save]    │  ← 操作按钮
└────────────────────┘
```

### 4.3 Collection 面板功能要素

| 要素 | 说明 |
|------|------|
| **搜索框** | 几百个 Collection 时搜索过滤 |
| **Collection 列表** | 可切换显示的 Collection（不止看一个） |
| **SKU 分组** | 可折叠，显示该 SKU 下的资产数 |
| **缩略图网格** | ~60-80px 小图，显示 role badge |
| **Drop zone** | 每个 SKU 分组下方有 [拖到此处] 区域 |
| **操作按钮** | Export / Save / Edit Full |
| **"Edit Full"按钮** | 点击 → 切换为全屏 Collection 编辑器 |

## 5. 交互流程

### 5.1 打开 Collection 面板
- **方式 1**: 点击工具栏 "☰ Collection Panel" 按钮 → 右侧滑出面板
- **方式 2**: 右键资产 → "Show in Collection Panel" → 自动打开并定位
- **方式 3**: 快捷键 (如 Ctrl+Shift+C)

### 5.2 拖拽 Assets → Collection
1. 用户在左面板浏览/筛选资产
2. 右面板显示目标 Collection + SKU 分组
3. 从左侧拖资产 ⠿ 手柄（或直接拖卡片）→ 到右侧某个 SKU 的 drop zone
4. 松手 → API: link SKU + add to Collection + 刷新右侧面板

### 5.3 双向拖拽
- Assets → Collection: 添加资产到 Collection 的某个 SKU 角色
- Collection → Assets: 从 Collection 中移除（拖到 Assets 面板外 = 移除）

### 5.4 Collection 面板内编辑
- 拖拽调整资产顺序（小范围内 SortableJS）
- 点击资产 → 左侧网格高亮该资产
- 双击资产 → 打开全屏编辑器

## 6. 与全屏编辑器的关系

```
全屏 Collection 编辑器 (已有)  ←→  Collection 侧面板 (新增)
       │                                    │
       │  点 "Edit Full"                     │  点 "Collapse to Panel"
       │  ─────────────────→               │  ←─────────────────
       │                                    │
       │  保留: SKU 切换、角色分配、         │  新增: 缩略图预览、drop zone、
       │  拖拽排序、版本历史、导出            │  搜索 Collection、多 Collection 切换
```

**两者共存**: 用户可以选择在全屏编辑器中深度操作，也可以在侧面板中快速浏览和拖入资产。

## 7. 对其他来源的扩展性

当前设计只需扩展面板左侧的"来源":

| 来源 | 面板内容 | 操作 |
|------|---------|------|
| **Assets** (当前) | 资产网格 + 筛选 | 拖到 Collection |
| **NAS** (未来) | NAS 浏览器 (树 + 网格) | Import then drag |
| **Folder** (未来) | 文件夹树 + 内容 | 拖到 Collection |

右侧 Collection 面板保持不变 — 它不关心资产从哪来。

## 8. 实施优先级

| Phase | 内容 | 优先级 |
|-------|------|--------|
| **P0** | `splitpanes` 分隔面板 + 右侧 Collection Panel 基础布局 | 🔴 立即 |
| **P0** | Collection Panel 显示 SKU 列表 + 资产缩略图 | 🔴 立即 |
| **P0** | 拖拽 Assets → Collection Panel drop zone | 🔴 立即 |
| **P1** | 搜索 Collection (搜索框) | 🟡 下一步 |
| **P1** | SKU 分组折叠/展开 | 🟡 下一步 |
| **P1** | Collection Panel 内缩略图 role badge | 🟡 下一步 |
| **P1** | "Edit Full" 切换全屏 | 🟡 下一步 |
| **P2** | 多选拖拽 | 🟢 后续 |
| **P2** | Collection 面板内排序 | 🟢 后续 |
| **P3** | NAS → Collection Panel | 🔵 远期 |

## 9. 参考来源

- splitpanes: https://antoniandre.github.io/splitpanes (Vue 3 resizable panels)
- split.js: https://github.com/nathancahill/split (zero-dependency)
- AEM Assets touch UI structure: https://experienceleague.adobe.com/en/docs/experience-manager-65-lts/content/implementing/developing/introduction/touch-ui-structure
- Notion Side Peek: https://www.makeuseof.com/change-notion-side-peek-setting/
- Figma UI3: https://help.figma.com/hc/en-us/articles/23954856027159-Navigating-UI3
- Lightroom Classic: dual monitor workflow (Adobe official docs)
- Total Commander: https://www.ghisler.com (dual-pane file manager reference)
