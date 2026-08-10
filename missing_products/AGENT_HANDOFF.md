# missing_products — Agent 交接文档

> **用途**：新对话接手本项目的入口。读完本文档可完整理解「通途→EN→赛狐 老产品补齐」的前因后果、当前状态、下一步与全部技术细节。
> **代码位置**：`missing_products/` 目录（识别脚本 + 创建脚本 + 文档）。
> **最后更新**：2026-08-10

---

## 1. 项目背景

运营反馈赛狐可能漏建商品。排查发现：**通途有库存的 SKU** 需对应 **EN 物料（含成本）** 和 **赛狐商品**，形成完整链条，才能做库存同步。

三系统数据流：
```
通途(库存) ──SKU/客户物料号──► EN(物料+成本) ──产品编号──► 赛狐(商品)
```

### 阶段性目标

| 阶段 | 目标 | 状态 |
|------|------|------|
| 1 | EN 物料 + 成本存在 | ✅ 已完成（老产品）|
| 2 | 赛狐商品完整 | ⏳ **下一步** |
| 3 | 通途↔赛狐库存同步 + 定期校准 | 📋 待做 |
| 4 | 几何链条/攀岩块（套件）| ⏸️ 暂缓 |

---

## 2. 当前状态（2026-08-10）

### 缺口分析结果
- 通途有库存 SKU：**1411 个**
- 匹配 EN 客户物料号：1397 个
- **未匹配：14 个**（全部为非优先级杂项，见 §6）

### 已完成：EN 老产品补齐
| 产品族 | 创建内容 | 成本机制 |
|--------|---------|---------|
| **星球 KS0019** | 完整矩阵 25/41cm × 木星/月球/黑月球/地球 + 12件套（7 变体 + BOM + 14 客户码）| SXBZPK# Item Price（25cm=9.54, 41cm=12.51）|
| **石头 KS0018** | 12 单石（浅灰1-6/深灰1-6）+ LSPPW03/04（14 变体 + valuation + BOM + 14 客户码）| valuation_rate（单石 7.85, LSPPW 47.036）|
| **张嘴熊** | KS0026-TDR-340-LIGHTBROWN（153 = 2×76.5）| SXBZPK#KS0026-340 Item Price 153 |
| **泰迪熊** | 7 个 TT 码 + 抱心泰迪(3) + 白色泰迪(1) 归类 | — |
| **方形枕套 KS0013** | 宽边正方形枕头-荷兰绒-80*80*18-**咖啡色**（KS0013-HLR-80-COFFEE，39.98 + 简化BOM）| SXBZPK#KS0013-80 Item Price 39.98 |

**通途未匹配从 54 → 14**（仅剩杂项）。

---

## 3. 下一步工作

### 3.1 赛狐侧补齐（最高优先）
缺口分析显示需创建约 23 个赛狐 SKU（按 SPU 去重后）：
- 星球 KS0019：7 SKU（25cm/41cm × 木星/月球/黑月球/地球 + 12件套）
- 石头 KS0018：14 SKU（12 单石 + LSPPW03/04）
- 张嘴熊：1 SKU
- 方形枕套 KS0013：**1 SKU（必须含颜色 = KS0013-HLR-80-COFFEE）**

方法：用 `multi_attr_saihu/erpnext_to_saihu.py` 从 EN 纵向物料导出生成赛狐多属性导入文件，再导入赛狐。

> ⚠️ **注意**：Codex 已把 `KS0013-HLR-80`（无颜色）建进赛狐（SPU ID 25064, SKU ID 3894655）。这是错误的，**需删除或重建为 `KS0013-HLR-80-COFFEE`（含颜色）**。
> Codex 还发现：赛狐「属性管理」中 13 个缺失 SPU 无产品专属属性簇，需先确认赛狐属性簇创建接口。

### 3.2 库存同步（阶段 3）
- 建映射表：`{通途SKU: {赛狐SKU, EN物料, 成本}}`
- 同步扣减 + 定期校准脚本（每天/每周）
- 参考 `missing_products/docs/specs/old-product-completion-plan.md` 的「库存同步设计」

