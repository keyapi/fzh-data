# NAS-ERPNext 文件夹对账 — Agent 交接文档

> 最后更新: 2026-06-15 | 分支: `feature/nas-itemgroup-folders` | 状态: Phase 6 完成，12 叶子组已部署到 NAS

## 背景

视觉部负责人 LM 需要在 Synology NAS `/产品信息/` 下，按 ERPNext 生产环境 Item Group "产品" 子树的叶子节点创建文件夹。每个物料组建一个 `{custom_model_id}_{name}` 文件夹，内含 4 个标准子文件夹（调研报告/设计稿/图片/视频）。之后 LM 会手动将设计师产出整理进去。

## 阶段性目标 & 完成情况

### Phase 1: 基础设施 (✅ 完成)
- [x] `NAS_API/synology.py` — 共享 Synology API 模块 (基于 N4S4/synology-api 库)
- [x] `nas_itemgroup_folders/build_nas_folders.py` — 初始批量建文件夹脚本
- [x] `nas_itemgroup_folders/.env` — 任务配置

### Phase 2: 对账引擎 (✅ 完成)
- [x] `reconcile.py` — 核心对账引擎: ErpnextItem/NasFolder/Action 数据模型
- [x] `compare()` — 按 KS 编码比对，6 种状态分类
- [x] `scan_erpnext()` / `scan_nas()` — 双端扫描器
- [x] `detect_orphans()` — 孤儿中间文件夹检测
- [x] `safe_name()` / `expected_path()` / `parse_model_id()` — 工具函数

### Phase 3: 集成测试 (✅ 完成)
- [x] flat ↔ tree 布局切换（空文件夹自动搬迁）
- [x] 内容感知: 有文件→MOVE_APPROVAL，空→自动 MOVE
- [x] 改名检测: NAME_MISMATCH / STRUC_MISMATCH
- [x] 孤儿检测: 布局切换后残留空中间文件夹自动清理
- [x] 终端 GBK 编码根治
- [x] 15 个自动化鲁棒性测试全部通过

### Phase 4: 全量创建 (✅ 完成)
- [x] 全量 `--full` 创建 404 个叶子节点（flat 布局）
- [ ] `dam-prototype/main.py` 旧 SynologyNAS 类迁移到 NAS_API

### Phase 5: 文件夹扫描与变更追踪 (✅ 完成)

**背景**: LM 和同事需要了解 `/产品信息` 下哪些文件夹已有文件、哪些为空，
并在同事陆续放入设计师产出后追踪进度。

**需求**:
1. 扫描 `/产品信息` 下所有文件夹，统计每个文件夹的文件数和大小
2. 保存快照，支持后续对比
3. 同事放文件后，重新扫描能自动显示变更

**实现**: `scan_product_folders.py`
- 纯 NAS 只读操作，不依赖 ERPNext
- 复用 `NAS_API/synology.py` 的 `get_nas()` 和 reconcile 的 `parse_model_id()`
- 递归扫描每个文件夹及其子文件夹（4 层：叶子 → 调研报告/设计稿/图片/视频）
- 输出终端表格：有文件的排前面，空文件夹折叠展示
- JSON 快照保存到 `out/scan_{timestamp}.json`
- 自动对比上次快照，显示新增/移除文件夹、文件数增减

**使用**:
```bash
uv run python nas_itemgroup_folders/scan_product_folders.py
```

**执行时间**: ~5 分钟（404 文件夹 × 5 层 API 调用）

### Phase 6: 叶子组支持 (✅ 完成)

**背景**: ERPNext 新增 12 个"叶子组" Item Group——`is_group=1` + `is_leaf_group=1`（自定义字段），
`custom_model_id` 为 `LGKSxxxx` 格式。它们是 KS 子物料组的品类容器，需要在 NAS 上也有对应文件夹，
且 KS 子文件夹应嵌套在叶子组下。

**需求**:
1. 在 NAS `/产品信息/` 下创建 12 个 `LGKSxxxx_名称` 文件夹，每含 4 个标准子文件夹
2. 将 52 个 KS 子文件夹从根目录移入对应叶子组
3. 有内容的文件夹不自动移动（MOVE_APPROVAL），防止丢失设计师文件

**实现**: `leaf_group_ops.py` + reconcile 引擎扩展

