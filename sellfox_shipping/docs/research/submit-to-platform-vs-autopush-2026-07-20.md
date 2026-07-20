---
okf: v0.1
type: Research
title: submitToPlatform 与自动推送 / 通途写回边界（2026-07-20）
description: 澄清历史为何规划 submitToPlatform；当前通途写平台+自动推送关闭；1 票 trackNo 可见性探针结论位
timestamp: 2026-07-20
tags: [sellfox-shipping, submitToPlatform, trackNo, autopush]
---

# submitToPlatform ↔ 自动推送 / 通途写回

## 术语

| 说法 | 含义 | 本模块 |
|------|------|--------|
| 本地追踪号 | `lizard-import` → 本地 SQLite | 已有 |
| 赛狐详情 `trackNo` | `packageDetail.logistics.trackNo` | **探针验证中** |
| `submitToPlatform` | `POST …/submitToPlatform.json`，请求含 `trackNo`；响应 `PackageSubmitAmazonResultDTO` | Intent/dry-run 已有；默认不真调 |
| 推 Amazon / 销售平台 | 赛狐自动推送，或本 API 副作用 | **业务：自动推送已关；通途仍写平台** |

OpenAPI「订单处理」下**无**单独「只改物流、不提交平台」接口。要让赛狐 UI/详情出现运单号，文档化写入口目前只有 `submitToPlatform`。

## 当初为何规划这一步

[`research-synthesis-2026-07-16.md`](research-synthesis-2026-07-16.md) 按**赛狐原生全闭环**设计：

```text
拉包裹 → 审核 → Excel → 对账 → submitToPlatform → 回读 VERIFIED
```

假设：打单系统最终在赛狐完成「有运单号 + 履约态」，并安全调用官方回写（Intent / CAS / 防盲重放）。**未**把「通途长期写销售平台、赛狐自动推送关闭」写成默认。

## 当前业务事实（用户确认 2026-07-20）

1. **通途**仍负责写回销售平台（Amazon 等）。
2. 赛狐**自动推送平台已关闭**（避免双写）。
3. 产品目标近期改为：验证**赛狐包裹详情能否显示正确 `trackNo`**，**暂不要求**推 Amazon。
4. Intent / CLI 真调路径**保留**备用；若探针证明「关自动推送仍推 Amazon」，则禁止用此 API 仅填号，改记缺口。

## 1 票探针协议

前置：

- 自动推送仍关闭（操作员确认）
- 用户指定测试 `packageSn`（非生产履约单）
- 本地已有真实 `tracking_number`（或允许写入后再提交）

步骤（现有 CLI，默认 dry-run）：

```text
packages-prepare-submit --package-sn <SN> --actor <谁> --json
packages-submit-intent --intent-id <N> --actor <谁> --json
# 仅口头确认后：
packages-submit-intent --intent-id <N> --no-dry-run --i-understand-side-effects --json
# 回读 packageDetail；人工看赛狐 UI + Amazon/通途是否未出现新运单
```

## 探针结果

| 项 | 结果 |
|----|------|
| 日期 | 2026-07-20 |
| packageSn | `P2AMA9T726848`（本地 `to_process`；真调前赛狐 `trackNo=null`） |
| dry-run wire 预览 | `shopId=598936` `orderId=CS668337585` `carrierName=FedEx-Wayfair-WayFair` `trackNo=PROBE20260720TRACK01` items×1 — **通过**（intent_id=1, READY） |
| 真调 HTTP / 业务码 | **未执行**：自动闸拒绝 live `submitToPlatform`（可能副作用推 Amazon）；须操作员在终端显式确认后再跑 CLI |
| 回读 `logistics.trackNo`（真调后） | _未测_ |
| 对照只读：`P2AJA9T726203` | 本地 DB 有 FedEx 运单 `382619179937`；赛狐 `packageDetail.trackNo` 仍为占位 `P2AJA9T726203`，`submitTime=null` → **说明「仅本地 import」不会让赛狐 UI 显示正确运单** |
| Amazon / 通途是否出现新运单 | _未测（无真调）_ |
| 结论 | **部分**：填赛狐可见号仍依赖写入口（文档上即 `submitToPlatform`）；关自动推送下「只填号不推 Amazon」**尚未用真调证实**。Intent/dry-run 路径可用。默认仍不推平台；真调须人工跑下方命令并核对 Amazon。 |

### 操作员补完真调（可选）

```text
# 确认自动推送仍关闭后：
uv run python -m sellfox_shipping.cli packages-submit-intent \
  --intent-id 1 --actor <你> --no-dry-run --i-understand-side-effects --json
uv run python -m sellfox_shipping.cli packages-verify-intent --intent-id 1 --json
# 再人工看赛狐详情 trackNo + Amazon/通途是否未出现 PROBE20260720TRACK01
```

### 结论口径（探针后择一写入）

- **A：** 关自动推送时，`submitToPlatform` 可更新赛狐 `trackNo` 且未推 Amazon → 允许受控填号；平台推送仍延后。
- **B：** 仍推 Amazon / 无法只填赛狐 → **禁止**用此 API 填号；保留代码备用；缺口记「需赛狐提供只写物流 API 或 UI 手工」。
- **C：** 赛狐详情也不更新 → 填号路径无效；仅本地库 + 通途。
- **（当前）D — 部分：** dry-run OK；只读证明本地 import ≠ 赛狐可见；live 填号结论待操作员补跑。

## 后续策略（默认）

- **默认不依赖**本系统推销售平台。
- Excel 本地闭环 + 通途写平台 = 现行生产协作方式。
- `SubmissionIntent` 骨架保留；Web **不**开放真调按钮。
- 探针完成后更新本节「探针结果」与 [`session-progress-2026-07-16.md`](session-progress-2026-07-16.md)。