### 3.3 剩余 14 个未匹配（用户已确认暂缓）
见 §6 列表。

---

## 4. 关键技术细节

### 4.1 服务器 SSH（重要！生产 IP 已换）
- **生产**：`47.116.128.218`（frappe 用户），pem `D:/Work/Aliyun/ssh/aliyun_fzh_erpnext_20240726.pem`
- SSH config 别名已更新（`阿里云-FZH-ERPNext-frappe/root` → 新 IP）
- 测试：`8.133.254.66`（sh-erpnext-test / 上海测试）
- 旧香港 IP `8.223.4.206` 已废弃

### 4.2 BOM Cost List 生成（关键！）
报表：`key_test.bom_cost_list`（Script Report），在服务器上运行：
```bash
ssh frappe@47.116.128.218 -i D:/Work/Aliyun/ssh/aliyun_fzh_erpnext_20240726.pem
cd ~/frappe-bench && env/bin/python /tmp/gen_bom_xlsx2.py
```
**必须的 6 个 filter**（缺了会漏数据/列错序）：
```python
{'item_group': '产品', 'show_disabled': 1, 'show_ref_code': 1,
 'sum_columns_at_end': 1, 'pllc_sfg_missing_use_cover': 0, 'simplified_column_view': 0}
```
- `show_disabled=1`（显示禁用物料，否则漏 200+ 行）
- `sum_columns_at_end=1`（成本累加列在最右，列序才对）
- `show_ref_code=1`（含客户物料号列）
- 输出格式：71 列，`<br>`→`, `，文件名 `EN产品BOM成本列表_{stamp}.xlsx`
- 服务器脚本 `/tmp/gen_bom_xlsx2.py` 生成到 `~/frappe-bench/sites/erpnext.vilavi.cn/private/files/bom_cost_export2.xlsx`，再 scp 回本地
- `export_query` API 会返回「没有要导出的数据」（filters 格式问题），不要用，直接服务器 execute

### 4.3 EN 成本机制
| 产品族 | 机制 |
|--------|------|
| 星球/张嘴熊/方形枕套 | 成品 BOM 只套 `SXBZPK#`（绍兴包装皮壳），SXBZPK# 走 **Item Price「标准采购」** |
| 石头 | valuation_rate + 自引用 BOM（无真实组件）|
| 三角靠枕 KS0001 | 全 BOM（皮壳#+内胆#，皮壳BOM 10 道工序）|

### 4.4 EN 物料四层体系
```
底层值表 (Item Attribute Value All Fabric/Color, FAB-*/CLR-*)
   └─ 物料属性 (custom_select_doctype 引用; 面料/颜色=1, 尺寸=0)
        └─ 模板物料 (has_variants=1) → 变体 (variant_of=模板)
```
- 面料/颜色属性引用底层表（`custom_select_from_all_attribute_values=1`），尺寸独立（=0）
- 9 类配套物料：皮壳#(同产品属性)、内胆#(尺寸+内胆面料/颜色)、绍兴包装皮壳#/成品#/半成品#(尺寸)、波兰PL/美东USNJ/美中USTX包装成品#(尺寸)、重量模板#(面料+尺寸)
- 详细见 `docs/solutions/conventions/erpnext-item-variant-creation-convention.md`

### 4.5 EN 核心原则（必读，避免犯错）

> 这些原则是 EN 物料体系的「潜规则」，Codex 曾因不懂而犯错。新建/补全物料前必须逐条核对。

1. **属性集必须完整（面料+尺寸+颜色是标配）**
   - 绝大多数产品族属性集 = 面料+尺寸+颜色（三角靠枕/星球/石头/泰迪熊都是）
   - **例外**：重量模板# 用 面料+尺寸（无颜色，减维护）；包装# 仅尺寸
   - ⚠️ 若产品有颜色（如方形枕套是咖啡色），**变体必须含颜色**。若目标产品族缺颜色属性，**应先补颜色属性**，不能接受不完整属性集
   - 教训：KS0013 宽边正方形枕头原本只有 面料+尺寸（历史不完整），直接建无颜色变体是错的，已修复为 `KS0013-HLR-80-COFFEE`

