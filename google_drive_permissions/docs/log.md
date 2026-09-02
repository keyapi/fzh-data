---
okf: v0.1
type: Log
title: Google Drive 权限管理 — 操作时间线（2026-09）
---

# 操作日志

> 记录这次权限运维的背景、过程、结果、残留。日期跨 2026-09-01 ~ 09-02。

## 背景

用户（kyzh2022 名下）有大量 Google 表 / Colab notebook 被历史共享给多名员工。存在：
1. 前财务负责人换成现任（zj），需继承编辑权限；
2. 一批离职/停用账号仍残留权限；
3. 服务账号只能管理显式共享给它的文件，无法全局审计；
4. 用户想长期自动化操作自己的 Drive，却遇到 OAuth reminder / 7 天过期顾虑。

## 过程

### 阶段 A：给现任财务补权（2026-09-01）
- 给 12 张月度通途订单表（通途订单202501-202512）加现任财务负责人（zj）的 writer。
- 校验：已有 2 张（202501/202507）原本就有，其余 10 张补齐。

### 阶段 B：全量盘点 + 补权 + 清理（SA 视角，130 表）
- Drive files.list 带 permissions 一次性盘点服务账号可见的 130 张 spreadsheet。
- 给所有含 zhongyu0702 的表补 zj 权限（89 张）。
- 移除已确认离职/停用账号权限（两批共 17 个账号，283+ 处）。
- 列出 8 张「公开链接 anyone」表（其中 1 张 anyone=writer 最危险），用户先选择不处理。

### 阶段 C：搭建用户 OAuth，全局审计（989 表 + 134 Colab）
- 建立用户级 OAuth（client_id 234331188447-ttn1928b7…，scope drive）→ `gsheets-user-oauth.json`。
- 全量盘点：989 张 spreadsheet + 134 个 Colab = 1123 文件。
- 用用户身份移除 DHL Colab 上的 3 个离职账号（服务账号因「仅属主可改共享」此前被 403 拒）等。

### 阶段 D：Colab 归属分析 + 业务托管（2026-09-02）
- 分析 134 个 Colab：15 个有同事 writer = 业务 Colab；119 个纯个人/测试/备份。
- 给 15 个业务 Colab 补 SA writer（12 个新增 + 3 个已有）。
- 发现 DHL Colab 是「仅属主可改共享」（SA canShare=False）→ 属主 `writersCanShare` 修复，SA 现可完整操作全部 15 个。

### 阶段 E：台账落地
- 生成 Google Sheet 台账：账号主清单（39 条）+ 现状明细（313 行，电子表格281/Colab32）。
- 明确「台账为权威源，CSV 不入仓」。

## 结果

- 17 个离职账号已清理；在职/外部账号保留；自己 + 服务账号 + Automa SA 标「不取消」。
- 15 个业务 Colab 已由 SA 完整托管（含 DHL 修复）。
- 台账已建，SA 已加为 editor，Agent 可读取调用。
- 用户 OAuth token 实测仍可刷新，身份正确；已设 7 天到期前自动重授权提醒兜底。

## 残留 / 未处理（用户决策）

1. **4 个「属主是离职账号」的文件**：Mano DE / Mano FR / Vercart IT（mxdeals1023 属主），无法靠清权限（Drive 不允许移除离职属主），需复制/重建。用户选择**暂不管**。
2. **公开链接表**：实测 11 张 anyone 可访问（6 张 writer）。用户选择**暂不管**。
3. **Publish 到 Production**：Google Cloud Console「Publish app」被"OAuth configuration is incomplete"锁住，TBD。
4. **用户 OAuth 7 天过期**：靠 cron 提醒兜底，长期方案是发布 Production。

## 待办金句

> 数据以 Google Sheet 台账为准；执行权限变更前先读「账号主清单」看处理方式。
