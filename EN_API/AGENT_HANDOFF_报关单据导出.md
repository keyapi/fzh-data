# 销售出库 → 报关单据导出 功能规格说明

> 本规格可直接粘贴给部署在 EN 环境的 Agent 执行开发。
> 目标：根据 ERPNext「销售出库单 (Delivery Note, DN)」的主表 + `items` 明细子表，导出一份含 **4 个固定工作表** 的报关单据 Excel，格式严格对齐海关统一模板。

---

## 0. 背景与目标

- EN 系统 = ERPNext（生产 `https://erpnext.vilavi.cn`，测试 `https://ensh.vilavi.cn`）。
- 销售出库 = ERPNext 标准 `Delivery Note` 文档，明细在 `items` 子表（`Delivery Note Item`）。
- 物料 = ERPNext 标准 `Item` 文档，含大量 `custom_*` 自定义字段（单重/体积/包装等）。
- 参考模板：`数据源/ZJ26DZJR0403-报关单据.xlsx`（4 个 sheet：报关发票 / 装箱单 / 报关合同 / 报关单NEW）。

**产出**：`customs_export.py`（已实现），输入 DN 单号，输出 4-sheet 的 `报关单据_{DN号}.xlsx`。

### 已确认决策（2026-08-19 更新，覆盖下文部分字段）

1. **去除模板自带图片/印章**：模板 3 个 sheet 顶部有「宁波中基惠通集团股份有限公司」抬头图片 + 签名，导出时清除全部图片（`ws._images = []`）。
2. **发票号留空**：报关发票 G9 / 装箱单 H9 / 报关单NEW I2 的「发票号」暂留空（后续人工/系统补）。
3. **境外收货人留空**：报关单NEW C5 及发票/装箱单/合同的「To Messrs / 买方」全部留空（Customer 暂无英文名）。
4. **生产销售单位留空**：报关单NEW A8 不填；但 A4「境内发货人」仍填发货方中文名。
5. **目的国（地区）按客户映射**：DANEEY / CENTRADE / 美国FBA仓 → `UNITED STATES(502)`；波兰公司 → `PL(327)`；后续新增在 `US_CUSTOMERS` / `PL_CUSTOMERS` 里加。**注意**：贸易国(D10)/运抵国(G10) 现已**留空**，该映射目前只用于「最终目的国(K列)」填中文（美国→`美国(502)`）。
6. **单价/总价统一 = BOM 成本**：**4 个 sheet 全部**用 BOM 成本，即单价 = `bom_rate` / 6.8、总价 = `bom_cost` / 6.8、TOTAL = `Σbom_cost` / 6.8。汇率暂定 6.8（人民币→美元），后续换汇率表。
7. **境内货源地 = 常量** `绍兴市（33069）`。
8. **装箱单 Package 列 = 用户填写**：当前通过 `PACKAGE_BY_DN[DN单号]` 字典按物料编码写死（DN-26-00063、DN-24-00575 已录入），后续改为弹窗让用户填写确认。
9. **内胆等零价值/零重量物料暂搁置**：内胆 `bom_rate=0`、`bom_cost=0`、毛净重/体积=0（EN 未维护内胆成本与重量），当前导出为 0，**暂不处理**；待后续确认后再调整这些字段的取值来源。
10. **英文品名翻译 = 简单 DeepSeek 直连**（已实现）：对中文品名（去色后）直接调 DeepSeek 翻译成英文，**不涉及任何关联查询**。详见 §13。
11. **报关合同留空**：`Time of Shipment(装运期)`(E39)、`TERMS OF PAYMENT`(E43) 留空。
12. **报关单NEW 留空**：出境关别(G4)、运输方式(G6)、贸易国(D10)、运抵国(G10)、指运港(J10)、离境口岸(L10)、申报单位(A54) 均留空。
13. **所有小数统一保留 3 位**：单价/总价/金额/毛重/净重/体积等所有带小数的数值，用 `number_format='0.000'` 强制 3 位（补零对齐，多退少补）；整数（数量/件数/项号）不参与。

