---
okf: v0.1
type: Log
title: NAS_API 变更日志
---

# 变更日志

## 2026-08-31
- **更新** `reference/nas-multi-domain-access.md`、solutions 条目 — 澄清 OpenWrt 自定义域全栈（非仅 NAS 加证）、路径 A/B 与 QC 跳转关系；DSM 外部访问 DDNS 不能改 QC 目标、勿删 myds、无 mxdeals 优先；中国区 QC 政策摘要。

## 2026-08-28
- **新增** `reference/nas-multi-domain-access.md` — 汇总 2026-08-27~28 多域名访问实施：nas.daneey.com（阿里云+OpenWrt ACME）、nas.vilavi.cn（Cloudflare 灰云+DDNS+ACME）、DSM 反代与证书绑定铁律、联通 443 限制、QC 直连/中继与 Chrome 安全 DNS 问题。
- **新增** `../AGENT_HANDOFF.md`、`.agents/skills/nas-access/SKILL.md`。
- **政策记录**：统一入口仍为 `fangzhouhui.quickconnect.cn`；深圳 `myds.me` 未决。

## 2026-08-27
- **实施** `nas.daneey.com`：OpenWrt 阿里云 DDNS + DNS-01 证书 → DSM 导入 `aJodgl` → 反代 443/11024（Host: fzh.myds.me）。
- **教训**：误绑 DSM 桌面服务到新证导致 `fzh.myds.me:11024` 证书警告；已回滚默认证 `RmB4St`。
