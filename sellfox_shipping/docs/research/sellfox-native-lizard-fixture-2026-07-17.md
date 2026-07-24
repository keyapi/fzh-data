---
okf: v0.1
type: Research
title: 赛狐原生蜴国际测试夹具（通途样例重映射）
description: 将 02/03/04 样例的通途 P 号换成赛狐 packageSn，供本地导出/导入/面单对照（不写回平台）
timestamp: 2026-07-17
tags: [sellfox-shipping, fixture, lizard, p1b]
---

# 赛狐原生蜴国际测试夹具

## 目录（gitignore，含地址 / 面单 PII）

`sellfox_shipping/数据源/蜥蜴国际-p0-样例/sellfox-native-fixture/`

| 文件 | 内容 |
|------|------|
| `00-tongtu-to-sellfox-package-map.csv` | 通途 P# → Amazon order id → packageSn |
| `02-sellfox-lizard-upload.xlsx` | 38 行；参考编号=赛狐 `packageSn`；地址/SKU 来自赛狐包裹；重尺=pageList+ERPNext |
| `03-sellfox-lizard-tracking-return.xlsx` | 原 03 中对应 38 行；参考编号换成 `packageSn`；**物流单号/运费等保留原蜴国际返回值** |
| `04-lizard-labels-2026-07-15.pdf` | 38 页面单；`CUST REF` / `Ref No` 已换成赛狐 `packageSn` |
| `REPORT.json` | 生成时对账：上传 38、导入匹配 38 |

重生成上传/追踪号夹具：

```bash
uv run python sellfox_shipping/scripts/rebuild_sellfox_lizard_fixtures.py
```

重生成面单 PDF（通途→赛狐）：

```bash
uv run python sellfox_shipping/scripts/replace_tongtu_refs_in_labels.py
```

PDF 替换细节见 [pnumber-to-sellfox-trace-2026-07-17.md](pnumber-to-sellfox-trace-2026-07-17.md) §6。

## 验证结果（2026-07-17）

- 通途 38 P# → 赛狐包裹：**38/38**（`P81401195` 的 Amazon 号应为 `…0563432`，非文档误写的 `…0563433`）
- 上传表构建：**38 exported / 0 skipped**
- 用 03 夹具跑 `parse_tracking_return`：**matched=38, unmatched=0**
- 面单 PDF：**38/38** 参考号已替换；无残留 `P814`

## 怎么测「追踪号落库」（不写回赛狐）

```bash
uv run python -m sellfox_shipping.cli lizard-import-tracking \
  -i "sellfox_shipping/数据源/蜥蜴国际-p0-样例/sellfox-native-fixture/03-sellfox-lizard-tracking-return.xlsx"
```

### 实测（2026-07-17，本地 `shipping.db`）

| 轮次 | matched / persisted | unmatched | conflicts |
|------|---------------------|-----------|-----------|
| 首次（缺 7 个 `P2AJA9T…`） | 31 | 7 | 0 |
| 补同步 7 包后再导 | **38** | **0** | 0 |

导入时若本地 `tracking_number == package_sn`（赛狐占位），视为可覆盖，写入真实物流单号。

**禁止** `submitToPlatform`（历史单多为 `has_shipped`）。