2. **客户码全局唯一**
   - 一个客户物料号只能登记在一个 EN 物料上（自定义 app 校验：`客户物料号已存在于其他物料`）
   - 移动/重建时，必须先移除旧物料上的客户码，再登记到新物料

3. **属性值必须先行**
   - 创建变体前，属性（面料/尺寸/颜色）的值必须已存在
   - 加属性值时**必须带 abbr**（ERPNext Server Script 校验 `abbr.lower()`，不带报 500）
   - 若缺值：先 `PUT /api/resource/Item Attribute/{name}` 加 `{attribute_value, abbr}`

4. **尺寸属性不引用底层表，面料/颜色引用**
   - 尺寸 `custom_select_from_all_attribute_values=0`（独立定义）
   - 面料/颜色 `=1` + `custom_select_doctype=Item Attribute Value All Fabric/Color`

5. **变体命名规律**：`{模板}-{面料abbr}-{尺寸abbr}-{颜色abbr}`
   - abbr 来自 All Fabric/All Color 的 `abbr`（如 荷兰绒=HLR, 咖啡色=COFFEE, 漂白荷兰绒=PBHLR）
   - 尺寸 abbr 来自属性值（如 41cm=41, 80*80*18=80）

6. **成本机制分产品族**（创建前先查同类已有变体的 BOM，不要套错）：
   | 产品族 | 成本机制 |
   |--------|---------|
   | 星球/张嘴熊/方形枕套 | 成品 BOM 只套 `SXBZPK#`（绍兴包装皮壳），SXBZPK# 走 Item Price「标准采购」 |
   | 石头 | valuation_rate + 自引用 BOM（无真实组件）|
   | 三角靠枕 KS0001 | 全 BOM（皮壳#+内胆#，皮壳BOM 10 道工序，需 workstation）|

7. **一键创建配套物料及变体**（EN UI 按钮）
   - Client Script「物料 一键创建配套物料及变体 多选菜单」→ `key_test.add_item_semi.create_supporting_items_and_variants`
   - 角色：Item Supporting Material Manager / System Manager
   - ⚠️ 该函数创建变体但**不自动加颜色属性值**（星球 41cm 建完缺 月球/黑月球 颜色值，需手动补）

8. **配套物料属性集**（9 类，不同产品族可能不同）：
   | 配套物料 | 属性组合 |
   |---------|---------|
   | 皮壳# | 面料+尺寸+颜色（同产品）|
   | 内胆# | 尺寸+内胆面料+内胆颜色 |
   | 绍兴包装皮壳#/成品#/半成品# | 尺寸 |
   | 波兰PL/美东USNJ/美中USTX包装成品# | 尺寸 |
   | 重量模板# | 面料+尺寸 |

### 4.5 赛狐 API
- `SELLFOX_API/client.py` → `SellfoxClient`（proxy 模式 `SELLFOX_PROXY_API_KEY`）
- 商品列表：`POST /api/commodity/getCommoditySpuList.json` + `pageList.json`
- 赛狐商品创建用多属性 SPU 模式

---

## 5. 关键脚本/文件

| 文件 | 用途 |
|------|------|
| `missing_products/identify_missing_products.py` | 三系统缺口分析（4 数据源交叉比对）→ 报告 xlsx |
| `missing_products/create_en_materials.py` | 幂等创建 EN 物料（--dry-run / --phase 1-6）|
| `missing_products/docs/specs/old-product-completion-plan.md` | 老产品补齐计划（OKF Spec）|
| `docs/solutions/conventions/erpnext-item-variant-creation-convention.md` | EN 物料创建惯例（OKF Reference）|
| `.agents/skills/erpnext-item-create/SKILL.md` | 新建 EN 物料 skill |
| `SELLFOX_API/client.py` | 赛狐 OpenAPI 客户端 |
| `D:/Work/赛狐/网页自动化/tongtu_auto_export.py` | 通途 6 仓库存导出（浏览器自动化）|

