# CLAUDE.md

## 通用守则 (Andrej Karpathy)

> 源自 [Andrej Karpathy 对 LLM 编码陷阱的观察](https://x.com/karpathy/status/2015883857489522876)，由 [andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills) 整理。
> **权衡取舍**：这些准则偏向谨慎而非速度。对于琐碎任务，自行判断。

### 守则 1：编码前思考
**不假设。不隐藏困惑。呈现权衡。**
- 明确陈述你的假设。如果不确定，询问。
- 如果存在多种解释，呈现它们——不要默默选择。
- 如果有不清楚的地方，停下来。指出困惑之处。提问。

### 守则 2：简洁优先
**用最少代码解决问题。不做投机性工作。**
- 不添加未被要求的功能；不为一次性代码创建抽象。
- 不为不可能发生的场景做错误处理。
- 扪心自问："资深工程师会觉得这过于复杂吗？"如果是，就简化。

### 守则 3：精准修改
**只碰必须碰的。只清理自己造成的混乱。**
- 不"改进"相邻的代码、注释或格式；不重构没坏的东西。
- 匹配已有风格，即使你更倾向于不同的写法。
- 删除因你改动而不再使用的导入/变量/函数；不删除已存在的死代码。
- 检验标准：每一行被改动的代码都能直接追溯到用户的请求。

### 守则 4：目标驱动执行
**定义成功标准。循环验证直到达成。**
- "添加校验" → "先写非法输入测试用例，再让它们通过"
- "修 bug" → "先写一个能复现的测试，再让它通过"
- 多步骤任务陈述简要计划，每步标注验证点。

---

## 项目信息

Project: fzh-data — FZH 公司数据管道工具集。当前主要用于维护**赛狐 / ERPNext / 通途**三方数据一致性。

## 公司背景 (FZH)

**FZH** 是跨境电商公司，在北美和欧洲销售**家居纺织品**（填充物为 PP棉/海绵的靠枕、沙发等）。
销售平台：Amazon（北美+欧洲）、Wayfair、Home24、Shopify 等。

### 供应链架构

```
绍兴工厂 (中国)
  ├─ 生产皮壳、内胆、半成品
  ├─ 部分成品直接生产 → FBA / 直接发货
  │
  └─ → 海外分公司仓库：
       ├── USNJ (美东, NJ州) → 填充/压缩/包装/仓储/发货(2C+2B)
       ├── USTX (美中, TX州) → 同上
       └── POLAND (波兰)     → 同上
            │
            └─ → Amazon FBA / 第三方海外仓
```

### 赛狐仓库映射

| 公司仓库 | 赛狐仓库名 | 说明 |
|----------|-----------|------|
| USNJ 美东仓 | CENTRADE | 已启用 |
| USTX 美中仓 | DANEEY | 已启用 |
| POLAND 波兰仓 | POLAND | 已启用 |
| 绍兴工厂(本地) | — | 未启用（赛狐本地仓限制多） |

> 赛狐有两种仓库类型：**本地仓**（中国仓，更多限制，未启用）和**海外仓**（我们用的 3 个分公司仓）。

### 三系统产品定义（关键差异）

三个系统对"SKU"的定义不一致，匹配时必须注意：

| 系统 | 维护方 | 定义 | 格式 |
|------|--------|------|------|
| **EN/ERPNext** | 供应链（张克勇） | **成品** = `物料组-面料-尺寸-颜色`；半成品用前缀（`皮壳#物料组-…` / `内胆#物料组-…`） | KSxxxx-XXX-100-RED |
| **赛狐** | 参考 EN | 同上，暂不含半成品 | KSxxxx-XXX-100-RED |
| **通途** | 销售团队 | 随意维护，常有**人工后缀** | TT0031128K0063817-淘汰 / C/Cord-Black-100-wow-Cover |

**通途人工后缀**（在 `KNOWN_SKU_SUFFIXES` 中维护）：

| 后缀 | 数量 | 含义 | 安全性 |
|------|------|------|--------|
| `-淘汰` | 2 | 产品停产/淘汰标记 | ✅ 稳定 |
| `-out` | 7 | 同上，退出标记 | ✅ 稳定 |
| `-Cover` | ~450 | 皮壳半成品（通途为拆多包裹发货而加） | ⚠ BOM只含成品，需注意特殊场景 |
| `-Foam` | — | 海绵半成品（同上） | ⚠ 同上 |

> EN 的 SKU 定义服务于供应链+工厂的"不重不漏"刚需（每个成品唯一标识），赛狐参考 EN。
> 通途由销售团队自行维护，SKU 随意加后缀，导致跨系统匹配困难。
> 匹配策略：两边都剥离已知后缀再比较。输出到赛狐始终用 BOM 的 `产品编号`（EN 标准格式）。

### 赛狐平台限制

- 海外仓不能直接通过库存调账修改库存数量和采购单价，需通过**其他入库/其他出库**实现成本调整
- 采购成本=0 的行赛狐静默跳过不导入
- 导入模板工作表名必须为 `商品`，Data Validation 丢失会被拒绝

### 赛狐库存核心策略（初期过渡阶段）

**当前阶段**：赛狐初期使用中，实际发货仍在通途操作。赛狐只用来获取订单成本（尾程前），暂不管理真实库存。

**关键认知：赛狐入库批次与成本**

- 赛狐使用**先进先出（FIFO）**逻辑：同一仓库+SKU 先后入库 A、B 两批，订单优先消耗 A 批次，A 耗尽后才用 B
- B 批次的成本**不能修正** A 批次的成本（后入库不等于覆盖）
- 赛狐允许修改历史入库单里的成本，但**只能逐行手动改**，无批量导入方式
- 因此初期一次性把 3 仓全套成本导入，后续主要做**成本修正**（手动），而非频繁新建入库

**库存数量策略**

| 决策 | 说明 |
|------|------|
| **不追求与通途数量一致** | 通途 SKU 体系混乱、2 套系统短期难以对齐 |
| **安全冗余数量（1000）** | 避免赛狐 0 库存导致订单无法标记发货，远超业务需要 |
| **仓库分布参考通途** | 通途"哪个仓有此 SKU"比"库存多少"更可信，避免跨仓虚构 |
| **不写回平台库存** | 赛狐暂未开通，虚假数量不会污染销售平台 |

**入库方式**

| 方式 | 状态 | 说明 |
|------|------|------|
| 期初库存导入 | 已用过 | 相同 SKU+仓库不可重复导入 |
| 其他入库 | ✅ 已有脚本 | `sellfox_import_other_inbound.py` 自动导入+确认+验证 |
| 其他出库 | ✅ 已有脚本 | `sellfox_import_other_outbound.py` 自动导入+确认+验证 |
| **海外仓备货单** | ✅ 主要方式 | `--sku=` 过滤单SKU, 双格式(格式2默认: 绍兴+加工→采购单价, 头程→头程费用) |
| **run_full_restock_flow.py** | ✅ 调度器 | 串联 导出→其他出库清零→备货单导入 完整流程 |

**当前流程**：
1. `run_full_restock_flow.py --generate-only` 生成 Excel 文件
2. `run_full_restock_flow.py --yes` 完整流程（导出+清零+生成+导入）
3. 导入后赛狐手动确认出库 / 检查收货状态
4. 后续成本修正：赛狐界面手动修改入库单成本行

---

## Skill 索引

每个模块对应一个 Skill（`.claude/skills/<name>/SKILL.md`），Claude 自动按用户触发词加载。详情见各 Skill 文件 + 模块的 `AGENT_HANDOFF.md`。

| Skill | 目录 | 功能 | 触发词特征 |
|-------|------|------|-----------|
| `stock-init` | `stock_init/` | 通途库存 + EN BOM 成本 → 赛狐库存初始值导入 | 库存初始值、库存导入、通途库存、EN BOM成本 |
| `item-cost` | `item_cost_sx/` | EN BOM 成本 → 赛狐采购成本导入 | 采购成本、BOM成本、绍兴发货 |
| `item-weight` | `item_weight_size/` | 重量模板匹配 → 赛狐商品重尺导入 | 重尺、重量、尺寸、装箱量 |
| `category` | `category/` | EN 物料属性 + 分类树 → 4 级分类导入 | 商品分类、四级分类、类目 |
| `multi-attr` | `multi_attr_saihu/` | ERP 纵向物料 → 赛狐多属性 + 通途配对 | 多属性、SPU、物料导出、通途配对 |
| `warehouse-restock` | `warehouse_restock/` | EN BOM → 三成本拆分 → 海外仓备货单导入 | 海外仓备货单、备货单、三成本拆分 |
| `other-outbound` | `other_outbound/` | 赛狐库存明细 → 其他出库导入（清零库存） | 其他出库、清零库存、出库单 |
| `en-image-upload` | `EN_API/` | 赛狐图片链接 → ERPNext API 更新物料组主图 | 图片链接、上传图片、物料组主图、EN API |

八个业务模块**相互独立**（`category` 仅动态导入 `multi_attr` 的一个函数）。
两个**辅助 skill** (`frappe-core-api` / `frappe-errors-api`) 来自 [Frappe_Claude_Skill_Package](https://github.com/OpenAEC-Foundation/Frappe_Claude_Skill_Package) (MIT), 辅助所有 ERPNext API 相关开发调试。

## Tech stack

- Python >= 3.10, managed with **uv** (`pyproject.toml` at root)
- `pandas` for DataFrame operations, `openpyxl` for Excel read/write
- No packaging — standalone scripts run with `python script.py` from module directories

```bash
uv sync                          # install pandas, openpyxl
cd <module_dir> && python <script>.py   # run any script
```

## Code conventions

- **Column names in Chinese**: Excel column headers use UPPER_CASE (e.g. `COL_SKU = "产品编号"`, `SAI_HU_SHEET = "商品"`)
- **`os.chdir()` pattern**: Each script changes `os.getcwd()` to the script's directory at startup
- **Auto file selection**: Scripts auto-select input files (latest by `st_mtime`, excluding `~$` lock files)
- **Excel output**: All `.xlsx` gitignored. Timestamped filenames (`*_YYYYMMDD_HHMMSS.xlsx`)

## Git conventions

- Commit messages in **Chinese**, format: `type(scope): description`
- Common types: `feat`, `fix`, `docs`, `init`, `refactor`

### Git workflow

1. Development happens on the **worktree branch** (e.g. `claude/xxx`), NOT directly on `main`
2. Verify the change works, then merge into `main`:
   ```bash
   cd D:\Work\赛狐\Cursor
   git checkout main
   git merge claude/xxx
   ```
3. Sync the worktree branch back:
   ```bash
   cd .claude/worktrees/xxx
   git merge main
   ```
4. Never commit directly to `main` from the worktree — use the branch

## Lessons learned

### 1. Auto file selection: keyword specificity
`_find_file("重尺")` matched template `模板 商品重尺-*.xlsx` because "商品重尺" contains "重尺". Use most specific keyword (e.g. `"重尺数据"`). Verify each pattern matches only one file.

### 2. Directory naming: 数据源/ subdirectory
Keep code and data under one module directory. Use `数据源/` for inputs, `out/` for outputs.

### 3. Module structure convention
```
module_dir/
├── <script>.py / README.md / AGENT_HANDOFF.md
├── __init__.py (empty, for uv build)
├── 数据源/ (gitignored) / out/ (gitignored)
```

### 4. 赛狐 import template: worksheet name must be `商品`
`openpyxl` defaults to `Sheet1` but 赛狐 requires `商品`. Always set `SAI_HU_SHEET = "商品"`.

### 5. 赛狐 purchase cost: zero equals empty
赛狐 treats `采购成本=0` as empty — won't import 0 values. Generate two output files: import (filter cost=0) + reference (keep all).

### 6. SKU matching by prefix (shared across modules)
SKU format: `款式ID-面料-尺寸-颜色` (4 segments). First 3 define a "group key". Weight template: strip `ZLMB#` prefix. Rule: ≥4 segments → key = `"-".join(parts[:3])`; =3 → whole SKU; <3 → no match.

### 7. Excel file locking
`~$*.xlsx` lock files appear when Excel is open → `PermissionError`. Always exclude `~$` prefixed files in auto-selection.

### 8. uv environment
`uv sync` can fail if old `.venv` has stale artifacts → `rm -rf .venv && uv sync`. ONE `.venv` at repo root shared by all modules.

### 9. openpyxl destroys Data Validation on save
`openpyxl.load_workbook() + wb.save()` silently drops Data Validation → 赛狐 rejects file. Fix: `shutil.copy(template) → pd.ExcelWriter(mode='a')` for template-based outputs; or `pd.ExcelWriter() → to_excel(sheet_name='商品')` for new files.

### 10. Windows + Chinese path encoding
Shell commands with Chinese paths fail with `UnicodeEncodeError`. Prefer Python (`shutil`, `pathlib`) over shell for file ops. `PYTHONIOENCODING=utf-8` env var helps.

### 11. Left-merge / SKU whitelist pattern
赛狐 has fixed SKU set → read 赛狐商品导出 → `set(SKU)` as whitelist. Left-join to source data. Unmatched source rows reported but excluded from import.

### 12. 输出文件拆分
Import file (filtered, cost>0) vs reference file (all). Clear filename distinction (`_导入_` vs `_全量参考_`).

### 13. 问题报告统一格式
Multi-sheet `.xlsx`: `汇总` + N detail sheets + `每仓统计`. Each sheet对应一个问题类别，空 sheet 写占位行 "（无数据）". Detail sheets 含产品名称列.

### 14. Data source origins (who provides each Excel)
When debugging column changes, know which system produces each file. See Lesson #14 details in previous CLAUDE.md versions or ask user.

### 15. Keep docs updated immediately
After every fix/discovery, write to CLAUDE.md/md files in the same session. Don't wait for reminders.

### 16. Git worktree: commit from worktree, not main repo
Shell CWD resets to worktree but git commands could operate on main repo. Verify `git branch` shows `* claude/<name>` before commit. If mistake: `git reset --hard <prev>` on main, `git cherry-pick <hash>` on worktree.

### 17. COS 防盗链导致外部图片 URL 在 ERPNext 不显示预览
赛狐导出的图片链接是 COS URL。直接用 `file_url` 模式创建 File 记录 (Doctype=File, file_url=COS URL)，ERPNext 页面不显示预览。根因: COS 开启了防盗链，浏览器通过 ERPNext 页面加载图片时带 `Referer: ensh.vilavi.cn` → COS 返回 403。修复: 下载图片 → 以真实文件上传 ERPNext → 使用本地 `/files/xxx` 路径。

### 18. ERPNext upload_file API: file_url vs 真实文件上传
- `upload_file(file_url=...)`: 创建 File 记录但 `file_size=0`, `thumbnail=None`, 不更新父文档字段
- `upload_file(file=...)` (multipart): 创建 File 记录 `file_size>0`, 但仍不更新父文档字段
- Item Group 的 image 字段需额外 `PUT /api/resource/Item Group/{name}` 设置
- 两步缺一不可: File 记录 (UI 显示) + PUT image 字段 (数据存储)

### 19. ERPNext REST API filters/fields 参数格式
- 必须用 `json.dumps()` 而非手动拼接 JSON 字符串
- 自定义字段 (custom_*) 在 filters 中需带 doctype 前缀: `[["Item Group", "custom_model_id", "=", "KS0001"]]`
- `fields` 参数不要包含自定义字段 (会被 "Field not permitted in query" 拒绝)
- `requests` 的 `params` 参数会自动 URL-encode，不要手动编码

### 20. nginx 返回 417 Expectation Failed
ERPNext 测试服务器 nginx/1.18.0 对 `Expect: 100-continue` 返回 417。解决: 自定义 `HTTPAdapter` 在 `send()` 中 `request.headers.pop("Expect", None)`。curl 用 `-H "Expect:"` 可绕过。

### 21. .env 文件管理凭证 (stdlib only)
- `.env` (gitignored) 存真实凭证，`.env.example` (git 跟踪) 为模板
- 手动解析 `key=value` (stdlib only, 无 python-dotenv 依赖)
- `os.environ.setdefault()` 确保环境变量优先级高于文件
- 加载顺序: 系统环境变量 > 模块 `.env` > 项目根 `.env`

### 22. SSH 连 GitHub 失败排查
**症状**: `git push` → `Permission denied (publickey)` 或 `Connection timed out`。
**排查顺序**:
1. `ssh -T git@github.com` — 端口 22 不通则超时，通但 key 不对则 Permission denied
2. 22 端口超时可试 443: `ssh -T -p 443 git@ssh.github.com`（需先 `ssh-keyscan -p 443 ssh.github.com >> ~/.ssh/known_hosts`）
3. 确认 `~/.ssh/config` 中 `Host github.com` 配置了 `IdentityFile ~/.ssh/id_ed25519_github` + `IdentitiesOnly yes`
4. 443 端口 Host 名是 `ssh.github.com`，不在 config 的 `Host github.com` 规则内，可能没匹配到指定 key。可 `ssh-add ~/.ssh/id_ed25519_github` 让客户端自动尝试该 key
5. 大概率 22 端口只是临时抽风，等几分钟重试即可 — 不要误判为权限问题

### 23. 赛狐 其他出库 导入规则
- **临时单号 = 自定义分组键**（不是系统单号）。同一临时单号的多行合并为**一笔**出库单，不同临时单号拆分
- 系统单号 (OB2605260546 格式) 是赛狐导入后自动生成的，不可预知
- 出库模板仅 **1 行表头**（不同于海外仓备货单的 2 行）
- 同一 (出库仓库+SKU) 已有待确认记录时，新导入会被拒绝
- **"条"统计** = 出库单笔数（父行），不含展开的 SKU 子行
- Playwright MCP 文件上传受限于项目根目录，需先 `cp` 到 `D:/Work/赛狐/网页自动化/.playwright-mcp/`
- 赛狐 API 下载需 POST `{"ids":[taskId]}` 获取 COS URL 再下载，不能直接 GET

### 24. 赛狐导入结果检查
- 导入完成后，弹窗会显示"成功 X 条，失败 Y 条"
- **导入后需手动刷新页面**才能看到新记录（页面不会自动刷新列表）
- 临时单号不可跨导入重复使用（即使导入内容不同）
- VXE 表格（赛狐列表页使用的组件）的 checkbox/下拉菜单对 MCP Playwright 不友好，复杂选择操作建议人工完成

### 25. 库存明细导出包含店铺/FNSKU 维度
- 同一 SKU+仓库 在库存明细里可能有**多行**（不同店铺/FNSKU），不能按 SKU+仓库 聚合
- 生成其他出库文件时，必须逐行保留店铺和 FNSKU，每条对应一行出库
- 赛狐自定义 popover 多选组件（如商品类型筛选）对 MCP evaluate 不稳定，推荐用 API 参数或商业逻辑（如 `-ALL` 后缀）过滤

### 26. 赛狐海外仓备货单模板与规则
- 模板**2 行表头**（不同于其他出库的 1 行），7 个 sheet（4 个 hidden Data Validation）
- 隐蔽限制：**单个备货单 ≤ 500 条**（弹窗未注明，赛狐内部校验）
- 总计 ≤ 5000 条，超过 500 需拆批次（不同临时单号）
- 临时单号可选（单批导入时），多批导入需各自不同

### 27. 海外仓备货单模板三成本映射
- `指定采购单价` = 绍兴发货成本（单价）
- `物流费用` = 头程运费 × 1000（总金额，赛狐会自动除以数量得单价）
- `其他费用` = 国外加工成本 × 1000
- `*头程分摊方式` / `*税费分摊方式` = 自定义
- `*备货数量` = 1000
- 赛狐隐性公式: `单个头程费用 = (物流费用 + 其他费用 + 报关税费) / 备货数量`

### 28. MCP 操作赛狐的局限
- 自定义 select-container 组件用 evaluate 点击不稳定，易误关
- VXE 表格 checkbox/menu 难定位，excel 导入后对话框被 Playwright timeout 误判
- 建议核心业务逻辑用 Python 脚本，MCP 仅用于探索和一次性操作
- 操作前后必须导出备份库存明细

### 29. 赛狐模板列号精确映射
海外仓备货单模板 2 行表头，**列号不是连续的**：
- col 13: `指定采购单价`
- col 14: `*备货数量`
- col 15: `商品包装重量（g）` ← 不是 `单个头程费用`！
- col 16: `物流费用`
- col 17: `其他费用`
- col 20: `单个头程费用` ← 格式 2 填这里，不是 col 15！

**每次改模板填充逻辑必须对照模板 Excel 确认列号**，不能凭记忆。

### 30. Playwright file_chooser 事件时序
`page.wait_for_event("filechooser")` 必须在点击按钮**之前**注册：
```python
# ✅ 正确：用 with 包裹点击
with page.expect_file_chooser(timeout=10000) as fc_info:
    add_file_btn.click()
file_chooser = fc_info.value

# ❌ 错误：先点击再等事件——file chooser 已弹出但没人接
add_file_btn.click()
file_chooser = page.wait_for_event("filechooser")
```

### 31. VXE 表格父行/子行结构
赛狐的 VXE 表格有父行（含单据号/确认按钮）和子行（含 SKU 详情）。
- 搜索 SKU 命中子行，但 **"确认入库"/"确认出库"按钮在父行**
- 不能按 SKU 行找按钮 → 直接找页面上第一个可见的"确认入库"/"确认出库"按钮
- 确认后需**刷新页面**才能看到状态变更

### 32. 赛狐搜索必须先切搜索类型
所有页面的搜索框左边有下拉菜单（入库单号/出库单号/备货单号/SKU/品名等）。
默认值不是 SKU。搜索 SKU 前必须：
1. 点击下拉 → 选 "SKU"
2. 再填 SKU → 回车
否则搜不到。

### 33. 其他入库完整流程
- URL: `/web/warehouse/otherIn/index.html`
- 模板 19 列，1 行表头，hidden sheets 含 Data Validation
- 导入后记录处于"待确认"，**库存不增加**
- 必须点击每行的"确认入库"按钮，库存才生效
- 同理：其他出库导入后需"确认出库"库存才减少

### 34. 测试数据隔离
- 测试单 SKU 时，**生成脚本加 `--sku=` 过滤**，避免把全量数据导入赛狐
- `build_saihu_warehouse_restock.py` 已支持 `--sku=test001-white`
- 导入前检查文件内容（`openpyxl` 读 row count 和 SKU 列）

### 35. 网页自动化脚本体系
`D:\Work\赛狐\网页自动化\` 下有完整的 Playwright 脚本：

| 脚本 | 功能 | 默认模式 |
|------|------|----------|
| `sellfox_auto_export.py` | 导出库存明细（浏览器/API 双模式） | 可见，`--headless` 切换 |
| `sellfox_import_other_inbound.py` | 其他入库：生成 Excel → 导入 → 确认 → 自验证 | 可见 |
| `sellfox_import_other_outbound.py` | 其他出库：导入 → 确认 → 自验证 | 可见 |
| `sellfox_import_warehouse_restock.py` | 海外仓备货单导入 | 可见 |
| `sellfox_restock_allocate_ship.py` | 备货单分配库存+发货（独立脚本） | 可见 |
| `sellfox_import_update.py` | 商品规格更新（参考：闭环验证模式） | 可见 |

**所有脚本默认可见浏览器**，`--headless` 切换。E2E 测试不要加 `--headless`，确保能看到过程。
脚本间互相调用用 `subprocess.run()`，各自管理 Playwright 上下文（通过 `sellfox-profile/` 共享登录状态）。

### 36. E2E 测试即断言验证
CLAUDE.md 守则 4 "目标驱动执行"：改完代码就跑验证，不是打开浏览器看了算完。
- 数据生成脚本用 `assert` 验证输出列值、列名映射、行数
- 每次改完代码必须实际生成一遍 + 断言验证
- "看起来对了"不等于对了——列号偏移、后缀命名这些错误肉眼容易漏

### 37. 三成本三种输出格式
赛狐订单只能显示 2 个成本字段，三成本需压缩。三种格式应对不同场景：

| 格式 | `--fmt` | 后缀 | 采购单价 | 头程费用 | 适用 |
|------|---------|------|----------|----------|------|
| 1 | `1` | `_1三成本分开` | sx | freight+proc (赛狐算) | 旧格式兼容 |
| 2 | `2` (默认) | `_2加工并入采购` | sx+proc | freight | 当前默认 |
| 3 | `3` | `_3三成本全并入采购` | sx+freight+proc | 空 | 赛狐 Bug 兜底 |

格式 3 背景：赛狐 Amazon 订单标记发货后利润明细只有采购成本、无头程费用。三成本全灌入采购单价可保利润不偏。

### 38. 按列名查找替代硬编码列号
`openpyxl` 填充模板时，先读模板第 2 行表头建立 `{列名: 列号}` 映射，再按列名写入。
硬编码列号 = 依赖模板列顺序不变，极易出错（列号偏移、合并单元格等）。

### 39. 文件命名双重校验
文件名同时包含数字编号和中文描述：`_1三成本分开.xlsx`、`_2加工并入采购.xlsx`。
数字快速识别，中文防歧义。工业界双重校验模式。

### 40. 通途 SKU 后缀匹配记录
`get_warehouse_sku_map()` 返回后缀清理记录，问题报告新增"后缀清理匹配" sheet。
当前清理后缀：`-淘汰`(2), `-out`(9), `-Cover`(428), `-Foam`(28)。
每类后缀的含义和风险见"三系统产品定义"表。

### 41. 库存总数 = 可用数 + 占用数
赛狐库存明细中 `库存总数 = 可用数 + 占用数`（全 2390 行精确成立）。
- **可用数**：自由库存，可被其他出库扣除
- **占用数**：已被订单锁定的库存，其他出库**无法扣除**
- **计划数/在途数**：不属于物理库存（计划数=已创建未发货备货单，在途数=已发货未收货）
- 其他出库**只能用可用数清零**，用库存总数会导致"可用良品库存不足"拒绝确认

### 42. Playwright 点击按钮正确姿势
**禁止用 `page.evaluate('btn.click()')`** — JS click 绕过 loading mask 导致服务器拒绝。
正确做法：
```python
# ✅ Playwright 原生 click
btn = page.locator('button', has_text='确认出库').first
btn.wait_for(state='visible', timeout=5000)
btn.click()
# 等 loading mask 出现→消失
mask = page.locator('.el-loading-mask').first
mask.wait_for(state='attached', timeout=10000)
mask.wait_for(state='hidden', timeout=120000)
```
**加载中遮罩（`el-loading-mask`）** 出现在 VXE 表格操作后，未消失前阻止后续点击。

### 43. 批量勾选 + 一次性操作
分配库存/发货时**不要逐行操作**（每行都会触发 loading mask）。
- 先勾选全部目标行（循环点 checkbox）
- 再点一次工具栏按钮（分配库存/发货）
- 确认弹窗点一次确定
- 用 `--after HH:MM` 时间过滤避免误操作旧单

### 44. 海外仓备货单页面 tab 陷阱
`stockOrder/index.html` 默认可能停留在任意 tab（待配货/待发货/待收货）。
**"添加单据"按钮只有"全部"tab 才显示**。导入前必须：
```javascript
// 点击"全部"tab
el.querySelector('*').find(e => e.textContent.trim()==='全部').parentElement.click()
```
否则导入脚本因找不到"添加单据"按钮而失败。

### 45. 确认弹窗时序
点击"发货"后弹出 `el-message-box__wrapper`，按钮文本有 `\n` 包裹需 `.trim()`。
**确认后等待遮罩消失**，大订单（500+行）处理可能需 30-60 秒。
导入等待超时至少设 120 次 × 2s = 240s（之前 80s 导致 POLAND_p3 超时）。

### 46. Excel 生成后立即导入的陷阱
两次生成的 Excel 临时单号格式如果仅用 `datetime.now().strftime("OB%Y%m%d%H%M")`（精确到分钟），同分钟内的多次运行会产生**相同临时单号**，赛狐拒绝重复导入。
修复：`f"OB{datetime.now().strftime('%Y%m%d%H%M%S')}{batch_id}"` — 精确到秒+批次后缀。

---

## Documentation enforcement

**These are NOT guidelines. They are commit-time requirements.** Derived from the principle that stale docs are worse than no docs — the next agent session relies on them being accurate.

### When you modify a `.py` script

1. **Check** if the change affects any of these in `AGENT_HANDOFF.md`:
   - Function names, signatures, or behavior
   - Column name constants (`COL_*`)
   - Field mappings or business rules
   - CLI arguments or default paths
   - Boundary conditions or known issues
2. **If yes** → update `AGENT_HANDOFF.md` **in the same commit**.
3. **If the module's purpose or scope changed** → update the corresponding SKILL.md `description` YAML field.

### When you fix a bug caused by incorrect assumptions

Add a lesson to the "Lessons learned" section above. Format: Problem → Root cause → Fix → Rule.

### Before committing

Run this self-check:

```
[ ] .py files changed? → Are corresponding AGENT_HANDOFF.md changes in the same diff?
[ ] New pitfall discovered? → Added to Lessons learned above?
[ ] Module scope changed? → SKILL.md description updated?
```

If a `.py` change intentionally does NOT require doc updates (typo fix, reformatting), explain why in the commit message.

### Why this matters

The next agent session (whether yours, GQ's, or a colleague's via Claude Desktop) starts by reading CLAUDE.md, SKILL.md, and AGENT_HANDOFF.md. If those files are stale, the agent will make decisions based on wrong information — wasting time and introducing bugs.

---

## Skill 管理规则

### 核心原则

1. **每个模块一个 Skill**，职责单一，不堆砌
2. **SKILL.md 是入口索引**（< 300 行），只放触发条件、约束、管道概要
3. **AGENT_HANDOFF.md 放详情**（函数表、字段映射、边界条件、踩坑），按需加载
4. **description 是触发命中的关键** — 必须包含用户真正会说的自然语言
5. **所有 skill 文件纳入 git**，可回滚、可协作

### description 编写规则

- 包含用户真正会说出口的词：模块名、动词、数据源名
- 中英文都要覆盖（如 "库存初始值"+"stock_init"+"通途库存"）
- 用自然语言短语而非关键词堆砌
- 明确 NOT 情况：什么情况下**不要**触发此 skill（如 "不要用于采购成本导入"）

### 触发词覆盖规则

description 中必须覆盖以下类型的触发词：

| 类型 | 示例 |
|------|------|
| 模块名中英文 | stock_init/库存初始值、item_cost/采购成本、multi_attr/多属性 |
| 核心动词 | 导入/导出/计算/匹配/生成/校验/配对 |
| 数据源名 | 通途库存/EN BOM/重量模板/物料属性/分类导出 |
| 用户习惯说法 | 库存初始化/成本借用/属性炸开/四级分类/通途配对 |

### 编写原则

| 原则 | 说明 |
|------|------|
| **SKILL.md < 300 行** | 只保留触发条件、约束、管道概要、输出文件 |
| **AGENT_HANDOFF.md 放细节** | 函数表、字段映射、CLI 参数、边界条件、踩坑记录 |
| **去重** | SKILL.md 不重复 CLAUDE.md 内容，不重复 AGENT_HANDOFF.md 内容，用引用代替 |
| **发现即更新** | 每次脚本修改或新发现边界条件，立即更新 AGENT_HANDOFF.md，不积累记忆负担 |

### 运行规则

- **永远用 `uv run python`** 或 `python`（uv 管理的 venv）
- **永远用 `uv add <包名>` 加依赖**，自动写入 `pyproject.toml`
- 每个脚本从模块目录运行：`cd <module_dir> && python <script>.py`

---

## Module docs location

Each module has `README.md` (human) + `AGENT_HANDOFF.md` (agent). Read both before modifying code. SKILL.md in `.claude/skills/<name>/` is the agent entry point and references AGENT_HANDOFF.md for details. Never duplicate content between SKILL.md and AGENT_HANDOFF.md — SKILL.md links to AGENT_HANDOFF.md, not copies from it.
