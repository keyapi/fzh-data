# 生产工单数据排查方法论

> 用于排查 ERPNext 生产工单数据异常，特别是"一键完工"导致的虚报数据。
> 与英文版 `docs/solutions/best-practices/erpnext-work-order-investigation-methodology.md` 同步（同为 8 步）。

## 背景问题

自定义"一键完工"功能会用虚拟员工创建所有工序的 Job Card，按工单计划量填充完成量，
跳过真实的扫码报工流程。这导致工单工序子表数据不反映实际生产情况。

## 探案步骤 (8步法)

### 步骤 1: 物料类型分类

先按 `production_item` 前缀分类，决定后面哪些"异常"其实是正常：

- **`KS` 前缀** — 成品fg（皮壳 + 内胆 + 充棉）。工序路由为空，`open_material_qty = 0` 属正常。
- **`PK#` 前缀** — 半成品：皮壳。多工序路由，应有扫码报工。
- **`ND#` 前缀** — 半成品：内胆。同皮壳。

### 步骤 2: 遗留虚拟工序检查

检查工序里是否含"缝制"——一键完工时代的遗留工序。出现说明 BOM/路由从未更新，
该工序的 Job Card 数据无意义，标记待修。

### 步骤 3: 查 Version 活动记录

```
GET /api/resource/Version?filters=[["ref_doctype","=","Work Order"],["owner","=","yangyisen92@dingtalk.com"]]
```

**判断**: 如果工单有杨义森的修改记录 → 疑似一键完工

**典型痕迹**:
- status 从 "草稿" 变为 "未开始"  
- custom_label_combination 被设置
- actual_start_date / actual_end_date 以 ~0.017s 间隔快速迭代 (程序化操作特征)

### 步骤 4: 查 open_material_qty

```
GET /api/resource/Work Order/{name}?fields=["open_material_qty"]
```

**判断**:
- 半成品 `PK#`/`ND#`：`= 0` → **异常**，裁剪必须领料；为零说明整个工序数据不可信（全假）
- 半成品 `> 0 但 < qty` → 实际裁剪量（如布料用完），后续工序最大完成量以此为上限
- 成品 `KS`：`= 0` → **正常**，路由上没有裁剪工序
- `= qty` → 可能与计划一致，需结合步骤 5 判断

### 步骤 5: 查 Job Card time_logs.employee

```
GET /api/resource/Job Card/{name} → time_logs[] 子表
```

**判断**:
- `HR-EMP-00001` = 虚拟员工（一键完工），数量 = 计划量，不是真实产量
- 其他 employee ID = 真实工人，数量反映实际扫码产量

⚠️ `time_logs` 只在**单条** Job Card 查询时返回，列表查询不含子表。

### 步骤 6: 查 Job Card owner (补充交叉验证)

列表查询可带的字段：

```
GET /api/resource/Job Card?filters=[["work_order","in",[...]],["docstatus","<",2]]
fields=["name","work_order","operation","for_quantity","total_completed_qty","employee","owner"]
```

**判断**:
- 所有 JC owner = 杨义森 → 全部虚拟，数据不可信
- 存在真实员工 (如 105-prd4qxz8w9, yj0_wq85xz6km 等) → 有真实扫码报工
- **`owner` ≠ `employee`** —— employee 在 `time_logs` 子表（步骤 5），owner 是记录创建人

### 步骤 7: 查 Stock Entry 所有权

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

### 步骤 8: 交叉验证与分类

| 数据源 | 含义 |
|--------|------|
| 真实 JC 汇总 | 实际工序完成量（下限） |
| SE 入库汇总 | 实际入库量 |
| open_material_qty | 裁剪开料量（生产上限） |
| 工序子表裁剪量 | 可能被一键完工覆盖 |
| produced_qty | 系统产出量（可能虚高） |

几个真实数据源 (JC/SE/open_mat) 应大致一致，如有差异取合理范围。

## 一键完工痕迹链 (确认特征)

以上分步只能做到「疑似」。**同时满足**以下条件才确认一键完工（AND 门，不是出现过某一条就算）：

1. Version 记录中 owner=yangyisen92
2. status 变更: 草稿 → 未开始
3. custom_label_combination 被设置 (如 "PP001-SX003-XH00...")
4. actual_start_date 和 actual_end_date 在 1-2 秒内完成设置
5. actual_end_date 被多次迭代更新 (间隔 ~0.017-0.25s，程序化)

### 示例: WO-26-00082（混合真实+虚拟）

| 数据源 | 数量 | 可信度 |
|--------|------|--------|
| 真实 JC（李清君分 9 批扫码） | ~185 | 真实下限 |
| SE 入库（yj0_wq85xz6km，10 批） | 216 | 真实 |
| open_material_qty | 298 | 真实上限 |
| 虚拟 JC（HR-EMP-00001） | 300 | 伪造 |
| produced_qty | 285 | 碰巧接近真实 |

结论：实际产量约 285。不能只看 `produced_qty` 或跨工序把 JC 加总。

## ⚠ Job Card 完成量怎么算

**按工序分别算，不要跨工序求和。** 同一批件数会在**每道工序各生成一张 Job Card**，
跨工序求和会把产量按工序数放大。

- 问"这批做了多少件" → 取**第一道工序（裁剪/开料）**的完成量
- 问"某道工序做了多少" → 才取那道工序的完成量
- 实测：某工单 2 批 × 22 件 = **44 件**；把 裁剪/皮壳整件/锁扣眼/拷边 四道工序的
  `total_completed_qty`（空则 `for_quantity`）相加会算成 176，虚高 4 倍

## ⚠ Work Order.status / produced_qty 可能没回写

实测有工单头部仍是 `Not Started`、`produced_qty = 0`，但工序卡已显示几十件过完多道工序。
判断"是否已开工"要看**工序卡数量**（0 张工序卡 + 工序全 Pending 才是真未开工），
不能只看工单状态——否则会把在产工单误判成未开工。

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
- Skill: `.agents/skills/erpnext-wo-audit/SKILL.md`（按触发词自动加载）
- 英文版（同一方法论的英文 learning）: `docs/solutions/best-practices/erpnext-work-order-investigation-methodology.md`
- 销售订单侧的发货/未发排查（不同问题域）: `docs/solutions/workflow-issues/erpnext-so-closed-unshipped-and-unstarted-work-orders.md`
- 数据: `erpnext/data/2026-06_*.json` (不提交 git)
- 报告: `erpnext/data/2026-06_工单排查报告.xlsx` (不提交 git)