---

## 1. 四个工作表（固定名称，顺序不可变）

| # | Sheet 名 | 对应单据 | 语言 |
|---|----------|----------|------|
| 0 | `报关发票 ` (INVOICE) | 商业发票 | 英文 |
| 1 | `装箱单` (PACKING LIST) | 装箱单 | 英文 |
| 2 | `报关合同 ` (SALES CONFIRMATION) | 销售确认书/合同 | 英文+中文注释 |
| 3 | `报关单NEW ` (Customs Declaration) | 出口货物报关单 | 中文（含英文名称列） |

> 注意 sheet 名末尾有空格（`报关发票 `、`报关合同 `、`报关单NEW `），是从模板继承的，建议保留以对齐模板。

---

## 2. 数据来源与聚合规则

### 2.1 数据源

1. **DN 主表**（`/api/resource/Delivery Note/{name}`，`docstatus=1`）：
   - `name`（单号，兼作发票号/合同号）
   - `posting_date`（出库日期）
   - `customer`（客户 → 境外收货人/买方）
   - `items` 子表

2. **DN Item 子表**（每行字段）：
   - `item_code`（物料编码，如 `PK#KS0001-QDKTR-100-WHITE`）
   - `item_name`（物料名称，如 `皮壳#三角靠枕-全涤宽条绒-100-白色`）
   - `qty`（数量）、`uom`（单位）
   - `rate`（单价）、`amount`（金额 = rate×qty）

3. **Item 主数据**（`/api/resource/Item`，按 `item_code` 查）：
   - 重量/体积/包装相关自定义字段（见 §9，字段名需在 ERPNext 实例核对）
   - `item_languages` 子表（`tt_sku` / `item_name_cn` / `item_name_es`）— 目前只有中文+西语

### 2.2 物料编码/命名规则（关键）

- 编码：`<类别前缀>#<款式ID>-<面料码>-<尺寸>-<颜色>`
  - 例：`PK#KS0001-QDKTR-100-WHITE`
  - `PK`=皮壳(类别前缀)、`KS0001`=款式ID、`QDKTR`=面料、`100`=尺寸、`WHITE`=颜色
- 名称：`<类别>#<款式名>-<面料名>-<尺寸>-<颜色>`
  - 例：`皮壳#三角靠枕-全涤宽条绒-100-白色`

### 2.3 聚合规则（核心逻辑）

**去掉颜色维度，按「款式-面料-尺寸」汇总**：

1. 对每个 DN Item 的 `item_code` / `item_name`，**去掉最后一个 `-` 段（颜色）**：
   - `PK#KS0001-QDKTR-100-WHITE` → `PK#KS0001-QDKTR-100`
   - `皮壳#三角靠枕-全涤宽条绒-100-白色` → `皮壳#三角靠枕-全涤宽条绒-100`
2. 按去色后的 key 分组，聚合：
   - `qty` 求和 → 总数量
   - `amount` 求和 → 总金额
   - `单价` = 总金额 / 总数量（加权平均，保留 4 位小数）
3. 一个 DN 可能含多种类别前缀（如 `PK#`皮壳、其它靠枕/沙发等），分组时**保留类别前缀段**，仅去颜色段。

> 尺寸段形如 `100`、`90x40x50`，用 `x` 连接不出现 `-`，因此「按 `-` 切分去掉最后一段」是安全的。

---

## 3. Sheet 0 — 报关发票 (INVOICE)

尺寸参考：A1:J35（数据行数可变），列宽 B=15.1 C=31 D=18.5 E=9 G=16.4。

