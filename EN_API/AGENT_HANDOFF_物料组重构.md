# AGENT_HANDOFF: EN 系统物料组重构完整记录

> 最后更新: 2026-06-11 10:50
> 执行人: Claude Code (worktree: nervous-boyd-8412bf)

---

## 一、项目概述

### 目标
按赛狐商品分类(`Commodities2026_06_09(1).xlsx`)重构 EN 系统物料组(Item Group)树结构。将产品按 SPU→赛狐分类路径映射到正确的物料组节点下。

### 环境

| 环境 | URL | 凭证变量 |
|------|-----|---------|
| **生产系统(prod)** | https://erpnext.vilavi.cn | `PROD_ERP_API_KEY` / `PROD_ERP_API_SECRET` |
| **测试系统(test)** | https://ensh.vilavi.cn | `TEST_ERP_API_KEY` / `TEST_ERP_API_SECRET` |

### 项目路径
```
D:\Claude Demo\fzh-data\EN_API\
```

---

## 二、执行过程 & 时间线

### 第 1 轮: 初始执行 (2026-06-10 15:30~16:38)

| 步骤 | 结果 | 问题 |
|------|------|------|
| Dry-run 预览 | ✅ **5 节点创建, 256 产品移动** | - |
| 第1次正式执行 | ❌ 中断 | `tee` 输出缓冲, 看不到日志 |
| 第2次执行 | ❌ 中断 | nginx 417 + Server Script 500 |

**遇到的问题与解决**:

| # | 问题 | 根因 | 解决 |
|---|------|------|------|
| 1 | tee 缓冲导致日志为空 | Python stdout 全缓冲 | `PYTHONUNBUFFERED=1` |
| 2 | POST 500 创建物料组失败 | Server Script `物料组_款式id_格式控制` 校验 `custom_model_id` | 用户禁用该脚本 |
| 3 | nginx 417 Expectation Failed | urllib3 添加 `Expect: 100-continue`, nginx/1.18 不支持 | 修复 `_NoExpectAdapter.send()` |
| 4 | 部分节点创建后不存在 | 417 重试逻辑问题 | 手动补创建 |

### 第 2 轮: 数据恢复 + 逻辑对齐 (2026-06-10 17:00~17:45)

| 步骤 | 结果 |
|------|------|
| 从备份恢复生产系统 | ✅ 256 个产品还原, 5 个新节点删除 |
| 修复脚本逻辑(叶子跳过 + 重路由) | ✅ 对齐测试脚本 |
| 正式执行 | ✅ 20 节点创建 + 271 产品移动成功 |

### 第 3 轮: 叶子节点保护 + 三角靠枕修复 (2026-06-11 09:00~10:20)

| 步骤 | 结果 |
|------|------|
| NSM tree 导致 browser 不显示 | ✅ `rebuild_tree` 修复 |
| 三角靠枕被误转为组(is_group=1) | ✅ `fix_leaf_node.py --name 三角靠枕` |
| 创建 Commodities 重构版 | ✅ 三角靠枕→三角靠枕类 |
| 脚本添加 `--env` 参数 | ✅ `--env test\|prod` |
| 叶子节点检测逻辑 | ✅ `analyze()` + `build_moves()` 双重保护 |

### 第 4 轮: 平条靠枕修复 + 通用化 + 全量对比 (2026-06-11 10:20~11:00)

| 步骤 | 结果 |
|------|------|
| 平条靠枕被误转为组(is_group=1) | ✅ `fix_leaf_node.py --name 平条靠枕` |
| 测试系统修复 | ✅ 子节点 2/2, 产品 149/149, is_group=0 |
| 生产系统修复 | ✅ 子节点 2/2, 产品 180/180, is_group=0 |
| Commodities 更新 | ✅ 添加 平条靠枕→平条靠枕类 映射 |
| `fix_leaf_node.py` 通用化 | ✅ `--name` 参数, 支持任意叶子节点 |
| **备份 vs 当前全量对比** | **✅ 仅 2 个叶子节点差异, 已全部修复** |

### 备份对比结论

重构前备份(`20260610_163718.json`, 3624条)与当前系统对比:

