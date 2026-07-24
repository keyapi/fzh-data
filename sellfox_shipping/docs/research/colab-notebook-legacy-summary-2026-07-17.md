---
okf: v0.1
type: Research
title: Colab 通途/FedEx/蜴国际 notebook 遗产逻辑摘要
description: 对本地同步的 202409 Colab notebook 的结构梳理：哪些在生成承运人上传表、哪些只做背贴/拆分，以及与赛狐 P1B 的关系
timestamp: 2026-07-17
tags: [sellfox-shipping, lizard, tongtu, colab, legacy]
---

# Colab notebook 遗产逻辑摘要（2026-07-17）

**源文件（本地 Drive 同步，不入 Git）：**  
`G:\我的云端硬盘\Colab Notebooks\李娜 美中 通途 Fedex excel 生成 SKU PDF 分割 202409.ipynb`  
约 148 cells；名称里「蜥蜴国际」= 现称「蜴国际」。大量历史/实验 cell 已注释，**不能当作现行唯一真理**。

> **安全提醒：** Cell 0 内嵌了 Google Sheets **service account 私钥**。该 notebook 在 Drive 上同步，建议尽快在 Google Cloud 轮换密钥，并改为环境变量/密钥文件，勿再把私钥写进 notebook。

## 1. Notebook 实际在干什么（按区块）

| 区块 | 主题 | 与 P1B 关系 |
|------|------|-------------|
| **0** | 安装依赖、Colab/Drive、**内嵌 gspread 凭证** | 无（运维） |
| **0.1** | 通途对接 **VITE-FedEx** 后的 PDF：奇偶页拆成 Label / 背贴；PDF 抽 `P########` 包裹号 | VITE 后处理；非 Excel 上传生成 |
| **2.x** | 通途 **官方 FedEx** Excel：多 SKU 合并一行、州缩写、克→磅(`/1000*2.2`)、cm→inch(`/2.5`)、按品类分 sheet、生成 4×2" SKU PDF | **FedEx 官方通道**，不是蜴国际模板 |
| **3.x「蜥蜴国际」** | 已拿到的 **蜴国际 PDF+Excel 成对文件** → 抽包裹号 → 合并 Google「US SKU Name」→ 生成**背贴 PDF** | **下游背贴**，不是「生成上传给蜴国际的 Excel」 |
| **4.x「7条」** | 另一承运人（7条）Label+Excel → 背贴；多仓批量 zip | 同类背贴流水线 |
| **后半（47+）** | UPS OCR、SPS/PB→通途、邮件汇款、Prophet 演示等 | 大多标注「以下不用」/实验，可忽略 |

**结论：** 该 notebook **不负责**从订单系统「造」蜴国际上传表；上传表来自**通途导出**（或你后来的小程序变格式）。Section 3 假定 Excel/PDF **已经从蜴国际侧回来或已成对存在**，再做人读背贴。

## 2. 与蜴国际 Excel 列相关的遗产约定

Channel 开关：`通途Fedex` vs `通途蜥蜴国际`（Cell 24/27）。

| 语义 | 通途Fedex 列 | 通途蜥蜴国际列 |
|------|--------------|----------------|
| 包裹匹配键 | `Market Place Order ID` | **`参考编号/Reference Code`** |
| SKU | `Item SKU` | **`备注/Remark`** |
| 数量 | `Quantity` | **`箱数`** |
| 品名（背贴用） | `Buyer Notes` | **`收件人公司名称`**（模板无专用品名列，只好占用公司名） |
| 重尺 | Weight / L / W / H | **`重量` / `长` / `宽` / `高`** |
| 电话/邮编/州 | Buyer Phone… | `收件人电话…` / `邮编…` / `州/Province` |

背贴侧 PDF 正则仍按**通途 8 位** `P\d{8}`（如 `P81401351`）。赛狐 `packageSn` 为 `P2A…` 更长，**旧 PDF 抽取逻辑不能直接套用**。

## 3. 单位换算（仅 FedEx 官方导出路径）

Cell 13 / `merge_excel_gsheet_pack`（FedEx）：

- 重量：`克 / 1000 * 2.2` → 磅  
- 尺寸：`cm / 2.5` → 英寸  
- 州：全称 → 两字母缩写  

对**蜴国际上传样例**（同事 B）：重量保持**克级数值**（如 3390），尺寸 cm，`计量单位=cm/kg`——与 FedEx 磅/英寸路径**不同**。P1B 应按蜴国际模板要求转换，不必套用 notebook 的 `/1000*2.2`。

## 4. 对赛狐路径的含义

1. **参考编号 = 赛狐 `packageSn`**（用户 2026-07-17 确认）。本地库形如 `P2AKA9T726212`；P0 样例 `P8140…` 是通途号，仅代表旧流程。  
2. Notebook **不能**替代 `SpreadsheetCarrierAdapter` 的「赛狐包裹 → 蜴国际上传 Excel」；最多复用：州缩写、多 SKU 合并、`备注`/`收件人公司名称` 占用方式、背贴（P2）思路。  
3. 赛狐 `getPackagePage` 的 `logistics` **当前无 `packageWeight`/长宽高**（已用 50 条样本验证）→ 导出重尺需另寻来源（商品重尺库 / 人工 / 其它 API），否则上传表重量为空。

## 5. 试转换产物

- `sellfox_shipping/数据源/蜥蜴国际-p0-样例/trial-sellfox-to-lizard-upload-10.xlsx`（gitignore）  
- 10 条 `to_process` + 蜴国际 + 有地址；`参考编号`=赛狐 `packageSn`  
- **重量/长宽高全部空**（API 无数据）；发货编码暂填样例中的 `S0143`（待业务确认）
