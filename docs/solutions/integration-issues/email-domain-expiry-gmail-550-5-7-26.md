---
okf: v0.1
type: Reference
title: 邮件域名到期 → Gmail 550-5.7.26 拒收：续费≠恢复，注册商≠DNS 托管商
description: 域名过期后阿里云把注册局 NS 切到过期停放组，SPF/MX/DKIM 全部停止解析；续费不等于恢复。含三层排查（RDAP→权威 NS→真实 zone）、自定义 DKIM selector、补 DMARC 与修 MX 优先级。
date: 2026-11-06
category: integration-issues
module: email_delivery
problem_type: integration_issue
component: email-delivery
severity: high
applies_when:
  - "公司域名邮件被 Gmail/Outlook 以 550-5.7.26「sender is unauthenticated, SPF/DKIM did not pass」拒收"
  - "域名已续费但邮件仍未恢复，或 MX/SPF/DKIM 记录解析不到"
  - "排查 registrar 与 DNS 托管商不一致（阿里云注册、DNSPod/Cloudflare 实际解析）"
  - "为腾讯企业邮等补 SPF/DKIM/DMARC 记录或修正 MX 优先级"
tags: [email-delivery, dns, spf, dkim, dmarc, domain-expiry, dnspod, cloudflare]
---

# 邮件域名过期 → Gmail 5.7.26 硬拒：续费不等于恢复，SPF/DKIM/DMARC 要按注册局→托管商→记录三层重建

## Context

2026-11-05 18:16，同事用 `@vilavidress.com` 地址经**腾讯企业邮**给 Gmail 收件人发业务邮件（含面单附件），被 Gmail 直接拒收：

```
550-5.7.26 Your email has been blocked because the sender is unauthenticated.
Authentication results: DKIM = did not pass;
SPF [vilavidress.com] with ip [54.207.22.x] = did not pass.
In reply to DATA command.
```

这类 550-5.7.26 是**收件方在 DATA 阶段硬拒**，不是进垃圾箱、也不是延迟退信——发件侧（腾讯企业邮）全程显示"已发送"，同事完全无感。整个排查的关键不是"邮件服务坏了"，而是**域名侧的发信身份证明全部消失**。诊断链路按证据顺序如下：

1. **先排除伪造/第三方中继**：反查发送 IP `54.207.22.x` → `smtpbgbr2.qq.com`（AS16509，圣保罗节点）。说明信确实是从腾讯企业邮的海外出口发出去的，不是被冒用、也不是别家中继。
2. **正面查域名**：用三个 DoH（`doh.pub`、`dns.alidns.com`、`cloudflare-dns.com`）交叉查询 `vilavidress.com` —— 没有根 TXT（即没有 SPF）、没有 MX、没有 `_dmarc`、没有 `dkim._domainkey`；而且**每个主机名都 CNAME 到 `expired.hichina.com`**（阿里云的过期域名停放页）。三路结果一致，排除单一递归缓存作祟。
3. **查注册局权威数据**：Verisign RDAP 显示 NS = `EXPIRENS3.HICHINA.COM` / `EXPIRENS4.HICHINA.COM`，status `active`，到期 `2027-11-03`，last changed `2026-11-04T15:00Z`。也就是说**域名已经续费**，但注册局层面的 NS 仍指向"过期停放"组。
4. **绕过缓存直接问权威 NS**：`dns7.hichina.com` / `dns8.hichina.com` 对 TXT、MX 一律返回 **NODATA**，只回 SOA（serial `2021102219`）。证明不是 TTL 缓存问题，是**记录根本没在服务**。
5. **根因**：域名 `2026-11-03` 到期 → 阿里云把注册局 NS 切到过期停放组 → 全部邮件 DNS 记录停止解析。`2026-11-04` 完成续费（到期延到 `2027-11-03`），但 NS 没回、记录不服务。腾讯企业邮照常发信，收件方查不到 SPF、验不了 DKIM，Gmail 按 5.7.26 拒收。**续费本身没有恢复邮件。**
6. **真正的分水岭是注册商控制台截图**：域名在阿里云注册，但 **DNS 托管在 DNSPod**（`a.dnspod.com、b.dnspod.com、c.dnspod.com`）。续费后在阿里云控制台执行了一次"同步"，注册局 NS 才回到 DNSPod。
7. **DNSPod 里的 zone 其实是完好的**：SPF `v=spf1 include:spf.mail.qq.com ~all`；MX `mxbiz1.qq.com`、`mxbiz2.qq.com`（两条曾同为优先级 5，后改为 5/10）；DKIM 是**自定义 selector** `sjnr2306._domainkey`（2023 年加的 1024-bit RSA）。只探常见 selector（`dkim`、`s1`、`s2`、`tencent`、`mail`、`default`、`dkim1` …）全部 NXDOMAIN —— 差一点得出"这台域名没有 DKIM"的错误结论。
8. **另一台主域 `vilavi.cn` 在 Cloudflare**（NS `alex.ns.cloudflare.com、grace.ns.cloudflare.com`）：SPF、MX 齐全，DKIM selector 是另一个自定义名 `evhe2306._domainkey`（有完整公钥），**唯独没有 DMARC**。经 Cloudflare API 加上 `_dmarc` TXT = `v=DMARC1; p=none`（TTL 600），三路 DoH 立即都能看到。
9. **最终状态**：两台域名 SPF / MX / DKIM / DMARC 齐备，`vilavidress.com` 的 NS 回到 DNSPod。剩下的验证动作是发一封 Gmail 测试信，确认 `spf=pass` / `dkim=pass` / `dmarc=pass`。

