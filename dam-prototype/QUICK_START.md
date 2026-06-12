# DAM 双面板 — 快速接手 (2026-06-12)

> **读我就够。** 详细见 `AGENT_HANDOFF.md`

## 项目

`dam-prototype/` — FastAPI + Vue 3 CDN + SQLite 的 DAM 原型
启动: `cd dam-prototype && uv run python main.py --port 8098`
浏览器: `http://127.0.0.1:8098`

## 当前架构 (双面板 v2)

```
┌─ Sidebar ──┬─ Left (Assets Grid) ──┬─ Right (Collection Browser) ──┐
│ Type/Tags  │ 🔍 Search             │ 📋 Collections (searchable)   │
│ Products   │ 📁 Folder tree        │   ├─ Collection A  ▼          │
│ Folders    │ 🖼️🖼️🖼️ (draggable) │   │  SKU: KS0001 | 🖼️🖼️🖼️ │
│ NAS        │                       │   │  SKU: KS0002 | 🖼️🖼️     │
│ Collections│                       │   └─ Collection B  ▶          │
└────────────┴───────────────────────┴───────────────────────────────┘
```

- **左面板**: SortableJS `pull:'clone' put:false` — 整张卡片可拖 (无把手, cursor:grab)
- **右面板**: 展开 Collection → 所有 SKU inline 显示缩略图条, SKU 行即 drop target
- **拖拽语义**: Assets → Collection = Clone (引用), 不支持反向
- **删除引用**: 图片 hover → ✕ 按钮

## 关键文件

| 文件 | 内容 |
|------|------|
| `static/index.html` | **全部前端** (~93KB 单文件 Vue 3 SPA) |
| `main.py` | FastAPI 后端 |
| `AGENT_HANDOFF.md` | 完整技术文档 |
| `docs/dual-pane-research.md` | 方案调研 |
| `DESIGN.md` | CSS 设计令牌 |

## ~~唯一已知问题 — P1~~

**ESC 和拖出取消在 Codex 桌面应用侧边栏浏览器中不工作。**
Playwright 测试通过, 但内嵌浏览器中不生效。

已尝试: 闭包→window 变量, keydown→keyup, capture phase, 全部 6 轮未解决。
猜测根因: Codex 侧边栏浏览器不转发键盘事件到页面, 或 SortableJS forceFallback 不兼容。

**当前缓解**: 3 种取消方式 (ESC / 屏幕按钮 / 右键), 左下角调试面板显示 `dragActive` 和 `keys:` 计数。
如果 `keys:` 始终为 0, 证明键盘事件被阻断 → 只能用按钮/右键。

**建议修复方向**:
1. 把 ESC listener 改成监听页面空白区域 click (mousedown+mouseup 不在 drop zone 上 → 取消)
2. 或者接受按钮/右键取消方案, 去掉调试面板, 把取消按钮做漂亮

## 前端关键变量

- `window.__dragActive` — 全局拖拽状态 (Sortable onStart/onEnd 设)
- `rpExpandedCollections` (reactive Set) — 展开的 Collection
- `rpCollectionItems` (reactive {}) — 懒加载 items
- `rpThumbSize` (ref, default 80) — 缩略图大小
- `leftSearch` / `rpSearch` — 左右面板独立搜索

## 最近 git

```
40714f1 feat(dam): debug panel + 3-way cancel
91c24a5 fix(dam): _dragActive -> window.__dragActive
c2d9667 fix(dam): ESC keyup + onMove fix
e36a63d fix(dam): ESC capture + onMove validation
755930a feat(dam): ESC cancel + ghost fade-out
8f26224 feat(dam): ghost auto-scale + drop animations
9eea8d5 feat(dam): inline SKU strip + whole-card drag
```

分支: `feature/dam-folder-upload`