| 单元格 | 合并 | 内容 / 字段映射 |
|--------|------|----------------|
| B2 | B2:G2 | 发货方中文名：`方州汇国际电子商务（北京）有限公司` |
| B3 | B3:G3 | 发货方英文名（需提供/确认，见 §7） |
| B4 | B4:G4 | 发货方英文地址（需提供/确认） |
| B5 | B5:G5 | 固定 `INVOICE` |
| B7 | — | 固定 `To Messrs:` |
| B8 | B8:C11 | 买方 = DN.customer 英文名 + 地址（多行，`\n` 分隔） |
| F8 / G8 | — | `Date.` / `posting_date` |
| F9 / G9 | — | `Invoice No.` / DN.name |
| F10 / G10 | — | `Sales Contract No.` / DN.name |
| F11 | — | `Letters of Credit No.`（留空） |
| B13 / C13 | — | `Transport Detail:` / 运输路线常量（见 §7） |
| D13 / F13 | F13:G13 | `Terms of Payment:` / 付款方式常量（见 §7） |
| B14 | — | `Marks & Number.`（表头，固定） |
| C14 | C14:E14 | `Description of Goods & Quantity`（表头） |
| F14 / G14 | — | `Unit price` / `Total Amount`（表头） |
| F15 | F15:G15 | 成交方式，如 `FOB NINGBO,CHINA`（见 §7） |
| **数据行 16..N** | | 每个聚合后的物料一行 |
| C{行} | — | 品名（英文，翻译 `name_en`，见 §13） |
| D{行} | — | 总数量（数值） |
| E{行} | — | 英文单位（PIECES / SETS，见 §7 单位映射） |
| F{行} | — | 单价（3 位小数） |
| G{行} | — | 总金额 |
| C{合计行} / D / F / G | — | `TOTAL:` / 总数量 / `USD` / 总金额 |
| C{末行} | — | `TOTAL PACKED IN <箱数英文大写> CTNS`（数字转英文，见 §7） |

> 数据行数 = 聚合后的物料种类数（样例 16 行）。B15:B33 为「唛头」竖列合并（样例留空），按需保留。

---

## 4. Sheet 1 — 装箱单 (PACKING LIST)

尺寸参考：B1:L41，列宽 B=17 C=19 D=13.6 E=11 F=12.6 H=9.6 J=7.1。

| 单元格 | 合并 | 内容 / 字段映射 |
|--------|------|----------------|
| B2 | B2:J2 | 发货方中文名 |
| B3 | B3:J3 | 发货方英文名 |
| B4 | B4:J4 | 发货方英文地址 |
| B5 | B5:J5 | 固定 `PACKING LIST` |
| B7 | — | 固定 `To Messrs:` |
| B8 | B8:E11 | 买方英文名+地址 |
| F8 / H8 | — | `Date:` / posting_date |
| F9 / H9 | — | `Invoice No.:` / DN.name |
| F10 / H10 | — | `S/C No.:` / DN.name |
| B13 / C13 | C13:K13 | `Transport Detail:` / 运输路线常量 |
| B15 | — | `Marks & Number.`（表头） |
| C15 / D15 / E15 | — | `Description of Goods` / `Quantity` / `Package`（表头） |
| F15 | F15:G15 | `Gross Wt`（表头） |
| H15 | H15:I15 | `Net Wt`（表头） |
| J15 | J15:K15 | `Measrs`（表头） |
| **数据行 17..N** | | |
| C{行} | — | 品名（英文） |
| D{行} | — | `{qty} {英文单位}`，如 `31 PIECES` |
| E{行} | — | `{箱数}CTNS`，如 `1CTNS`（无空格） |
| F{行} | — | 毛重 Gross Wt（kg，数值） |
| H{行} | — | 净重 Net Wt（kg，数值） |
| J{行} | — | 体积 Measrs（CBM，数值，3 位小数） |
| C{合计} / E / F / H / J | — | `TOTAL：` / `{总箱数} CTNS` / 毛重合计 / 净重合计 / 体积合计 |
| G{合计} / I{合计} / K{合计} | — | `KGS` / `KGS` / `CBM`（单位标签） |
| D36 | D36:K36 | `TOTAL PACKED IN <箱数英文大写> CTNS` |
| D37 | D37:K37 | `TOTAL GROSS WEIGHT {毛重合计}KGS` |
| D38 | D38:K38 | `TOTAL NET WEIGHT {净重合计}KGS` |
| D39 | D39:K39 | `TOTAL MEASUREMENTS {体积合计}M3` |

