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
3. **境外收货人**：报关单NEW C5 填收货人预设**名称+地址**（`CONSIGNEE_DATA`，CLI `--consignee`/弹窗下拉选择；未指定且客户无法自动映射时**兜底默认 `centrade`**，不再保留模板 BO MITE 样例）。发票/装箱单/合同的「To Messrs / 买方」仍留空（如需区分可配置）。
4. **境内收货人(境内发货人 A4) 与 生产销售单位(A8) 固定同一主体**：`CONFIG["domestic_party_cn"] = "（9111010856368328XF）（11149609R4）方州汇国际电子商务(北京)有限公司"`（不在弹窗体现）。与模板 A4/A8 现填值逐字符一致。
5. **目的国（地区）按客户映射**：DANEEY / CENTRADE / 美国FBA仓 → `UNITED STATES(502)`；波兰公司 → `PL(327)`；后续新增在 `US_CUSTOMERS` / `PL_CUSTOMERS` 里加。**注意**：贸易国(D10)/运抵国(G10) 现已**留空**，该映射目前只用于「最终目的国(K列)」填中文（美国→`美国(502)`）。
6. **单价/总价统一 = BOM 成本 × 加成 ÷ 汇率**：**4 个 sheet 全部**用 BOM 成本，即单价 = `bom_rate` × 1.45 ÷ 6.8、总价 = `bom_cost` × 1.45 ÷ 6.8、TOTAL = `Σbom_cost` × 1.45 ÷ 6.8（`usd_price()` 封装，**先 ×1.45 涨价、最后 ÷ 汇率，仅最终一步取整 3 位**）。汇率暂定 6.8、加成系数 `price_markup=1.45`（均暂定，后续换汇率表/确认加成）。
7. **境内货源地 = 常量** `绍兴市（33069）`。
8. **装箱单 Package 列 = 用户填写**：当前通过 `PACKAGE_BY_DN[DN单号]` 字典按物料编码写死（DN-26-00063、DN-24-00575 已录入），后续改为弹窗让用户填写确认。
9. **内胆等零价值/零重量物料暂搁置**：内胆 `bom_rate=0`、`bom_cost=0`、毛净重/体积=0（EN 未维护内胆成本与重量），当前导出为 0，**暂不处理**；待后续确认后再调整这些字段的取值来源。
10. **英文品名翻译 = 简单 DeepSeek 直连**（已实现）：对中文品名（去色后）直接调 DeepSeek 翻译成英文，**不涉及任何关联查询**。详见 §13。
11. **报关合同留空**：`Time of Shipment(装运期)`(E39)、`TERMS OF PAYMENT`(E43) 留空。
12. **报关单NEW 留空**：出境关别(G4)、运输方式(G6)、贸易国(D10)、运抵国(G10)、指运港(J10)、离境口岸(L10) 留空；**申报单位 A54 改为「仅当传入 `declaration_unit` 时写入，否则保留模板原值」**（不再无条件清空）。
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
| A4 | 境内收货人值：`（9111010856368328XF）（11149609R4）方州汇国际电子商务(北京)有限公司`（`CONFIG["domestic_party_cn"]`，同 A8） |
| G4 | 出境关别值（如 `NINGBO,CHINA`，见 §7；当前留空） |
| A5 / C5 | `境外收货人` / 名称+地址（`CONSIGNEE_DATA` 预设，C5 合并 C5:F6 两行显示；未指定且客户无法映射时兜底默认 `centrade`） |
| G5 / I5 / K5 | `运输方式` / `运输工具名称及航次号` / `提运单号` |
| G6 | 运输方式值（如 `BY SEA`） |
| A7 / G7 / I7 / K7 | `生产销售单位` / `监管方式` / `征免性质` / `许可证号` |
| A8 | 生产销售单位值：同 A4 `（9111010856368328XF）（11149609R4）方州汇国际电子商务(北京)有限公司`（`CONFIG["domestic_party_cn"]`，固定，不在弹窗体现） |
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
| A54 (A54:D54) / H54 | 申报单位：仅当传入 `declaration_unit` 才写 `申报单位  {value}`，否则保留模板原值 / `申报单位（签章）` |

---

## 7. 常量与配置项（建议做成脚本顶部字典/配置，勿硬编码散落）

| 配置项 | 说明 | 样例值 | 状态 |
|--------|------|--------|------|
| 发货方中文名 | 报关抬头 | `方州汇国际电子商务（北京）有限公司` | 已定 |
| 发货方英文名 | 中文名对应英文译名 | 待提供/确认 | **需确认** |
| 发货方英文地址 | 英文注册地址 | 待提供/确认 | **需确认** |
| 买方 | DN.customer → Customer 英文名+地址 | 待确认 Customer 是否有英文名/地址字段 | **需确认** |
| 币制 | 报关币种 | `USD` | 可配 |
| 汇率 | 人民币→美元 | `6.8`（暂定，后续换汇率表） | 可配 |
| 报关单价加成 | 单价 = BOM成本 ÷ 汇率 × 加成 | `1.45`（`CONFIG["price_markup"]`，暂定） | 可配 |
| 成交方式 | Invoice/合同/报关单 | `FOB`（及 `FOB NINGBO,CHINA`） | 可配 |
| 付款方式 | Invoice/合同 | `AFTER 90 DAYS` / `BY T/T 90 DAYS` | 可配 |
| 运输路线 | 起运港→目的港 | `FROM NINGBO,CHINA TO LONG BEACH,UNITED STATES BY SEA` | 可配 |
| 运输方式 | 报关单 | `BY SEA` | 可配 |
| 监管方式 | 报关单 | `一般贸易` | 可配 |
| 原产国/最终目的国 | 报关单 | `中国` / `美国(502)` | 可配 |
| 境内货源地 | 报关单 L 列 | `绍兴市（33069）`（已确认常量） | 已定 |
| 申报单位 | 报关单底部 | `宁波市鸿欣报关有限公司` | 可配 |
| 境外收货人 | 报关单NEW C5 | `CONSIGNEE_DATA` 预设：centrade/daneey/poland + 自定义；兜底默认 `centrade` | 可配 |
| 境内收货人/生产销售单位 | 报关单NEW A4/A8 | `（9111010856368328XF）（11149609R4）方州汇国际电子商务(北京)有限公司`（`CONFIG["domestic_party_cn"]`，固定，不在弹窗体现） | 已定 |
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
6. **境外收货人 / To Messrs / 买方**：报关单NEW C5 已改为填充（见决策3）；发票/装箱单/合同的 To Messrs / 买方 仍留空（如需可配置）。
7. **境内收货人/生产销售单位**：报关单NEW A4/A8 已改为固定 `CONFIG["domestic_party_cn"]`（`（9111010856368328XF）（11149609R4）方州汇国际电子商务(北京)有限公司`，见决策4）。
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
- [x] 境外收货人预设（`CONSIGNEE_DATA`，CLI `--consignee`）+ 生产销售单位固定值（A8）+ 申报单位按需写入（A54）（2026-08-25）

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

