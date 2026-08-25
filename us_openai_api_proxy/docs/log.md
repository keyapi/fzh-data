---
okf: v0.1
type: Log
title: 变更日志
description: US OpenAI API Proxy 模块的时序变更记录
tags: [openai, api-proxy, changelog]
---
# 变更日志

## 2026-07-01 (v0.11)

- **v0.11**: 七一 GFW 全面封锁事件 — SSRDog 订阅中午12点失效, Tailscale 北京直连 US 中断 (100% 丢包), SSH 公网 IP 被 DPI 拦截
- **v0.11**: 应急方案: SSH ProxyJump 上海跳板 + SOCKS5 代理 (`-D 1080 -J sh-erpnext-test`)
- **v0.11**: 链路: PC → 上海服务器 → Tailscale (上海↔US direct 170ms) → US Vultr → 互联网
- **v0.11**: 确认上海 Tailscale 正常 — vultr 节点 active/direct 149.28.67.226:41641
- **v0.11**: 更新 GFW 应急翻墙流程到 operations.md

## 2026-07-02 (v0.12)

- **v0.12**: 办公室全员应急代理部署完成 — OpenWrt/OpenClash → 上海 SSH SOCKS5 隧道 → US Vultr
- **v0.12**: 上海 `socks5-tunnel` systemd service 部署, 绑定 Tailscale IP :1080, iptables 限制仅 OpenWrt 可访问
- **v0.12**: OpenWrt Tailscale 路由正常 — OpenWrt 自身可达上海 Tailscale IP (ping 85ms)
- **v0.12**: OpenClash 新增 Emergency 代理组 + SH-Tailscale-US SOCKS5 节点, Auto fallback 首位
- **v0.12**: 验证通过 — 办公室流量经 Emergency[SH-Tailscale-US] 代理, Google/Microsoft 正常
- **v0.12**: 回滚就绪 — SSRDogAnyTLS.yaml.bak 备份 + 回滚步骤文档化
- **v0.12**: `openclash_custom_overwrite.sh` 持久化方案 — 订阅更新后自动注入 Emergency（注入两个路径，幂等）
- **v0.12**: OpenClash 关键发现：UCI `config_path` 为 `config/SSRDogAnyTLS.yaml`，但 Clash 实际加载根目录同名文件
- **v0.12**: overwrite 脚本已验证：恢复干净备份 → 运行脚本 → 双路径注入成功 → 重启 Clash → 流量走 Emergency
- **v0.12**: 更新 operations.md — 订阅更新持久化机制 + 用户操作流程
- **v0.12**: Tailscale 确认 Personal 永久免费计划 — 6 用户 / 无限设备，当前 3 用户 7 设备远在限额内

## 2026-07-03 (v0.12 修复)

- **v0.12-fix**: SSRDog 订阅恢复 — 新链接下载成功，节点已更新（32GB 剩余，25 天重置）
- **v0.12-fix**: **关键 bug 修复**：overwrite 脚本此前强制 `MATCH,Emergency`，导致 SSRDog 恢复后流量仍走 Emergency
- **v0.12-fix**: 修复逻辑：MATCH 保持原始 `SSRDOG`，Emergency 放入 Auto fallback **末尾**（SSRDog 优先，Emergency 兜底）
- **v0.12-fix**: 验证：SSRDog 正常时走 `Japan丨02` 节点，全部流量回归 SSRDog；Emergency 静默待命
- **v0.12-fix**: 订阅更新全流程验证通过：LuCI 更新订阅 → 自动下载 → overwrite 注入 Emergency（末尾兜底）→ SSRDOG 优先使用
- **v0.12-fix**: 关键行为确认：旧订阅链接过期自动失败 → 新链接自动重试成功 → MATCH 保持 SSRDOG 未被覆盖 → Emergency 在 Auto 末尾静默待命

## 2026-07-27 (v0.13)

- **v0.13**: US Vultr DNS 故障 — 7/20 内核升级后重启，Tailscale MagicDNS 冷启动失败（`no upstream resolvers set, returning SERVFAIL`）
- **v0.13**: 根因：MagicDNS 在无上游解析器时返回 SERVFAIL（Tailscale 已知问题 #15471/#14252），重启前因长期运行未暴露
- **v0.13**: 修复：`tailscale set --accept-dns=false` + systemd-resolved 配置持久化（Vultr DNS 108.61.10.10 + Cloudflare 1.1.1.1 备用）
- **v0.13**: 应急线路验证恢复：上海 SOCKS5 → US → Google 200 / YouTube 200