> 毛重/净重/体积/箱数计算公式见 §9（字段需在 ERPNext 实例确认）。

---

## 5. Sheet 2 — 报关合同 (SALES CONFIRMATION)

尺寸参考：A1:J53，列宽 B=9 C=9.9 D=12.9 E=10 F=9 H=10.1 J=13.8。

| 单元格 | 合并 | 内容 / 字段映射 |
|--------|------|----------------|
| B2 / B3 / B4 | B2:J2 等 | 发货方中文名 / 英文名 / 地址 |
| D6 | — | 固定 `SALES CONFIRMATION` |
| H7 / I7 | — | `S/C NO：` / DN.name |
| B8 / H8 / I8 | — | `To Messrs:` / ` Date：` / 合同日期 |
| B9 | B9:J11 | 买方英文名+地址 |
| B12 | — | 固定 `(卖买双方根据下列规定之条款达成以下交易)` |
| B13 / C14 | — | `⑴Name of Commodity & Specifications` / `(货物名称及规格)` |
| F13 / F14 | — | `⑵Quantity` / `(数 量）` |
| H13 / H14 | — | `⑶Unit Price` / `(单  价)` |
| J13 / J14 | — | `⑷Amount` / `(金  额)` |
| H15 / J15 | H15:I15 | `FOB NINGBO,CHINA` / `USD` |
| **数据行 16..N** | | |
| B{行} | — | 品名（英文） |
| F{行} / G{行} | — | 数量 / 英文单位 |
| H{行} / I{行} | — | 单价 / `/PIECES`（或 `/SETS`） |
| J{行} | — | 金额 |
| B33 / F33 / J33 | — | `TOTAL:` / 总数量 / 总金额 |
| B34 | — | 固定 `With 5 % more or less ...` |
| B35 / D35 | — | `5.Packing（包装）：` / `suitable for international transportation` |
| B36 / D36 | — | `6.Shipping Marks(唛头):` / `AS PER INVOICE` |
| B39 / E39 | — | `7.Time of Shipment(装运期):` / 装运日期（posting_date） |
| B40 / F40 | — | `8.Ports of Shipment & Destination(...)：` / 运输路线 |
| B41 | — | 固定 `Partial Shipments and Transshipments Not Allowed` |
| B42 / D42 | — | `9.Insurance (保险)：` / `AS ARRANGED` |
| B43 / E43 | — | `10.TERMS OF PAYMENT:` / `BY T/T 90 DAYS`（付款方式常量） |
| B45 | — | `11.Remarks(备注):`（留空或备注） |
| B46 | — | 固定 AEO 条款（可选保留） |
| B47 / H47 | — | `SELLERS（卖方）：` / ` BUYERS（买方）：` |
| H48 | H48:J50 | 买方英文名 |

---

## 6. Sheet 3 — 报关单NEW (Customs Declaration)

尺寸参考：A1:Y64，列宽 A=6.5 B=13.1 C=15.9 D=17 E=14.2 F=0.5 G=11 H=11.2 I=8.5 J=12.2 K=14.8 L=12.9 M=10.5 N=8.1。

> ⚠️ **按已确认决策 12**：下表 G4(出境关别)、G6(运输方式)、D10(贸易国)、G10(运抵国)、J10(指运港)、L10(离境口岸)、A54(申报单位) 当前均**留空**（单元格填 None）。

### 6.1 顶部信息区（固定坐标，直接填值）

