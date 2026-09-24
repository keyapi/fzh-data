# AGENTS.md

> 本文件是项目**唯一指令来源**，Claude Code / Codex CLI 共用。
> `CLAUDE.md` 只是指向本文件的入口（内容为一行 `AGENTS.md`），**不要直接编辑 CLAUDE.md**。

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

**克隆 · Windows 上带 `-c core.symlinks=true`**（本仓库的 `CLAUDE.md` 与 `.claude/skills` 是 git 跟踪的 symlink；Windows 的 `core.symlinks` 默认 `false`，不带 flag 会检出成普通文件 → Claude Code 看不到任何项目 skill）。Windows 建文件符号链接需要开发者模式。

```bash
git clone -c core.symlinks=true https://github.com/keyapi/fzh-data.git
cd fzh-data && git config core.symlinks true    # 持久化；否则 pull 拉到的新 symlink 条目又会退化成普通文件
```

带了这个 flag 就不必再跑 `setup.ps1`（它只剩 Claude Desktop 需要 —— Desktop 只读用户级 `~/.claude/skills/`）。**macOS / Linux 直接 `git clone` 即可。**

```bash
# 0. 检测并安装 Git（如未安装）
#    Agent 执行：先 `git --version` 检查，若不存在则按 OS 安装：
#    Windows:  winget install Git.Git --silent --accept-package-agreements
#    Mac:      brew install git
#    Linux:    sudo apt-get install -y git

# 1. 安装 uv (Python 包管理器) — 只需一次
#    Windows: powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
#    Mac/Linux: curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 安装项目依赖
uv sync

# 2.5 环境体检（按本机 OS 打印建议；默认不自动装软件）
#     uv run python scripts/env_doctor.py
#     Windows 常见建议：安装 PowerShell 7 稳定版（winget id Microsoft.PowerShell）、
#     加载 windows-agent-shell skill，避免 && ParserError 与 GBK/UTF-8 乱码。
#     需要对照探针时：uv run python scripts/env_doctor.py --probe
#     ⚠️ 用户主权：把建议告诉用户，确认后再 winget / 改系统设置。不要擅自全量导入。

# 3. 检查并安装 Node.js（如未安装则自动装）
#    Agent 执行：先 `node --version` 检查，若不存在则：
#    Windows:  winget install OpenJS.NodeJS.LTS --silent --accept-package-agreements
#    Mac:      brew install node
#    Linux:    sudo apt-get install -y nodejs

# 4. 安装 MCP 服务器 —— 按需选装，不必全装
#    ★ 选型表 / 各宿主配置路径 / 启停与裁剪 / 排错：docs/mcp-setup.md
#    最常用两个：
#      Tavily（AI 优化搜索，1000 次/月免费，推荐）：uv pip install mcp-tavily
#        注册 → https://app.tavily.com/home → 取 Key → 写进你宿主配置的 TAVILY_API_KEY
#      free-web-tools（免费无需 Key）：uv pip install git+https://github.com/changcheng967/free-web-tools.git
#    通途 ERP2 MCP：填 tongtool_api/.env 后按宿主分别注册（clone 不会自动出现）
#      Codex:  powershell -File tongtool_api/setup_codex_mcp.ps1
#      Cursor: uv run python tongtool_api/setup_cursor_mcp.py
#    （不要用全局 pip——包必须装到项目 .venv 里）

# 4.5 安装 Compound Engineering 插件（可选，但强烈建议）—— 只为 Claude Code
#    `ce-okf` 收尾 skill 的第 1 步会调 `/ce-compound` 产出学习正文。
#    ⚠️ 它**不在本仓库**，是第三方插件（MIT）：EveryInc/compound-engineering-plugin
#    不装也能跑完（ce-okf 会走内置模板兜底），但正文质量降级：
#    丢掉重叠检测（判断"该更新哪篇已有文档"而不是新建重复的一篇）、
#    grounding 校验（核对文档里的断言有没有证据）等。
#    这是在 **Claude 里跑的斜杠命令**，不是 shell 命令 —— 脚本代劳不了：
#      /plugin marketplace add EveryInc/compound-engineering-plugin
#      /plugin install compound-engineering
#    Cursor / Codex 各自的 marketplace 装法见上游 README。这两个宿主本来就没有
#    `/ce-compound`，一向靠兜底，不影响能否使用 ce-okf。

# 5. 给 Claude Desktop 补用户级 skill 链接（Claude Code 不需要；Codex 用户跳过）
#    Claude Code 靠上面克隆好的项目级 `.claude/skills` 就够了。
#    只有 Claude Desktop 读 ~/.claude/skills/，才需要这一条：
#    powershell -ExecutionPolicy Bypass -File setup.ps1
#    ⚠️ 必须在**主仓库根目录**跑；在 worktree 里跑会把链接指到临时 worktree，
#       且脚本对已存在路径 [SKIP]，事后在主仓库再跑也修不回来（只能手工删链接重建）。

# ⚠️ MCP 装完必须让宿主**完全退出**再开：Claude Desktop 托盘右键 → Quit；Codex 完全退出；Cursor 重载窗口。
#    Claude Desktop 的 3P 模式与普通模式是**两个独立配置文件**，改错会静默无效 —— 路径见 docs/mcp-setup.md。
#    通途 MCP：Codex 与 Cursor 要分别注册。仓库 `.cursor/` gitignore，没有可点的 Cursor 安装提示。
```


