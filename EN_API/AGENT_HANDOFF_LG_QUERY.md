# LG 前缀物料组 — 款式ID更新交接说明

> **生成时间**: 2026-06-15
> **工具脚本**: 
>   - `query_item_groups_by_model_id.py` (查询)
>   - `update_lg_model_ids.py` (更新款式ID)
> **相关文档**: [AGENT_HANDOFF.md](AGENT_HANDOFF.md) (通用交接)

---

## 1. 业务背景

在 EN 系统（ERPNext）中有 12 个物料组（Item Group）的 `custom_model_id`（款式ID）为 `LG001`~`LG012` 格式。需求是将它们修改为更有意义的命名方式：

**规则**: `LGxxx` → `LG` + 该物料组**子孙后代中最小款式ID**

例如: `LG001` 的子孙中最小款式ID是 `KS0496` → 新ID为 `LGKS0496`

这样新ID直接表达了「LG 款式 + 对应的最小子款编号」，更易于识别和管理。

---

## 2. 更新映射关系

| 物料组名 | 原款式ID | 子孙最小款式ID | 新款式ID |
|:---|:---:|:---:|:---:|
| 户外托盘垫印花款类 | LG001 | KS0496 (户外托盘垫印花款-条纹) | **LGKS0496** |
| 可组合扶手沙发 | LG002 | KS0220 (可组合扶手沙发套件) | **LGKS0220** |
| 儿童泡沫攀岩块类 | LG003 | KS0238 (儿童泡沫攀岩块-长方体平台) | **LGKS0238** |
| 逗号组合沙发 | LG004 | KS0369 (逗号组合沙发右扶手款) | **LGKS0369** |
| 自由模块沙发 | LG005 | KS0502 (自由模块沙发-靠背款) | **LGKS0502** |
| 组合式户外沙发 | LG006 | KS0525 (组合式户外沙发-转角) | **LGKS0525** |
| 游乐场懒人沙发模块 | LG007 | KS0407 (游乐场懒人沙发模块-转角款) | **LGKS0407** |
| 歌剧院床头靠枕套装 | LG008 | KS0511 (歌剧院床头靠枕套装-标准) | **LGKS0511** |
| 户外托盘垫 | LG009 | KS0459 (户外托盘垫-圆形) | **LGKS0459** |
| 床头软装组合 | LG010 | KS0489 (床头软装组合-床头靠垫) | **LGKS0489** |
| 复古造型大体量沙发 | LG011 | KS0387 (复古造型大体量沙发-右扶手) | **LGKS0387** |
| 几何链条抱枕 | LG012 | KS0334 (几何链条抱枕-蓝色) | **LGKS0334** |

> 所有新ID经冲突检测：**无重复，全部安全**。

---

## 3. 执行步骤

### 3.1 查询阶段（已完成）

使用 `query_item_groups_by_model_id.py` 确认测试系统有 12 条 LG 前缀记录。

### 3.2 子孙最小款式ID查询（已完成）

对每个 LG 物料组递归遍历其子孙节点，找到最小的 `custom_model_id`：
- 所有 LG 组都是**组节点**（`is_group=1`）
- 子孙中的款式ID全部为 **KS** 前缀（`is_group=0` 叶子节点）
- 每个 LG 组下有 3~11 个含款式ID的子孙

### 3.3 更新执行（已完成 - 测试系统）

```bash
# 预览
cd D:\Claude Demo\fzh-data\EN_API
python update_lg_model_ids.py --dry-run

# 执行更新（测试系统）
python update_lg_model_ids.py

# 执行更新（生产系统 - 待定）
python update_lg_model_ids.py --env prod
```

**更新时间**: 2026-06-15 13:53（测试系统）
**结果**: 12/12 成功，0失败，0冲突

### 3.4 验证（已完成）

执行后重新查询确认：
```bash
python query_item_groups_by_model_id.py --env test --prefix LG --json
```
返回 12 条记录，`custom_model_id` 全部为新格式 `LGKSxxxx`。

---

## 4. 脚本说明

### `update_lg_model_ids.py`

完整流程:
1. 全量拉取物料组
2. 按 `custom_model_id LIKE 'LG%'` 筛选 LG 节点
3. 递归遍历每个 LG 组的子孙节点，找最小款式ID
4. 构建新ID = `"LG" + min_child_id`
5. 冲突检测（新ID不能与系统中任何已有ID重复）
6. PUT 更新 `custom_model_id` 字段
7. 生成变更报告 Excel + JSON

参数:
| 参数 | 说明 |
|------|------|
| `--env test|prod` | 目标环境（默认 test） |
| `--dry-run` | 预览模式，不实际写入 |

---

## 5. 输出文件

| 文件 | 路径 | 说明 |
|------|------|------|
| 查询脚本 | `EN_API/query_item_groups_by_model_id.py` | 按款式ID前缀查询物料组 |
| 更新脚本 | `EN_API/update_lg_model_ids.py` | 执行款式ID更新 |
| 更新结果 Excel | `EN_API/out/LG款式ID更新结果_test_20260615_135335.xlsx` | 汇总 + 变更明细 |
| 更新结果 JSON | `EN_API/out/LG款式ID更新结果_test_20260615_135335.json` | 结构化变更记录 |
| 验证结果 JSON | `EN_API/out/LG物料组查询结果_20260615_135401.json` | 更新后验证快照 |
| 本文档 | `EN_API/AGENT_HANDOFF_LG_QUERY.md` | 交接说明 |

---

## 6. 执行状态

| 环境 | 状态 | 时间 | 结果 |
|:---|:---:|:---:|:---:|
| 测试系统 (ensh.vilavi.cn) | ✅ 已完成 | 2026-06-15 13:53 | 12/12 成功 |
| 生产系统 (erpnext.vilavi.cn) | ✅ 已完成 | 2026-06-15 14:11 | 12/12 成功 |

## 7. 备查文件

- **测试系统更新前**: `out/LG物料组查询结果_20260615_134037.json`
- **测试系统变更记录**: `out/LG款式ID更新结果_test_20260615_135335.json`
- **生产系统变更记录**: `out/LG款式ID更新结果_prod_20260615_141122.json`
- **生产系统验证快照**: `out/LG物料组查询结果_20260615_141142.json`

## 8. 后续工作

1. **其他系统对接** — 如果赛狐或其他系统使用了 `LG001`~`LG012` 作为款式ID，需要同步更新
2. **物料管理与 BOM** — 为新 LGKS 款式建立 BOM 成本，参考 `item_cost_sx/bom_cost_to_saihu_item_cost.py`
3. **图片上传** — 为 LGKS 物料组上传图片，参考 `upload_item_images.py`

---

## 9. 快速启动

```bash
cd D:\Claude Demo\fzh-data\EN_API

# 查询当前测试系统 LG 前缀物料组（验证更新结果）
python query_item_groups_by_model_id.py --env test --prefix LG

# 查询当前生产系统 LG 前缀物料组（验证）
python query_item_groups_by_model_id.py --env prod --prefix LG

# 如需要再次执行更新（已全部完成，无需重复执行）
python update_lg_model_ids.py --env test --dry-run   # 预览
python update_lg_model_ids.py --env prod --dry-run   # 预览
```
