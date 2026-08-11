# missing_products — Agent 交接文档

> **用途**：新对话接手本项目的入口。读完本文档可完整理解「通途→EN→赛狐 老产品补齐」的前因后果、当前状态、下一步与全部技术细节。
> **代码位置**：`missing_products/` 目录（识别脚本 + 创建脚本 + 文档）。
> **最后更新**：2026-08-11

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
| 1 | EN 物料 + 成本存在 | ✅ 已完成（老产品与本轮主线）|
| 2 | 有库存产品对应的赛狐商品完整 | ✅ 已完成（2026-08-11 回读验证）|
| 3 | 通途↔赛狐库存同步 + 定期校准 | 📋 待做；先设计映射与审批范围 |
| 4 | 几何链条/攀岩块（套件）| ⏸️ 暂缓 |

---

## 2. 当前状态（2026-08-11）

### 缺口分析结果
- 通途有库存 SKU：**1411 个**
- 精确登记 EN 产品成品：**1397 个**
- **未精确登记：14 个**（2 个套件 + 12 个已知非产品项，均暂缓，见 §6）
- 皮壳完整 SKU 108 个、海绵完整 SKU 25 个均已精确登记 EN 产品；这些产品 SKU 已从赛狐列表 API 回读存在

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

### 3.1 主线已完成：先刷新证据，禁止照旧报告重复创建
2026-08-11 的刷新审计确认：有库存通途 SKU 1411 个，其中 1397 个已把**完整**码精确登记到 EN 产品成品，余下 14 个是用户确认暂缓项；皮壳 108 个、海绵 25 个对应的 EN 产品 SKU 在赛狐均已存在。

后续遇到新缺口时，先运行 `audit_three_systems.py` 刷新四方数据，再判断。`-Cover/-Foam` 去尾缀基码只作为候选，不能当作已登记；赛狐创建目标是 EN 产品 `item_code`，不是通途半成品原码。完整流程与反例见：

- `docs/solutions/conventions/tongtu-en-sellfox-instock-sku-mainline.md`
- `.agents/skills/missing-products/SKILL.md`

赛狐属性簇/属性值仍不能由 OpenAPI 创建：缺属性时要按模板生成 Excel，由用户导入并确认成功，再 API 创建产品 SKU 并从列表回读。不得为本轮核验修改已有商品的在售状态。

### 3.2 库存同步（阶段 3）
- 建映射表：`{通途SKU: {赛狐SKU, EN物料, 成本}}`
- 同步扣减 + 定期校准脚本（每天/每周）
- 参考 `missing_products/docs/specs/old-product-completion-plan.md` 的「库存同步设计」

### 3.3 剩余 14 个未匹配（用户已确认暂缓）
见 §6 列表。

### 3.4 主线之后的只读调研（不写入）
- 全量调查 `PK#` 与 `HM1510` 是否已有客户物料号，以及同一通途 SKU 在产品、皮壳和海绵中的重复关系。
- 结合销售订单导入、BOM、生产和库存研究拉链款弧形靠枕的共用皮壳、通用海绵和一对多维护方式。
- 调研完成前不迁移、不删除配套物料上的客户码；主体骨架也留到后续单独范围。

---

> **2026-08-11 状态修正（优先于本节上方遗留的历史计划）**：赛狐产品 SKU 补齐已完成。错误的无颜色 `KS0013-HLR-80` 已由用户在赛狐后台删除，正确对象为 `KS0013-HLR-80-COFFEE`。赛狐 OpenAPI 能读取 SPU/SKU 并创建产品 SKU，但不能创建属性簇或属性值；缺属性时必须先由用户在赛狐 UI 导入属性 Excel，确认成功后才可 API 创建 SKU。
>
> 最新主线回读：108 条有库存皮壳通途 SKU、25 条有库存海绵通途 SKU 均已以**完整 SKU**登记到至少一个 EN 产品变体，且对应 EN 产品 `item_code` 均已存在于赛狐。不得依据上方的旧计划重复创建赛狐 SKU；先拉取最新三方数据，再运行 `audit_three_systems.py`。
>
> 现在的下一步是库存同步设计：先审阅 `{通途完整SKU: {EN产品物料, 赛狐产品SKU, 成本}}` 映射，明确一对多/多对一的库存归属，获得用户确认后再实施同步。`PK#` 与 `HM1510` 的客户码只做只读研究，不能替代 EN 产品登记，也不得在主线中迁移或删除。

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
| `missing_products/audit_three_systems.py` | 主线审计：完整通途 SKU → EN 产品精确登记 → 赛狐产品 SKU 回读 |
| `missing_products/register_product_customer_codes.py` | 仅对审计确认的候选写入 EN 产品客户码；默认 dry-run，`--apply` 后回读 |
| `missing_products/build_mainline_report.mjs` | 生成面向业务复核的主线工作簿（分类、赛狐状态、一对多历史关系） |
| `missing_products/investigate_supporting_customer_codes.py` | 只读调查 `PK#`/`HM1510` 客户码，禁止用于本轮迁移或清理 |
| `missing_products/create_en_materials.py` | 幂等创建 EN 物料（--dry-run / --phase 1-6）|
| `missing_products/docs/specs/old-product-completion-plan.md` | 老产品补齐计划（OKF Spec）|
| `docs/solutions/conventions/tongtu-en-sellfox-instock-sku-mainline.md` | 三方主线完整规则、设计过程、错误做法、验证清单 |
| `docs/solutions/conventions/erpnext-item-variant-creation-convention.md` | EN 物料创建惯例（OKF Reference）|
| `.agents/skills/missing-products/SKILL.md` | 通途有库存 SKU 三方主线自动触发入口 |
| `.agents/skills/erpnext-item-create/SKILL.md` | 新建 EN 物料 skill |
| `SELLFOX_API/client.py` | 赛狐 OpenAPI 客户端 |
| `D:/Work/赛狐/网页自动化/tongtu_auto_export.py` | 通途 6 仓库存导出（浏览器自动化）|