### 常用命令
```bash
# 缺口分析
cd missing_products && uv run python identify_missing_products.py

# 创建 EN 物料（dry-run 预览 → 分 phase 执行）
uv run python create_en_materials.py --dry-run
uv run python create_en_materials.py --phase 6

# 重新生成 BOM Cost List（SSH 服务器）
# 见 §4.2，生成后 scp 回 missing_products/数据源/ + warehouse_restock/数据源/
```

---

## 6. 剩余 14 个未匹配（用户确认暂缓）

| 分类 | SKU | 备注 |
|------|-----|------|
| 辅料/耗材 (7) | Buttonkit-pl(1000万), Cotton-US/EU(~10万), CEN-PPCotton-5lb, Card006, Buttonkit, Box-pl | 售后耗材（棉包/卡片/针线/纸箱），无需 EN 产品物料 |
| 套件 (2) | TT0031192K0063867(几何链条), TT0031102-zuhe-all(攀岩块) | 需用套件形式，暂缓 |
| ASIN (1) | 497268621 | Mars Pillow 包装费，非产品 |
| 其他 (4) | InvitationLetter(邀请信), DLZYFX001(编织袋), TEST-1, YCSOFA001(云仓沙发) | 非产品/待定 |

---

## 7. 经验教训

1. **BOM Cost List 报表 filter 必须带全**：`show_disabled` 和 `sum_columns_at_end` 漏了会导致漏行/列错序，缺口分析结果严重偏差（60→142 假象）
2. **物料属性加值必须带 abbr**：ERPNext 有 Server Script 校验 `abbr.lower()`，不带会 500
3. **通途 SKU ↔ EN 客户物料号大小写不敏感**：`KDHY-020-MAHUI-60CM` vs `-60cm` 历史差异
4. **通途 SKU 前缀 ≠ EN SPU**：`PPL-*`(石头) ↔ `KS0018-*`，SPU 库存须按客户物料号聚合
5. **幂等创建脚本**：每个操作先查再建，安全重跑
6. **星球/张嘴熊/方形枕套用简化 BOM**（只套 SXBZPK#，无工序）；石头用 valuation_rate 自引用 BOM——不同产品族 BOM 模式不同，创建前先查同类已有变体
7. **客户物料号错配**：XINGQIU-Moon-10(25cm月球) 曾被登记到 KS0018(印花石头)，已修复移回 KS0019
8. **旧产品（dead products）**：成本不必 100% 精确（不再生产），简化处理优先，但 EN 物料+成本必须存在（库存价值用）
9. **属性集完整性**：产品有颜色就必有颜色属性。KS0013 宽边正方形枕头原本缺颜色（历史不完整），建方形枕套时应先补颜色属性，不能接受无颜色变体
10. **客户码唯一性**：一个客户码只能挂一个物料。重建/移动时先移除旧的再登记新的
11. **交接文档必须含 EN 原则**：光列「建了什么」不够，必须写「为什么这么建、规则是什么」，否则另一个 AI（Codex）会照抄错误

---

## 8. Git 历史（本分支）

```
99b99ed feat(missing_products): 方形枕套 KS0013 补齐 + 窄边正方形抱枕 KS0014 方案(已废弃)
f420693 feat(missing_products): EN 老产品补齐脚本 — 星球/石头/张嘴熊/泰迪熊
8759024 docs(missing_products): 老产品补齐计划 — EN物料/成本→赛狐商品→库存同步
727c86a feat(missing_products): 赛狐缺失商品排查 + EN物料创建惯例文档/skill
```

分支：`claude/awesome-satoshi-c903d5`（feature 分支，遵循「不直接提交 main」规则）

---

## 9. 新对话快速上手

1. 读本文档（你已经读了）
2. 确认 EN 状态：跑 `identify_missing_products.py` 看未匹配（应 14）
3. 做**赛狐侧补齐**：从 EN 导出纵向物料 → `erpnext_to_saihu.py` 生成赛狐导入文件
4. 若需新建 EN 物料：`create_en_materials.py --dry-run` 预览 → 执行
5. 若需重新生成 BOM Cost List：SSH 服务器跑 `/tmp/gen_bom_xlsx2.py`（见 §4.2）
6. 库存同步：参考计划文档 §库存同步设计