关键证据一览（外部 DNS 事实为 2026-11-06 当日观测）：

| 证据源 | 观察值 | 说明 |
|--------|--------|------|
| Gmail 退信头 | `DKIM = did not pass; SPF [vilavidress.com] with ip [54.207.22.x] = did not pass` | 未认证发件人，DATA 阶段硬拒 |
| 发送 IP 反查 | `54.207.22.x` → `smtpbgbr2.qq.com`（AS16509，圣保罗） | 确实走腾讯企业邮海外出口，非第三方中继 |
| 三路 DoH 查 `vilavidress.com` | 无根 TXT / 无 MX / 无 `_dmarc` / 无 `dkim._domainkey`；主机名 CNAME → `expired.hichina.com` | 域名被过期停放，邮件记录整体消失 |
| Verisign RDAP（注册局权威） | NS = `EXPIRENS3.HICHINA.COM、EXPIRENS4.HICHINA.COM`；status `active`；expiration `2027-11-03`；last changed `2026-11-04T15:00Z` | 已续费，但 NS 仍在停放组 |
| 权威 NS `dns7.hichina.com、dns8.hichina.com` | TXT/MX 返回 NODATA，仅 SOA，serial `2021102219` | 记录未服务，排除缓存问题 |
| 注册商控制台 | 阿里云注册，DNS 托管在 DNSPod（`a.dnspod.com、b.dnspod.com、c.dnspod.com`） | 注册商 ≠ DNS 托管商 |
| DNSPod zone | SPF `include:spf.mail.qq.com ~all`；MX `mxbiz1.qq.com、mxbiz2.qq.com`；DKIM `sjnr2306._domainkey` | 区域本身完好，只等 NS 指回来 |
| Cloudflare（`vilavi.cn`） | NS `alex.ns.cloudflare.com、grace.ns.cloudflare.com`；SPF/MX/DKIM(`evhe2306._domainkey`) 齐全；无 DMARC | 补了 `p=none`，TTL 600 |
| 最终状态 | 两台域名 SPF/MX/DKIM/DMARC 齐备，NS 回 DNSPod | 待 Gmail 测试信确认三项 pass |

## Guidance

### A. 恢复清单（按顺序，别跳步）