---

## 14. 交接信息（2026-08-24，供新对话接手）

### 工作方式（重要）
- 仓库根：`D:/Claude Demo/fzh-data`（git）。**在主检出使用持久分支 `feature/customs-export`，不要新建 worktree / 分支。**
- 继续前先切分支：`git checkout feature/customs-export`
- 改完直接提交 + `git push`，PR #193 自动更新
- 凭证：`EN_API/.env` 有 `PROD_ERP_API_KEY/SECRET` + `DEEPSEEK_API_KEY`（gitignored，磁盘上已有）

### 当前状态
- 分支 `feature/customs-export` 已提交（首提 `6607a99`），已推送，PR #193（base: main）
- 文件：`EN_API/customs_export.py`（主脚本）+ 本文档
- 模板：`EN_API/数据源/ZJ26DZJR0403-报关单据.xlsx`
- 已测输出：`EN_API/out/报关单据_DN-{24-00575,26-00056,26-00063}.xlsx`
- 主检出上 `.claude/launch.json` 的修改已 stash（非本功能相关，回 dev 可 pop）

### 功能概述
销售出库(DN) → 4-sheet 报关 Excel：去色聚合 → 并行 DeepSeek 英文翻译（发票/装箱单/合同品名列 + 报关单NEW D 列英文，C 列中文）→ 装箱组合(混装)算每物料箱数/毛净重/体积 → 超 16 行自动插行。价格 = bom_rate/bom_cost ÷ 6.8(USD)，小数 3 位。

### 审查结论（PR #193 同事 Agent 已评审：装箱组合模型可行，但当前不能作正式报关依据）
- **P0-1 逐物料数量硬对账**：`packed_qty[item] = Σ(group.carton_qty × item.qty_per_carton)` 必须与 DN 数量一致（生产 DN-26-00056 差 35 件，19 物料仅 5 个一致）。未装/超装/方案有而 DN 没有/DN 有而方案未覆盖 → 禁止生成正式文件（只允许草稿）。
- **P0-2 物料"箱数"语义**：`c_cartons[code] += c` 是「涉及箱数」非「独占箱数」，混装相加 > 物理总箱（DN-26-00056：295 vs 实际 95）。应改为 `involved_cartons` 或输出箱号/箱号范围，明细行箱数禁止用于总箱数，总箱数只从 `sum(group.carton_qty)`，混装行标 `MIXED/SHARED`，装箱单建议按组合/箱号展示。
- **P1-3 重量分摊**：净重优先按实际单重加权（理论重=qty×单重），数量占比仅作 fallback；单重缺失需黄警 + 记录 `allocation_method`；箱皮重单独分摊；处理 3 位小数尾差。
- **业务待确认（最大未决风险）**：皮壳+内胆如何申报 —— A 完整成品（用皮壳数作套数） vs B 分别申报。需报关行确认，**当前不要固化"隐藏内胆"**。
- **架构**：建议「物理装箱层」（记录含内胆的全部实物）与「报关商品映射层」（物理组件→申报商品/HS/申报要素）解耦。
- **Frappe 模型**（部署到 EN 时）：`Customs Packing Plan`(DN/状态/版本/确认人) → `Customs Packing Group`(组合/箱号范围/每箱毛净重/CBM) → `Customs Packing Group Item`(物料/每箱数量/单重来源/分摊结果)，后续加 `Customs Declaration Mapping`。弹窗交互：左侧组合、右侧物料、固定显示 `DN数量/已装/剩余/超装`、红(阻断)/黄(警告)分开、草稿与确认分离、DN 修改后方案失效重确认。

### 建议下一步（P0）
1. 实现逐物料数量硬对账门槛（`packed_qty` vs DN 数量，未装/超装阻止正式导出）
2. 修复箱数语义/按组合展示（involved_cartons、箱号范围、MIXED 标记）
3. （P1）净重按实际单重加权分摊

### 验证命令
```bash
cd "D:/Claude Demo/fzh-data/EN_API"
python customs_export.py --dn DN-26-00056   # 生产，19 项并行翻译约 1-2 分钟
# 输出 out/报关单据_DN-26-00056.xlsx，逐 sheet 核对
```

### 境外收货人 / 生产销售单位 / 申报单位（2026-08-25 新增）

弹窗/CLI 可选收货人预设，导出时自动填 C5 境外收货人（名称+地址）；生产销售单位 A8 固定；申报单位 A54 按需写入。

