---
okf: v0.1
type: Reference
title: UPS 开发者账号与 fzh-ups-track 应用建立记录
description: 2026-09-03 为 UPS Track API 建开发者应用全过程（账号/账户/应用/凭证存放/验证）——凭证不入文档
updated: 2026-09-03
---

# UPS 开发者账号与 fzh-ups-track 应用建立记录（2026-09-03）

> 目标：为 [ups_track](../../README.md)（UPS 跟踪码批量查询）申请 UPS 官方 Track API 的 OAuth 凭证。
> **安全红线**：本文档**不含任何真实 Client ID/Secret**；凭证只存本机 git 忽略的 `.env`。

## 一、关键信息

| 项 | 值 | 备注 |
|----|----|------|
| UPS 账号登录邮箱（开发者/OAuth 关联） | `service@icentrade.com` | **应用创建后不可更改**，改邮箱会失去访问权 |
| 绑定的 UPS 计费/账户 | **`8E270A`** | 用于生产访问关联；Track 按跟踪号查，多仓库账户不影响 |
| 应用名 | **`fzh-ups-track`** | 门户内可见 |
| Credentials Issued | **2026-09-03** | — |
| 产品订阅 | **Authorization (OAuth)** = Approved；**Tracking** = 可用（下见验证） | Track API 必需 |
| 回调 URL | 无（只用 client-credentials） | — |
| 联系人（Primary Contact） | Paula Ma / us@mxdeals.com / 389 Route 10 Unit R, East Hanover NJ 07936 / 732-762-1702 | UPS 建应用时要求，仅用于联系 |

## 二、凭证存放（本机，勿提交）

写入工作区根目录 **`.env`**（已由 `.gitignore` 忽略），变量：

```bash
UPS_CLIENT_ID=…        # 开发者门户 My Apps → fzh-ups-track 内查看（眼睛图标显示）
UPS_CLIENT_SECRET=…
UPS_API_ENV=cie        # cie=测试(wwwcie.ups.com)；prod=生产(onlinetools.ups.com)
# UPS_HTTP_PROXY=…     # 国内直连 onlinetools.ups.com 不通时用
```

运行前加载：`cd <repo> && set -a && . ./.env && set +a`

## 三、建立过程（时间线 / 复现路径）

1. **前置**：已有 UPS.com 公司账号登录；`developer.ups.com` 与 ups.com **共用同一账号**（无需另建一套 UPS 账号）。
2. 浏览器打开 **developer.ups.com** → **Log In**（首次需接受开发者条款）。若用受控浏览器，登录会话是临时的：要点"记住设备"，否则每次受保护操作（如 Add Apps/Create Application）会再走 **step-up 登录 + 邮箱验证码**。
3. **My Apps** → **Add Apps**（URL `/apps/add-app/...`）：
   - Step1 shipper-account：目的选 "I want to integrate UPS technology into my business"；**Choose an account → 8E270A**；勾 UPS API ACCESS AGREEMENT → **Next**。
     > 注：该字段必须选一个账户绑定（UPS 规则），**不代表只能查该账户的件**；Track 按号查，多 UPS 账户不必建多个 app。多个 app 只在将来需要以不同运单号分别用 Shipping API 时才考虑。
   - Step2 contact-detail：填 Primary Contact（见上表）→ **Next**。
   - Step3 apps-details：**App Name = fzh-ups-track**；Callback URL 留空；右侧 **Add Products** 添加 **Tracking**（OAuth 自动含）→ **Next**。
   - Step4 summary：核对（App `fzh-ups-track` / 账户 `8E270A` / 订阅 Tracking + OAuth）→ **Confirm**。
4. 创建后进入应用详情 **developer.ups.com/apps/fzh-ups-track**：Credentials 下 **Client ID / Client Secret**（点眼睛显示）。

## 四、验证结果（2026-09-03，自动化实测）

| 环境 | 结果 |
|------|------|
| CIE（test） | token + track 均 200；确定性样例返回 DELIVERED |
| **prod（生产）** | 真号 `1ZC0019E0301406005` → **label 2026-06-09 / WeHaveYourPackage 2026-07-30 / Delivered 2026-08-04**，与 2026-08-14 PB 人工核查记录完全一致 ✅ |

结论：OAuth 与 Tracking 在 **test+prod 均可查询真实跟踪号**；词表提取（label/actual_ship/delivered 三时点）在真实数据上验证通过。

## 五、日常使用

```bash
cd <repo> && set -a && . ./.env && set +a
python -m ups_track.cli query --input 跟踪号清单.csv --env prod --out 结果
# 产出 结果.summary.csv / 结果.timeline.csv / 结果.raw.json
```

## 六、维护备注

- 凭证丢失/泄露可在门户 My Apps → 应用内轮换/复制；**勿提交、勿外发**。
- 换账户 / 新增发货账户做 Shipping API 时，可另建一个 app（凭证按账户隔离）。
- 本机受控浏览器登录用持久化 profile（本会话 Playwright，`%TEMP%\ups_pw_profile`），仅会话用途；正式运营请以人工在真实浏览器操作维护。