## 2026-08-25 (v0.14)

- **v0.14**: 主翻墙供应商切换 — SSRDog 不续约（8/28 到期），OpenClash 切换到 BoostNet 订阅
- **v0.14**: BoostNet 策略组结构：主组 `BoostNet`(select) → `自动选择`(url-test) / `故障转移`(fallback)，另有香港/日本/台湾/新加坡/美国区域组
- **v0.14**: 自定义覆写规则全部 `Auto` → `自动选择`（BoostNet 无 `Auto` 组，SSRDog 遗留组名失效）
- **v0.14**: 验证通过：`cursor.com` / `claude.ai` / `api2.cursor.sh` 走 `GeoSite(category-ai-chat-!cn) → 自动选择[日本07]`
- **v0.14**: Emergency 兜底保留（SH-Tailscale-US + DIRECT），SSRDog 配置文件暂留至 BoostNet 试用通过后清理
- **v0.14**: 延迟 100ms+ 属新供应商常态，持续验证 ChatGPT/Cursor 实际稳定性中
- **v0.14-fix**: DNS 故障修复 — BoostNet 订阅的 `nameserver-policy` 把 google/github/openai 等强制指向 Cloudflare DoH（大陆被墙），导致外网域名解析全挂；替换为 `223.5.5.5` 后恢复（见 Lesson 31）
- **v0.14-fix**: DNS 修复持久化 — `openclash_custom_overwrite.sh` 新增 `fix_dns_cloudflare()`，订阅更新/重启后自动把 Cloudflare DoH 换成 223.5.5.5；已端到端测试（source 恢复 Cloudflare 版模拟订阅更新 → 脚本自动修复 → DNS 恢复）
- **v0.14**: 流量机制核实 — 路由完全由 OpenClash 规则决定（国内IP直连 + Clash规则→DIRECT/代理），与供应商无关；实测无国内IP误走代理，YouTube 视频是最大流量来源（~30%）；基于 SSRDog ~280G/月历史，BoostNet 400G/月 有 ~40% 余量（详见 operations.md「翻墙流量机制与额度」）

## 后续规划

- **Phase 2 (独立备份线路)**：在 Vultr 部署 VLESS+Reality 作为不依赖订阅的备份出口
  - 协议：VLESS + XTLS Vision + Reality（当前 GFW 环境下最抗封锁）
  - 目标：不依赖任何第三方订阅，机场挂掉也有自己的翻墙出口
  - OpenClash 双线路：BoostNet 优先，Reality fallback（参考当前 Emergency 兜底结构）
- **短期优化**：上海 SSH 隧道添加健康检查 cron（每 60s curl 测试，失败告警）
- **密钥安全**：上海服务器上的 `id_ed25519_us_proxy_tunnel` 用完可删，或创建受限专用密钥
- **清理**：BoostNet 试用稳定后删除 SSRDog 相关配置文件（`config/SSRDogAnyTLS.yaml*`）与备用配置（`meta.yaml` / `ssrdog.yaml` / `laoda_metaglide.yaml`）

## 2026-06-25 (v0.10)

- **v0.10**: OpenClash 翻墙全断事件诊断 — 代理订阅链接过期, 所有非中国 IP TCP 流量被 TPROXY 劫持到失效代理, 导致 SSH/外网全死
- **v0.10**: SSH config 优化: `us-ubuntu-proxy` 改为 Tailscale 内网 IP 优先, 新增 `us-ubuntu-proxy-pub` 公网备用
- **v0.10**: 确认 OpenClash 流量劫持链路: 非中国 IP TCP → iptables REDIRECT → Clash :7892 → 失效代理 → 连接秒断
- **v0.10**: 确认 china_ip_route 绕过规则正常工作 (中国 IP TCP/UDP RETURN, 非中国 IP 仍进 Clash)
- **v0.10**: 诊断方法: 切换 WiFi 直连光猫绕过 OpenClash 验证, SSH SOCKS 代理应急翻墙

## 2026-06-24 (v0.9)

