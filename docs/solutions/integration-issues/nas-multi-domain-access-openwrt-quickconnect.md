---
okf: v0.1
type: Solution
title: 群晖 NAS 多域名访问 — OpenWrt ACME、DSM 反代与 QuickConnect 选路
description: 在保留 fzh.myds.me 默认证的前提下，用 OpenWrt 为 nas.daneey.com / nas.vilavi.cn 签第二张证并反代；记录 QC 直连/中继、联通 443 与深圳未决项。
module: NAS_API
date: 2026-08-28
last_updated: 2026-08-31
category: integration-issues
problem_type: integration_issue
component: infrastructure
severity: medium
symptoms:
  - "深圳无法解析或访问 fzh.myds.me，QuickConnect 跳转后失败"
  - "自定义域名访问 DSM 证书与主机名不匹配"
  - "办公室局域网访问公网域名无响应（NAT 回环）"
  - "外网 https://nas.daneey.com/ 无端口不可用，:11024 可用"
  - "部分浏览器 QuickConnect 走 cn4 中继而非 fzh.myds.me 直连"
root_cause: configuration_gap
resolution_type: documentation_update
tags: [nas, synology, quickconnect, openwrt, acme, cloudflare, daneey, vilavi, dsm, reverse-proxy]
related_components: [NAS_API, us_openai_api_proxy]
---

# 群晖 NAS 多域名访问 — OpenWrt ACME、DSM 反代与 QuickConnect 选路

## Problem

北京办公室群晖 NAS 长期通过 QuickConnect（`fangzhouhui.quickconnect.cn`）统一入口访问。深圳办公室及部分网络无法解析群晖官方 DDNS `fzh.myds.me`，导致 QC 自动跳转后失败。需要在**不替换 QC 统一入口**、**不破坏 `fzh.myds.me` 默认证**的前提下，增加阿里云/Cloudflare 自定义域名，并理清办公室劫持、外网端口与 QC 直连/中继选路。

## Symptoms

- 深圳访问 `https://fzh.myds.me:11024/` 失败（园区 DNS 特殊）。
- `http://nas.mxdeals.com:11024` 办公室无响应；手机流量上证书为 `fzh.myds.me` 与主机名不符。
- 光猫仅转发 11024；外网 `https://nas.daneey.com/`（443）不通，`:11024` 通。
- 办公室 OpenWrt WiFi 上部分台式机 Chrome 打开 QC 走 `cn4` 中继，Edge/手机仍直连 `fzh.myds.me:11024`。

## Investigation

1. NAS 双网口：`192.168.100.242`（OpenWrt）与 `192.168.1.5`（光猫）；公网 `123.117.236.65`。
2. OpenWrt `dhcp.@domain` 已将 `fzh.myds.me`、`nas.daneey.com`、`nas.vilavi.cn`、`nas.mxdeals.com` 劫持到 `.242`。
3. 误将 DSM 桌面服务绑到新证 → 全站 11024 SNI 变化；已回滚 `RmB4St`。
4. 反代须设 `Host: fzh.myds.me`，否则 `proxy_pass` 环回 400。
5. Cloudflare 橙云导致 `nas.vilavi.cn:11024` 不可用；改灰云 A 记录后外网 11024 通。
6. 公网多地探测：11024 open，443/80 timeout（联通限制或光猫占用）。
7. QC：公网 IP hairpin 超时；LAN 劫持直连 200；Chrome 安全 DNS 可绕过劫持。

## Solution

### 1. nas.daneey.com（阿里云 + OpenWrt）

- OpenWrt `ddns.myddns_ipv4` → 阿里云更新 A 记录。
- `acme.nas_daneey`：`dns_ali`，生产 Let's Encrypt，不更新 LuCI。
- DSM 导入为第二张证 `aJodgl`；反代 443/11024；`SYNO.Core.Certificate.Service` 仅绑 ReverseProxy。

### 2. nas.vilavi.cn（Cloudflare + OpenWrt）

- Cloudflare A **灰云** → 公网 IP；Zone token（DNS Edit + Zone Read）。
- `ddns.nas_vilavi` + `update_cloudflare_com_v4.sh`；`dns_server=1.1.1.1`。
- `acme.nas_vilavi`：`dns_cf` + `CF_Zone_ID`；CAA `letsencrypt.org` 解决 LE 签发。
- DSM 导入/更新 `orAHAw`；反代与绑定同 daneey 模式。

### 3. 访问策略（用户确认）

| 场景 | 推荐 |
|------|------|
| 对外统一宣传 | `https://fangzhouhui.quickconnect.cn/` |
| 深圳/已知 DNS 问题 | `https://nas.daneey.com:11024/` 或 `https://nas.vilavi.cn:11024/` |
| 北京办公室书签 | 同上或 `https://fzh.myds.me:11024/`（劫持下直连） |

不强制全员改用固定域名，以免失去 QC 中继兜底。

### 4. Chrome QC → cn4

关闭 Chrome「使用安全 DNS」或改为「当前服务提供商」；`chrome://net-internals/#dns` 清缓存。根因：DoH 解析公网 IP → NAT 回环失败。

### 5. 两条访问路径（2026-08-31 澄清）

**常见误解：** `nas.daneey.com` / `nas.vilavi.cn` 不只是「NAS 里加了证书」，而是 **OpenWrt + DSM 全栈**；且与 QuickConnect 跳转是**两条独立路径**。