- **常量**：`CONSIGNEE_DATA`（centrade/daneey/poland 名称+地址，新增只改这一处）、`DEFAULT_CONSIGNEE="centrade"`（弹窗默认选中 + 未映射兜底）、`CONFIG["domestic_party_cn"]="（9111010856368328XF）（11149609R4）方州汇国际电子商务(北京)有限公司"`（A4 境内收货人 + A8 生产销售单位固定值）。
- **CLI 参数**：`--consignee {centrade|daneey|poland|custom}`、`--consignee-name`、`--consignee-addr`、`--declaration-unit`。
- **解析**：`resolve_consignee(args, customer)` —— CLI 优先 → 客户自动映射（DANEEY→daneey、Centrade→centrade、波兰→poland）→ 兜底 `centrade`（不再保留模板原值）。
- **单元格**：C5（合并 C5:F6）写 `名称\n地址`（wrap_text）；A4（境内收货人）+ A8（生产销售单位）都写 `CONFIG["domestic_party_cn"]`；A54（合并 A54:D54）仅当传 `declaration_unit` 才写 `申报单位  {value}`。
- **EN 部署侧待修正**（EN Agent 2026-08-25 实现，与本仓库模板/需求有出入，需其确认修正）：
  1. EN 文档写**申报单位在 A6**，但模板申报单位实际在 **A54**（A6 为空）——若 EN 部署模板一致则需改为 A54。
  2. EN 未实现**生产销售单位 A8 = 绍兴雪雁针纺有限公司**（本仓库已按决策4写入）。
  3. EN 只写 **C5=地址**，未写**公司名**——需求为名称+地址。
  4. EN 未填发票/装箱单/合同的**买方/To Messrs**（如需可配）。
  5. EN 收货人名称/地址字段在 JS 设 readonly，建议改 HTML 直设避免闪烁；目的国联动、申报单位与收货人联动列为待优化。
- **弹窗页签设计**（供 EN 弹窗参考）：页签①装箱方案（箱子分组卡片+箱数，已实现）；页签②报关信息（境外收货人下拉+可编辑名称/地址、目的国、申报单位）；页签③预留（发票/合同/价格）。切换页签保留输入；底部全局统计栏（已装组数/箱数合计/对账状态）+ `[取消][保存草稿][确认导出]`。固定值（生产销售单位）不进弹窗。

### BOM 成本取值（cost_pk / cost_nd，2026-08-25）