**reconcile.py 改动**:
- `ErpnextItem` 新增 `is_leaf_group` / `leaf_group_model_id` 字段
- `scan_erpnext()` 收集 `is_leaf_group=1` 节点，为 KS 子节点标记所属叶子组
- `expected_path()` 支持 `leaf_group_folder_name` 参数，生成嵌套路径
- `compare()` 构建叶子组查找表，自动生成 MOVE/MOVE_APPROVAL

**leaf_group_ops.py — 精准手术刀**:
- 直接操作 NAS API，不扫全盘（秒级 vs 全量对账 5 分钟）
- 支持单个/全部操作：`status` / `create` / `move` / `verify` / `setup`

**使用**:
```bash
uv run python nas_itemgroup_folders/leaf_group_ops.py status          # 查看全部状态
uv run python nas_itemgroup_folders/leaf_group_ops.py setup LGKS0220  # 单个
uv run python nas_itemgroup_folders/leaf_group_ops.py setup --all     # 全部12个
uv run python nas_itemgroup_folders/leaf_group_ops.py verify LGKS0459 # 验证某个
```

**NAS 部署结果**: 12 叶子组 / 48 标准子文件夹 / 52 KS 子文件夹已移入，全部验证通过。

## 架构

```
NAS_API/                         ← 共享 NAS 模块
  synology.py                    ← Synology FileStation 封装 (基于 synology-api 库)
  .env                           ← NAS 凭证

nas_itemgroup_folders/
  reconcile.py                   ← 对账引擎 (纯逻辑 + Scanner)
  build_nas_folders.py            ← CLI + NAS 操作编排 + 报告 (全量)
  scan_product_folders.py         ← 文件夹扫描 + 快照对比 + 变更追踪
  leaf_group_ops.py               ← 叶子组精准操作 (秒级, 不扫全盘)
  verify_tree_structure.py        ← 树结构预览
  test_robustness.py              ← 15 场景鲁棒性测试
  README.md                       ← 用户文档
  AGENT_HANDOFF.md                ← 本文件
  .env                            ← NAS_TARGET_FOLDER, ERP_API_*, SUB_FOLDERS
  out/                            ← JSON 报告 + snapshots + scan_*.json
```

## 关键概念

### 对账矩阵 (reconcile.py)

每次运行从头发起对比，按 KS 编码（`custom_model_id`）关联：

| 状态 | 说明 | 操作 |
|------|------|------|
| MATCH | 名称 + 路径都一致 | 检查子文件夹完整性 |
| MISSING | ERPNext 有，NAS 无 | 自动创建 + 标准子文件夹 |
| NAME_MISMATCH | 同 KS 码，名称不同 | 空→RENAME; 有内容→BLOCKED |
| STRUC_MISMATCH | 同 KS 码，路径不同 | 空→MOVE; 有内容→MOVE_APPROVAL |
| EXTRA | NAS 有 (KS格式)，ERPNext 无 | 空→DELETE_EMPTY; 有内容→BLOCKED |
| IGNORE | NAS 有 (非 KS 格式) | 不碰 |

**唯一抓手: KS 编码** (`parse_model_id` 匹配 `^[A-Z]{2}\d{4}_` 模式)。
一旦文件夹名丢失 KS 前缀，引擎无法匹配，归入 IGNORE。

### 布局模式

- **flat**: `/产品信息/KS0001_三角靠枕/`
- **tree**: `/产品信息/床品类/床头靠枕/三角靠枕类/KS0001_三角靠枕/`
- 切换时空文件夹自动 CopyMove，有内容需确认 (MOVE_APPROVAL)

### 孤儿检测

布局切换后，空的中间文件夹（如 tree→flat 残留的 床品类/床头靠枕/...）自动检测并清理。
仅针对 ERPNext 有效名称集合内的空文件夹做清理；未知文件夹、有内容文件夹跳过。

## 使用

```bash
cd nas_itemgroup_folders

# 全量对账 (5 分钟)
uv run python build_nas_folders.py              # 测试模式 (KS0001, KS0002)
uv run python build_nas_folders.py --full       # 全量
uv run python build_nas_folders.py --dry-run    # 仅对比

# 文件夹扫描 + 变更追踪 (5 分钟)
uv run python scan_product_folders.py

# 叶子组精准操作 (秒级)
uv run python leaf_group_ops.py status          # 查看12个状态
uv run python leaf_group_ops.py setup LGKS0220  # 创建+移动 单个
uv run python leaf_group_ops.py setup --all     # 全部

# 测试
uv run python test_robustness.py                # 全部鲁棒性测试
```

## 经验教训

