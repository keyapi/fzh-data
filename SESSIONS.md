# 开发过程记录

> 每个重要 session 结束时追加一段，记录做了什么、做了什么决定、下一步。
> 新 session 的 Agent 读此文件即可接上。

---

## 2026-05-20 — 文档体系整合 + Skills 引入

**做了什么：**
- 引入 `.claude/skills/` 体系，5 个模块各一个 SKILL.md（YAML frontmatter + 触发词 + 约束 + 参考链接）
- CLAUDE.md 从 289 行精简到 151 行，模块列表改为 Skill 索引表
- 根分支 master → main，远程同步，删除远程 master
- 创建 GitHub repo `keyapi/fzh-data`，添加 GQ (`Jack-wq-ops`) 为 collaborator
- SSH key 配置完成（`~/.ssh/id_ed25519_github`）
- README.md 补齐 stock_init 模块，更新架构图，统一数据目录约定
- `.gitignore` 改为仅忽略 `.claude/worktrees/` + `settings.local.json`，skills/ 纳入版本

**决定：**
- SKILL.md 作为 Agent 触发入口，不复制 AGENT_HANDOFF.md 内容，只引用
- AGENT_HANDOFF.md 保留在模块目录，作为 Agent 的唯一详细参考
- 模块 README.md（给人看）+ AGENT_HANDOFF.md（Agent 字典）+ SKILL.md（Agent 入口）三层，各司其职
- 用 SESSIONS.md（本文件）记录开发过程，解决上下文丢失问题

**修改文件：** CLAUDE.md, README.md, .gitignore, 新增 `.claude/skills/*/SKILL.md`（5个）

**下一步：** 等 GQ 用 Claude Desktop 试用验证

---

## 2026-05-15 — stock_init 递增导入 + 差异报告

**做了什么：**
- 输出目录改为 `out/{时间戳}/` 子目录隔离
- 新增与上次导入文件对比的差异逻辑（`--compare-to` CLI 参数）
- 生成多 sheet 差异报告 xlsx（汇总、新增条目、成本变更、数量变更、条目消失）
- 输出仅含新增条目的模板格式导入文件（`新增条目_导入_{stamp}.xlsx`）
- 赛狐三次导入实测验证：A→成功(2085条)，B新增→成功(195条)，B中已存在行→失败（符合预期）
- CLAUDE.md 新增 Lesson #17(共享库存)、#18(成本借用)、#19(输出拆分)、#20(Git worktree)

**决定：** 锚点递增模式——对比 `out/上次导入_基准.xlsx`，只导入新增条目

---

## 2026-05-14 — stock_init 模块创建 + 成本借用实现

**做了什么：**
- 创建 `stock_init/build_saihu_stock_init.py`（683行），完整管道：
  通途库存(6仓) + EN BOM成本 → 仓库映射(→3赛狐仓) → 成本借用 → SKU白名单过滤 → 输出
- 实现成本借用策略：同比重模板键（前3段SKU）列内 0→非零，纯列内操作
- 实现 `_write_issues()` 多 sheet 问题报告
- 赛狐导入实测：成本=0 静默跳过，库存=0 可以导入
- 赛狐客服确认：共享库存只需仓库+SKU即可成本补录

**决定：**
- 开局和日常入库一律用共享库存（店铺/FNSKU 留空）
- 生成两个文件：导入用（成本>0）+ 参考用（全量）

---

## 2026-05-13 及更早 — 基础设施

**做了什么：**
- openpyxl Data Validation 破坏问题：定位到 load_workbook+save 会丢弃扩展
  修复：全模块改用 shutil.copy + pd.ExcelWriter(mode='a') 或纯 ExcelWriter
- item_weight_size 模块：重尺数据匹配、多 sheet 问题报告格式确立
- item_cost_sx 模块：BOM成本→采购成本，同前缀借用
- category 模块：分类树校验、CategoryIndex
- multi_attr_saihu 模块：3脚本流水线（炸开→转换→配对）
- CLAUDE.md 建立：Karpathy 守则 + 22 条踩坑记录 + Git workflow
- uv 环境、Windows 中文路径编码、Excel 锁定等坑已记录

**决定：**
- 问题报告统一为多 sheet xlsx 格式（汇总 + N 明细 + 每仓统计）
- 模块独立，os.chdir() 模式，各自 README + AGENT_HANDOFF
- Commit 中文消息，format: `type(scope): description`
