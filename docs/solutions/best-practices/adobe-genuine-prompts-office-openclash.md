---
title: 办公室 OpenClash 屏蔽 Adobe 授权校验域名的处理与教训
date: 2026-09-07
category: best-practices
module: office-network-openclash
problem_type: best_practice
component: tooling
severity: low
applies_when:
  - 办公室局域网内某厂商客户端联网触发"授权合规/非官方渠道"弹窗，客户端被迫离线使用
  - 需要屏蔽某域名的子域但无法用 /etc/hosts 通配符表达
  - OpenClash 透明代理位于多级 NAT（如 光猫→OpenWrt→新华三→AP）之后，无法按单台客户端隔离规则
tags: [adobe, illustrator, ags, license-validation, openclash, office-network, hosts, nat]
---

# 办公室 OpenClash 屏蔽 Adobe 授权校验域名的处理与教训

## 背景

办公室某同事的 Adobe Illustrator 2023（macOS，非订阅授权方式部署）联网即触发 **Adobe Genuine Service（AGS）** 的授权合规弹窗，只能断网使用，非常不便。弹窗语言随出口线路地区变化（经日本节点出网时显示日文），说明客户端能连通 Adobe 校验服务器并收到按地区本地化的判定结果。办公室网络为三层 NAT：联通光猫 → OpenWrt(OpenClash 透明代理) → 新华三 ER3208G3-P-E → 无线 AP，WiFi 客户端都分配 192.168.10.x。

## 排查过程

1. **现象确认**：断网时不弹窗、联网弹窗 → 弹窗依赖"能连通厂商校验服务器"。
2. **方案一（在她 Mac 上用 hosts 屏蔽验证域名）**：写了双击运行的 .command 脚本，把 `prod.adobegenuine.com`、`genuine.adobe.com`、`lm.licenses.adobe.com` 及若干固定的 `*.adobe.io` 指向 `0.0.0.0`，并停用 AGS 后台服务。**结果无效**。
3. **查路由器日志定位真实校验域名**：OpenClash 记录所有连接。同事弹窗瞬间日志显示她实际连的是 **`lre1kgz2u4.adobe.io`**、`adobeid-na1.services.adobe.com`、`www.adobe.com`。其中 `lre1kgz2u4.adobe.io` 是 Adobe 授权校验接口，**子域前缀（lre1kgz2u4）随机/轮换**。
4. **为什么 hosts 无效（根因 1）**：`/etc/hosts` **不支持通配符**，无法表达 `*.adobe.io`，只能写固定子域；Adobe 轮换前缀后立刻失效。这是 hosts 方案的根本局限，与用户操作无关。
5. **为什么无法按设备隔离（根因 2）**：查 OpenClash 日志的去重来源 IP，WiFi 客户端全部表现为 `192.168.100.181`（新华三 WAN 口，NAT 后）。OpenClash 看不到各客户端真实 IP，且 Clash 规则不支持 MAC 匹配 → 无法只封某台。
6. **方案二（路由器全局 REJECT 校验域名）**：在自定义规则加两条，模拟"对校验请求断网"：

   ```yaml
   - DOMAIN-SUFFIX,adobe.io,REJECT
   - DOMAIN-SUFFIX,adobegenuine.com,REJECT
   ```

   实测 `lre1kgz2u4.adobe.io`、`prod.adobegenuine.com` 均 `match ... using REJECT`，Google 等正常流量不受影响。同事重开 Illustrator 后不再弹窗，**有效**。

## 为什么有效

- 弹窗需要客户端连通校验服务器拿到"非官方授权"判定；把校验域名整体 REJECT，客户端到校验服务器的请求被拒绝，等同"对该校验断网"，与"断网不弹窗"的行为一致。
- `DOMAIN-SUFFIX,adobe.io` 通配了 `*.adobe.io` 的所有随机子域，绕开了 hosts 无法通配的问题。
- 只封 `adobe.io` + `adobegenuine.com`（API/校验域），未封整个 `adobe.com`（否则连官网/下载也受影响）。

## 经验教训

1. **/etc/hosts 无通配符**：厂商用随机前缀子域（`lreXXXX.adobe.io`）时，hosts 屏蔽必然失效，必须在能通配的层做（DNS wildcard 或代理规则的 `DOMAIN-SUFFIX`）。
2. **先看路由器日志找"真实域名"再动手**：OpenClash 日志记录了每个连接的目标域，能精确告诉你该屏蔽谁，而不是猜一个固定域名清单。
3. **多级 NAT 下无法按设备隔离**：OpenClash 只见新华三 NAT 后的单一 IP。要按设备隔离必须在那台设备本地（hosts/进程级防火墙）处理，或改网络拓扑。
4. **全局 REJECT 的副作用要监控**：本方案影响全办公室所有 Adobe 客户端的校验（含订阅授权用户的云功能/校验）。实施前确认办公室无订阅授权用户；若日后出现，需改为按设备/进程级方案（如客户端本地进程防火墙），或只对个别设备生效的规则。

## 当前状态（可回滚）

- 规则位于 OpenWrt `/etc/openclash/custom/openclash_custom_rules.list`（已备份 `.bak-adobe-*`），运行配置同步生效。
- 回滚：删除自定义规则中 `adobe.io` / `adobegenuine.com` 两条 REJECT 后重启 OpenClash 即可。
- 相关文档：`us_openai_api_proxy/docs/operations.md`（办公室 OpenClash 运维），`us_openai_api_proxy/docs/log.md` v0.14 记录同一时期的 BoostNet 迁移与规则调整。

## 相关
- [us_openai_api_proxy/docs/operations.md](../../../us_openai_api_proxy/docs/operations.md) — 办公室 OpenClash 运维手册
- [us_openai_api_proxy/docs/log.md](../../../us_openai_api_proxy/docs/log.md) — 变更日志（v0.14）