| 单元格 | 内容 / 字段映射 |
|--------|----------------|
| A1 (A1:N1) | 固定 `中华人民共和国海关出口货物报关单` |
| A2 | `预录入编号:` |
| H2 / I2 | `发票号：` / DN.name |
| K2 | `委托协议号:` |
| A3 / G3 / I3 / K3 / L3 | `境内发货人` / `出境关别` / `出口日期` / `申报日期` / `备案号` |
| G4 | 出境关别值（如 `NINGBO,CHINA`，见 §7） |
| A5 / C5 | `境外收货人` / 买方英文名 |
| G5 / I5 / K5 | `运输方式` / `运输工具名称及航次号` / `提运单号` |
| G6 | 运输方式值（如 `BY SEA`） |
| A7 / G7 / I7 / K7 | `生产销售单位` / `监管方式` / `征免性质` / `许可证号` |
| G8 | 监管方式值（如 `一般贸易`） |
| A9 / D9 / G9 / J9 / L9 | `合同协议号` / `贸易国（地区）` / `运抵国（地区）` / `指运港` / `离境口岸` |
| A10 / D10 / G10 / J10 / L10 | DN.name / 贸易国（如 `UNITED STATES(502)`）/ 运抵国 / 指运港（如 `LONG BEACH,UNITED STATES`）/ 离境口岸（如 `NINGBO,CHINA`） |
| A11 / D11 / E11 / G11 / H11 / I11 / K11 / M11 | `运输包装种类` / `件数` / `毛重（千克）` / `净重（千克）` / `成交方式` / `运费` / `保费` / `杂费` |
| A12 / D12 / E12 / G12 / H12 | `CTNS` / 总箱数 / 毛重合计 / 净重合计 / `FOB` |
| A13 | `随附单证及编号` |
| A15 | `标记唛码及备注` |

### 6.2 明细表头（第 17 行）

`项号 | 商品编号 | 中文名称 | 英文名称 | 数量单位(合并F) | 单价 | 总价 | 币制 | 原产国(地区) | 最终目的国(地区) | 境内货源地/产地 | 征免`

### 6.3 明细数据行（每物料占 2 行）

- **第 N 行（项号行，偶数行，从 18 开始）**：

| 列 | 字段映射 |
|----|----------|
| A 项号 | 顺序号 1,2,3… |
| B 商品编号 | HS 编码（**留空**，见 §8） |
| C 中文名称 | 去色后的物料名称（如 `皮壳#三角靠枕-全涤宽条绒-100`） |
| D 英文名称 | 翻译后的英文 `name_en`（见 §13；HS/英文名当前留空） |
| E 数量单位 | `{qty}{中文单位}`，如 `31只`、`185套` |
| G 单价 | 单价（加权平均） |
| H 总价 | 总金额 |
| I 币制 | `USD` |
| J 原产国（地区） | `中国` |
| K 最终目的国（地区） | `美国(502)`（常量，见 §7） |
| L 境内货源地/产地 | 产地常量（见 §7，样例 `宁波其他(33029)` 等） |
| M 征免 | 留空 |

- **第 N+1 行（申报要素行，奇数行）**：A:B 合并（空），C:N 合并，内容为「申报要素」（**留空**，见 §8）。

> 样例 16 个物料占 18~48 行。合并区间逐行生成：偶数行 `A{row}:B{row}` 合并、`C{row}:N{row}` 合并。报关单模板每页行数有限（样例 16 项），若物料过多需分页或扩展，v1 先按「扩展行数」处理并记录该限制。

### 6.4 底部区（固定坐标）

| 单元格 | 内容 |
|--------|------|
| A51 (A51:H51) | `TOTAL：USD {总金额}` |
| A52 / D52 / G52 / K52 | `特殊关系确认：否` / `价格影响确认：否` / `支付特许权使用费确认：否` / `自报自缴：` |
| A53 / C53 / D53 / K53 | `申报人员` / `申报人员证号` / `电话` / `海关批注及签章` |
| A54 (A54:D54) / H54 | 申报单位（如 `申报单位  宁波市鸿欣报关有限公司`，见 §7）/ `申报单位（签章）` |

