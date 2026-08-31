# 生产工单数据排查方法论

> 用于排查 ERPNext 生产工单数据异常，特别是"一键完工"导致的虚报数据。

## 背景问题

自定义"一键完工"功能会用虚拟员工创建所有工序的 Job Card，按工单计划量填充完成量，
跳过真实的扫码报工流程。这导致工单工序子表数据不反映实际生产情况。

## 探案步骤 (6步法)

### 步骤 1: 查 Version 活动记录

```
GET /api/resource/Version?filters=[["ref_doctype","=","Work Order"],["owner","=","yangyisen92@dingtalk.com"]]
```

**判断**: 如果工单有杨义森的修改记录 → 疑似一键完工

**典型痕迹**:
- status 从 "草稿" 变为 "未开始"  
- custom_label_combination 被设置
- actual_start_date / actual_end_date 以 0.017s 间隔快速迭代 (程序化操作特征)

### 步骤 2: 查 open_material_qty

```
GET /api/resource/Work Order/{name}?fields=["open_material_qty"]
```

**判断**:
- `= 0` → 裁剪从未在系统报开料，整个工序数据不可信（全假）
- `> 0 但 < qty` → 实际裁剪量（如布料用完），后续工序最大完成量以此为上限
- `= qty` → 可能与计划一致，需结合步骤 3 判断

### 步骤 3: 查 Job Card 所有权

```
GET /api/resource/Job Card?filters=[["work_order","in",[...]],["docstatus","<",2]]
fields=["name","work_order","operation","for_quantity","total_completed_qty","employee","owner"]
```

**判断**:
- 所有 JC owner = 杨义森 → 全部虚拟，数据不可信
- 存在真实员工 (如 105-prd4qxz8w9, yj0_wq85xz6km 等) → 有真实扫码报工
- **汇总真实 JC 的 for_quantity 或 total_completed_qty → 得到实际工序完成量**

**示例**: WO-26-00082 李清君(105-prd4qxz8w9) 分9批扫码共 ~185 件，但杨义森创建了 300 件的虚拟 JC 覆盖

### 步骤 4: 查 Stock Entry 所有权

```
GET /api/resource/Stock Entry?filters=[["work_order","=",wo],["stock_entry_type","=","Manufacture"]]
```

然后查 items 子表获取入库量:
```
GET /api/resource/Stock Entry/{name} → items[].qty (t_warehouse 有值、s_warehouse 无值的行)
```

**判断**:
- SE owner = 杨义森 → 入库量很可能 = 计划量（不可信）
- SE owner = 其他人 → 真实入库
- **汇总所有真实 SE 的 items qty → 得到实际入库量**

**示例**: WO-26-00082 的 SE 由 yj0_wq85xz6km 创建，10 批共 216 件入库

### 步骤 5: 交叉验证

| 数据源 | 含义 | WO-26-00082 示例 |
|--------|------|-----------------|
| 真实 JC 汇总 | 实际工序完成量 | ~185 (分9批) |
| SE 入库汇总 | 实际入库量 | 216 (分10批) |
| open_material_qty | 裁剪开料量 | 298 |
| produced_qty | 工单产出量 | 285 |
| 工序子表裁剪量 | 可能被一键完工覆盖 | 300 (虚假) |

三个真实数据源 (JC/SE/open_mat) 应大致一致，如有差异取合理范围。

### 步骤 6: 一键完工痕迹链 (确认特征)

同时满足以下条件 → 确认一键完工:
1. Version 记录中 owner=yangyisen92
2. status 变更: 草稿 → 未开始
3. custom_label_combination 被设置 (如 "PP001-SX003-XH00...")
4. actual_start_date 和 actual_end_date 在 1-2 秒内完成设置
5. actual_end_date 被多次迭代更新 (间隔 ~0.017-0.25s，程序化)

## 数据分类

| 分类 | 特征 | 数据可信度 | 处理方式 |
|------|------|-----------|---------|
| **一键完工-无开料** | open_mat=0, 全部JC=杨义森, 全部SE=杨义森 | 不可信 | 需物理盘点核实 |
| **一键完工-有开料** | open_mat>0, JC有真实工人+杨义森 | 开料可信,工序量被覆盖 | 以open_mat为准 |
| **非Completed+一键完工** | 状态!=Completed, 但杨义森触碰过 | 工序量虚报, 开料可信 | 以open_mat为准 |
| **正常扫码-工序瓶颈** | 无杨义森记录, 工人扫码JC | 可信 | 工序瓶颈分析有效 |
| **正常完成** | 无杨义森, 状态Completed | 可信 | 正常 |

## 使用的 API 端点

- `/api/resource/Work Order` — 工单主表 + 工序子表
- `/api/resource/Version` — 变更历史
- `/api/resource/Job Card` — 工序报工记录
- `/api/resource/Stock Entry` — 入库单 (Manufacture 类型)

## 相关文件

- 分析脚本: `erpnext/scripts/gen_report.py`
- 数据: `erpnext/data/2026-06_*.json` (不提交 git)
- 报告: `erpnext/data/2026-06_工单排查报告.xlsx` (不提交 git)