| 路径 | 谁管 DNS | 谁管证 | 是否写入 DSM「外部访问→DDNS」 | QC 会自动跳吗 |
|------|----------|--------|------------------------------|---------------|
| **A：OpenWrt 自定义域** | OpenWrt DDNS（阿里云/Cloudflare） | OpenWrt ACME → DSM 导入第二张证 + 反代 | **否**（刻意不写，避免与 OpenWrt 重复更新） | **否** — 须用户手动输入 URL |
| **B：QC 统一入口** | 群晖 Synology DDNS（`fzh.myds.me`） | DSM 默认证 `RmB4St` | **是**（用户配置的 Synology 提供商） | **是** — 探测成功则跳 `fzh.myds.me:11024`，失败则 `cn4` |

路径 A 完整步骤：OpenWrt 更新公网 A 记录 → ACME DNS-01 签发 → DSM `import` 第二张证 → 反代 443/11024（`Host: fzh.myds.me`）→ OpenWrt 办公室 dnsmasq 劫持。

路径 B 由群晖云端登记；浏览器打开 `fangzhouhui.quickconnect.cn` 后，QC 页 JS 只探测**群晖已知主机名**（当前为 `fzh.myds.me`），**不会**探测 daneey/vilavi/mxdeals。

### 6. DSM「外部访问→DDNS」能否改 QC 跳转目标？

**结论：不能指望；勿删 `fzh.myds.me`。**

- DSM **没有**「DDNS 优先级」或「让 mxdeals 优先于 myds」的选项。
- 删除 `fzh.myds.me` 高风险：默认证 `RmB4St`、QC 账号绑定、续期都可能受影响；**不会**可靠地变成只跳 `nas.mxdeals.com`。
- 仅把 `nas.mxdeals.com` 加进外部访问 DDNS、不配独立证+反代：QC 即使尝试跳转也会证书主机名不匹配。
- 若要让某自定义域成为 QC **候选**直连目标，需：独立 LE 证 + 反代 + 写入 DSM 外部访问 DDNS，且仍**不保证**覆盖中国区 QC 对 `myds.me` 的偏好（2023 年起国内 `*.direct.quickconnect.cn` IPv4 公网解析已关闭，外网多走中继）。

**深圳问题本质：** QC 成功时仍跳 `myds.me`；深圳 DNS 解析 myds 失败 → 打不开。备用域（daneey/vilavi）走路径 A，**必须手动书签**，不能靠改 DSM DDNS 列表替代 QC。

### 7. 中国区 QC 政策（调研摘要）

群晖工单/社区（2023-11）：为符合国内环境，`*.direct.quickconnect.cn` 已关闭 **IPv4 公网解析**；外网 QC 默认经中继。有公网 IP 时官方建议 **自建 DDNS + 端口转发**（即路径 A），而非指望 QC 直连。详见 [Synology QuickConnect 白皮书](https://global.download.synology.com/download/Document/Software/WhitePaper/Os/DSM/All/enu/Synology_QuickConnect_White_Paper_enu.pdf)。

## Why This Works

- **第二张证 + 反代 SNI**：nginx 按 `server_name` 出示对应 LE 证，默认 DSM 服务仍用 `fzh.myds.me`。
- **OpenWrt 劫持**：LAN 客户端解析自定义域名到 NAS，不经光猫回环。
- **灰云 + 11024**：Cloudflare 橙云不代理非标准端口；外网必须灰云 A + 光猫转发 11024。
- **QC 选路**：客户端侧连通性探测决定直连或 cn4，与服务器配置正交；办公室需 DNS 劫持配合。

## Prevention

| 规则 | 说明 |
|------|------|
| 勿绑 DSM 桌面服务到新证 | 只绑 ReverseProxy service |
| 反代 Host 头 | 固定 `fzh.myds.me` |
| Cloudflare NAS 记录 | 永远灰云 |
| ACME 凭证 | `CF_Token` 仅 Zone 级，不入 git |
| 外网 HTTPS | 默认写 `:11024`，直到 443 公网打通 |
| 文档入口 | `NAS_API/AGENT_HANDOFF.md`、`NAS_API/docs/reference/nas-multi-domain-access.md` |
| 勿用 DSM DDNS 改 QC 目标 | daneey/vilavi 走 OpenWrt 路径；QC 只认群晖登记名（myds） |
| 勿删 `fzh.myds.me` | 保默认证与 QC 登记；mxdeals「优先」无官方开关 |

## Open Items

- 深圳 `fzh.myds.me` 解析（QC 跳 myds 后失败；备用书签 daneey/vilavi）
- 联通公网 443
- `nas.mxdeals.com` 独立证书（若要做 QC 候选需全栈，仍不保证替代 myds）
- 台式机 Chrome QC 直连（安全 DNS）
- 可选实验：隐身窗口测 QC 最终 URL（改外部访问 DDNS 前必做对照）

## Cross-References

- [NAS_API/docs/reference/nas-multi-domain-access.md](../../../NAS_API/docs/reference/nas-multi-domain-access.md)
- [NAS_API/AGENT_HANDOFF.md](../../../NAS_API/AGENT_HANDOFF.md)
- [us_openai_api_proxy/docs/office-lan-access.md](../../../us_openai_api_proxy/docs/office-lan-access.md)