### 1. Windows GBK 终端编码 (⚠️ 最高优先级)

**症状**: Python stdout 中文全部乱码，导致读取 NAS 文件夹名时做出错误判断。

**根因**: Windows 终端 `chcp 936` (GBK)，Python 不设 `PYTHONIOENCODING` 时继承 GBK。

**修复 (三层防护)**:
```python
# ① 脚本层面 — 每个脚本头部
sys.stdout.reconfigure(encoding="utf-8")

# ② Shell 层面 — ~/.bashrc
export PYTHONIOENCODING=utf-8

# ③ 子进程层面 — subprocess.run 参数
encoding="utf-8", errors="replace"
```

**已有先例**: 项目 `warehouse_restock/` 的 `run_full_restock_flow.py` 和 `test_e2e_flow.py` 早已在子进程调用中设置 `PYTHONIOENCODING=utf-8`。

### 2. synology-api 库的 API 差异

| API | 返回值类型 | 判断成功 |
|-----|-----------|---------|
| `get_file_list()` | `{success: True, data: {files: [...]}}` | `resp.get("success")` |
| `create_folder()` | `{success: True/False}` | `resp.get("success")` |
| `start_copy_move()` | **task ID 字符串** `"FileStation_17812..."` | `isinstance(resp, str) and "FileStation_" in resp` |
| `upload_file()` | `{success: True}` | `resp.get("success")` |
| `rename_folder()` | `{success: True/False}` | `resp.get("success")` |
| `delete_blocking_function()` | void (抛异常表示失败) | try/except |

最坑的是 `start_copy_move` — 返回字符串而非 dict，导致早期 `resp.get("success")` 永远失败。

### 3. NAS `#recycle` 回收站行为

- **有内容的文件夹** → 删除后进回收站，可恢复
- **空文件夹** → 删除后不进回收站，永久丢失
- `#recycle` 目录 FileStation API 返回 407 (需 DSM 网页端管理)

**对引擎的影响**: 空文件夹的 CREATE/RENAME/MOVE/DELETE 无数据损失风险。
有内容的操作必须 BLOCKED 或需确认。

### 4. 孤儿检测设计演进

**初版 (危险)**: 把所有不在 ERPNext 名称集合里的文件夹当孤儿 → 删了 LM 的手动文件夹。

**修正版 (安全)**:
1. 仅在布局切换 (tree↔flat) 后触发
2. 只清理 ERPNext 有效名称集合内 + 空的文件夹
3. 有内容的文件夹 → 只报告不删除
4. 非 KS 格式、非有效名称的 → 跳过 (手动文件夹保护)

### 5. 鲁棒性测试设计要点

- 每个测试独立: setup → mutate → reconcile → verify → restore
- 通过子进程调用 `build_nas_folders.py` 获得真实对账输出
- 解析子进程 stdout 提取状态计数（MATCH/CREATE/MOVE/...）
- **执行操作的 run 输出操作结果，需再跑 `--dry-run` 验证最终 MATCH 状态**

### 6. 全量对账 vs 精准操作 (⚠️ 性能认知)

**症状**: 用 `build_nas_folders.py --full` 做单叶子组测试，等了 22 分钟才被用户打断。

**根因**: 全量对账每次扫描 NAS 全部 404 个文件夹（递归 5 层 × 每层 API 调用），即使只需要操作 1 个叶子组。用户说"哪怕亲自去看 NAS 都不会这么慢"——完全正确。

**修正**: `leaf_group_ops.py` 只发 1 + 4 + N 次 API（创建 1 + 子文件夹 4 + 移动 N 个子节点），秒级完成。**操作范围决定工具选择：**
- 全量创建/对账 → `build_nas_folders.py` (5 分钟)
- 精准操作几个文件夹 → `leaf_group_ops.py` (秒级)
- 查看状态 → `leaf_group_ops.py status` (秒级)

### 7. `get_nas()` vs 直接 `FileStation()` — 端口解析 (⚠️)

**症状**: 手动 `FileStation(ip_address=host, port=5001)` 连接被拒。

**根因**: NAS_URL 是 `https://fzh.myds.me:11024`（自定义端口），直接构造 `FileStation` 时没有解析端口，用了默认 5001。`get_nas()` 工厂函数调用了 `_parse_nas_url()` 正确提取端口 11024。

**教训**: 永远用 `get_nas()` 或 `_parse_nas_url()`，不要手动构造 `FileStation`。

### 8. ERPNext 结构会变 — 以最新读取为准