---

## 7. 常量与配置项（建议做成脚本顶部字典/配置，勿硬编码散落）

| 配置项 | 说明 | 样例值 | 状态 |
|--------|------|--------|------|
| 发货方中文名 | 报关抬头 | `方州汇国际电子商务（北京）有限公司` | 已定 |
| 发货方英文名 | 中文名对应英文译名 | 待提供/确认 | **需确认** |
| 发货方英文地址 | 英文注册地址 | 待提供/确认 | **需确认** |
| 买方 | DN.customer → Customer 英文名+地址 | 待确认 Customer 是否有英文名/地址字段 | **需确认** |
| 币制 | 报关币种 | `USD` | 可配 |
| 成交方式 | Invoice/合同/报关单 | `FOB`（及 `FOB NINGBO,CHINA`） | 可配 |
| 付款方式 | Invoice/合同 | `AFTER 90 DAYS` / `BY T/T 90 DAYS` | 可配 |
| 运输路线 | 起运港→目的港 | `FROM NINGBO,CHINA TO LONG BEACH,UNITED STATES BY SEA` | 可配 |
| 运输方式 | 报关单 | `BY SEA` | 可配 |
| 监管方式 | 报关单 | `一般贸易` | 可配 |
| 原产国/最终目的国 | 报关单 | `中国` / `美国(502)` | 可配 |
| 境内货源地 | 报关单 L 列 | `绍兴市（33069）`（已确认常量） | 已定 |
| 申报单位 | 报关单底部 | `宁波市鸿欣报关有限公司` | 可配 |
| 数字转英文 | 箱数大写 | 658 → `SIX HUNDRED AND FIFTY EIGHT` | 需写 num2words 工具 |
| 单位映射（中文） | 报关单NEW 数量单位 | `件→只/个/条`、`套→套` 等 | **需确认** EN 的 uom 实际取值 |
| 单位映射（英文） | 发票/装箱单/合同 | `件→PIECES`、`套→SETS` | 需确认 |

---

## 8. 已确认「留空」的字段（本版本不填充，结构保留）

1. ~~**英文名称**~~（已改为「复用 EN 翻译功能」，见 §13，不再留空）。
2. **HS 编码（商品编号）**（报关单NEW B 列）→ 留空。
3. **申报要素**（报关单NEW 每个物料的第 2 行）→ 留空。
4. **唛头 Marks & Number**（发票/装箱单 B 列竖排）→ 留空。
5. **发票号**（报关发票 G9 / 装箱单 H9 / 报关单NEW I2）→ 留空。
6. **境外收货人 / To Messrs / 买方**（报关单NEW C5 + 发票 B8 + 装箱单 B8 + 合同 B9、H48）→ 留空（Customer 暂无英文名）。
7. **生产销售单位**（报关单NEW A8）→ 留空（境内发货人 A4 仍填发货方中文名）。
8. **模板自带图片/印章/签名**（宁波中基惠通集团股份有限公司抬头）→ 导出时清除全部图片。

---

## 9. 装箱数据来源（已实测：用 DN 子表，不用 Item 主数据）

装箱单的毛重/净重/体积/箱数，**实际来源是 DN 的子表**（不是 Item 主数据的 `custom_*` 字段——那些字段实测全是 0，不可靠）：

| 装箱单字段 | 实际来源 |
|-----------|----------|
| 箱数 Package | `PACKAGE_BY_DN[DN号]`（用户填写）优先，否则 `DN.outer_box_summary` 行数 |
| 毛重 Gross | `Σ DN.outer_box_summary[].outer_carton_weight`（kg） |
| 体积 Measrs | `Σ DN.outer_box_summary[].outer_carton_volume` / 1,000,000（m³） |
| 净重 Net | `Σ DN.item_weight_cats[].item_weight` / 1000（g→kg） |