- **v0.9**: 钉钉视频会议卡顿修复 — 开启 OpenClash "绕过中国大陆IP" + 添加钉钉域名 DIRECT 规则
- **v0.9**: 根因: `china_ip_route=0` (关闭) 导致国内 IP 的 UDP 流量被 TPROXY 劫持进 Clash 内核, 代理节点 UDP 转发性能差
- **v0.9**: 修复: `china_ip_route=1` (开启) → iptables 层面 RETURN 国内 IP 流量, 不进 Clash 内核
- **v0.9**: 双重保险: 覆写规则添加 5 条钉钉域名 DIRECT 规则 (dingtalk.com/dingtalk.cn/dingtalkapps.com/alicdn.com/KEYWORD:dingtalk)
- **v0.9**: 效果: NAT TCP 254 pkts RETURN vs 188 REDIRECT, MANGLE UDP 471 pkts RETURN vs 73 TPROXY
- **v0.9**: 不影响翻墙: 非国内 IP 流量仍正常进 Clash 代理

## 2026-06-23 (v0.8)

- **v0.8**: Tailscale 安全升级 v1.32.3 → v1.98.4 (手动静态二进制替换, arm64)
- **v0.8**: 验证新版 iptables 规则 — ts-forward MARK 方向未变化, 手工 MASQUERADE 仍需保留
- **v0.8**: 升级后重新认证, 所有节点正常, 手机 new-api + 翻墙正常

## 2026-06-23 (v0.7)

- **v0.7**: 方案 A 实施完成 — 办公室全员可通过路由器访问 Tailscale 网络
- **v0.7**: OpenWrt R68S 安装 Tailscale v1.32.3 + 防火墙 zone 配置 + LAN↔tailscale 转发
- **v0.7**: 关键修复: MASQUERADE on tailscale0 (ts-forward MARK 只匹配入站，出站无 SNAT)
- **v0.7**: 回程路由: 192.168.10.0/24 via 192.168.100.181 (新华三 LAN 子网)
- **v0.7**: 新华三 ER3208G3-P-E 静态路由: 100.64.0.0/10 → 192.168.100.1 (WAN1)
- **v0.7**: 验证通过: 手机 (无 Tailscale) 访问 new-api + 翻墙均正常
- **v0.7**: 踩坑 5 条: 防火墙冲掉 iptables / MARK 方向 / 三层 NAT 回程 / 新华三 LuCI 混淆 / Hash 路由

## 2026-06-23 (v0.6)

- **v0.6**: 新增 `docs/office-lan-access.md` — 办公室全员访问 Tailscale 5 种方案全景 (OpenWrt/PC网关/公网/全员Tailscale/Subnet Router)
- **v0.6**: 方案 A (OpenWrt 路由器) 详细部署步骤 — 当前优先级最高

## 2026-06-22 (v0.5)

- **v0.5**: Lesson 25 — docker-compose 必须自包含 (漏 SQL_DSN → 降级 SQLite), 必须从官方 compose 出发
- **v0.5**: Lesson 26 — Docker bridge 无法访问宿主机 Tailscale (经典冲突, iptables MASQUERADE 修复, 附 5 个社区链接)

- **v0.5**: 上海 ERPNext 测试服务器加入 Tailscale (100.119.28.72)
- **v0.5**: Docker v29.1.3 安装 (DaoCloud 镜像, 清华 apt 源)
- **v0.5**: new-api Docker 部署 (MySQL 8.0 + Redis 7 + calciumion/new-api, 端口 3000)
- **v0.5**: 上海 Tailscale 延迟优化 — 启用 Peer Relays (`--relay-server-port 3478`)
- **v0.5**: Lesson 20-24 — Tailscale MagicDNS / shim-signed / 阿里云镜像 / Docker 代理 / 国内 Tailscale 延迟
- **v0.5**: sh-agent 用户创建 + 用户权限体系确立
- **v0.5**: 上海 SSH config: `ssh sh-erpnext-test`

## 2026-06-22 (v0.4)

- **v0.4**: 迁移至 Ubuntu 24.04 (1C2G) — 放弃 Windows Server，新开 Vultr Ubuntu
- **v0.4**: systemd 部署 + 健康检查 cron + SSH SOCKS OAuth
- **v0.4**: Lesson 16-19

## 2026-06-18 (v0.3)

- **v0.3**: 放弃 Windows Server（多用户 RDP 冲突 + NSSM 失败）
- **v0.3**: Lesson 10-15

## 2026-06-18 (v0.2)

- **v0.2**: LAN 网关部署 + ping != TCP 端口通
- **v0.2**: Lesson 8-9

## 2026-06-18 (v0.1)

- **v0.1**: 初始搭建 — Tailscale P2P 直连、CLIProxyAPI v7.2.16、OKF 文档骨架
- **v0.1**: Lesson 1-7