1. **先给发送 IP 定性**。反查 IP 的 PTR/归属，确认是自家邮件服务商出口还是第三方中继。若是自家出口，问题几乎必然在域名 DNS，而不是账号或密码。
2. **查注册局 RDAP，不看缓存**。直接读 Verisign RDAP 的 NS 与 `events`：NS 形如 `EXPIREN*.HICHINA.COM` 就是"过期停放"，到期时间已更新说明续费成功——这只证明域名保住了，**不证明邮件能通**。
3. **绕过递归缓存，直接问权威 NS**。用 RDAP 拿到的 NS 名做 `nslookup -type=TXT/-type=MX`。返回 NODATA/SOA 而没有任何记录 → 记录不在服务，问题在 DNS 而不是在邮件服务商。
4. **去注册商控制台看 DNS 托管商是谁**。注册商是阿里云，不代表 DNS 在阿里云；本案 DNS 实际在 DNSPod，主域又在 Cloudflare。**先认清 NS 归属，再决定去哪儿改记录**。
5. **续费后把 NS 打回真实托管商**。本案是在阿里云控制台执行"同步"后，注册局 NS 才回到 DNSPod。回查 RDAP 确认 NS 已变更，再用权威 NS 验证记录真的开始返回（不是只看控制台绿标）。
6. **在真实 zone 上逐项复核四件套**：根 TXT(SPF)、MX、DKIM TXT、`_dmarc` TXT。任何一项缺都算未恢复。
7. **DKIM selector 从邮件服务商管理后台读**。腾讯企业邮的管理后台有「查看配置」入口，能直接给出 selector 名（本案 `sjnr2306`、`evhe2306`）。**不要用常见 selector 猜**——猜不到只能证明"你没猜中"，不能证明"没有 DKIM"。
8. **补 DMARC**。`p=none` 起步、加 `rua` 收聚合报告；`p=none` 只是观察模式，但不加 `rua` 就连报告都没有。
9. **发测试信，读 `Authentication-Results` 自证闭环**（见下）。
10. **接受缓存窗口**。记录 TTL 600 有正缓存；否定答案按 SOA minimum 缓存（Cloudflare 常见 1800s）；NS 委派变更在 `.com` 侧最长可到 24–48h（委派 TTL 可能接近 2 天）。**修复后立刻重试失败，不代表没生效**。

### B. 验证命令（公共 DoH + RDAP）

```bash
# 1) 三路 DoH 交叉查 NS / SPF / MX / DMARC（路径各不相同，注意别拼错）
curl -s 'https://doh.pub/dns-query?name=vilavidress.com&type=NS' -H 'accept: application/dns-json'
curl -s 'https://dns.alidns.com/resolve?name=vilavidress.com&type=TXT' -H 'accept: application/dns-json'
curl -s 'https://cloudflare-dns.com/dns-query?name=_dmarc.vilavidress.com&type=TXT' -H 'accept: application/dns-json'
curl -s 'https://cloudflare-dns.com/dns-query?name=sjnr2306._domainkey.vilavidress.com&type=TXT' -H 'accept: application/dns-json'

# 2) 注册局权威：NS 有没有回、到期时间、最近变更事件
curl -s 'https://rdap.verisign.com/com/v1/domain/vilavidress.com' \
  | jq '{status, events, nameservers: [.nameservers[].ldhName]}'

# 3) 绕过缓存直问权威 NS（Windows 自带 nslookup 即可）
nslookup -type=TXT vilavidress.com dns7.hichina.com
nslookup -type=MX  vilavidress.com dns7.hichina.com
```

判读要点：三路 DoH 结果不一致时，以**权威 NS 的直查**为准；RDAP 的 `nameservers` 才是注册局当前真实委派，控制台显示会滞后。

### C. 读 Gmail 的 Authentication-Results

在收件人 Gmail 里「显示原始邮件」，找 `Authentication-Results: mx.google.com` 这一段：

```
Authentication-Results: mx.google.com;
       spf=pass (google.com: domain of ... designates 54.x.x.x as permitted sender) smtp.mailfrom=vilavidress.com;
       dkim=pass header.i=@vilavidress.com header.s=sjnr2306 header.b=...;
       dmarc=pass (p=NONE sp=NONE dis=NONE) header.from=vilavidress.com
```

- 三行看 `spf` / `dkim` / `dmarc` 是否都是 `pass`；
- `spf` 的 `smtp.mailfrom` 域、`dkim` 的 `header.i` 域，要与信头 `From:` 域**对齐**（DMARC alignment），否则即使单项 pass，`dmarc` 仍可能 fail；
- `header.s=` 就是实际使用的 selector，可与后台配置对照；
- `dmarc=pass` 才是"长期不再被 5.7.26 拒"的依据——Gmail 的准入只看 SPF **或** DKIM 有一条通过，但 DMARC 对齐才让这条链稳定成立。

## Why This Matters