**注意**：

- 这些子表**不是所有 DN 都有**：2024 旧 DN（如 DN-24-00575）`outer_box_summary`/`item_weight_cats` 为空 → 毛净重/体积全 0，仅箱数由用户提供。
- 2026 新 DN（如 DN-26-00063）有完整装箱数据（2 箱、毛重 36.15kg、净重 33.5kg、体积 0.165m³）。

> ⚠️ 部署到 EN 时，若需自动算毛净重/体积，应优先读 DN 的 `outer_box_summary`/`item_weight_cats` 子表，而不是 Item 主数据的 `custom_*` 字段。

---

## 10. 可复用的现有代码/模式（在 EN_API 仓库内）

| 文件 | 可复用内容 |
|------|-----------|
| `dn_trace_report.py` | DN 拉取模式：`paginated_get("Delivery Note", ...)` + `get_single("Delivery Note", name)` 取含 `items` 子表的完整文档；`load_credentials(env)` 凭证；nginx 417 处理 |
| `shopify_to_en.py` / `write_us_sku_languages.py` | `ErpnextClient` 类（`_NoExpectAdapter` 去掉 Expect 头）、`_get/_put`、SKU→Item 映射 API `vilavi_pim.api.pim_api.get_sku_item_itemgroup_mapping` |
| `upload_pim_images.py` | openpyxl 写入、`item_languages`/子表读写参考 |
| `数据源/ZJ26DZJR0403-报关单据.xlsx` | **推荐作为模板**：复制后填充，保留全部合并单元格/边框/字体/列宽 |

**实现建议**：用 openpyxl 打开模板文件 → 覆盖顶部固定单元格（公司/买方/日期/单号）→ 清空并重写明细数据行 → 重写合计行 → 保存为新文件。相比从零构建，模板填充能 100% 对齐格式。数据行数变化时，用 openpyxl 的 `insert_rows` / `delete_rows` 调整后再填。

---

## 11. 验证方法（端到端）

✅ **已实测通过**：`DN-26-00063`（2026，6 行明细→2 行聚合，有 bom_cost + 装箱数据）、`DN-24-00575`（2024，50 行明细→40 行聚合，bom_cost=0 + 无装箱数据，翻译 40 个物料并行完成）。

1. **环境**：先 `--env test`（`ensh.vilavi.cn`）跑通，再切 `prod`。
2. **取一个真实 DN**：`python dn_trace_report.py --dn DN-xxx --test` 确认能拉到该 DN 及 `items`。
3. **拉一个真实 Item**：确认 §9 的重量/体积字段真实 fieldname 与是否有值。
4. **生成导出文件**：运行新脚本 `python customs_export.py --dn DN-xxx --env test`。
5. **逐 sheet 核对**：
   - 4 个 sheet 名、顺序、合并单元格、列宽与模板一致；
   - 明细行数 = 去色聚合后的物料种类数；
   - 同款式不同颜色（如 `…-100-WHITE` 与 `…-100-BLACK`）被合并为一行，数量=两者之和；
   - 合计行（数量/金额/毛净重/箱数/体积）等于各明细之和；
   - 报关单NEW 的 C 列中文名为「去色后的物料名称」，D 列/B 列/申报要素为空。
6. **边界**：空 DN（无 items）、单物料、多颜色同款式、跨类别前缀（PK# 与其它）各自成行。

---

## 12. 交付状态（customs_export.py 已实现）

**脚本 `customs_export.py` 已实现并实测通过**（DN-26-00063、DN-24-00575 两个真实 DN 均已验证）。当前能力：