**目标**：皮壳(PK#)→`cost_pk`（BOM皮壳成本，替代旧 cost_fg）；内胆(ND#)→`cost_nd`（BOM内胆成本，替代当前 0）；产品(其他)→`sx_cost_all`（绍兴总成本，不变）。

**数据源**：BOM 成本报表 V2（`数据源/bom_cost_list_v2_2026-57-25-15-8.json.gz`，gzip JSON，`result` 行），键=`item_fg`（成品编码 `KS号-面料-尺寸-颜色`）。相关列：`item_fg`、`item_pk`（皮壳编号带 PK#）、`cost_pk`、`cost_nd`、`sx_cost_all`。旧 `cost_fg` ≈ `cost_pk + cost_nd`（旧列含内胆，已拆分）。

**内胆匹配（membership-based，关键）**：
1. 内胆码去 `ND#` 前缀按 `-` 切分：段[0]=KS号、段[1]=尺寸；
2. 遍历 BOM 行，`item_fg` **不去色**直接切分，匹配 `首段==KS号 且 尺寸出现在任一字段段`（**不用「最后一段=尺寸」**——成品可能带颜色/不带颜色，段位不固定）；
3. 命中取该行 `cost_nd`（为 0/缺失则继续找有值的行）；未命中 → bom_rate=0 + 黄色告警。

⚠️ **不要用颜色词表去色**：实测词表只覆盖约 50% 颜色，278/546 个 (KS,尺寸) 组会失配（如 DEEPBLUE、CREAMYBEIGE、BROWNSTRIPE）；membership 匹配已验证 9/9 命中且 KS0455（DEEPBLUE）也命中。

**皮壳匹配**：`item_code[3:]` 去 PK# 后按成品码匹配 → `cost_pk`（逻辑不变，仅换列）。

**参照实现**：`customs_export.py` 末尾 `_load_bom_cost_report()`（读 gzip JSON）+ `_get_nd_cost_ref(item_nd, bom_rows)`（membership 匹配，返回 `(cost_nd, matched_row)`），与 EN `delivery_plan/doc_event.py` 的 `_get_nd_cost` 逻辑一致。

**实测命中（DN-26-00056）**：ND#KS0001-100→7.1992、140→8.6572、153→9.568、194→10.982、KS0003-60→6.191、KS0007-194→20.465、KS0321-153→15.574、KS0383-153x50x24→9.1592、KS0383-194x50x24→10.2424。

**边界**：尺寸含 `x`（如 `153x50x24`）正常按 `-` 切分；`cost_nd` 有约 600 行为 0（数据未填）→ 导出 0 并告警，待补数据。

### 报关单价加成 ×1.45 + 装箱主物料对齐（2026-08-26）

**价格公式变更**：报关单价由 `BOM成本 ÷ 6.8` 改为 `BOM成本 ÷ 6.8 × 1.45`（`CONFIG["price_markup"]=1.45`，集中管理）。`usd_price(rmb)` 封装：`round(rmb/6.8×1.45, 3)`。发票(F/G)、合同(H/J)、报关单NEW(G/H) 及 TOTAL（G33/J33/A51）全部走 `usd_price()`，装箱单无价格不受影响。

**EN 侧 BUG 修复（2026-08-26）**：
1. **pkg_map 重复累加**：`export_customs_documents_with_packages` 里混合装箱曾对每个 `code_agg` 都累加 packages → TOTAL 多算、次要物料出现"幽灵箱数"。改为**只把 packages 累加给主物料 `code_aggs[0]`**，与 `exclude_codes` 完全对齐。
2. **前端主物料识别不一致**：`do_export()` 用 `g.items`（DN 行原始顺序）取 `code_aggs[0]`，与弹窗 UI 按 `PRIORITY_MAP={皮壳:1,成品:2,内胆:3}` 排序的主物料可能错位。改为**导出前按 PRIORITY_MAP 重排 `code_aggs`**，保证后端 `code_aggs[0]` = UI 主物料，`exclude_codes` 与弹窗视觉一致。
3. 修复后保证：`pkg_map` 只含主物料箱数；`totals["cartons"]` = Σ用户填 packages（装箱单 TOTAL = 弹窗箱数合计）；混合装箱次要物料走 `exclude_codes` 不显示。

**验证（本仓库）**：`usd_price(49.1878)=10.489`；发票/合同/报关单NEW 的单价、总价、TOTAL 均为原值 ×1.45，守恒成立（总价 = 单价 × 数量）。

### 混合装箱合并导出（2026-08-26，EN 侧，取代"优先级排除"）

> 本逻辑**取代**了上一版"主物料优先级修正"（`EXPORT_PRIORITY_MAP` 按 成品>皮壳>内胆 选主 + 全局排除次要物料）。现改为：**按 qty 最大选主物料 + 次要数量并入主物料合并导出 + 排除仅限同箱组**。

**改动文件**：`delivery_plan/public/js/delivery_note.js`（do_export）+ `delivery_plan/api/customs_export_api.py`（`_merge_dn_items(dn_items, packages_list)` + `_accumulate`）。

1. **可编辑行/主物料选择**：按弹窗展示的物料 qty，**选数量最大的那一行**；平局取第一行（`it.qty > max_qty` 严格大于）。
2. **数量累加合并**：主物料导出数量 = 组内所有物料 qty 之和（`total_qty`）；`amount/bom_cost` 按比例缩放（qty 增加，金额/成本同比例放大）。
3. **排除仅限同箱组**：后端按 `carton_group + outer_carton_no` 把 DN items 分桶，多物料组只跳过**同组内**次要物料（`secondary_codes`）——**不同箱组的同名物料互不影响**，各自参与导出。
4. **单物料箱组**：直接聚合，无排除。
5. **loose 组**（无箱号、按物料分组、单物料）：不受影响，正常导出（packages=0）。
6. **导出数据**：每组只推 `main_code / total_qty / packages / secondary_codes`；不再传全局 `exclude_codes`。
7. **价格**：`usd_price = round(rmb × 1.45 ÷ 6.8, 3)`（先涨价后换汇，仅最终一步取整）。

**修复的两个问题**：① 混合组次要物料（disabled 行）不再导出冗余 0 数量行；② 次要物料不再被全局排除导致其他箱组同名物料误杀。

> ⚠️ 业务提示：合并导出后主物料数量 = 整箱总件数（皮壳+内胆等折叠为一个商品项），接近"皮壳+内胆申报口径"里"报一种物料、隐藏其余"的取向，**仍未获报关行确认**（见"未决业务问题"），勿固化。皮壳成本 `cost_pk` / 内胆成本 `cost_nd` 的 BOM 取值逻辑不受影响。

### 申报要素页签 + loose 分组键修复 + 三页签弹窗（2026-08-27，EN 侧）

**改动文件**：`delivery_plan/api/customs_export_api.py`（新增 `get_aggregated_items` / `get_items_hierarchy` / `get_editable_items_hierarchy` / `_merge_dn_items` / `_accumulate`）、`delivery_plan/utils/customs_export.py`（`CustomsExporter.export()` 新增 `merged_dn_items` / `declaration_elements` 参数 + `safe_write`）、`delivery_plan/public/js/delivery_note.js`（三页签弹窗）。无新增 DocType/表。

1. **loose 分组键修复**：散件组键由 `__none` 改为 `loose__<drop_color(code)>`——旧版 `__none` 导致主物料 code 匹配不上 → 散件导出 0 物料。
2. **合并函数**：`_merge_dn_items(dn_items, packages_list)` 按 `group_key` 分桶；单物料组直接聚合；混合组只留 `main_code` 行，`qty=total_qty`，`amount/bom_cost` 按 `scale=total_qty/qty` 缩放（保单价）；次要物料跳过不写 Excel。
3. **三页签弹窗**：①装箱方案（qty 最大行为可编辑行、次要行 disabled+灰显、同步箱数）②报关信息（收货人/目的国/申报单位）③申报要素（见下）。
4. **申报要素**：对每个可编辑物料填 5 段 → `seg1|seg2|seg3|seg4|seg5|||`；seg1 品牌类型(0-4)、seg2 出口享惠(0-2)、seg3 物料组名称(自动)、seg4 品牌(无/有)、seg5 型号(无/有)。写入报关单NEW 该物料申报要素行 `C{row+1}`（用 `safe_write` 规避 MergedCell 报错）；未填写降级 `0|0|||无品牌|无型号|||`。
5. **seg3 物料组层级口径（已最终确认）**：取「**根的直接子级 = 第 1 层**」（根=第0层，直接子级=第1层）；无第 1 层则取物料组自身。⚠️ 先后纠正过「第2层」「倒数第2层」，最终口径为第 1 层，已发修正给 EN Agent。

### EN 侧 BUG 修复交接（2026-08-28）

1. **混合装箱数量重复乘 bug（`_merge_dn_items`）**：主物料行被「每条都按 `target_qty` 累加」→ 同色 3 条 × 3 = 9。修复：单物料组 qty=total_qty；混合组只找 `main_code` 那一行累加一次 `target_qty`，次要物料跳过。
2. **`UnboundLocalError: totals`**：`[exporter_agg]` 调试日志在 `totals` 定义前引用 → 日志块下移到 `totals` 定义之后。
3. **皮壳/内胆净重归类**：`cat_map={皮壳:PK, 内胆:ND}` 按 code 前缀从 `item_weight_cats` 取净重（克→kg）。建议后续：cat_map 配置化、净重换算抽工具函数、`outer_carton_weight` 单位统一核对。

### 英文品名翻译改为查表组装（2026-08-28，EN 侧，替代 DeepSeek API）

废弃 DeepSeek API 翻译（响应慢/不稳/措辞漂移），改为**查表组装**——确定性翻译，同物料永远一致，解决评审提的"报关翻译一致性"问题。

- **规则**（按编码前缀）：
  - 成品 `KS0001-DM-194` → 物料组翻译 + 面料翻译 + 尺寸
  - 皮壳 `PK#KS0001-HLR-194` → `pillow cover for ` + 物料组翻译 + 面料翻译 + 尺寸
  - 内胆 `ND#KS0001-194` → `Inner liner for ` + 物料组翻译 + 面料翻译 + 尺寸
  - 扣类 `KZ1050-5#` → 物料组翻译 + 尺寸（无面料）
- **查询逻辑**：
  - 物料组翻译：优先用编码前缀（KS0001）查 `Item Group.custom_model_id → item_group_translation`；查不到再用中文品名第一段（三角靠枕）模糊匹配物料组名称
  - 面料翻译：编码第二段（DM/HLR）→ `Item Attribute Value All Fabric.abbr → fabric_translation`
  - 尺寸：编码第三段（194）或第二段（5#），颜色不参与
- **数据依赖**：Item Group 需有 `custom_model_id` + `item_group_translation`；面料表需有 `abbr` + `fabric_translation`
- **扩展**：新增物料类型（如 `BJ#`）只需在 `translate_by_lookup()` 加 `elif` 分支定义固定前缀翻译，其余逻辑复用
- **待确认**：物料组+面料+尺寸的**拼接格式**（分隔符/顺序）未明示；面料/翻译字段缺失时的回退（是否降级为中文原文）

### 多余整行删除（2026-08-28，本仓库与 EN 测试服务器均已实现 `delete_extra_rows`）

最终 Excel 按实际导出的物料数 N **删除数据区末尾的多余整行**（不是清空单元格、不是从中间删）。范围：报关发票 / 装箱单 / **报关合同** / 报关单NEW（用户最终确认 4 张表都要删）。

- **数据区行范围**（模板默认 16 物料）：发票 16..31（TOTAL 33）；装箱单 17..32（TOTAL 34）；**报关合同 16..31（TOTAL 33）**；报关单NEW 每物料 2 行 18..49（TOTAL 51）。
- **删除规则**：N < 16 时删除数据起始行+N 起的连续整行——发票/装箱单/合同各 `16-N` 行；报关单NEW `2×(16-N)` 行（含申报要素行）。N ≥ 16 由 `expand_sheets` 扩展，不删。
- **合并单元格处理（关键）**：`_delete_rows_safe(ws, start_row, count)` 用 `ws.delete_rows` 整行删；删除前处理合并——删除区内完全包含的移除、跨越边界的收缩到边界（如唛头列 B15:B33→B15:B(15+N)）、**删除区下方（TOTAL/页脚行）的整体上移 count 行**（openpyxl 的 delete_rows 不会平移合并区，须手动处理，否则 TOTAL 合并会变"孤儿合并"失去样式）。
- 已在 EN 测试服务器部署（`utils/customs_export.py`，备份 `customs_export.py.bak_20260828`）+ 本仓库参考实现，均验证通过（N=3：发票 max_row 22、合同 TOTAL 合并 B20:E20、报关单NEW TOTAL 合并 A25:H25）。

### 物料 >16 自动加行（2026-08-28，EN 服务器补齐）

服务器原 fill 函数固定 `for i in range(16)`，>16 物料会被静默丢弃。已移植参考脚本的 `expand_sheets`/`_expand_rows`（insert_rows + 合并修复），并修正 4 个 fill 函数：

- 循环 `range(16)` → `range(max(16, len(agg)))`
- 发票/装箱单/合同 TOTAL 与页脚写死坐标（C33/C34/B33/D36 等）→ 加 `+k` 偏移（`k = max(0, len(agg)-16)`）
- 报关单NEW TOTAL `A51`/`A54` 写死 → `A{51+k}`/`A{54+k}`（`k = 2*max(0, len(agg)-16)`），并为扩展出的申报要素行**自动创建 A:B / C:N 合并**
- `export()` 填表前调用 `expand_sheets(wb, len(agg))`（N>16 才插入行；N<16 时 `delete_extra_rows` 删多余行，两者互斥互补）
- 已验证 N=20：发票数据 16..35/TOTAL C37、报关单NEW 项号 1..20/TOTAL A59/末行申报要素合并 C57:N57
- **样式继承修复（2026-08-31）**：`insert_rows` 不继承样式，>16 扩展出的新行字体/边框缺失（实测发票 R32-33 变宋体12、应微软雅黑10）。新增 `_copy_row_style`，`_expand_rows` 插入行后从模板数据行复制样式——发票/装箱单/合同参考 `at_row-1`，报关单NEW 每物料 2 行交替参考 item 48 / element 49。已验证 N=18 扩展行字体与模板一致。

### 固定收货方 + 翻译尺寸修复（2026-09-07，参考脚本 + EN 测试服务器均已实现）

> 需求：境内收货人(境内发货人 A4) 与 生产销售单位(A8) 均固定为方州汇含编码串；**境外收货人 C5 = 报关信息页签「选择收货人」选中的公司名（仅名称、不带地址；缺省/未传时默认 Centrade Inc）**；英文品名尺寸不再截断、分隔符统一 `*`。

**A4/A8 固定值（参考脚本 `EN_API/customs_export.py` 已改，2026-09-07）**
- 新增 `CONFIG["domestic_party_cn"]="（9111010856368328XF）（11149609R4）方州汇国际电子商务(北京)有限公司"`，与模板 报关单NEW A4/A8 现填值逐字符一致（公司名内括号用半角，编码括号用全角）。
- `fill_declaration()`：`A4 = A8 = CONFIG["domestic_party_cn"]`（删除旧 `production_unit` 键，不再用 `shipper_cn` 覆盖 A4）。
- 境外收货人（2026-09-08 改回“选择即导出”）：`resolve_consignee()` 按 CLI `--consignee` 选择即导出（仅名称），未指定默认 Centrade；`fill_declaration()` C5 写选中的公司名（`consignee_name`，忽略地址）。
- 发票/装箱单/合同抬头 B2/B3 仍是纯公司名（`shipper_cn/en`），不混入编码。

**EN 测试服务器（8.133.254.66 / ensh）已落地（2026-09-07，备份 `customs_export.py.bak_20260907`）**
- `delivery_plan/utils/customs_export.py`：A4/A8 写 `domestic_party_cn`；C5 写 `consignee_info.name`（弹窗选择/填写的公司名，仅名称、忽略地址），空则兜底 Centrade；`export()` 收货人用传入 `consignee_name/addr`（两者都空才兜底 Centrade）；波兰预设已改为 **Pillow Palette Ltd**（`ul. Krucza 68/9, 53-411 Wrocław, mail: kontakt@pillowpalette.pl, 786 603 993`）；已 `bench restart` 生效。
- ⚠️ **运行时模板改为「正常上传文件」查找（2026-09-09 起，不再用绝对路径目录）**：`_get_template_path()` 按 **File doctype** 查 `file_name=ZJ26DZJR0403-报关单据.xlsx`（优先 `/private/` 上传，无则任一上传记录），`_uploaded_template_path()` 取 `get_full_path()`（DB 内容则落临时文件）；`_ensure_clean_template()`（4 sheet + 报关合同 H48:J50）把关结构。旧版 os.walk 抓 `报关单据_*.xlsx` 当模板会 MergedCell 崩溃/串头，已废弃。测试机当前命中公开 `/files/` 上传版可导出；若要干净 private 版需替换上传同名（同名重复会被 Frappe 加哈希后缀，精确 file_name 只认一条）。**供生产：直接正常上传该模板文件即可，不再要求 customs_templates 目录。**

**翻译尺寸修复（EN `translate_by_lookup` 查表组装，2026-09-07 已实现+实测）**
- 现象/根因：`蓝白条纹款中控台车载狗窝-棉麻-45*22*27cm` 的 **item_code 尺寸段只存宽度 `45`**（如 `KS0181-MM-45`），完整 `45*22*27cm` 只在中文品名里 → 旧逻辑取编码尺寸段只出 `45`。
- 修复：新增 `_dim_token()`（把 x/X/×/＊ 统一 `*`，整段保留）+ `_size_from_name()`（扫描中文品名各 `-` 段取最完整尺寸段，优先同首段数字且更长者）；`translate_by_lookup` 用 `size_final = _size_from_name(...) or _dim_token(code_size) or code_size`。
- 实测：`KS0181-MM-45`/`棉麻-45*22*27cm` → `...Cotton and linen 45*22*27cm`；`ND#KS0383-153x50x24` → `...153*50*24`。
- 示例：源 `45*22*27cm` → `45*22*27cm`；源 `153x50x24` → `153*50*24`。

**靠枕固定宽高 —— 已恢复并加开关（2026-09-08 最终版）**
> ⚠️ 历程：曾实现→业务暂缓→EN 回退；随后**恢复为「默认补全 + 弹窗可关」**（因已开票的单当时尺寸不完整，需能取消以与开票一致）。

- 规则：中文品名含 `三角靠枕` → 尺寸补 `*20*50`；含 `平条靠枕` → 尺寸补 `*15*50`（常量 `FIXED_DIM_CN`，`(关键词, 宽, 高)`）。成品 KS#、皮壳 PK#、内胆 ND# 等凡含字眼都补；**尺寸已是完整三围（含 x/*/cm）则不动**。
- 开关：报关弹窗**页签栏下方常驻「导出选项：☑ 靠枕尺寸补全（三角靠枕×20×50 ／ 平条靠枕×15×50）」勾选**，默认勾选、**所有页签都可见**（放顶部栏而非某个页签内，避免不易发现/勾选框太小）；取消则不补全（只长度，和已开票一致）。
- 落点：`delivery_plan/utils/customs_export.py` 的 `FIXED_DIM_CN`/`_enrich_dim_cn`；`CustomsExporter.export(..., enrich_flat_dim=True)` 里在翻译前对每个 `name_agg` 调 `_enrich_dim_cn()`（受开关控制，`aggregate_items` 本身不再无条件补全）。中文 C 列与英文 D 列（查表组装）都带完整尺寸。
- 联动：`api/customs_export_api.py::export_customs_documents_with_packages` 增参 `enrich_flat_dim`（`_as_bool` 兜底 True）；`delivery_note.js` 顶部页签栏下方常驻「导出选项」勾选框（id `pkg_enrich_flat_dim`，默认勾选、全页签可见）随 `frappe.call` 传该参。
- 参考脚本：`EN_API/customs_export.py` 同逻辑，CLI 增 `--no-enrich-flat-dim`（默认补全，去色后翻译前应用）。
- 实测（EN 测试机 DN-26-00054）：勾选 → C=`三角靠枕类-涤麻-194*20*50`、D=`Triangle pillow ... 194*20*50`；取消 → C=`三角靠枕类-涤麻-194`、D=`... 194`。`平条靠枕-涤纶-153`→`平条靠枕-涤纶-153*15*50`。狗窝等含完整尺寸产品不受影响。
- 前端 JS 改动需浏览器硬刷新 / `bench clear-cache` 才生效。

**申报要素第⑥段补完整尺寸（2026-09-09）**：申报要素字符串由 `seg1..seg5|||` 改为 `seg1..seg5|seg6||`，**seg6=完整尺寸**。口径：**始终从中文名提取/补全**——三角靠枕→`长度*20*50`、平条靠枕→`长度*15*50`，与品名补全开关**解耦**（开关关时中文 C 列只 `194`，申报要素 seg6 仍 `194*20*50`）。实现：`export()` 对每行算 `it["size_decl"]`（对 `_enrich_dim_cn(name_agg)` 各 `-` 段取 `_dim_token` 最完整者）；`fill_declaration` 拼串加 seg6。实测：`0|0|床品类|无品牌|无型号|194*20*50||`。参考脚本不生成申报要素，无需镜像。

**待办（未做）**：本地参考改动未 commit（feature 分支 feature/customs-export-bom-consignee）；prod `erpnext.vilavi.cn`(47.116.128.218) 未同步（暂不动，SSH 不可达）。

**弹窗箱数「累加/合并」修正（2026-09-09，production issue DN-26-00070）—— 仅测试机 delivery_note.js 已落地**
- 现象：① 卡 `OBN-…001 · 箱组1` 显「2箱合计 自动=2」，用户找不到第2箱；② 箱18/19（同 XMMBS-153-HEMPNATURAL）不累加、同箱同 SKU 被拆 2/3 行。
- 根因（prod 数据+代码实证）：`get_aggregated_items` 逐 DN 行入 `(carton_group, outer_carton_no)` 箱组、**同箱同 SKU 行不折叠**；JS `code_solo_count` 只认 `g.items.length===1` 的箱 → 仅 001 与 035（各自恰 1 行）被并成「2」。且 035 是 **WHITE**、与 001 GREY 因去色 code_agg `PK#KS0001-PR-194` 合并（显示却用 001 的完整码 → 误导）。真实纯装箱 PR-194 有 10 个（001/002/003/004/009/031/035/036/044/052）。
- 已确认口径（用户）：**合并键 = 去色型号**；展示 = **相同内容箱子并成一张卡 + N 箱号清单**。
- 方案（**只改 `delivery_plan/public/js/delivery_note.js` 的 show_package_dialog**；后端 customs_export_api.py / utils **零改动**，无需 bench restart，仅硬刷新）：
  - 同箱多行按 code_agg 折叠成一行；纯装箱按 code_agg 归池（忽略箱内数量差——主物料无歧义）；混装箱仅当逐物料数量完全一致才归并（否则主物料随箱而异会误并）。
  - 合并卡显「N 箱合计」角标 + `合并箱号：OBN-…/…` 清单（自然序）；默认箱数 = N（单箱卡默认 1，loose 仍 0）。
  - 展示行：单色显完整码；同型号跨色并入时显去色码（避免「GREY 卡含 WHITE」误导）。
  - do_export 改为**逐成员箱提交**：`{group_key: 成员箱原 cg__oc, packages: 首=N/其余=0, main_code, total_qty: 该箱折叠总量, secondary_codes}` → 后端仍按每箱归并，`pkg_map` 每物料箱数 = N，`totals.cartons` = 物理箱数。删除了旧的 `code_solo_count/solo_multi` 逻辑。
- 备份：测试机 `delivery_note.js.bak_20260909`（md5 d3dee7ef…）；新版 md5 `bd1ecef8…`（node 语法通过）。
- 预演（prod DN-26-00070 数据）：49 物理箱 → 18 张内容卡（纯池：PR-194 N=10、XMMBS-153 N=7、CMM-153 N=6、PR-153 N=5、CMM-194 N=4、CMKTR-153-GREY N=3、XMMBS-100 N=3、XMMBS-183 N=1、PR-140 N=1；混装箱 9 个各自独立）+ 8 loose。箱数合计=49。
- 回归（test DN-26-00053，新 payload 走 API）：混装(KS0001-DM-194+KZKP)+纯装箱，导出成功、装箱单 E=`2CTNS`、TOTAL=`2 CTNS`、item_count=1，与物理箱一致。
- ⚠️ **prod 未同步**：JS 改动在测试机；prod delivery_note.js 需走 delivery_plan git 流程**按 diff 移植**（prod 文件可能与 test 有差异，勿整文件覆盖）。移植后用户在 prod DN-26-00070 弹窗复核合并卡与箱号清单。

**导出排版规范化（2026-09-09）—— 测试机 utils/customs_export.py（备份 .bak_20260909b，md5 `04ba37…`，已 bench restart）+ 本地参考 EN_API/customs_export.py（已镜像，py_compile 通过）**
- 用户 4 条需求：
  1) 内容格**不折叠/不换行 → 一行显示**：模板数据区默认 `wrap_text=True`，长英文品名会换行撑高行高。做法：`_plain_left_single_line(wb)` 对所有有内容格设 `wrap_text=False + shrink_to_fit=False`，并 `re.sub(r"\s*\r?\n\s*"," ")` 去掉字符串里的换行。
  2) **报关发票 `F15='FOB NINGBO,CHINA'` 是模板静态文本**（fill_invoice 不写 F15）→ **用户自行删模板该格后重上传**（File doctype file_name=ZJ26DZJR0403-报关单据.xlsx）。同款静态：`报关合同 ` H15、`报关单NEW` H12='FOB' / G4 / L10='NINGBO,CHINA'（本次未动）。
  3) **报关合同每物料行名称区四列合并 B:E**：`_merge_contract_name_cols(wb["报关合同 "], len(agg))`，先拆数据行内与 B:E 重叠旧合并（如模板默认 B16:C16/扩展复制 B:C）再并 `B:E` 逐行（数据行 16..16+N-1）；总计/页脚合并区不触碰。
  4) **所有内容格统一水平左对齐**（含数字/表头；`horizontal='left'`，垂直/旋转保留原值）。