- **续费 ≠ 恢复**。这是本案最大的认知缺口：付款成功、到期日已延后、控制台显示"正常"，但注册局 NS 仍停在过期停放组，记录一条都不服务。只查"域名是否过期"会得出完全相反的结论。
- **注册商 ≠ DNS 托管商**。同一家公司两台域名，一台 DNS 在 DNSPod、一台在 Cloudflare；对着阿里云控制台找记录，会找不到、也改不对。先 RDAP 看 NS，再决定进哪个控制台。
- **"没有 DKIM"是最危险的错误结论**。腾讯企业邮使用**随机自定义 selector**，扫描常见名字全部 NXDOMAIN 是预期结果。据此给域名重配 DKIM，会覆盖或误删正在用的 key，反而制造新故障。selector 只能从邮件管理后台读。
- **认证是一条链**。SPF 缺失/覆盖不到发送 IP，加上 DKIM 公钥查不到 → 收件侧无法完成任何一项认证 → Gmail 5.7.26 硬拒。补 DMARC 对齐是把这条链固化的长期解，而不是"再加一条记录"。
- **缓存会让"修好了"看起来没修好**。正缓存 TTL、否定缓存 SOA minimum、NS 委派 TTL 三层叠加，最坏 24–48h。没有这个预期，就会在已经修好的系统上继续乱改。
- **业务侧零感知**。发件服务器照常 250 接收，退信只回到发件人；域名到期这类基础资源若不监控，会以"客户说没收到"的形式暴露。

## When to Apply

- 收到 `550-5.7.26` / `SPF did not pass` / `DKIM did not pass` 类退信，且发件域是自家域名时。
- 域名刚过期又续费、或刚做过域名转入/转出、注册商与 DNS 托管商变更之后。
- 新建发信域名、迁移邮件服务商（企业邮 / 自建 / ESP）后做发信合规自查。
- 排查"邮件能发出去但对方收不到/Gmail 拒收"的任何工单——先按本文第 1–5 步走一遍，再怀疑邮件网关本身。
- 域名的到期与 NS 委派应纳入例行巡检，而不是等退信才发现。

## Examples

**修复前后对照（`vilavidress.com`，2026-11-06 观测）**

| 项 | 事故中 | 修复后 |
|----|--------|--------|
| 注册局 NS | `EXPIRENS3.HICHINA.COM、EXPIRENS4.HICHINA.COM`（过期停放） | 回到 DNSPod `a.dnspod.com、b.dnspod.com、c.dnspod.com` |
| 根 TXT (SPF) | 无 | `v=spf1 include:spf.mail.qq.com ~all` |
| MX | 无（仅停放页） | `mxbiz1.qq.com`(5) / `mxbiz2.qq.com`(10) |
| DKIM | `sjnr2306._domainkey` 查不到 | 完整公钥可解析 |
| 主机名解析 | CNAME → `expired.hichina.com` | 正常指向各自服务 |
| Gmail 结果 | 550-5.7.26 硬拒 | 待测试信确认 spf/dkim/dmarc = pass |

**主域 `vilavi.cn` 的补齐动作**：SPF / MX / DKIM(`evhe2306._domainkey`) 原本就在，仅缺 DMARC；通过 Cloudflare API 写入 `_dmarc` TXT `v=DMARC1; p=none`（TTL 600），三路 DoH 立即一致可见。

**易踩的小坑**

- DNSPod 两条 MX 曾**同为优先级 5**：可用但不规范，应为 5/10，让收件方有确定的主备顺序。
- DKIM 目前是 **1024-bit RSA**：能通过认证，但后续应升级到 2048-bit（升级时新旧 selector 并存过渡，别直接覆盖）。
- `p=none` 且**没有 `rua`**：等于开了观察模式却没有报告，等于没开。
- 只查 `dkim._domainkey` 就断言无 DKIM：本案 selector 是 `sjnr2306`，正确做法是先从腾讯企业邮后台「查看配置」取名字，再针对性查询。

## Related

- `docs/solutions/integration-issues/nas-multi-domain-access-openwrt-quickconnect.md` —— 同属域名/DNS/证书运维域，多域名解析与访问链路的相邻经验
- `NAS_API/AGENT_HANDOFF.md` —— NAS_API 模块交接：域名、证书与入口的落地细节