> **首次打开项目时，Codex 弹窗问「是否信任此项目」→ 务必选「是」！**
> 选「否」会导致 `.codex/config.toml` 里的 MCP 和 `.agents/skills/` 全部不加载。
> MCP 安装完成后：**Claude Desktop** 托盘右键 → Quit；**Codex** 必须完全退出再打开；**Cursor** 写完 `~/.cursor/mcp.json` 后先看工具目录，没有再 Customize → MCP 并重载窗口。
>
> 所有脚本通过 `uv run python <script.py>` 运行，不需要全局 Python / conda。
> 如果 `uv` 不是命令，重新打开终端或手动加 `$env:Path += ";$env:USERPROFILE\.cargo\bin"`（Windows）或 `export PATH="$HOME/.cargo/bin:$PATH"`（Mac/Linux）。
>
> Windows Agent：跑 shell 前加载 `.agents/skills/windows-agent-shell/SKILL.md`；优先 `pwsh`；禁止 PS 5.1 `Set-Content -Encoding UTF8`（BOM）。
>
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
| `sellfox-api` | `SELLFOX_API/` | 赛狐 OpenAPI 文档镜像（419 端点）+ 连通性测试 |
| `sellfox-amazon-settlement` | `sellfox_settlement/` | 赛狐结算中心V2 + 紫鸟列式报表自动取回 Amazon 账期；钉钉迟交/错位审计；店名↔渠道账号 |
| `sellfox-api` | `SELLFOX_API/` | 赛狐 OpenAPI 文档镜像（443 端点）+ 连通性测试 |
| `sellfox-combo-create` | `SELLFOX_API/` | EN 套件 Product Bundle ↔ 赛狐组合商品：sync-combos 对账/创建/回读断言 |
| `sellfox-cover-inventory` | `sellfox_cover_inventory/` | 三角类皮壳共享库存代理：KS 库存池 + PK# 组合 + cover_combo_ops 创建/对账 |
| `sellfox-shipping` | `sellfox_shipping/` | 赛狐尾程打单（订单获取→承运人标签→追踪回写）三界面架构 |
| `vite-api` | `vite-api/` | VITE 多承运商打单 API 文档（测试环境默认） |
| `fedex-track` | `fedex_track/` | FedEx 官方 Track API 批量查询 + 运营异常报表(仿 ups_track；多Sheet/Amazon营业日口径；复用跟踪号多票) |
| `gls-track` | `gls_track/` | GLS 波兰自发货批量跟踪(公开无鉴权 REST **免开发者账号**) + FedEx 风格异常表；loader 拆一格多号；monthly 一步整月。统一多承运商由 `parcel_track`(PR#215) 接入 |
| `parcel-track` | `parcel_track/` | 通途混合订单分流 UPS/FedEx/GLS + 共享迟发/承运延误/卡件运营表（处理 3 营业日；GLS 波兰历；`--workers` 每家串行） |
| `yiglobal-api` | `yiglobal-api/` | 蜴国际打单 API 文档（原 `蜴国际-API/`；env：`YIGLOBAL_*`） |
| `en-image-upload` | `EN_API/` | 图片上传（CLI + Web UI + 物料组主图） |
| `nas-itemgroup-folders` | `nas_itemgroup_folders/` | NAS-ERPNext 物料组文件夹对账 + 叶子组 (LGKS) 管理 |
| `nas-access` | `NAS_API/` | 群晖多域名访问、QC 选路、OpenWrt ACME+反代、DSM 第二张证 |
| `dingtalk-oa-approval` | `dingtalk/dingtalk_oa_approval/` | 钉钉 OA 销售收款确认单：API 附件 + aflow 浏览器导出 + 账期月过滤 + NAS 归档（不改本地同步） |
| `us-openai-api-proxy` | `us_openai_api_proxy/` | US Vultr Tailscale + CLIProxyAPI → ChatGPT API 共享 |
| `new-api-deployment` | `new-api-deployment/` | new-api 部署（上海阿里云）+ 订阅/配额管理 |
| `new-api-dingtalk-oidc` | `new-api-dingtalk-oidc/` | 钉钉 OAuth → OIDC 桥接代理（FastAPI） |
| `dam-prototype` | `dam-prototype/` | DAM 数字资产管理原型 |
| `erpnext` | `erpnext/` | 工单排查 (setup→fetch→report 流水线) |
| `tongtool-order-cost` | `tongtool_order_cost/` | 通途订单特殊规则 1.7.0 本地引擎 + Google Sheet SKU 改名 |
| `tongtool-order-shipping` | `tongtool_order_shipping/` | 通途订单导出 → 组合件合并成「每包裹一行」的承运商批量导入 csv + 仓库背贴 PDF（代码暂在同事 Colab，本目录只放硬约束与迁移落点） |
| `gsheet-monthly-order` | `.agents/skills/gsheet-monthly-order/` | 月度成品 xlsx → 固定 gsheet 月度 ws（复制/归档/只覆盖变化列） |
| `erpnext-wo-audit` | `.agents/skills/erpnext-wo-audit/` | 工单排查 Skill，按触发词自动加载 |
| `missing-products` | `.agents/skills/missing-products/` | 通途有库存 SKU → EN 产品客户码 → 赛狐产品 SKU 三方主线补齐/审计 |
| `platform-account-reconciliation` | `platform_account_reconciliation/` | OSTKUS/Wayfair 账期费用级对账 + EN Tongtool Order 匹配 |
| `channel-account-sync` | `channel_account_sync/` | Google 表渠道账号 → EN Channel Account（人变才加行，Amazon 按国家站） |
| `intent-router` | `intent_router/` | 中文意图 → 本仓库模块路由（TypeSafe Jev + 置信度闸门；只分类不执行） |
| `advertise` | `advertise/` | Amazon 广告数据分析（SP 报告 → 多维分析 → Excel 报告 + 否定词生成） |
| `ai-access-poc` | `ai_access_poc/` | 统一 AI 接入 C′ 的 PoC（壳 Open WebUI + 板 IvyeaOps 只读） |
| `amazon-pairing` | `amazon_pairing/` | Amazon 在售未配对 Listing 只读智能审核（MSKU/ASIN/parent 家族） |
| `cost-adjust` | `cost_adjust/` | 赛狐成本补录单：改已入库库存的采购成本与头程（不清零重入） |
| `google-drive-permissions` | `google_drive_permissions/` | Google 表格/Colab 共享权限盘点与增删 |
| `colab-kit` | `colab_kit/` | Colab notebook 读写改工具箱：取/备份/列格/插格/替换/语法自检/回写/回读比对/并发守卫 |
| `nas-product-visuals` | `nas_product_visuals/` | 群晖 NAS 产品目录扫描 + ACL 权限实时修复脚本集 |
| `pb-orders` | `pb_orders/` | Pottery Barn 出件：SPS 库存预检（明细级）→ 通途导入 xlsx + 标签/背贴 PDF；CLI + 网页版 |
| `pb-reconciliation` | `pb_reconciliation/` | Pottery Barn 对账月度更新 + TM 佣金结算表 |
| `sellfox-api-proxy` | `sellfox-api-proxy/` | 赛狐 API 代理网关（破 IP 白名单 + 凭证安全分发） |
| `sps-api` | `sps_api/` | SPS Commerce API 可行性探测（EDI / ASN / 发票 / 库存） |
| `ups-track` | `ups_track/` | UPS 官方 Track API 批量查询（当前状态 + 完整节点时间线） |
| `web-automation` | `.agents/skills/{web-automation,playwright-setup,tongtu-automation,sellfox-automation}/` | 网页自动化能力舱（通途/赛狐浏览器 + 通用 Playwright），子项目在 `web_automation/` |
| `windows-agent-shell` | `.agents/skills/windows-agent-shell/` | Windows Agent shell：优先 pwsh、禁 bash/`&&`（5.1）、UTF-8 无 BOM |
| `ce-okf` | `.agents/skills/ce-okf/` | 对话收尾一条龙：ce-compound 正文 + OKF 级联 + 索引联动 + 凭证扫描 + 提交 + PR |
| `design-md` | `.agents/skills/design-md/` | 创建/管理 DESIGN.md（设计方向、tokens、视觉规则单一事实源） |
| `design-review` | `.agents/skills/design-review/` | 视觉审查 → 原子提交修复 + 前后对比截图（上线前收紧 UI） |
| `dingtalk-robot` | `.agents/skills/dingtalk-robot/` | 钉钉自定义机器人通知 + 文件附件（经 ERPNext 中转，ActionCard 推送下载链接） |
| `ecommerce-image-workflow` | `.agents/skills/ecommerce-image-workflow/` | 参考商品图 → 紧凑电商图片集（主图/特性图/场景图） |
| `erpnext-item-create` | `.agents/skills/erpnext-item-create/` | EN 物料/变体创建（值表→属性→模板→变体→配套物料） |
| `frontend-design` | `.agents/skills/frontend-design/` | 有辨识度的生产级前端界面（网页/落地页/仪表盘/组件） |
| `item-group-translation` | `.agents/skills/item-group-translation/` | EN 物料组 item_group_translation 批量中译英（腾讯云 TMT） |
| `okf` | `.agents/skills/okf/` | OKF v0.1 文档规范（type 必填 / 每目录 index.md / 每 bundle log.md） |
| `tongtool-api` | `.agents/skills/tongtool-api/` | 通途 ERP2.0 API 与官方 MCP 接入（查询/调研/排错） |
| `tongtool-warehouse-sync` | `.agents/skills/tongtool-warehouse-sync/` | 通途仓库改名/新增后三处对账登记（通途→ERPNext→财务共享表） |
| `workbuddy-config` | `.agents/skills/workbuddy-config/` | WorkBuddy 配置公司 new-api 网关自定义模型（models.json） |
| `frappe-core-api` | — | ERPNext REST API 开发（外部 skill） |
| `frappe-errors-api` | — | ERPNext API 错误处理（外部 skill） |

> **网页任务路由（弱模型/新同事也必须遵守）**：任何通途/赛狐/通用浏览器任务，
> Agent **不得**自己拼外部绝对路径、选 venv 或直接装 OCR。
> 一律先跑 `uv run python web_automation/scripts/dispatch.py <task> --check`，
> 按输出状态字面执行：`READY` 继续 / `NEED_BROWSER` 跑 bootstrap / `NEED_LOGIN` 让人手动登录
> / `NEED_OCR` 先问用户 / `NEED_USER_CONFIRMATION` 先确认范围带 `--confirm-scope`
> / `BLOCKED` 报告停止。写操作默认只许确认范围内商品，绝不扩大到全量。
> 环境体检：`uv run python web_automation/scripts/doctor.py`。

> 每个模块有 `AGENT_HANDOFF.md`（Agent 参考）和 `README.md`（人读）。
> Skill 文件在 `.agents/skills/<name>/SKILL.md`，Agent 按触发词自动加载。
> **ERPNext 系统访问**: 生产 (`erpnext.vilavi.cn`) → REST API, 测试 (`ensh.vilavi.cn`) → FAC MCP + REST API. 详见 `EN_API/README.md`
> **ERPNext API 凭证**: 从 `EN_API/.env` 读取 `ERP_API_KEY` / `ERP_API_SECRET`，认证头 `Authorization: token <key>:<secret>`

## 关键行为规则

1. **赛狐导入前先确认范围**：默认只用测试商品，绝不全量导入
2. **环境默认 prod**：普通用户不需要知道测试环境，`--env test` 仅开发用
3. **不要跟 FilePond 内部布局打架**（Lesson 56）——用独立网格渲染
4. **uvicorn log_level 永远用 info**（Lesson 59）——启动日志是唯一确认信号
5. **图片压缩加 size guard**（Lesson 60）——压缩后变大则保留原图
6. **不要用 PowerShell Start-Job 启 Web 服务**（Lesson 58）——端口隔离不可达
7. **新建 Item Group 叶子组**：必须设 `is_group=1, is_leaf_group=1, custom_model_id=LGKS+最小子KS编号`（见 `docs/company-context.md`）
8. **永远不直接 push main**：任何改动（包括文档）必须走 `feature/xxx` 分支 → 提交 → `git push -u origin feature/xxx` → GitHub 开 PR → 审批后合并。唯一例外：紧急 revert。
   **所有 Agent（Claude Code、Codex CLI 等）都必须遵守本条。**
   如果 Agent 不确定如何创建 PR，用 `gh pr create --title "..." --body "..."` 命令。
9. **提交 PR 前扫描凭证**：以下命令必须全部零输出。禁止硬编码密钥/token/密码，禁止提交 CSV 数据文件、PDF、图片到公开仓库。违反 PR 不得合并（详见 `CONTRIBUTING.md` 安全检查章节）
   ```bash
   # 0. 工作区全量扫描（含还没 git add 的脚本；上面的 diff 扫描看不到这些）
   uv run python scripts/check_secrets.py
   # 传统 key=value 格式
   git diff origin/main...HEAD | grep -iE "(api_key|api_secret|password|token|ghp_|github_pat_)\s*=\s*['\"]?\w{8,}"
   # curl header 中的凭证
   git diff origin/main...HEAD | grep -iE '"[^"]*:\s*[A-Za-z0-9+/=_-]{20,}[^"]*"'
   # Markdown 文档中的 token/key 表格
   git diff origin/main...HEAD | grep -iE '(token|key|api_key)\s*[:|]\s*`?[A-Za-z0-9+/=_-]{20,}'
   # x-api-key 头 / Bearer token
   git diff origin/main...HEAD | grep -iE 'x-api-key:\s*[A-Za-z0-9]{20,}|Bearer\s+[A-Za-z0-9_-]{20,}'
   ```
10. **OKF 文档规范**：新建子项目/模块时，必须创建 `docs/` 目录，按 [OKF v0.1](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) 规范编写文档。所有 `.md` 文件必须有 YAML frontmatter（`type` 字段必填），每个目录必须有 `index.md`，每个 bundle 必须有 `log.md`。参考示例：`advertise/docs/`。触发 `/okf` 或编辑 Markdown 时自动加载 OKF skill。
11. **索引联动更新**: 修改或新建子项目 OKF 文档后，**必须**运行 `python scripts/update_index.py` 同步更新根目录 `index.md`。完成子项目文档更新后输出 "已同步更新根目录索引"。
    动过 `docs/solutions/` 时**同样必须**跑 `uv run python scripts/check_solutions_health.py --fix`：它重建根平表并体检孤儿文档 / 索引漂移 / 断链 / 上表篇数。新增的 learning 若是孤儿，要么挂到相关 skill（只写路径，不复制内容），要么写进 `docs/solutions/exclusions.txt` 并给原因——**不允许静默放着**。

## 文档体系

```
AGENTS.md                        ← 你正在读的，项目总纲 + 路由地图
├── index.md                      ← 自动生成的子项目文档索引（scripts/update_index.py）
├── CONTRIBUTING.md               ← 技术开发贡献指南（B 类用户）
├── CONCEPTS.md                    ← 共享领域词汇（实体、流程、状态概念）
├── docs/onboarding.md            ← 非技术同事快速上手（A 类用户）
├── docs/company-context.md       ← 公司背景、供应链、三系统 SKU 定义
├── docs/agent-guide.md           ← Skill 管理规则、代码约定、文档 checklist
├── docs/mcp-setup.md             ← MCP 选型与安装指南（选什么、装哪个宿主、启停与裁剪、排错）
├── docs/lessons/                 ← MCP 等工具接入的踩坑与实测记录（Notion / Tavily）
├── docs/solutions/               ← 已解决问题记录（bug、最佳实践、工作流），YAML frontmatter 可按 module/tags 搜索
├── erpnext/docs/                  ← 工单排查 OKF 文档（方法论、经验教训、API 参考）
├── docs/codex_test_enapi_full.md ← Codex 测试 EN_API 全记录
├── EN_API/AGENT_HANDOFF.md       ← EN_API 模块详情（API 端点、压缩、启动）
├── erpnext/AGENT_HANDOFF.md       ← 工单排查模块（setup→fetch→report）
├── warehouse_restock/AGENT_HANDOFF.md ← 备货单模块详情
├── (其他 6 个模块)/AGENT_HANDOFF.md   ← 各模块详情
└── .agents/skills/*/SKILL.md     ← Agent Skill 入口（按触发词加载）
```

### 经验库路由（`docs/solutions/`）

**动手前先查这里有没有现成结论**——踩过的坑基本都在。107 篇按 category 分 8 类，每类一份 `index.md`：

| 类别 | 篇数 | 什么时候读 |
|------|-----|-----------|
| `workflow-issues/` | 29 | 账期对账、迟交/错位、跨期结算、批处理流程 |
| `integration-issues/` | 20 | API 鉴权 / 限流 / 字段长度 / OIDC / Webhook 等集成踩坑 |
| `architecture-patterns/` | 18 | 「这个管道/系统为什么这样设计」 |
| `tooling-decisions/` | 12 | 脚本、工具选型、产出校验 |
| `developer-experience/` | 10 | Windows / worktree / MCP / Colab 等本机环境坑 |
| `conventions/` | 9 | 团队约定（配对、命名、SOP） |
| `best-practices/` | 7 | 通用工程做法（防漏数、知识库防腐、先搜再造、安全加固） |
| `documentation-gaps/` | 2 | 文档与断言的缺口 |

定位单篇：`grep -rl "^module: <模块名>" docs/solutions/`（frontmatter 有 `module` / `tags` / `problem_type`）。
全量平表：`docs/solutions/index.md`（由 `scripts/check_solutions_health.py --fix` 生成）。
体检：`uv run python scripts/check_solutions_health.py`——查孤儿文档、索引漂移、断链、上表篇数是否过期。

### 团队协作角色

| 角色 | 怎么用 | 参考文档 |
|------|--------|---------|
| **A 类：非技术同事** | Agent 运行脚本 / Web UI，不提代码 | `docs/onboarding.md` |
| **B 类：技术开发** | 分支开发 → PR → 审批 → merge | `CONTRIBUTING.md` |
| **项目主** | 审批 PR，维护 main，管控版本 | 本文档 |

> 所有经验教训（Lesson 1-60）已分散到各子模块 AGENT_HANDOFF.md 中，不堆在根目录。
