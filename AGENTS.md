# AGENTS.md

> 本文件是项目**唯一指令来源**，Claude Code / Codex CLI 共用。
> `CLAUDE.md` 应为此文件 symlink，不要直接编辑 CLAUDE.md。

## 通用守则

### 编码铁律 (Karpathy)

1. **编码前思考**：不假设。不确定就提问。
2. **简洁优先**：最少代码解决问题，不做投机性工作。
3. **精准修改**：只碰必须碰的，匹配已有风格，删掉死代码。
4. **目标驱动**：先写验证用例，再让它通过。

### 工作流三原则 (adapted from gstack ETHOS.md)

**① 先搜再造 (Search Before Building)** — 三层搜索，按顺序：

1. **搜项目内**：模块索引定位 → 读 AGENT_HANDOFF → 复用已有函数/API
2. **搜网上**：GitHub 项目、开源库、用户评价、最佳实践、成熟方案
3. **再自己造**：确认没有现成的之后才从零写。重新发明轮子是最贵的

> 实例：Web 图片上传 UI 先搜 FilePond/SortableJS 成熟库 → 选用后再适配，而非从零写拖拽组件。

**② 把湖煮干 (Boil the Lake)** — 数据管道版：

- **每一步都生成报告**：总行数 / 成功 / 跳过 / 失败 / 跳过原因，格式见 `docs/agent-guide.md`
- **未匹配记录必须保留**：什么没匹配上、为什么，不静默丢弃
- **数量对账**：入 N 行 → 出 M 行，N−M 去哪里了？差数在报告里可追溯
- **列验证全覆盖**：缺列报错，不猜"差不多"
- **不要煮海**：CI/CD、监控面板、架构重写不是我们的湖

**③ 用户主权 (User Sovereignty)** — Agent 推荐，用户决定。赛狐导入前必须确认范围，绝不擅自扩大到全量。你永远缺用户的领域上下文。

## 项目信息

**fzh-data** — FZH 跨境电商数据管道工具集，维护**赛狐 / ERPNext / 通途**三方数据一致性。

### Agent 新机器首次 clone 后必做

```powershell
# 1. 安装 uv (Python 包管理器) — 只需一次
powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"

# 2. 安装项目依赖
uv sync

# 3. 初始化 symlink (CLAUDE.md, skills)
powershell -ExecutionPolicy Bypass -File setup.ps1
```

> 以上 3 步做完即可正常开发。所有脚本通过 `uv run python <script.py>` 运行，不需要全局 Python / conda。
> 如果 `uv` 不是命令，重新打开终端或手动加 `$env:Path += ";$env:USERPROFILE\.cargo\bin"`。
> 如果同事 agent clone 后不知道怎么做，让它读本项目 AGENTS.md 的本节。

### 运行环境

- Python >= 3.10 + uv (详见 `pyproject.toml`)
- 运行方式：`uv run python <script.py>`，脚本从所在目录运行
- Git：中文 commit `type(scope): description`，开发在分支 -> merge 到 main
- 公司背景、供应链、三系统 SKU 定义 -> `docs/company-context.md`

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
| `nas-itemgroup-folders` | `nas_itemgroup_folders/` | NAS-ERPNext 物料组文件夹对账 + 叶子组 (LGKS) 管理 |
| `us-openai-api-proxy` | `us_openai_api_proxy/` | US Vultr Tailscale + CLIProxyAPI → ChatGPT API 共享 |
| `dam-prototype` | `dam-prototype/` | DAM 数字资产管理原型 |
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
7. **新建 Item Group 叶子组**：必须设 `is_group=1, is_leaf_group=1, custom_model_id=LGKS+最小子KS编号`（见 `docs/company-context.md`）
8. **永远不直接 push main**：任何改动（包括文档）必须走 `feature/xxx` 分支 → 提交 → `git push -u origin feature/xxx` → GitHub 开 PR → 审批后合并。唯一例外：紧急 revert。
9. **提交 PR 前扫描凭证**：`git diff origin/main...HEAD | grep -iE "(api_key|api_secret|password|token|ghp_|github_pat_)\s*=\s*['\"]?\w{8,}"` 必须有零输出。禁止硬编码密钥/token/密码，禁止提交 CSV 数据文件、PDF、图片到公开仓库。违反 PR 不得合并（详见 `CONTRIBUTING.md` 安全检查章节）
8. **OKF 文档规范**：新建子项目/模块时，必须创建 `docs/` 目录，按 [OKF v0.1](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) 规范编写文档。所有 `.md` 文件必须有 YAML frontmatter（`type` 字段必填），每个目录必须有 `index.md`，每个 bundle 必须有 `log.md`。参考示例：`advertise/docs/`。触发 `/okf` 或编辑 Markdown 时自动加载 OKF skill。

## 文档体系

```
AGENTS.md (< 200 lines)           ← 你正在读的，项目总纲 + 路由地图
├── CONTRIBUTING.md               ← 技术开发贡献指南（B 类用户）
├── docs/onboarding.md            ← 非技术同事快速上手（A 类用户）
├── docs/company-context.md       ← 公司背景、供应链、三系统 SKU 定义
├── docs/agent-guide.md           ← Skill 管理规则、代码约定、文档 checklist
├── docs/codex_test_enapi_full.md ← Codex 测试 EN_API 全记录
├── EN_API/AGENT_HANDOFF.md       ← EN_API 模块详情（API 端点、压缩、启动）
├── warehouse_restock/AGENT_HANDOFF.md ← 备货单模块详情
├── (其他 6 个模块)/AGENT_HANDOFF.md   ← 各模块详情
└── .agents/skills/*/SKILL.md     ← Agent Skill 入口（按触发词加载）
```

### 团队协作角色

| 角色 | 怎么用 | 参考文档 |
|------|--------|---------|
| **A 类：非技术同事** | Agent 运行脚本 / Web UI，不提代码 | `docs/onboarding.md` |
| **B 类：技术开发** | 分支开发 → PR → 审批 → merge | `CONTRIBUTING.md` |
| **项目主** | 审批 PR，维护 main，管控版本 | 本文档 |

> 所有经验教训（Lesson 1-60）已分散到各子模块 AGENT_HANDOFF.md 中，不堆在根目录。
