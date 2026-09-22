---
okf: v0.1
type: Log
module: colab_kit
created: 2026-09-22
updated: 2026-09-22
---

# colab_kit — 变更日志

- **新增**: 本模块与 `colab_kit/colab_kit.py` —— 把"改同事 Colab notebook"这套动作固化成 CLI。网络命令 6 个（`meta`/`fetch`/`backup`/`guard`/`write`/`verify`），本地命令 8 个（`cells`/`dump`/`find`/`insert`/`backup-cell`/`sed`/`syntax`/`diff`）。来历：本次处理 Overstock 订单处理 notebook 时，读/写/改/回读校验每一步都是现写的 Drive 调用，用完即散 —— 而这类需求会反复出现（PB 订单处理本地化等），所以独立成模块。做法与踩坑见 `docs/solutions/developer-experience/colab-notebook-drive-api-editing.md`。
- **实测**: 本地命令对真实 31 格 notebook 跑通（`cells`/`find`/`diff`/`syntax`）；其中 `find` 对 `merged_sku = ` 命中 **2 格**（生效代码 + 注释掉的老代码）—— 正是 `sed` 默认拒绝多命中的理由。网络命令只读手测：`meta` → `fetch` → `guard`（用过期 `modifiedTime` 正确 exit 2；用新值 exit 0）→ `verify --expect-changed ""`（无差异）。`uv run pytest colab_kit/tests -q` → 14 passed。