### 常用命令
```bash
# 当前主审计（先运行，后讨论写生产）
uv run python missing_products/audit_three_systems.py

# 业务报告（审计后运行）
node missing_products/build_mainline_report.mjs

# 只读调查配套物料客户码
uv run python missing_products/investigate_supporting_customer_codes.py

# 主线三方审计与业务工作簿（先只读；写入前必须检查 dry-run 报告）
uv run python audit_three_systems.py
node build_mainline_report.mjs
uv run python register_product_customer_codes.py

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
12. **属性完整性审计**：创建后必须逐变体查 `attributes` 是否含 面料/尺寸/颜色。2026-08-10 创建的全部物料已审计：**仅 KS0013-HLR-80 缺颜色（已删）**，其余正确。根因：宽边正方形枕头 KS0013 历史属性集不完整（只有 面料+尺寸），我直接跟随模板建了无颜色变体，未先补颜色属性
13. **item_code 必须用 abbr**（不用中文）：石头 12 单石曾用 `KS0018-LSRBS-25cm-浅灰1号`（中文），赛狐要求英文编号，已用 SSH `frappe.rename_doc` 改为 `KS0018-LSRBS-25cm-LIGHTGREY1` 等。REST 不能改 item_code（rename_doc 未白名单），需 SSH
14. **客户端码全局唯一 + 编号改动影响**：重建/重命名物料会牵动客户码（须先移除旧的）、BOM（rename_doc 自动更新）、Item Price（可能需重加）
15. **半成品通途 SKU 必须精确登记到 EN 产品**：`-Cover`/`-Foam` 去后缀基码只能用来找候选产品，不能当作已登记。完整 SKU 必须出现在至少一个 `KS` 产品变体的 `customer_items.ref_code`。原因：EN 销售订单 Excel 先用通途 SKU 找产品物料，再按“皮壳/成品/半成品”列决定交付形态；`PK#` 或 `HM1510` 上的登记不能替代产品登记。
16. **2026-08-11 主线对账结果**：通途有库存 1411 SKU，1397 已精确登记 EN 产品，剩余 14 为 2 套件 + 12 已知非产品项，全部暂缓。皮壳 108 条、海绵 25 条均已精确登记 EN 产品，并且其对应 EN 产品 SKU 在赛狐全部存在。本轮新增 3 条完整 `-Cover` 登记：`C/Linen-Coffee-194-661-WOW-Cover`、`C/Linen-Natural-183-688-wow-Cover`、`TT0000750K0063009-Cover`。
17. **配套物料客户码只读调查**：`PK#` 当前 0 条客户码；`HM1510` 有 75 个原始子表行、53 个唯一“物料+客户码”组合、52 个唯一客户码，大量值带“删除”前缀。唯一跨物料重复是 `删除Curve-Pillow-Foam-50`，本轮未修改。

---

## 8. Git 历史（本分支）

```
99b99ed feat(missing_products): 方形枕套 KS0013 补齐 + 窄边正方形抱枕 KS0014 方案(已废弃)
f420693 feat(missing_products): EN 老产品补齐脚本 — 星球/石头/张嘴熊/泰迪熊
8759024 docs(missing_products): 老产品补齐计划 — EN物料/成本→赛狐商品→库存同步
727c86a feat(missing_products): 赛狐缺失商品排查 + EN物料创建惯例文档/skill
```

> 上表只列出早期基础提交。2026-08-10 至 2026-08-11 的赛狐创建、属性导入、主线精确审计和 EN 客户码补齐包含在当前未合并工作区；提交前以 `git log` 与本次 PR diff 为准，不能据此判断尚未完成。

分支：`claude/awesome-satoshi-c903d5`（feature 分支，遵循「不直接提交 main」规则）

---

## 9. 新对话快速上手

1. 读本文档，再读最新主线工作簿与三方审计输出，确认数据时间戳。
2. 先只读运行 `audit_three_systems.py`：应对账为 1411 = 1397 精确登记 + 14 暂缓项；不要直接依据旧的「需创建赛狐商品」页写数据。
3. 对任何新缺口，先检查 EN 产品模板属性、完整 `customer_items`、赛狐 SPU/属性/SKU；缺赛狐属性时生成 Excel，待用户导入确认后才 API 创建产品 SKU。
4. 对 `-Cover`/`-Foam`，完整通途 SKU 必须挂至至少一个产品变体；去后缀基码只用来找候选。候选不唯一时列为待确认，不写入。
5. 若需新建 EN 物料，先运行 `create_en_materials.py --dry-run` 并按 §4.5 属性完整性原则审计。
6. 若需重新生成 BOM Cost List，SSH 服务器跑 `/tmp/gen_bom_xlsx2.py`（见 §4.2）；完成后再审计。
7. 库存同步属于下一阶段，先经用户审阅映射和范围。