| 对比项 | 结果 |
|--------|------|
| 24 个赛狐节点中原叶子节点 | **2 个**: 三角靠枕、平条靠枕 |
| 已被修复(is_group=0, 在XXX类下) | ✅ 全部完成 |
| 其他 22 个节点 | 无差异(新创建或原是组) |

---

## 三、当前系统状态

### 生产系统 (erpnext.vilavi.cn)
- 总物料组数: **3,646**
- 赛狐分类节点: **24 全部存在且位置正确**
- 已移动产品: **271 个**
- 未匹配产品: **3,252 个**(无 SPU 映射, 留在原位)
- **三角靠枕**: `is_group=0`, parent=三角靠枕类 ✅
- **平条靠枕**: `is_group=0`, parent=平条靠枕类 ✅

### 测试系统 (ensh.vilavi.cn)
- 总物料组数: **1,643**
- 赛狐分类节点: **24 全部存在且位置正确**
- **三角靠枕**: `is_group=0`, parent=三角靠枕类 ✅
- **平条靠枕**: `is_group=0`, parent=平条靠枕类 ✅

---

## 四、脚本说明

### 关键脚本

| 脚本 | 用途 | 使用方式 |
|------|------|---------|
| `restructure_prod_full.py` | **主重构脚本** | `python restructure_prod_full.py --env prod\|test [--dry-run] [--skip-backup]` |
| `fix_leaf_node.py` | **通用叶子节点修复** | `python fix_leaf_node.py --name 三角靠枕 --env test [--dry-run]` |
| `restore_prod.py` | 从备份恢复生产系统 | `python restore_prod.py [--dry-run]` |
| `prepare_commodities.py` | 创建 Commodities 重构版 | `python prepare_commodities.py` |

### 主重构脚本 (`restructure_prod_full.py`) 关键逻辑

#### 叶子节点保护机制(双重检测)

1. **`analyze()` 检测目标节点** — 对每个赛狐分类节点:
   - 若在 EN 中已存在且 `is_group=0`(叶子): → `leaf_warning` 列表, **不创建/修改**
   - 若不存在: → `to_create` 列表

2. **`build_moves()` 检测源节点** — 对每个要移动的 EN 产品:
   - 若 `is_group=0`(叶子): → `leaf_skipped` 列表, **不移动**, 输出警告
   - 若 `is_group=1`(组): 正常移动

3. **用户确认后才处理**: 脚本检测到叶子后输出如下警告:
   ```
   ⚠ 其中 1 个是叶子节点(is_group=0)，已跳过（需用户确认）：
       三角靠枕: 床头靠枕 -> 三角靠枕类
   ```
   然后用 `fix_leaf_node.py` 手动修复。

#### 叶子节点修复流程 (新增叶子时)
```bash
# 1. 修改 prepare_commodities.py 的 REPLACE_MAP
# 2. 重新生成 Commodities 数据
python prepare_commodities.py

# 3. 修复叶子节点(先测试)
python fix_leaf_node.py --name 平条靠枕 --env test --dry-run
python fix_leaf_node.py --name 平条靠枕 --env test

# 4. 再修复生产
python fix_leaf_node.py --name 平条靠枕 --env prod

# 5. 验证
python restructure_prod_full.py --env test --dry-run --skip-backup
python restructure_prod_full.py --env prod --dry-run --skip-backup
```

#### 数据源指定
- 优先使用 `数据源/Commodities*重构版.xlsx`（路径修正版）
- 回退到最新的 `Commodities*.xlsx`
- 重构版通过 `prepare_commodities.py` 生成

#### `--env` 参数
- `--env prod`: 生产系统 (erpnext.vilavi.cn, PROD_ERP_API_*)
- `--env test`: 测试系统 (ensh.vilavi.cn, TEST_ERP_API_*)

---

## 五、叶子节点处理原则

### 核心规则
**叶子节点不可随意处理**。脚本检测到 `is_group=0` 的节点会自动跳过并警告。

### 已处理的叶子节点

| 叶子节点 | 对应组节点 | 子节点数 | 产品数 | 状态 |
|---------|-----------|---------|-------|------|
| 三角靠枕 | 三角靠枕类 | 6 | 100 | ✅ 已修复 |
| 平条靠枕 | 平条靠枕类 | 2 | 180 | ✅ 已修复 |

