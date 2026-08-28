---
okf: v0.1
type: Solution
title: 群晖 NAS 多域名访问 — OpenWrt ACME、DSM 反代与 QuickConnect 选路
description: 在保留 fzh.myds.me 默认证的前提下，用 OpenWrt 为 nas.daneey.com / nas.vilavi.cn 签第二张证并反代；记录 QC 直连/中继、联通 443 与深圳未决项。
module: NAS_API
date: 2026-08-28
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

## Open Items

- 深圳 `fzh.myds.me` 解析（QC 统一入口后续议题）
- 联通公网 443
- `nas.mxdeals.com` 独立证书
- 台式机 Chrome QC 直连稳定性

## Cross-References

- [NAS_API/docs/reference/nas-multi-domain-access.md](../../../NAS_API/docs/reference/nas-multi-domain-access.md)
- [NAS_API/AGENT_HANDOFF.md](../../../NAS_API/AGENT_HANDOFF.md)
- [us_openai_api_proxy/docs/office-lan-access.md](../../../us_openai_api_proxy/docs/office-lan-access.md)