**症状**: 第一次读 ERPNext 时 LGKS0496 嵌套在 LGKS0459 下；用户在对话中途更新了生产数据，重读后变为并列。用户引用旧结构要求验证，引发混淆。

**教训**: 每次操作前重新读取 ERPNext 确认结构。不要假设对话中前一次读取仍然有效。结构变更记录应写入对话上下文。

### 9. `parse_model_id` 对 LGKS 格式的兼容

**症状**: `LGKS0220` 是 4 字母 + 4 数字，不匹配 `^[A-Z]{2}\d{4}_` 正则。

**修正**: 已有的 fallback 机制——`parse_model_id` 接受可选的 `valid_model_ids` 集合，按 `_` 拆分取前缀查集合。只要 `scan_erpnext()` 把 LGKS model_id 加入 `valid_model_ids`，识别就自动生效。无需改正则。

## 环境变量

| 变量 | 所在文件 | 说明 |
|------|---------|------|
| `NAS_URL/USERNAME/PASSWORD` | `NAS_API/.env` | NAS 凭证 |
| `NAS_TARGET_FOLDER` | `nas_itemgroup_folders/.env` | 默认 `/产品信息` |
| `ERP_URL/API_KEY/API_SECRET` | `nas_itemgroup_folders/.env` | ERPNext 凭证 |
| `ITEM_GROUP_ROOT` | `nas_itemgroup_folders/.env` | 默认 `产品` |
| `SUB_FOLDERS` | `nas_itemgroup_folders/.env` | 逗号分隔，默认 `调研报告,设计稿,图片,视频` |

### 10. 新建叶子组的完整 checklist（2026-06-16 踩坑）

**症状**: Agent 创建叶子组时漏设 `is_leaf_group=1`、`custom_model_id=LGKSxxxx`，用错字段（写了 `custom_item_group_code` 而非 `custom_model_id`），以及不知道 LGKS 编号来源。

**根因**: AGENTS.md 模块索引未收录 `nas_itemgroup_folders` 模块，Agent 找不到叶子组文档。`docs/company-context.md` 也未记录叶子组约定。

**新建叶子组 checklist（必须全做）**:

| # | 字段 | 值 | 说明 |
|---|------|-----|------|
| 1 | `item_group_name` | `品类-子类` | 如 `户外托盘垫-云朵款` |
| 2 | `parent_item_group` | 所属父组 | 如 `户外托盘垫类` |
| 3 | `is_group` | `1` | 它是分组节点 |
| 4 | `is_leaf_group` | `1` | 它是叶子（自定义字段） |
| 5 | `custom_model_id` | `LGKSxxxx` | xxxx = 子节点中最小的 KS 编号 |

**LGKS 编号来源**: 查叶子组下的 KS 子节点（如 KS0493, KS0494），取最小值（0493），叶子组即为 `LGKS0493`。不是随便写的。

**环境差异**:
- **测试系统** (`ensh.vilavi.cn`): 有 FAC MCP，用 `mcp__fac__create_document` / `mcp__fac__update_document`
- **生产系统** (`erpnext.vilavi.cn`): 无 FAC MCP，用裸 REST API（`EN_API/` 的 `ErpnextClient`）

**同步顺序**: 测试系统 → 确认 → 生产系统 → NAS（`leaf_group_ops.py setup LGKSxxxx`）

**文档修复**: AGENTS.md 加入 `nas-itemgroup-folders` 索引 + 关键规则 #7；`docs/company-context.md` 加入叶子组约定。

## Git 提交历史

```
c27371f test(nas): 15-case robustness test suite
762fcc7 feat(nas): orphan detection with layout-aware auto-cleanup
4266184 docs(nas): comprehensive AGENT_HANDOFF with lessons learned
2e60f76 fix(nas): force UTF-8 stdout to prevent Windows GBK terminal garbling
e50f525 fix(nas): handle start_copy_move string return value
1ad639a fix(nas): recursive tree scan for KS folders at any depth
dfb829b fix(nas): create intermediate parent folders before MOVE
df6824f fix(nas): ancestor root stripping for tree layout
a0ba018 feat(nas): rewrite build script as ReconciliationRunner
feb9c47 feat(nas): reconcile ErpnextScanner + NasScanner
1e8f227 feat(nas): reconcile compare() engine with self-tests
376417c feat(nas): reconcile KS code parser + path calculator
1ada379 fix(nas): clean reconcile data models
ef4cbc4 feat(nas): reconcile data models
```