### 如何添加新的叶子节点修复
1. 你确认后, 在 `prepare_commodities.py` 的 `REPLACE_MAP` 添加映射
2. 运行 `python prepare_commodities.py` 重新生成数据
3. 运行 `fix_leaf_node.py --name XXX --env test` 测试
4. 运行 `fix_leaf_node.py --name XXX --env prod` 生产
5. 运行重构验证

---

## 六、数据文件

### 数据源
| 文件 | 说明 |
|------|------|
| `数据源/Commodities2026_06_09(1).xlsx` | 原始赛狐商品数据 |
| `数据源/Commodities2026_06_09_重构版.xlsx` | 重构版(含路径修正) |

### 备份文件
| 文件 | 时间 | 说明 |
|------|------|------|
| `out/生产系统备份_全量_20260611_090452.json` | 06-11 09:04 | ⭐ 最新备份 |

### 报告文件
| 文件 | 说明 |
|------|------|
| `out/物料组重构预览_20260611_104604.xlsx` | ⭐ 最新验证报告 |

---

## 七、代码变更记录

### `restructure_prod_full.py` 主要变更

| 变更 | 原因 |
|------|------|
| urllib3 `_make_request` 补丁 | nginx 417 |
| `_NoExpectAdapter.send()` 剥离 Expect 头 | nginx 417 |
| `build_moves()` 返回 `leaf_skipped` | 叶子保护 |
| `analyze()` 添加 `leaf_warning` 检测 | 叶子保护 |
| 优先使用重构版 Commodities | 路径修正 |
| `--env` 参数 | 支持双环境 |

### `fix_leaf_node.py` — 通用叶子节点修复脚本
- `--name`: 叶子节点名称
- `--env test|prod`: 目标环境
- `--dry-run`: 预览模式
- `--parent`: 可选, 指定 XXX类 的父节点(默认用叶子当前parent)

### `prepare_commodities.py` — Commodities 数据源构建
- `REPLACE_MAP` 字典配置所有需要替换的叶子→类的映射

---

## 八、常见问题

### Q: 物料组浏览器不显示新创建的节点
**A**: 重建嵌套集树:
```python
# 通过 API
POST /api/method/frappe.utils.nestedset.rebuild_tree
{"doctype":"Item Group","parent_field":"parent_item_group"}
```

### Q: 叶子节点被脚本跳过
**A**: 脚本不自动修改 `is_group=0` 的节点。使用 `fix_leaf_node.py`:
```bash
python fix_leaf_node.py --name 节点名称 --env test --dry-run
```

### Q: 运行时报 417 / 连接超时
**A**: 生产 API 有不稳定情况。重试即可。脚本有自动重试机制。

### Q: 需要添加新的叶子节点修复
**A**: 修改 `prepare_commodities.py` 的 `REPLACE_MAP`, 运行后按流程执行。

---

## 九、下个会话快速接手指南

### 5 分钟上手
1. **读本文件** — 了解完整上下文
2. **检查当前状态**:
   ```bash
   cd D:\Claude Demo\fzh-data\EN_API
   python restructure_prod_full.py --env prod --dry-run --skip-backup
   python restructure_prod_full.py --env test --dry-run --skip-backup
   ```
3. **查看最新报告**: `out/物料组重构预览_20260611_104604.xlsx`
4. **检查凭证**: `.env` 文件在项目根目录

### 可能的后续操作
- **同步生产→测试**: `python sync_item_groups.py`
- **生成对比报告**: `python compare_item_groups.py`
- **备份**: `python backup_prod.py`
- **回滚**: 使用 `out/备份归档/` 下的备份 JSON + 恢复脚本

### 关键原则速记
- **叶子先确认再动** — 脚本跳过, 用 `fix_leaf_node.py` 手动处理
- **先测试再生产** — 所有操作先 `--env test` 验证
- **先 dry-run 再执行** — 先 `--dry-run` 预览
- **修改数据源** — 编辑 `prepare_commodities.py` 的 `REPLACE_MAP`, 然后重新生成
