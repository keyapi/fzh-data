---
type: Research
title: FedEx 官方批量 Track 能力与账号组织勘查
description: 官方 Track API 批量(30/请求)可行；公司 FedEx 开发者账号组织盘点；production 前置=org 需绑未占用真实发货账号号
---

# FedEx 官方批量 Track 调研与账号勘查 (2026-09-04)

## 目标与结论

目标：给一批 FedEx 跟踪码 → 返回轨迹(仿 `ups_track`)。结论：
- **官方 Track API 支持批量，最多 30 个跟踪号/请求**，超出分块即可；**不需要单属于你自己的发货账号**(查号不需目的邮编；跨渠道/VITE/蜴国际出的 FedEx 单都能查)。配额 Track 10 万次/日、限速 1400 次/10s，免费。→ 与 UPS 走开发者账号同思路，完全成立。
- 例外仅两种 FedEx 侧状态：货主标 private → `TRACKING.AUTHORIZATION.ERROR`；面单被取消 → 返回 Cancelled 状态(不是报错)。
- 公司目前**只有 sandbox(test) 可用的 Track 凭证**，无 production 凭证 → 真实单号批量需先拿 prod key。

## 凭证实测

- 2023 TEST key `l7654…` / secret `5596…`：**sandbox 存活**，实测 `POST apis-sandbox.fedex.com/track/v1/trackingnumbers` 返回 200 + Virtual Response(mock 449044304137821, FDXG)。→ 可用于 sandbox 端到端开发。
- 2023 prod 疑似 `l794c…` / `53b6…`：prod+sandbox 均 401 NOT.AUTHORIZED → **已死**。
- `fzh_fedex_track` 项目(今天建)有 TEST key `l761575…`(secret 打码未取)绑 sandbox 账号 740980114。

## 真实跟踪号复核(playwright，FedEx 反爬冷会话会假报错，暖会话/重试后正常)

- `382915919064`：**Delivered** 2026-08-05 10:44，EAST HANOVER,NJ→NEWARK,DE(蜴国际 M6180 单)。
- `875397181317`：**Cancelled**(shipper 取消)，Label 8/5/26，Missouri City,TX→GILBERT,AZ。
- 两者都在 FedEx 系统内 → 官方 API 能返回。

## 开发者组织地图(均可登录，Playwright 实测)

