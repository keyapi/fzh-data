# AGENTS.md

> 本文件是项目**唯一指令来源**，Claude Code / Codex CLI 共用。
> `CLAUDE.md` 应为此文件 symlink，不要直接编辑 CLAUDE.md。

## 通用守则 (Andrej Karpathy)

1. **编码前思考**：不假设，呈现权衡。不确定就提问。
2. **简洁优先**：最少代码解决问题，不做投机性工作，不为不可能场景加错误处理。
3. **精准修改**：只碰必须碰的，匹配已有风格，删掉因你改动产生的死代码。
4. **目标驱动执行**：先写验证用例，再让它通过。多步骤陈述计划+验证点。

## 项目信息

**fzh-data** — FZH 跨境电商数据管道工具集，维护**赛狐 / ERPNext / 通途**三方数据一致性。

- 技术栈：Python ≥ 3.10 + uv + pandas + openpyxl（详见 `pyproject.toml`）
- 运行方式：`uv run python <script.py>`，脚本从所在目录运行
- Git：中文 commit `type(scope): description`，开发在分支 → merge 到 main
- 公司背景、供应链、三系统 SKU 定义 → `docs/company-context.md`

## 模块索引

| Skill | 目录 | 一句话 |
|-------|------|--------|
| `stock-init` | `stock_init/` | 通途库存 + EN BOM → 赛狐库存初始值 |
| `item-cost` | `item_cost_sx/` | EN BOM 成本 → 赛狐采购成本 |
| `item-weight` | `item_weight_size/` | 重量模板匹配 → 赛狐商品重尺 |
| `category` | `category/` | EN 物料属性 + 分类树 → 4 级分类导入 |
| `multi-attr` | `multi_attr_saihu/` | ERP 纵向物料 → 赛狐多属性 + 通途配对 |
| `warehouse-restock` | `warehouse_restock/` | EN BOM → 三成本拆分 → 海外仓备货单 |
| `other-outbound` | `other_outbound/` | 赛狐库存明细 → 其他出库清零 |
| `en-image-upload` | `EN_API/` | 图片上传（CLI + Web UI + 物料组主图） |
| `frappe-core-api` | — | ERPNext REST API 开发（外部 skill） |
| `frappe-errors-api` | — | ERPNext API 错误处理（外部 skill） |

> 每个模块有 `AGENT_HANDOFF.md`（Agent 参考）和 `README.md`（人读）。
> Skill 文件在 `.agents/skills/<name>/SKILL.md`，Agent 按触发词自动加载。

## 关键行为规则

1. **赛狐导入前先确认范围**：默认只用测试商品，绝不全量导入
2. **环境默认 prod**：普通用户不需要知道测试环境，`--env test` 仅开发用
3. **不要跟 FilePond 内部布局打架**（Lesson 56）——用独立网格渲染
4. **uvicorn log_level 永远用 info**（Lesson 59）——启动日志是唯一确认信号
5. **图片压缩加 size guard**（Lesson 60）——压缩后变大则保留原图
6. **不要用 PowerShell Start-Job 启 Web 服务**（Lesson 58）——端口隔离不可达

## 文档体系

```
AGENTS.md (< 200 lines)           ← 你正在读的，项目总纲 + 路由地图
├── docs/company-context.md       ← 公司背景、供应链、三系统 SKU 定义
├── docs/agent-guide.md           ← Skill 管理规则、代码约定、文档 checklist
├── docs/codex_test_enapi_full.md ← Codex 测试 EN_API 全记录
├── EN_API/AGENT_HANDOFF.md       ← EN_API 模块详情（API 端点、压缩、启动）
├── warehouse_restock/AGENT_HANDOFF.md ← 备货单模块详情
├── (其他 6 个模块)/AGENT_HANDOFF.md   ← 各模块详情
└── .agents/skills/*/SKILL.md     ← Agent Skill 入口（按触发词加载）
```

> 所有经验教训（Lesson 1-60）已分散到各子模块 AGENT_HANDOFF.md 中，不堆在根目录。
