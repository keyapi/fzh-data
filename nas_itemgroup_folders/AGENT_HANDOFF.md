# NAS-ERPNext 文件夹对账 — Agent 交接文档

> 最后更新: 2026-06-12 | 分支: `feature/nas-itemgroup-folders`

## 背景

视觉部负责人 LM 需要在 Synology NAS 上按 ERPNext 产品物料组（Item Group）创建文件夹结构。每个产品物料组建一个文件夹（`{custom_model_id}_{name}`），内含 4 个标准子文件夹：调研报告、设计稿、图片、视频。之后 LM 会手动将设计师产出的文件整理进去。

数据源: ERPNext 生产环境 (`https://erpnext.vilavi.cn`) Item Group "产品" 子树的叶子节点。
目标: NAS `/产品信息/` 共享文件夹。

## 架构

```
nas_itemgroup_folders/
  reconcile.py               # 对账引擎（纯逻辑）
  build_nas_folders.py        # CLI + 编排 + NAS 操作
  verify_tree_structure.py    # 树结构预览工具
  README.md                   # 用户文档
  AGENT_HANDOFF.md            # 本文件
  .env                        # 任务配置 (NAS_TARGET_FOLDER, ERP_API_*)
  out/                        # JSON 报告 + last_snapshot.json
```

NAS API 共享模块: `NAS_API/synology.py` — 封装 `synology-api` (PyPI: N4S4/synology-api) FileStation 类。凭证在 `NAS_API/.env`。

## 核心概念

### 对账矩阵 (reconcile.py)

每次运行从头对比 ERPNext vs NAS，按 KS 编码（`custom_model_id`，如 `KS0001`）关联两边：

| 状态 | 说明 | 操作 |
|------|------|------|
| MATCH | 名称 + 路径都一致 | 无事，检查子文件夹完整性 |
| MISSING | ERPNext 有，NAS 无 | 自动创建 + 标准子文件夹 |
| NAME_MISMATCH | 同 KS 码，名称不同 | 空→自动重命名；有内容→BLOCKED |
| STRUC_MISMATCH | 同 KS 码，路径不同 | 空→自动 MOVE；有内容→MOVE_APPROVAL |
| EXTRA | NAS 有 (KS格式)，ERPNext 无 | 空→报告可删；有内容→BLOCKED |
| IGNORE | NAS 有 (非 KS 格式) | 不碰 |

### 布局模式

- **flat**: `/产品信息/KS0001_三角靠枕/`
- **tree**: `/产品信息/床品类/床头靠枕/三角靠枕类/KS0001_三角靠枕/`（按 ERPNext 祖先链）

### 关键边界条件

- 有内容的文件夹（递归文件数 > 0）绝不自动删除/重命名/移动
- 空文件夹自动操作（CREATE/RENAME/MOVE）
- MOVE_APPROVAL 需用户确认后执行 CopyMove
- 子文件夹（调研报告等）缺失自动补建，多余不碰
- NAS `#recycle` 回收站：有内容→进，空文件夹→不进
- `start_copy_move` 返回 task ID 字符串（不是 dict），异步执行
- `SYNO.FileStation.CreateFolder` 的 `force_parent=True` 可自动创建中间路径

## 使用

```bash
cd nas_itemgroup_folders
uv run python build_nas_folders.py              # 测试模式 (KS0001, KS0002)
uv run python build_nas_folders.py --full       # 全量 404 个
uv run python build_nas_folders.py --dry-run    # 仅对比，不操作
uv run python build_nas_folders.py --layout tree   # 树状布局
uv run python build_nas_folders.py --layout flat   # 扁平布局
```

## 环境变量

| 变量 | 所在文件 | 说明 |
|------|---------|------|
| `NAS_URL/USERNAME/PASSWORD` | `NAS_API/.env` | NAS 凭证 |
| `NAS_TARGET_FOLDER` | `nas_itemgroup_folders/.env` | 目标路径，默认 `/产品信息` |
| `ERP_URL/API_KEY/API_SECRET` | `nas_itemgroup_folders/.env` | ERPNext 凭证 |
| `ITEM_GROUP_ROOT` | `nas_itemgroup_folders/.env` | 根节点，默认 `产品` |
| `SUB_FOLDERS` | `nas_itemgroup_folders/.env` | 标准子文件夹，逗号分隔 |

## 经验教训

### 1. Windows GBK 终端编码 — 最高优先级

Windows 终端默认 `chcp 936` (GBK)，Python stdout 输出中文全部乱码。**所有脚本必须加**:
```python
sys.stdout.reconfigure(encoding="utf-8")
```
`~/.bashrc` 已设 `export PYTHONIOENCODING=utf-8`。项目 `warehouse_restock/` 早已有此先例。

### 2. synology-api 库的 `start_copy_move` 返回值

返回 **task ID 字符串**（`"FileStation_1781234..."`），不是 `{success: True}` dict。判断成功用 `isinstance(resp, str) and "FileStation_" in resp`。

### 3. 孤儿文件夹检测

树布局下，改中间父节点名会导致 NAS 残留空壳中间文件夹。检测方法：递归扫描 NAS 树 → 过滤掉 KS 格式文件夹、标准子文件夹、ERPNext 有效中间节点名 → 余下为疑似孤儿。

**核心原则**: 只报告，绝不自动删除非 KS 格式的文件夹。

### 4. NAS 会话管理

synology-api 的 FileStation 实例持有 SID。多个脚本先后跑会互相抢占会话，导致 `Invalid session / SID not found`。每个独立 Python 进程应创建自己的 FileStation 实例。

### 5. 终端输出可靠性

涉及中文文件夹名时，不要依赖终端输出判断。写 JSON 文件到磁盘用 Read 工具验证。

## 下一步

- [ ] 全量执行 `--full` 创建 404 个叶子节点（需老板确认）
- [ ] 孤儿检测集成到报告（目前 `_fix_now.py` 临时实现，已删除）
- [ ] 树布局下 `scan_nas` 的 `床品类` 被标为 IGNORE——非 KS 格式的中间节点应单独归类
- [ ] `dam-prototype/main.py` 仍内嵌旧的 `SynologyNAS` 类，应迁移到 `from NAS_API.synology import SynologyNAS`
