---
okf: v0.1
type: Log
title: NAS_API 变更日志
---

# 变更日志

## 2026-11-11

- **新增** `reference/router-port-forward-inventory.md` 的「光猫要不要改桥接」调研：结论是**新办公室保持路由模式、不桥接**。核实要点：`光猫 LAN2 → 新华三 WAN2` 是策略路由已禁用的备用口，"直连"用户实际连的是光猫自带 WiFi；桥接后光猫 WiFi 不能上网，且 PPPoE 只能单台设备拨号；座机在上网/语音分 VLAN 时通常不受影响但须装维拨测；H3C ER3208G3-P-E 官方支持 PPPoE、双 WAN、多 SSID + SSID 绑 VLAN（含来源 URL）。

## 2026-11-10

- **新增** `reference/router-port-forward-inventory.md` — 办公室搬迁前的光猫（中兴 ZXHN F4610U）只读盘点：16 条端口转发逐条实测（其中 `5000`、`2049`、`111`、`892` 为内网无监听的死规则）、4 条静态 DHCP 绑定、LAN/PPPoE/DDNS/DMZ/ALG/防火墙/WiFi 现状，以及「新设备逐条重建」与「转发下沉 OpenWrt + DMZ」两套恢复方案。
- **事实修正**：`AGENT_HANDOFF.md` 原记光猫公网 IP `123.117.236.65`，实测已变为动态 IP；端口转发也不止 3 条，现以清单文档为准。
- **敏感值**不入库，存 `NAS_API/secrets/router-f4610u.local.md`（gitignore）。
- **决策**：公网 IPv4 为硬性前提（无 CGNAT）；宽带账号密码由联通配置；`13306` MariaDB 决定关闭；`5000`/`2049`/`111`/`892` 四条死规则只记录、换设备时再处理。
- **执行**：2026-11-10 已在光猫删除 `NASMariaDB`（13306）规则，现网端口转发由 16 条降为 15 条。

## 2026-09-20

- **修复（链接）**：`reference/nas-multi-domain-access.md` 三条链接少退一级 —— `../AGENT_HANDOFF.md` → `../../AGENT_HANDOFF.md`；指向根 `docs/solutions/...` 与 `us_openai_api_proxy/...` 的由 `../../` → `../../../`。`.agents/skills/nas-access/SKILL.md` 指向本仓库的 3 条链接同样由 `../../` → `../../../`。

## 2026-08-31
- **更新** `reference/nas-multi-domain-access.md`、solutions 条目 — 澄清 OpenWrt 自定义域全栈（非仅 NAS 加证）、路径 A/B 与 QC 跳转关系；DSM 外部访问 DDNS 不能改 QC 目标、勿删 myds、无 mxdeals 优先；中国区 QC 政策摘要。

## 2026-08-28
- **新增** `reference/nas-multi-domain-access.md` — 汇总 2026-08-27~28 多域名访问实施：nas.daneey.com（阿里云+OpenWrt ACME）、nas.vilavi.cn（Cloudflare 灰云+DDNS+ACME）、DSM 反代与证书绑定铁律、联通 443 限制、QC 直连/中继与 Chrome 安全 DNS 问题。
- **新增** `../AGENT_HANDOFF.md`、`.agents/skills/nas-access/SKILL.md`。
- **政策记录**：统一入口仍为 `fangzhouhui.quickconnect.cn`；深圳 `myds.me` 未决。

## 2026-08-27
- **实施** `nas.daneey.com`：OpenWrt 阿里云 DDNS + DNS-01 证书 → DSM 导入 `aJodgl` → 反代 443/11024（Host: fzh.myds.me）。
- **教训**：误绑 DSM 桌面服务到新证导致 `fzh.myds.me:11024` 证书警告；已回滚默认证 `RmB4St`。