- 插入点：export() 内 `delete_extra_rows` 之后、`wb.save` 之前。
- 验证：test DN-26-00053(N=1)/DN-26-00054(N=3) API 导出 → 全部 populated 格 left+0 wrap+0 换行；合同 B16:E16(、B17:E17/B18:E18) 合并，总计区合并未被误拆；invoice F15 仍在（静态待用户处理）。
- ⚠️ 注意：不换行后长文本在窄格可能**视觉截断**（内容仍在，点格可见）；**N>16** 扩展行的 B:E 未用真实大单验证（测试机无此类单），逻辑与 delete/expand 坐标一致。**prod 未同步**。
- **动态列宽（2026-09-09 续）**：新增 `_autofit_columns(wb)` —— 只加宽**真正会被右邻格截断**的列（判定=单行文本宽 > 该格+右侧连续空格子的可用宽；能溢出到空格完整显示的不拉宽；列宽只增不减、单列封顶 90 防病态）；个别静态长句「合并区已撑满整行仍放不下」（如 报关合同 B33 整行合并 B33:J33 底部条款）**仅该格回退允许换行**，不影响数据行高。调用顺序：`delete_extra_rows` → `_merge_contract_name_cols` → `_plain_left_single_line` → `_autofit_columns` → save。验证 test DN-26-00053/00054：残差截断格=0，数据行全单行，仅 B33 保留 wrap=True。
- **统一行高 + 表格全框线/粗外框（2026-09-10，测试机 utils md5 `111c08a5…`，备份 …bak_20260910a~d；本地参考已镜像）**：
  - `_uniform_row_heights`：报关发票/装箱单/报关合同**除顶部公司信息/标题块**（起实行 发票=6、装箱单=6、合同=9；报关单NEW 不动）外行高统一 **16.5**；唯一例外=含「回退换行」的静态长句行（合同备注条款行）设 30 保完整显示。
  - `_apply_table_borders(wb, len(agg))`：三表表格区**内部 thin 全框线 + 外框 thick**；区间随 N 动态 = 发票 `B14:G(17+N)`、装箱单 `B15:K(18+N)`、合同 `B13:J(17+N)`（含表头/数据/合计/中间空白行）。
  - **坑（边框线中断）**：Excel 按**每个子格**渲染边框，而 openpyxl 合并会把覆盖格变成只读 MergedCell、`merge_cells` 还会清掉已画好的子格 → 「只画锚点」或「拆开重画再合并」都会让合并区缺线。**最终=给表格内每个坐标（含合并覆盖格）直接放真实 Cell 写边框**（`ws._cells[(r,c)] = _Cell(...)`），合并关系保留；边框按位置（thick 仅四周、其余 thin）。
  - **验证坑**：openpyxl 读不出合并覆盖格样式 → 改用 **xlsx XML 级复核**（sheet XML 的 `s` → styles.xml 的 borderId 四条边）→ DN-26-00053/00054 三表 `cells_missing=0、border_mismatch=0`（测试机 utils md5 `b208800f…`，备份 …bak_20260910e/f）。粗细选 thick（嫌粗改回 medium 只需改 `Side(style=...)`）。**prod 未同步**。