- [x] 拉取 DN 主表 + items 子表（REST API，凭证从 `.env` 读）
- [x] 去色聚合（§2.3）
- [x] 4 个 sheet 按 §3~§6 填充（模板填充法，`load_workbook(TEMPLATE)` + 覆盖单元格）
- [x] 清除模板自带图片/印章（`ws._images = []`）
- [x] 装箱单 Package 列 = `PACKAGE_BY_DN[DN号]` 字典（用户录入）
- [x] 英文品名 = 并行 DeepSeek 翻译（§13）
- [x] 数字转英文大写（箱数 `TOTAL PACKED IN ... CTNS`）
- [x] 单位映射（中文/英文，`CONFIG["uom_map"]`）
- [x] 所有小数统一 `number_format='0.000'`（3 位）
- [x] 常量配置字典（§7）
- [x] 输出 `out/报关单据_{DN号}.xlsx`

**待办（部署到 EN 时）**：

- [ ] 翻译改走 EN `AIContentGenerator`（`vilavi_pim/utils/ai.py`），配置从 PIM Settings 读（见 §13）
- [ ] 装箱单 Package 从字典改为弹窗录入
- [ ] 报关单 NEW 申报要素 / HS 编码 / 英文名称的后续数据源（当前留空）
- [ ] 汇率 6.8 换汇率表
- [ ] 2024 旧 DN 价格缺失（bom_rate=0）的处理

---

## 13. 英文品名翻译（已实现：简单 DeepSeek 直连）

### 实现方式

报关品名的英文翻译，**直接调用 DeepSeek API 把中文品名（去色后）翻译成英文**，不涉及任何关联查询。已落地在 `customs_export.py`：

- **端点**：`https://api.vilavi.cn/v1/chat/completions`（用户 AI 网关）
- **模型**：`deepseek-v4-flash`（网关 `/v1/models` 可查；`deepseek-v4-pro` 会超时，勿用）
- **密钥**：`DEEPSEEK_API_KEY`（从环境变量或 `EN_API/.env` 读）
- **行为**：对每个聚合物料的 `name_agg`（中文）翻译一次；**并行翻译**（`ThreadPoolExecutor` 5 线程，进度实时打印 `[i/N]`）；失败重试 3 次（间隔 3s，timeout 60s），仍失败则回退中文原文；`temperature=0.3`
- **Prompt**：「你是专业的海关报关品名翻译助手…只输出英文品名本身」

需求落点：

| Sheet | 列 | 值 |
|-------|-----|-----|
| 报关单NEW | C 中文名称 | 中文 `name_agg`（保持） |
| 报关单NEW | D 英文名称 | 英文 `name_en` |
| 报关发票 | C Description | 英文 `name_en` |
| 装箱单 | C Description | 英文 `name_en` |
| 报关合同 | B Name of Commodity | 英文 `name_en` |

实测效果（DN-26-00063）：

- `皮壳#三角靠枕-全涤宽条绒-100` → `Triangle Pillow, 100% Polyester Wide Wale Corduroy`
- `内胆#三角靠枕-100-春亚纺` → `Triangular Cushion Insert, 100cm, Polyester Pongee`

### 部署到 EN 后的替换（待办）

- 当前直连 `api.vilavi.cn` + `.env` 密钥；部署到 EN 后改为调用 EN 现有 `AIContentGenerator`（`vilavi_pim/utils/ai.py`），其 AI Provider / API密钥 / API端点 / Model Name 均从 **PIM Settings** 读取（已探明：`ai_provider=DeepSeek`、`api_endpoint=https://api.deepseek.com/v1`、`model=deepseek-chat`，`api_key` 为密码字段、REST 返回掩码，仅服务端 `frappe.get_doc().get_password()` 可读）。

### 待确认

- **一致性**：报关品名要求同一物料每次导出英文一致（海关核验）。当前为每次实时翻译，同一中文可能偶发措辞漂移（如 `Triangle Cushion` vs `Triangular Cushion`）。如需严格一致，可后续加缓存/固化存储（Item 新增 `item_name_en`）。
- **品名粒度**：当前按「款式-面料-尺寸」整段翻译；是否需要精简为款式级（如 `Triangle Pillow`）由业务确认。
