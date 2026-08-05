---
okf: v0.1
type: Research
title: submitToPlatform 与自动推送 / 通途写回边界（2026-07-20）
description: 澄清历史为何规划 submitToPlatform；当前通途写平台+自动推送关闭；1 票 trackNo 可见性探针结论位；20260720 同事样例
timestamp: 2026-07-20
tags: [sellfox-shipping, submitToPlatform, trackNo, autopush]
---

# submitToPlatform ↔ 自动推送 / 通途写回

## 术语

| 说法 | 含义 | 本模块 |
|------|------|--------|
| 本地追踪号 | `lizard-import` → 本地 SQLite | 已有 |
| 赛狐详情 `trackNo` | `packageDetail.logistics.trackNo` | **探针验证中** |
| `submitToPlatform` | `POST …/submitToPlatform.json`，请求含 `trackNo`；响应 `PackageSubmitAmazonResultDTO` | Intent/dry-run 已有；live 曾真调一次 |
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

仓库级可检索固化（ce-compound）：[`docs/solutions/architecture-patterns/sellfox-trackno-write-path-vs-local-import.md`](../../../docs/solutions/architecture-patterns/sellfox-trackno-write-path-vs-local-import.md)。

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
| 真调 HTTP / 业务码 | **已执行 1 次**：`POST …/submitToPlatform.json` → 代理 **HTTP 401 Unauthorized**；intent/attempt → `UNKNOWN`；scope → `UNKNOWN_BLOCKED`；回读仍 `trackNo=null`、`status=to_process` |
| 回读 `logistics.trackNo`（真调后） | **未变**（仍 null）— 因 401，赛狐侧未写入 |
| 对照只读：`P2AJA9T726203` | 本地 DB 有 FedEx 运单 `382619179937`；赛狐 `packageDetail.trackNo` 仍为占位 `P2AJA9T726203`，`submitTime=null` → **说明「仅本地 import」不会让赛狐 UI 显示正确运单** |
| Amazon / 通途是否出现新运单 | 本次 401，**无**赛狐写副作用可观察 |
| 结论 | **E — 写路径受阻**：dry-run OK；本地 import ≠ 赛狐可见；**live 被代理 401 拒绝**，尚不能证明「关自动推送下 submitToPlatform 能否只填赛狐号」。intent#1 scope 已 `UNKNOWN_BLOCKED`，勿盲重放。 |

### 操作员补完（需先解决 401）

1. 确认代理 Key 对 `submitToPlatform` 有写权限（只读 `packageDetail`/`getPackagePage` 当前可用）。
2. 解除或新建 intent（当前 scope `UNKNOWN_BLOCKED` 会挡同 scope 重试）。
3. 再跑：

```text
uv run python -m sellfox_shipping.cli packages-submit-intent \
  --intent-id <新或已解阻> --actor <你> --no-dry-run --i-understand-side-effects --json
uv run python -m sellfox_shipping.cli packages-verify-intent --intent-id <N> --json
# 再人工看赛狐详情 trackNo + Amazon/通途是否未出现新运单
```

### 结论口径（探针后择一写入）

- **A：** 关自动推送时，`submitToPlatform` 可更新赛狐 `trackNo` 且未推 Amazon → 允许受控填号；平台推送仍延后。
- **B：** 仍推 Amazon / 无法只填赛狐 → **禁止**用此 API 填号；保留代码备用；缺口记「需赛狐提供只写物流 API 或 UI 手工」。
- **C：** 赛狐详情也不更新 → 填号路径无效；仅本地库 + 通途。
- **（曾）D — 部分：** dry-run OK；只读证明本地 import ≠ 赛狐可见；live 待跑。
- **（当前）E — 写路径受阻：** live 代理 **401**；填号结论待 Key/权限修复后再探针。

## 2026-07-20 同事样例（`数据源/蜥蜴国际-p0-样例/20260720/`）

| 文件 | 角色 |
|------|------|
| `上传到蜴国际的Excel.xls` | 上传表（3 行）；参考编号=**通途** `P81428…`（非赛狐 `P2A…`） |
| `蜴国际下载的 跟踪号.xlsx` | 返回表；列 `参考编号/Reference Code` + **`物流单号`** |
| `label(1).pdf` | 面单 PDF |

### 通途 P# → 赛狐 packageSn → 物流单号

| 通途参考编号 | 赛狐 packageSn | 蜴国际物流单号 | 赛狐 status | 赛狐 trackNo（只读前） |
|--------------|----------------|----------------|-------------|------------------------|
| P81428880 | P2AMA9T726894 | 382685918857 | has_shipped | 占位=packageSn |
| P81428893 | P2AMA9T726915 | 382685920386 | has_shipped | 占位=packageSn |
| P81428871 | P2ANA9T727052 | 874574378255 | has_shipped | null |

追溯：ERPNext `Tongtool Package` → Amazon 订单 → 赛狐 `order/detail`（前两票 `trackNo` 字段即 packageSn；第三票按收件人名+订单号对齐）。Amazon 订单已是 **Shipped**（通途已写平台）。

### 本批操作与边界

- 三票均 **`has_shipped`** → **禁止** `submitToPlatform`（项目规则）。
- 参考编号为通途号 → 直接 `lizard-import-tracking` 无法匹配本地 `package_sn`；已用 remapped 表（仅本地 `out/`，不入仓）导入：**3/3 persisted**，本地已有真实 FedEx 号。
- 赛狐详情仍为占位/空 → 再次证明「仅本地 import ≠ 赛狐 UI 可见号」。
- 渠道名解析为蜴国际-FedEx（控制台乱码不改结论）。

## 后续策略（默认）

- **默认不依赖**本系统推销售平台。
- Excel 本地闭环 + 通途写平台 = 现行生产协作方式。
- `SubmissionIntent` 骨架保留；Web **不**开放真调按钮。
- 先修代理对 `submitToPlatform` 的 401，再选 **to_process** 票重做填号探针；**勿**对今日 has_shipped 三票真调。
