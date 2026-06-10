# DAM Workspace — Vilavi PIM

> 数字资产管理原型。电商运营团队用来管理产品图片/视频/文档的内部工具。

## 当前状态

**原型 v2** — 可交互的 HTML 原型，浏览器验证通过。后端未开始。

## 启动

```bash
cd dam-prototype
uv run python main.py
```

浏览器自动打开 `http://127.0.0.1:8098`

## 功能

- 三栏布局：左侧筛选 + 中间缩略图网格 + 右侧详情面板
- 拖拽上传（FilePond / 原生）
- 缩略图拖拽排序（SortableJS）
- 标签筛选 + SKU 搜索
- AI 自动标签（模拟）
- 自动暗黑模式

## 文件

| 文件 | 说明 |
|------|------|
| `main.py` | FastAPI 后端骨架 |
| `static/index.html` | Vue 3 单页 DAM 工作台 |
| `DESIGN.md` | 设计令牌（颜色/字体/组件规范） |
| `docs/process.md` | 开发方法论记录 |
| `docs/ux-workflow.md` | 用户旅程和交互流程 |
| `docs/research.md` | 市场调研摘要 |

## 下一步

见 `docs/ux-workflow.md` — 先做用户访谈，再完善交互原型，然后开始后端开发。

---

详细技术信息见 [AGENT_HANDOFF.md](AGENT_HANDOFF.md)