| fedex.com 登录 | 身份 | 开发者组织 | 发货账号 | 备注 |
|---|---|---|---|---|
| `Centrade2`/******** | Paula(log@icentrade.com) Admin | CENTRADE INC **10695072** | 无 | 美东 |
| `daneey`/******** | Eric(ericho@daneey.com) Admin | CENTRADE INC **10879188** | 无 | 有项目 `fzh_fedex_track`(Basic Integrated Visibility=跟踪,TEST key,production 未开) |
| `leonzhao@daneey.com`/******** | 登录失败(密码错/锁) | ? | — | 美中 |
| `lihui@vilavidress.com` | `********`(见 .env) | 2023 建，强制重置+邮箱废 | ? | — | 需客服改邮箱 |

| `lihui@vilavidress.com` | PAULA MA(Admin) | **Centrade (10548976)** | **879197228**(EULA Completed) | **2023 主组织**，有项目 ShipAPITongtool(Rate/Ship/Other, 2023-03-21)；现可登录 |

> 补充：zhangkeyong@vilavidress.com(Admin, 邀请过期)；leonzhao@daneey.com(美中) 登录失败。

- **879197228 归属已定**：绑定在 **2023 主组织 Centrade(10548976)**(账号昵称 CentradeFedex01, EULA Completed)，就是它"被另一组织占用"的来源——**不是赛狐**，是公司自己 2023 的年会组织。管理员=PAULA MA(登录名 `lihui@vilavidress.com`，密码已重置为 ********)。
- 公司可控组织：Centrade(10548976, 有 879197228) / CENTRADE INC(10695072, Paula, 无账号) / CENTRADE INC(10879188, Eric, 无账号, 有 fzh_fedex_track TEST 项目)。

## production 解锁前置

FedEx 规则：开发者组织需绑**至少一个真实(未被其他 org 占用)的发货账号**才能发 production key。已确认 879197228 绑在 **2023 主组织 Centrade(10548976)**(EULA Completed)，且该组织现可登录(lihui@ / ********)。→ **路线 = 在该组织建/复用 Track 项目 → 生成 production key 绑 879197228 → 写 `.env` → 批量实测**。无需赛狐释放/客服/新账号。

## 参考 URL

- FedEx Quotas & rate limits: https://developer.fedex.com/api/da-dk/guides/ratelimits.html
- FedEx New Quotas & rate limits announcement: https://developer.fedex.com/api/en-md/announcements/New_Quotas_and_Rate_limits-Announcement.html
- FedEx Track OpenAPI: https://raw.githubusercontent.com/api-evangelist/fedex/refs/heads/main/openapi/fedex-track-api-openapi.yml
- FedEx 开发者门户 FAQ(org/user-id 关系): https://developer.fedex.com/api/en-co/support/faq.html
- 凭证说明: 公司 org=daneey(Eric)/Centrade2(Paula)，测试号 740561073(sandbox)；真实 879197228 被赛狐占用待解

## 腾讯企业邮箱管理员能否读员工邮件(2026-09-04 调研)

目标：接收发往 `lihui@vilavidress.com` 的 FedEx 重置邮件。结论：**没有一键"打开成员收件箱"**；有这几条路：

1. **邮件备份**(管理员设置"备份到某邮箱"规则)：自生效起把匹配来信实时备份 → 先建规则(收件人含 lihui@ 或关键词 FedEx)，再触发 FedEx 发码，新邮件会被备份到管理员可读邮箱。收费功能、不回溯旧信。
2. **邮件归档**(需申请+公章约3工作日、仅高级/VIP、启用后才有)：归档审计员可搜索归档库。
3. 成员若被删：新版走企业微信后台【协作→邮件→邮箱管理→邮箱回收站】30 天内恢复并重分配；旧版【操作日志】10 天内"恢复账号"。恢复后原密码失效，管理员可【通讯录→成员详情→更多操作→修改密码】——**仅限未绑定微信/手机的成员**；已绑定者只能本人自助重置(lihui 手机已失→此路不通)。
4. 管理员找回/免费版限制：绑定密保或验证域名所有权(CNAME)；免费版只能升级专业版让腾讯强重置。客服热线 400-166-2272。

来源：备份/归档 https://open.work.weixin.qq.com/help2/pc/19849 、https://www.qi-qq.com/NewsDetail/6717940.html ；恢复删除成员 https://www.tengxunqiyeyou.com/forum/forum.php?mod=viewthread&tid=607 、https://www.qq-exmail.cn/read/2456.html ；改成员密码 https://www.qq-exmail.cn/read/1507 、https://www.mail-qq.com/read/1508.html

推论：若 lihui 邮箱账号仍在且未绑微信/手机 → 管理员改密码直接登录最简；否则用"邮件备份规则"截获新来信最稳。

## 凭证落位

有效凭证在 worktree `.env`(gitignored)：`FEDEX_2023_TEST_KEY/SECRET`(sandbox 可用)；**production 已打通**：`FEDEX_API_KEY/FEDEX_SECRET_KEY/FEDEX_ACCOUNT_NUMBER=879197228/FEDEX_ENV=production`(项目 fzh_fedex_track, 组织 Centrade(10548976))。secret 仅在门户显示一次，勿随意重新生成。

## 端到端验证(2026-09-04)

POST `https://apis.fedex.com/track/v1/trackingnumbers`(用 production key)：
- `382915919064` → code=DL `Delivered`
- `875397181317` → code=CA `Shipment cancelled by sender`
两者均为货代(VITE/蜴国际)渠道出的 FedEx 单，**官方 API 按号可跨渠道查询**（无需单号属于自有账号）。
