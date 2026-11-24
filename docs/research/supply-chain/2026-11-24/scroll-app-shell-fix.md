---
okf: v0.1
type: Spec
title: USNJ 工作台三层滚动修复实施规格
description: 采用有界 app-shell 与主从双滚动面，明确 EN iframe 高度契约和验收边界
timestamp: 2026-11-24
tags: [supply-copilot, frappe, app-shell, master-detail, scroll]
---

# USNJ 工作台三层滚动修复实施规格

状态：已按后续授权实现本地预览，未 push、未部署。最初任务仅要求规格；协调者随后要求直接实现紧凑顶部、右侧分段，并确定原生 supply-planning Page + Shadow DOM。第 2–5 节保留最初 iframe 方案的实施参考；最终交付以第 9 节原生方案及实测结果为准。本轮生成了本地预览截图，未访问生产浏览器。

## 1. 结论与证据边界

根因：宿主用固定减数和 700px 最小高度撑大 iframe，嵌入页又以内容撑高文档、估算局部 workspace 高度，形成外层页面、列表、详情三个纵向滚动面。

采用成熟的 viewport-bound app-shell + list-details 模式：宿主自顶向下分配高度，壳和中间容器只分配空间，列表与详情负责内容滚动。Siemens Element 的 list-details 已区分列表、详情、头部、正文和响应式返回行为；借用结构，不引入其 Angular 组件。[来源 S4](#8-来源与采用理由)

### 1.1 已核对代码

生成器按任务指定读取：`C:/Users/zhang/orca/workspaces/Cursor/ui-v2-impl/supply_copilot/workbench_page.py`。当前工作树也有同一实现，核对基线为 `58c841ce52917cffd9b3cb46812fc38dd2e81dd0`；以下行号用于定位，不是未来补丁边界。

| 位置 | 已证实的行为 | 对问题的影响 |
|---|---|---|
| `STYLE`，约 255–294 行 | `body` 无高度/overflow 契约；`.topstack` sticky；`main` 有 22/28/44px padding，活动 `.view` 为 block | 内容继续撑高文档；sticky 不能代替锁定壳高度 |
| `.workspace`，约 321 行 | `height:var(--ws-h,560px)` | 只约束局部 workspace，未约束外壳 |
| `.board-scroll` / `.detail-content`，约 325/355 行 | 两者已有 `overflow:auto`，列表已有 `overscroll-behavior:contain`；表头与 `.detail-head` 已 sticky | 保留双 pane 设计，补齐上游空间分配和详情滚动链约束 |
| `measureWorkspace()`，约 1670 行 | `max(240, vh - stackH - 56)` | 未按实际 `.viewhead`、`.wbtop`、提案折叠区等占高分配；固定 240 下限在低窗口继续撑出 |
| `@container workbench (max-width:720px)`，约 422 行 | workspace 高度 auto，board block，board-scroll overflow visible | 窄屏重新依赖整页滚动，不能原样保留 |
| `#proposals-fold`，约 2566 行 | 在 workspace 后，且可自动展开 | 直接给 body 加 hidden 会把本地提案记录裁掉 |
| `.evlist` / `.analysis-pane .scroll-x`，约 515–527 行 | 存在额外滚动包装和窄屏高度规则 | 全局锁高后其他三个一级视图也必须分配滚动归属 |
| `saveUiState()` / `restoreUiState()`，约 1710 行 | 保存 `window.scrollY`，恢复 `window.scrollTo(0,saved.y)` | 应改为 pane 位置，避免焦点或恢复逻辑推动 hidden 祖先 |

**宿主核对限制**：任务中的 `key_test/key_test/page/usnj_workbench_step1/usnj_workbench_step1.js` 不在当前仓库受跟踪文件中，后续找到本地部署副本 D:/private/demand/deploy-step1/usnj_workbench_step1.js，核实同样存在固定减数和 700px 下限；未读取生产文件，不能声称已核对线上版本。已直接核对仓库模板 `supply_copilot/en_page/supply_workbench/supply_workbench.js:13–27`：`host = page.main`、`iframe.srcdoc`、sandbox 为 `allow-scripts allow-same-origin`，第 24 行确为 `height:calc(100vh - 160px);min-height:700px`。例如 768px 高视口里该规则至少占 700px，留给宿主顶部只有 68px，实际宿主顶部大于此值便外溢。实施者须先定位实际路由对应 controller，对比上述模板，再在实际生效文件和模板同步实施；禁止只改模板就宣称 EN 已修复。

项目内已查模块入口、`supply_copilot/en_page/README.md`、`demand_collaboration/AGENT_HANDOFF.md` 和经验库相关供应链条目；它们约束静态快照、CSP 和本地提案，没有可直接复用的滚动壳修复。

## 2. 高度与滚动架构契约

```text
EN viewport
├─ Frappe Desk navbar + page title/chrome                  auto
└─ 当前 Page .swb-desk-page（仅本路由）
   └─ page.main.swb-embed-host                            宿主测量剩余高度
      └─ iframe.swb-embed-frame                           100% × 100%
         └─ html / body                                  100%, overflow hidden
            └─ .app-shell                                100vh -> 100dvh
               ├─ .topstack                              auto, 不滚动
               │  ├─ .modebanner                         auto
               │  ├─ header.site                         auto
               │  └─ nav.topnav                           auto
               └─ main.app-main                          minmax(0,1fr), 不滚动
                  ├─ #collab-storage-notice               auto（有提示时）
                  └─ .view.active / #workbench-shell       剩余空间, min-height:0
                     ├─ .viewhead / .wbtop                 auto
                     └─ #workspace                        minmax(0,1fr)
                        ├─ .board                         grid: minmax(0,1fr) auto
                        │  ├─ #board-scroll                列表滚动面 A
                        │  │  ├─ #wb-table > thead th      sticky top:0
                        │  │  └─ #proposals-fold           同一滚动面内，保留全部记录
                        │  └─ .tablefoot                   auto, 固定可见
                        └─ #detail-slot
                           └─ #detail-content              详情滚动面 B
                              ├─ .detail-head              sticky top:0
                              └─ .detail-body              内容流，不另建滚动面

窄屏：列表 A 保持有界；选中行 -> 复用 #detail-sheet 原生 dialog
      #sheet-scroll 替代 B；其内 #detail-content overflow:visible
      模态打开时 A 为 inert/不可操作，只有抽屉 B 活跃；关闭后恢复行焦点和 A 位置
```

**只允许两个逻辑纵向滚动面：列表 A / 详情 B。** 其余宿主容器、iframe 文档、app-shell、main、workspace 不得产生用户滚动、焦点滚动或脚本恢复滚动。`overflow:hidden` 仍可能成为程序化滚动容器，不能把“没看到滚动条”当作通过；必须同时验证 scrollTop 不变。非根结构容器优先 `overflow:clip`；不支持时用 hidden 兜底并检查焦点行为。clip 不创建滚动容器，也不自动解决 grid/flex 最小尺寸，所有中间层仍显式 `min-height:0;min-width:0`。[MDN overflow](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/overflow)

main 在本方案中负责分配空间，**不能再加 `overflow-y:auto`**；通用 app-shell 示例中的 main 滚动职责在这里交给两个 pane。每个 pane 纵向单轴滚动，横向通过换行、已有列优先级和窄屏卡片呈现解决，不创建 pane 内嵌套横向表格滚动器。分析表的宽表策略见第 4 节。

## 3. 生成器逐项实施清单

以下 CSS 是实施目标骨架，尚未应用；应修改 `STYLE` 原规则及 container/media 覆盖规则，不能只在末尾追加相互冲突的规则。

```css
html, body { height:100%; overflow:hidden; }
body { margin:0; }
.app-shell {
  height:100vh; height:100dvh;
  display:grid; grid-template-rows:auto minmax(0,1fr);
  min-height:0; min-width:0; overflow:hidden; overflow:clip;
}
.topstack {
  position:static; display:grid; grid-template-rows:auto auto auto;
  min-height:0; min-width:0;
}
.app-main {
  display:flex; flex-direction:column;
  min-height:0; min-width:0; overflow:hidden; overflow:clip;
}
.app-main > .storage-notice { flex:0 0 auto; }
.view { display:none; }
.view.active { flex:1 1 0; min-height:0; min-width:0; }
#view-workbench.active { display:flex; flex-direction:column; }
#workbench-shell {
  flex:1 1 0; display:grid;
  grid-template-rows:auto auto minmax(0,1fr);
  min-height:0; min-width:0; overflow:hidden; overflow:clip;
}
#workspace {
  height:auto; min-height:0; min-width:0;
  display:grid; grid-template-columns:minmax(0,1fr) 420px;
  overflow:hidden; overflow:clip;
}
.board {
  display:grid; grid-template-rows:minmax(0,1fr) auto;
  min-height:0; min-width:0; overflow:hidden; overflow:clip;
}
#detail-slot { height:auto; min-height:0; min-width:0; }
#board-scroll, #detail-content {
  min-height:0; min-width:0;
  overflow-x:hidden; overflow-y:auto; overscroll-behavior:contain;
}
#detail-content { height:100%; }
#wb-table thead th, .detail-head {
  position:sticky; top:0; /* 保留现有不透明背景、边框和 z-index */
}
.sheet-wrap { height:100%; min-height:0; overflow:hidden; overflow:clip; }
#sheet-scroll { flex:1 1 0; min-height:0; overflow-y:auto;
  overflow-x:hidden; overscroll-behavior:contain; }
#sheet-scroll #detail-content { height:auto; overflow:visible; }
```

1. `build()` 在 `.topstack` 前增加 `.app-shell`，将 topstack 和 main 包入其中；给 main 加 `app-main`。非布局脚本、数据 JSON 不参与 grid。主区 padding 改为紧凑、计入 border-box 的响应式内边距，删掉原 44px 底部留白；不能靠负 margin 盖住越界。
2. `.topstack` 内 banner/header/nav 保留 auto 三行；壳自身两行 `auto minmax(0,1fr)`。所有从 main 到 pane 的中间 flex/grid 项补齐 `min-height:0;min-width:0`。`.viewhead` 和 `.wbtop` 留在主区固定行。
3. 删除 workspace 的 `--ws-h` / 560px fallback 与 `measureWorkspace()` 的固定 56px、240px 高度算法及调用。保留 `measureShell()` 的**容器宽度**判断、720px 边界、ResizeObserver 和断点切换时关闭抽屉逻辑；抽屉需要的 `--stack-h` 若继续使用，仅测量 topstack，不再写 workspace 高度。
4. 把完整 `#proposals-fold`（包含 `#proposals`、`#legacy-proposals`、`#collab-message` 及模拟视角按钮）从 workspace 后移至 `#board-scroll` 内、table 后，避免新增长列表滚动区。保留节点 ID、事件绑定、localStorage 键及提案数据；提交后仍可打开 fold，但不通过 document scrollIntoView 跳转。`.sr-only` 和 dialog 采用绝对/顶层布局，不占 grid 隐式行。
5. sticky 表头/详情头沿用原选择器；确认祖先没有新的 overflow 包装隔断 sticky。详情深层 `.lay`、`.raw`、表单等内容自然流入 B，不能 max-height + auto 再造第三个纵向滚动面。错误提示/空态也在对应 pane 内可达。
6. `saveUiState()` / `restoreUiState()` 保存并恢复 A、B（窄屏为 `#sheet-scroll`）的 scrollTop，去掉 window 坐标恢复；读取旧会话键时忽略旧 `y`，业务选择与筛选仍可恢复。渲染完成后再恢复 pane 坐标。焦点使用 `preventScroll`；确需让选中行可见时只调整 A 的 scrollTop，不调用能滚动祖先的无边界 `scrollIntoView()`。
7. 覆盖 <=720px 规则：workspace 改**有界**单列 grid，board 仍 grid，board-scroll 仍 auto；删掉 `height:auto + board:block + overflow:visible` 的旧组合。复用已有 `dialog.sheet` / `openSheet()` / `finishSheet()`，不另造抽屉。抽屉填满可用主区或在低高度时扩为 iframe 内全屏；删除强制 220px 等可能超出当前空间的下限，并以实际 iframe viewport 约束最大高度。
8. 抽屉打开后保留原生 showModal 焦点约束、Esc/关闭按钮、关闭后返回原行；记录 A/B 的位置，跨断点只移动已有详情节点，不能重复 DOM 或重建草稿。`.sheet-bar` 固定，`.detail-head` sticky，B 只在 sheet-scroll 上滚动。
9. 为 360px 和 200% 缩放增加紧凑 chrome：常驻简短演示身份、标题、导航、搜索/切换及详情入口；次要模式说明、计数、长介绍和高级筛选移到 A 内可展开区域（保留 ID/可访问名称与功能）。nav 从现有 `overflow-x:auto` 改为换行或紧凑两列，不能产生第三个横向滚动区。短视口（建议 max-height:480px）同样采用紧凑模式，不能压缩字体或隐藏业务字段凑高度。标题、输入框允许换行/缩小 min-width，避免 210px 搜索下限撑宽。
10. 桌面 pane 宽度沿用现有容器查询的 420/380/340px 规则；以**workbench 内容宽度**决定抽屉，不按浏览器外窗宽猜断点。窄屏卡片已有省略列的内容必须能在详情读全；列表卡片下用固定区标题替代表格 thead 的粘性表头。

## 4. 其他一级视图：锁壳不能裁内容

“两个滚动面”指同时可见的内容职责上限，不是要求所有 tab 强行显示两个空 pane；隐藏 `.view` 不应占高度、接收焦点或参与滚动。

| 视图 | 滚动归属与具体修改 |
|---|---|
| 证据链 `#view-evidence` | viewhead 固定，`.evgrid` 占剩余高度、`min-height:0`。列表由 `.evlist > .scroll` 接管 A，`.evpanel` 接管 B；`.evlist` 自身 overflow clip，删除窄屏 `max-height:280px;overflow:auto`。窄屏用列表→详情两屏，返回后保留列表位置，不能把两块自然堆高 |
| 分析方法 `#view-analysis` | viewhead/`.analysis-nav` 固定，`.analysis-pane.active` 占剩余空间并充当唯一 A。删除内部 `.scroll-x` 的 overflow 包装效果。560px 宽表在窄屏转换为带列名的行卡片/字段分组，字段不删除；不把外层横滚与内层竖滚叠起来，不引入表格库 |
| 口径 `#view-method` | 由 `.method` 充当唯一内容滚动面 A；其祖先及内部表格/说明不再滚动，长字段自然换行 |

各 pane 统一 `overflow-y:auto;overscroll-behavior:contain`、可聚焦 region 与可访问名称。200% 下长表头可换行，sticky 区不能覆盖全部正文；完整字段在详情/卡片可读，不能仅靠 title 悬停提供内容。

## 5. EN 宿主逐项实施清单

目标生效 controller：任务指定的 `key_test/key_test/page/usnj_workbench_step1/usnj_workbench_step1.js`；同时维护仓库 `supply_copilot/en_page/supply_workbench/supply_workbench.js` 模板。生产 controller 未读取（仅核对本地部署副本），故以下类名是明确的**新增契约**，Frappe 祖先选择器需要实施时以实际 DOM 确认。

1. `wrapper` 加 `.swb-desk-page`；`page.main` 加 `.swb-embed-host`；iframe 加 `.swb-embed-frame`。三者 `min-height:0;min-width:0`。host 为 border-box，无垂直 padding/border/margin，frame 为 `display:block;width:100%;height:100%;min-height:0;border:0`，去掉 inline iframe 基线留白。
2. 清除旧 `calc(100vh - 160px)` 和 `min-height:700px`；**唯一高度来源是宿主测量**。在 Page 已显示、frame 插入后以 requestAnimationFrame 进行首次测量：

   ```js
   const top = host.getBoundingClientRect().top;
   const nextHeight = Math.max(0, Math.floor(window.innerHeight - top));
   // host 下方到视口底部的 margin/padding 应在当前路由清零。
   // 只有 nextHeight 与上次整数高度不同才写 host.style.height。
   ```

   禁止读取 iframe 内容 scrollHeight 再反向扩高宿主，否则重新形成内容撑壳。隐藏路由不测量、不将 0 高缓存为有效值。Frappe 固定底栏若存在，必须明确其占位并从可用边界扣除实际测量值，不能重新引入魔法减数。
3. 在当前 Page 的实际 Frappe 祖先（通常 `.page-body`、`.page-wrapper`、`.layout-main-section-wrapper`、`.layout-main-section`，以实际 DOM 为准）检查底部 padding、margin、min-height 和 overflow。仅给本 Page 的这些节点加 `.swb-fit-ancestor`，清除导致底部溢出的留白/min-height，设 min-height:0 和 overflow clip；若发现宿主已有滚动位移，进入本路由时先恢复本 Page 的顶部布局再测量。不能全局锁住 Frappe body、影响其他 Desk 页面，也不能仅隐藏外层滚动条掩盖越界。
4. window `resize`、`orientationchange` 与 `visualViewport.resize` 触发同一个 rAF 合并的 update。观察宿主 chrome/上游布局尺寸变化（ResizeObserver），以应对侧栏切换、标题换行和 200% 缩放；不观察 iframe 内容来循环调整高度。只读几何后再写一次高度，取整并跳过未变值，防止 ResizeObserver 重排抖动。
5. `visualViewport` 可用时，软键盘/移动浏览器的可见底边用 `offsetTop + height` 与 `innerHeight` 取较小值，所有量保持 viewport CSS 像素；pinch/键盘情形单独验证，不把 visualViewport.height 与文档坐标混减。rotation 后重新测量。
6. Page on_show 重测；on_hide/切换路由时解除临时祖先类、resize/orientation/visualViewport 监听、ResizeObserver，并 cancelAnimationFrame。返回 Page 幂等重绑。不要每次显示都重建 iframe、重跑 xcall 或清空列表/详情状态；若当前 Frappe 版本无 on_hide 钩子，在路由切换清理并成对重绑。
7. 宿主不读取 frame 内容完成尺寸分配，不需要 postMessage 或新增网络请求。现有读取 HTML 的 xcall 和错误状态原样保留。
8. CSP 策略保持 `default-src 'none'`、`connect-src 'none'`、script-src 哈希等原约束；改脚本后由生成器正常重新计算哈希，不放宽 unsafe-inline。iframe sandbox 保持 `allow-scripts allow-same-origin`，不新增权限。

iframe 内的 100dvh 指向**iframe 自己的 viewport**，不是整个 EN 浏览器窗口；必须先修宿主分配，再由 CSS 自动填满内框。不能只在子页写 100dvh 期待宿主跟着收缩。

## 6. 验收与实施顺序

先写能重现外溢的布局验收，再改宿主和生成器。现有 `supply_copilot/tests/test_workbench_page.py` 中要求 `window.scrollTo(0,saved.y)` 的旧断言应改为 pane 位置行为；已有 CSP、数据契约、localStorage 和响应式抽屉测试继续保留。字符串断言不能代替真实几何和键盘验收。

### 6.1 视口矩阵（实施后执行，本轮均待测）

每组在浏览器 **100% 与 200% 页面缩放**执行；记录实际 `innerWidth/innerHeight`、iframe clientWidth/clientHeight、workbench clientWidth 和所用布局，不把 200% 下的有效 CSS 宽度仍算作原宽。分别测 EN 内嵌与单独打开静态页。

| 外窗基准视口 px | 100% 重点 | 200% 重点 | 状态 |
|---|---|---|---|
| 1440 × 900 | 双 pane，长列表与长详情 | 若实际容器 <=720 则抽屉；缩放后高度重算 | 待测 |
| 1024 × 768 | 根据容器宽决定双 pane/抽屉 | 紧凑 chrome，提示换行不溢出 | 待测 |
| 900 × 700 | 340px 详情或抽屉边界 | 筛选和 nav 不撑宽/撑高主区 | 待测 |
| 768 × 1024 | 含 Frappe 侧栏的实际可用宽 | 横竖屏互换，焦点和草稿保留 | 待测 |
| 360 × 800 | 列表卡片→原生抽屉 | 极窄 CSS 宽度、长字段和软键盘可达 | 待测 |

补测 720/721px **容器宽度**边界、1440×480 短窗口、抽屉打开时旋转及放大/缩小。矩阵需覆盖所有一级视图和 A–E 表，不只测工作台默认页。

### 6.2 三组必须通过的行为断言

1. **外层与边界**：宿主根和当前 Page 的可滚动祖先 `scrollHeight <= clientHeight + 1px`，没有工作台引起的纵向/横向外滚；frame bottom 不超过可见底边 1px，宽高与 host 一致。嵌入页 document/root scrollTop 始终 0。窗口 resize、rotation、侧栏/页头变化后两帧内稳定，无反复高度振荡；切走其他 Desk 页面滚动恢复正常。
2. **滚动隔离与内容完整**：鼠标、触控、PageDown/方向键分别滚 A/B，另一侧 scrollTop 与宿主位置不变；到上下边缘继续滚动不串到外层。列表表头、详情头、tablefoot 可见；最后一行、最后一个详情字段、展开提案历史、旧记录、错误提示、分析宽表全部可到达。窄屏只有抽屉 B 活跃，B 内不能再出现 detail-content 第二条纵向滚动条；所有可见纵向滚动元素按 A/B 白名单核对。
3. **键盘与状态**：Tab 能到达滚动 region、行按钮、搜索、筛选、表单和关闭按钮，焦点环不裁切；抽屉打开焦点进入，Esc/关闭返回原行，不能跳宿主顶部。筛选、行选择、切页签、刷新后恢复 pane 位置符合选择语义，切断点不丢草稿/本地提案。200% 缩放、软键盘和长文本下不出现不可达焦点或被 sticky 头永久遮挡的字段。

每格记录通过/失败、实际滚动面、复现步骤；仅把截图/几何记录放仓库外私有位置，不提交客户数据、生成 HTML、截图或 PDF。发现超高 chrome 时优先把次要控件归入 A 内紧凑区，不以 overflow hidden 裁掉功能后判通过。

### 6.3 本轮文档交付校验

检查 frontmatter、各层 index/log、相对链接；运行 `uv run python scripts/update_index.py` 同步根索引、`git diff --check` 和 `uv run python scripts/check_secrets.py`。这些只证明文档交付合规，**不证明滚动问题已修复**。

## 7. 风险与明确不做

| 风险 | 处理与判退条件 |
|---|---|
| Frappe Desk 容器版本/路由差异 | 实际 controller 尚未核对；先确认 DOM 和 on_show/on_hide，再限定当前 Page 的祖先类。若只改模板或全局 body 锁滚，不能验收 |
| iframe 重排、隐藏页测量为 0 | rAF 合并、整数幂等写入、显示后测量、监听及时清理；禁止观察内容高度形成反馈环 |
| 100dvh / overflow clip / overscroll 兼容 | 100vh 与 hidden 提供 fallback，显式 min-height:0；支持矩阵不足时仍需保证尺寸封顶及键盘可达，不能靠 overscroll 单独阻止宿主外溢 |
| 窄屏抽屉 / 宽表 | 复用 dialog，单一详情滚动面，宽表转字段卡片；不同时开启横向嵌套表格和整页纵滚 |
| banner/header/筛选在放大后占满高度 | 低高度和窄宽紧凑呈现，把次要内容搬入 A 中，保留演示身份与操作入口；若仍不可达则判失败，不能降低字号掩盖 |
| 锁壳导致提案、证据链和口径丢失 | 提案迁移入 A；各视图明确定义滚动 owner；以最后一条内容和全部控件可达作为门槛 |
| 刻意放弃根滚动能力 | app-shell 使用自定义内容滚动面，应单独验证键盘、会话位置恢复和焦点；不能引用 root-scroller 文章声称锁根无代价 |

不改数据、算法、快照/需求基准、业务权限或本地提案 schema；不新增网络请求；不引入前端框架、表格库、滚动插件或自制滚动条；不修改 CSP/sandbox 权限；初始只读范围已由后续明确实现授权替代；本轮已改布局及必要的高度/焦点/会话滚动逻辑，并新增原生适配层，仍不 push、不部署。

## 8. 来源与采用理由

保留任务提供的六个来源。本轮尝试读取全部链接；S1/S2/S3 工具无法取回，相关摘要属于任务已完成的调研输入，未冒充本轮独立验证。S4/S6 已读取原仓库固定提交文本；S5 另读其链接的原作者文章。以下为归纳及本项目适配，不是逐字引用。

| 编号 | 来源 | 采用点 / 边界 |
|---|---|---|
| S1 | [dembrandt scroll-areas](https://skillhub.360.com/skills/dembrandt/dembrandt-skills/scroll-areas) | 调研输入：每个滚动面要有职责；本轮无法取回原文 |
| S2 | [oh-my-openagent 4.19.4 layout-skill](https://cdn.jsdelivr.net/npm/oh-my-openagent@4.19.4/dist/skills/frontend/references/design/layout-skill.md#1) | 调研输入：有界 shell 和中间 min-height:0；本轮无法取回原文 |
| S3 | [UX Pattern Lab master-detail](https://uxpatternsguide.com/lab/pattern=master-detail&category=Navigation+And+Wayfinding) | 调研输入：窄屏改列表→详情或抽屉；本轮无法取回原文，原链接完整保留 |
| S4 | [Siemens Element list-details，固定提交](https://github.com/siemens/element/blob/9dff7c9c7c1ff0b43426477306bcb562a2b36d75/docs/components/layout-navigation/list-details.md) | 原仓库确认列表/详情职责、独立正文与固定操作区、窄屏两屏、返回焦点；本项目复用现有 dialog，并不引入 Angular |
| S5 | [daily.dev root scroller](https://daily.dev/posts/the-root-scroller-and-how-not-to-lose-it-ujk7eemn1)；[原作者 Polypane](https://polypane.app/blog/the-root-scroller-and-how-not-to-lose-it/) | 说明 root scrolling 的键盘/恢复能力与嵌套滚动代价；本文对工作台有意选择 pane 滚动，增加对应验收，不把该文章当作普遍建议锁根的依据 |
| S6 | [GMOD JBrowse vertical real estate，固定提交](https://github.com/gmod/jbrowse-components/blob/47e4e53bc93c7d80f39adbfbed3e55db3b88dc9a/agent-docs/ideas/waiting-on-a-call/vertical-real-estate.md) | 借鉴由顶层分配可用高度预算；这是领域设计笔记，非通用标准，不移植其合成滚动或复杂高度分配算法 |

补充原始技术定义：[MDN overflow](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/overflow)、[MDN min-height](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/min-height)、[MDN overscroll-behavior](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/overscroll-behavior)。本规格的具体类名、几何测量和迁移位置是基于当前代码的实施选择。

## 9. 最终交付：原生 supply-planning Page

后续明确授权替代最初“只写规格”范围。正式路由为 `/app/supply-planning`（15 字符），Page 标题为“供应链计划工作台”；沿用现有 `key_test` app，不新建 app，不在路由中包含分公司或日期。页内“高级筛选”显示当前分公司 USNJ 与快照日期；当前只读快照只有 USNJ，因此不伪造其他分公司可切换能力。

### 9.1 最终结构与代码落点

```text
Frappe Desk /app/supply-planning
└─ make_app_page -> page.main.supply-planning-main  测量剩余高度
   └─ .supply-planning-surface                    100%，没有 iframe
      └─ ShadowRoot
         ├─ scoped stylesheet（:root -> :host）
         └─ .supply-planning-root
            └─ .app-shell                       height:100%（原生覆盖 100dvh）
               ├─ .topstack                     紧凑标题/身份/快照/四视图/折叠元信息
               └─ main -> #workbench-shell
                  ├─ .wbtop                     数据切换/搜索/折叠高级筛选
                  └─ #workspace
                     ├─ #board-scroll           A：列表 + 本地历史
                     └─ #detail-content         固定详情头 + 分段 tab，不滚动
                        └─ .detail-body
                           └─ 当前 .dsec         B：摘要 / 证据 / 运营判断，三选一
                              └─ .submitline    运营判断中的 sticky 提交区
```

窄屏复用原生 dialog，只搬动同一详情节点，仍只有当前 `.dsec` 负责右侧滚动。`.sheet-scroll` 本身不滚动；抽屉高度/左右位置受测得的宿主内容区约束，不能从 viewport 假定整个 Desk 都可覆盖。证据与表单位于同一个右面板的分段中，不另开网络页面。切换分段不会重建表单，保留草稿与每段滚动位置。

| 仓库源文件 | 目标 / 行为 |
|---|---|
| `supply_copilot/workbench_page.py` | 有界 shell、紧凑 chrome、容器查询、只显示一个详情段、sticky 提交、pane 会话坐标；保留快照/提案数据契约 |
| `supply_copilot/en_page/supply_planning/supply_planning.json` | 部署至 `key_test/key_test/page/supply_planning/supply_planning.json`；Standard Page、key_test 模块、System Manager 角色 |
| 同目录 `supply_planning.js` | 部署至对应 `.js`；创建 Shadow Root、加载片段、限定 document 代理、测高、resize/rotation/页头观察、路由退出清理 |
| `supply_copilot/en_page/supply_planning_static.py` | 部署至 `key_test/key_test/demand_collaboration/`；白名单 `get_parts()` 返回 html/css/js，复用已有 `get_html()` 的固定私有文件读取与登录/角色校验 |
| `supply_copilot/en_page/supply_workbench_static.py` | 同目录依赖，继续读取固定 `private/supply_workbench.html`，不接受文件路径参数 |
| `supply_copilot/en_page/supply_workbench/supply_workbench.js` | 保留旧 iframe 模板的测高修复，作为旧入口兼容；它不是本轮最终原生 Page |
| `supply_copilot/tests/browser_supply_planning.js` | Playwright MCP 可重复运行的原生页验收函数，依赖本地 Frappe 宿主样例，不含客户数据 |

原生适配层仅将 document 的 getElementById/querySelector/querySelectorAll/activeElement/body/documentElement 和事件处理指向 Shadow Root/内部根节点；没有回退到宿主 document 查询。window/visualViewport 监听及 ResizeObserver 被跟踪，离开路由暂停，返回恢复，避免反复挂载和额外取数。宿主以 `innerHeight - main.getBoundingClientRect().top` 为基本测量，不使用固定 150/160px 减数或 700px 下限。

### 9.2 原生执行与安全边界

原生 Shadow DOM **不是 iframe sandbox，也不支持独立文档 CSP**。生成的静态 HTML 继续保留原 CSP 哈希策略；但 `get_parts()` 取出片段后由 Desk CSP 管理，不能宣称原子页的 `connect-src 'none'` 在 Shadow Root 内仍独立生效。原生适配用 `Function(document, window, ...)` 执行受信任的固定私有生成脚本；若 Desk CSP 禁止 Function，会显示加载失败，不修改/放宽宿主 CSP、不绕过策略。真实 Desk 的 CSP 及标准 Page 加载必须由部署者验证。

HTML 内只允许保留 application/json 数据脚本，执行脚本单独提取；数据、样式和脚本均来自原固定产物，不接收用户 URL、路径或远程脚本。仍只有一次白名单加载请求，交互不新增网络请求，不改角色、算法或业务数据。原 iframe 模板的 sandbox 权限未变。

### 9.3 本地验收结果与边界

本地 Chromium + 真实原生 controller + 模拟 Frappe chrome（内容区起点 142px）验收，未部署到真实 EN。`supply_copilot/tests` 与 `tests/test_supply_copilot.py` 共 **43 passed**；静态 CSP 哈希、字段/数量一致性、存储边界和原生片段拆分测试通过。

| 视口 | 顶部固定区 px | 完整可见建议行 | 外层溢出 | 运营判断提交按钮 |
|---|---:|---:|---|---|
| 1440×900 | 86 | 11 | 无 | 分段打开即见 |
| 1024×900 | 86 | 11 | 无 | 分段打开即见 |
| 900×900 | 86 | 8 | 无 | 分段打开即见 |
| 768×1024 | 86 | 10 | 无 | 分段打开即见 |
| 360×800 | 128 | 2（卡片） | 无 | 抽屉内即见 |

补测等效 200% 布局空间：720×450、512×450、450×450、384×512、180×400。十组均无宿主纵横溢出，右侧分段和提交可达，抽屉 Esc 返回原行焦点。180px 宽时长卡片高于可用列表窗口，不能同时显示一整行，但可在 A 内滚动及键盘选中；不把它算成满足桌面“8 行”指标。此处测试的是等效 CSS 视口，**没有实际操作浏览器工具栏 200% 缩放**，真实缩放/移动软键盘仍需 EN 现场验收。

真实滚轮验证：左滚后 A=450/B=0，右滚后 A=450/B=450，宿主 root=0，右侧头部坐标不变。另通过详情 tab 方向键切换、宿主页头高度变化后自适应、同一 surface 不重建、离开/返回路由解除/恢复高度锁、Shadow Root 与同 ID 宿主 canary 隔离，以及其他三个一级视图的滚动归属检查。旧页 1440×800 时 root 高 1095px、workspace 从 401px 开始；新默认 chrome 约 86px。

私有交付目录：`D:/private/demand/scroll-fix/`。原生预览 `supply-planning-native-preview.html`；完整生成静态页 `workbench-app-shell.html`；部署结构 `key_test/key_test/page/supply_planning/` 与 `key_test/key_test/demand_collaboration/`；测试报告 `native-browser-report.json`、截图 `native-desktop.png`。另测 900/1024/1440px 三种窗口高度，右侧提交按钮均可见且宿主无外溢。另有 native-mobile.png 窄屏截图。

本地预览服务为 `http://127.0.0.1:8766/scroll-fix/supply-planning-native-preview.html`，只用于本机检查。B 清单保留原预览的 299/282 行；产物和客户数据均未入库。

待协调者执行：检查真实 Frappe DOM/CSP，按目标路径放入产物并重新生成标准 Page 元数据/缓存，现场完成真实 200% 缩放与移动软键盘验收。本 worker 不部署、不 push。
