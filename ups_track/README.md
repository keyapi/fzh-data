---
okf: v0.1
type: Guide
title: ups_track — UPS 跟踪码批量查询
description: UPS 官方 Track API 批量查询工具：一堆跟踪码 → 每号当前状态 + 完整节点时间线 + raw JSON
updated: 2026-09-02
---

# ups_track — UPS 跟踪码批量查询工具

通用、可复用：喂一份 UPS 跟踪码清单，用 **UPS 官方 Track API（REST + OAuth2）**批量查询每个号的跟踪节点，
输出当前状态 + 完整时间线。不绑定 PB 对账 / sellfox 等任何单一业务，后续模块 import 即可。

## 为什么

UPS 跟踪页是 JS 渲染，HTTP 抓不到，只能浏览器逐单点。一堆跟踪码需要批量查节点信息时，人工不可行。

## 快速开始

```bash
# 1) 离线演示（无需凭证/网络，看流程与输出格式）
python -m ups_track.cli query --input tracking.txt --out result --mock

# 2) 真实查询（凭证见下方；默认 cie 测试环境）
python -m ups_track.cli query --input tracking.csv --env prod --out result

# 3) 断点续跑（上次中断后跳过已成功单号）
python -m ups_track.cli query --input tracking.csv --env prod --out result --resume
```

输入格式：
- `.txt`：每行一个跟踪号（行内可带空格备注：`1Z999... 备注`，第二段成为备注列）。
- `.csv`：首列跟踪号；若首行为表头（含 tracking/跟踪号 等词）自动识别列，其余列拼进备注。

输出（同一前缀三件套）：

| 文件 | 内容 |
|------|------|
| `result.summary.csv` | 每号一行：备注/当前状态/已交付/交付日期城市签收人/建标/实际发货/最近节点/错误 |
| `result.timeline.csv` | 每号**每个节点一行**：时间/状态类型码/描述/城市州邮编 |
| `result.raw.json` | 每号原始响应（留档 + `--resume` 断点依据） |

## 凭证（Phase 0，自办）

1. developer.ups.com 注册（公司 Daneey LLC）→ 建 App 取 OAuth `client_id/secret`。
2. 申请 Track API 生产访问；实测能否查你的 1Z 号（是否需要绑定 UPS shipper 账号）。
3. 变量（真值只放 gitignored `.env`，见 [.env.example](.env.example)）：
   `UPS_CLIENT_ID` / `UPS_CLIENT_SECRET` / `UPS_API_ENV=cie|prod` / 可选 `UPS_HTTP_PROXY`（国内直连不通时走代理）。

## 常用参数

`--workers N` 并发 / `--retries N` 可重试次数 / `--limit N` 只查前 N 个（调试）/
`--delay S` 每号间隔（温和节流）/ `--base-url` 显式覆盖 / `--proxy URL`。

## 测试

```bash
python -m pytest ups_track/tests -q   # 离线：mock HTTP，无需凭证/网络
```

文档：[docs/index.md](docs/index.md)