- **删除表头下空白行（2026-09-10 续，测试机 utils md5 `974a206e…`，备份 …bak_20260910g；本地参考已镜像）**：`_remove_blank_header_rows(wb)` 用 `_delete_rows_safe` 删 报关发票 row15 / 装箱单 row16 / 报关合同 row15（在 `delete_extra_rows` 之后）。删后**坐标整体上移 1**：数据起始 发票/合同 16→15、装箱单 17→16；`_apply_table_borders` 下边界 = 发票 `B14:G(16+N)`、装箱单 `B15:K(17+N)`、合同 `B13:J(16+N)`；`_merge_contract_name_cols` start_row=15。**副作用**：发票 row15 静态 FOB 被整行删掉（→ 发票的 FOB 无需再改模板）、合同 row15 的 FOB 与 **USD** 一并删除（USD 为金额列币种标识，若要保留改成只清 FOB 不删行）。验证：XML 级复核两单三表 `cells_missing=0、border_mismatch=0`；结构 发票 header14→数据15 / 装箱单 header15→数据16 / 合同 header14→数据15，内容无丢失。**prod 未同步**。
- **扣胚固定英文名（2026-09-10 续，测试机 utils 备份 …bak_20260910h；本地参考已镜像）**：用户要「扣胚-5号-铁底铁面」→ 固定英文。**查明代码无硬编码**（`97bcd56` 已改为查表；docstring 的 `扣子-5号-金属 → Button 5#` 只是示例）；ERP 该物料中文名已是「扣胚-5号-铁底铁面-银色」、组「扣胚」(`custom_model_id=KZKP1010`)，但组翻译/面料/Translation 全空 → 原输出仅 `5#`。实现=新增 `TRANSLATION_OVERRIDES = {"KZKP1010-5#-IRONBOTTOMSURFACE": "Button embryo {size} iron bottom surface"}`（utils 的 `translate_by_lookup` 组装前命中返回；本地参考 DeepSeek 版 `_do` 命中跳过 API）。用精确 code_agg 键避免误伤 `6#-IRONBOTTOMALUMINUMSURFACE`。bench execute 验证：5#→`Button embryo 5# iron bottom surface`、6#→仍 `6#`。其它五金如需再加 overrides。
- **数量/单位分列 + 表头恢复模板对齐（2026-09-10 续，测试机 utils md5 `081f8f93…`，备份 …bak_20260910i；本地参考已镜像）**：
  - **报关单NEW「数量单位」列代码内拆分（无需改模板）**：`fill_declaration` 起始 unmerge 模板合并表头 `E17:F17`（并把 E17 的 font/fill/border/alignment 复制到 F17）→ `E17='数量'`、`F17='单位'`；数据行 `E{row}=int(qty)`、`F{row}=uom_cn(uom)`（原为 `f"{qty}{uom}"` 合并写 E）。
  - **表头恢复模板样式**：新增 `DATA_START={"报关发票 ":15,"装箱单":16,"报关合同 ":15,"报关单NEW ":18}`；`_plain_left_single_line` 对 `cell.row < DATA_START[表]` 的行**跳过**（不左对齐、不去换行），表头/公司信息区保留模板原样（居中）。数据区仍左对齐+单行。
  - 验证 test DN-26-00054：E17=数量/F17=单位、E18=3/F18=个；发票 C14/F14 恢复 center(=模板)；数据行仍 left。**prod 未同步**。
  - **补竖线（md5 现 `7e569e78…`，备份 …bak_20260910j）**：模板数据行 `E.right`/`F.left` 均为空（原 E:F 被当作合并列）→ 分列后「数量｜单位」之间无线；已对**表头 E17/F17 与每个物料行**显式补 `thin` 竖线（`E.right=F.left=thin`，F 的 top/bottom 取 E）。元素行属 C:N 合并区、内部线本隐藏，无需处理。
