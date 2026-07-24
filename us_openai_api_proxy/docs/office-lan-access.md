---
okf: v0.1
type: Explanation
title: 北京办公室全员访问 Tailscale — 方案 A 实施记录
description: 在 OpenWrt + 新华三双层路由下，实现办公室所有设备无需安装 Tailscale 即可访问 Tailscale 网络内的上海 new-api 和美国 CLIProxyAPI
tags: [tailscale, openwrt, h3c, subnet, office-network, routing, nat]
---
# 北京办公室全员访问 Tailscale — 方案 A 实施记录

## 目标

办公室所有电脑（包括手机连 WiFi）能访问 Tailscale 网络内的 API 服务：

| 服务 | Tailscale IP | 端口 |
|------|-------------|------|
| 上海 new-api (API 分发) | `100.119.28.72` | 3000 |
| US CLIProxyAPI (ChatGPT) | `100.126.133.106` | 8317 |

## 公司网络拓扑

```
联通光猫 192.168.1.1
├── LAN1 → OpenWrt WAN (eth1, DHCP 192.168.1.3)
├── LAN2 → 新华三 WAN2 (备用，默认不走)
└── LAN3 → 群晖 NAS 192.168.100.242

OpenWrt (FastRhino R68S, ARMv8, OpenWrt R22.11.13)
├── WAN: eth1 (192.168.1.3)
├── LAN: br-lan (192.168.100.1/24)
│   ├── 新华三 WAN1 (192.168.100.181)
│   └── NAS (192.168.100.242)
└── OpenClash: redir-host 模式, tproxy, DNS 127.0.0.1:7874
    Passwall/ShadowsocksR (已停用)

新华三 ER3208G3-P-E (Release 0136P01)
├── WAN1: 192.168.100.181 → OpenWrt LAN (主)
├── WAN2: 直连联通光猫 (备用, 策略路由已禁用)
├── LAN: 192.168.10.0/24, 8 个 LAN 口 + VLAN
└── WiFi AP (FZH-5G) → 办公室 PC + 手机 (DHCP 192.168.10.x)
```

> 三层 NAT：联通光猫 → OpenWrt → 新华三 → WiFi 客户端。
> 关键设备 IP 和凭证在 `../.env`（gitignored）。

## 已实施：方案 A — OpenWrt + 新华三 双层配置

### 最终架构

```
办公室 WiFi 设备 (192.168.10.x, 无 Tailscale)
    │
    ↓ 默认网关
新华三 ER3208G3-P-E (192.168.10.1)
    │ 静态路由: 100.64.0.0/10 → 192.168.100.1 (WAN1)
    ↓
OpenWrt R68S (192.168.100.1) ← Tailscale: 100.124.94.69
    │ ts-forward: ACCEPT (out=tailscale0)
    │ MASQUERADE: POSTROUTING -o tailscale0
    ↓ WireGuard (Tailscale)
上海 new-api (100.119.28.72:3000)
美国 CLIProxyAPI (100.126.133.106:8317)
```

### 实施日期：2026-06-23

## 实施步骤

### 步骤 1：OpenWrt — 安装 Tailscale

**路由器配置：**
- 型号：FastRhino R68S，ARMv8 四核，CPU Mark 28662
- 固件：OpenWrt R22.11.13 / LuCI Master
- 存储：overlay 820MB，可用 602MB
- 架构：rockchip/armv8 (aarch64_generic)
- opkg 源：immortalwrt.org 21.02.1

```bash
opkg update
opkg install tailscale   # v1.32.3-1, ~3.6MB
```

### 步骤 2：OpenWrt — 启动 Tailscale

```bash
/etc/init.d/tailscale enable
/etc/init.d/tailscale start
tailscale up --accept-dns=false --accept-routes
```

关键参数：
- `--accept-dns=false`：不改路由器 DNS（保护 OpenClash）
- `--accept-routes`：接受其他节点发布的子网路由

浏览器打开认证 URL，用微软账户登录。在 Tailscale Admin Console 禁用 key expiry。

路由器 Tailscale IP：**100.124.94.69**

### 步骤 3：OpenWrt — 备份现有配置

实施前备份所有 UCI 配置、iptables 规则、路由表：
- 备份位置：`C:\Users\zhang\uci_full_backup_20260623.txt` 等
- 实际路径见 `.env`

### 步骤 4：OpenWrt — 防火墙配置

#### 4a：添加 tailscale0 网络接口 (UCI)

```bash
uci set network.tailscale=interface
uci set network.tailscale.proto='none'
uci set network.tailscale.device='tailscale0'
uci commit network
```

#### 4b：创建 tailscale 防火墙区域 (UCI)

```bash
uci add firewall zone
uci set firewall.@zone[-1].name='tailscale'
uci set firewall.@zone[-1].network='tailscale'
uci set firewall.@zone[-1].input='ACCEPT'
uci set firewall.@zone[-1].output='ACCEPT'
uci set firewall.@zone[-1].forward='ACCEPT'
uci set firewall.@zone[-1].masq='1'
```

#### 4c：双向转发 (UCI)

```bash
# lan → tailscale
uci add firewall forwarding
uci set firewall.@forwarding[-1].src='lan'
uci set firewall.@forwarding[-1].dest='tailscale'

# tailscale → lan (回程)
uci add firewall forwarding
uci set firewall.@forwarding[-1].src='tailscale'
uci set firewall.@forwarding[-1].dest='lan'

uci commit firewall
/etc/init.d/firewall restart
```

#### 4d：添加回程路由 — 192.168.10.0/24

OpenWrt 默认不知道新华三 LAN 子网，需手动添加：

```bash
uci set network.route_h3c=route
uci set network.route_h3c.interface='lan'
uci set network.route_h3c.target='192.168.10.0'
uci set network.route_h3c.netmask='255.255.255.0'
uci set network.route_h3c.gateway='192.168.100.181'
uci commit network
/etc/init.d/network reload
```

### 步骤 5：OpenWrt — 关键修复：MASQUERADE

**这是最关键的发现。** Tailscale v1.32.3 的 `ts-forward` MARK 规则只在 `in=tailscale0`（入站）时触发，去往 tailscale0 的出站流量未被标记，导致 `ts-postrouting` 的 MASQUERADE 不生效。LAN 设备的源 IP 不会被 NAT 为路由器的 Tailscale IP，远端服务器无法回包。

**修复：** 在 POSTROUTING 第一位添加无条件 MASQUERADE：

```bash
iptables -t nat -I POSTROUTING 1 -o tailscale0 -j MASQUERADE
```

**持久化：** 写入 `/etc/firewall.user`（防火墙重启时自动执行）。

### 步骤 6：新华三 — 静态路由

新华三 ER3208G3-P-E 的默认路由 `0.0.0.0/0 → 192.168.100.1 (WAN1)` 已存在，但为确保 Tailscale 流量不走 WAN2 备份链路，添加了一条更具体的静态路由：

| 字段 | 值 |
|------|-----|
| 目的 IP 地址 | `100.64.0.0` |
| 掩码长度 | `10`（即 255.192.0.0） |
| 优先级 | `2` |
| 下一跳 IP | `192.168.100.1` |
| 出接口 | WAN1 |
| 描述 | Tailscale |

新华三管理路径：`高级选项 → 静态路由 → 添加`

> 注：新华三的默认路由已经指向 OpenWrt，此静态路由为加强保障。新华三的策略路由（全部流量走 WAN2）已禁用，不影响。

### 步骤 7：验证

```bash
# 路由器自身验证
tailscale ping 100.119.28.72        # pong via DERP(hkg)
curl http://100.119.28.72:3000      # HTTP 200 (new-api)
curl http://100.126.133.106:8317/v1/models  # HTTP 200 (CLIProxyAPI)

# 办公室手机 (FZH-5G WiFi, 无 Tailscale)
http://100.119.28.72:3000/          # new-api 页面正常
https://google.com                  # 翻墙正常
```

- [x] 办公室任意设备 `curl http://100.119.28.72:3000` 返回 new-api 页面
- [x] 翻墙 (OpenClash) 不受影响
- [x] 路由器重启后规则/路由持久化

## 踩坑记录

### 坑 1：防火墙重启冲掉 Tailscale iptables 规则

`/etc/init.d/firewall restart` 会 flush 所有 iptables 规则并重建。Tailscale 的 `ts-forward` 和 `ts-postrouting` 链会被删除。修复：防火墙重启后必须 `tailscale restart` 恢复。

### 坑 2：ts-forward MARK 规则方向

Tailscale v1.32.3 的 ts-forward MARK 规则匹配条件是 `in=tailscale0`，只标记入站流量。出站流量（LAN → tailscale0）不会被标记，导致 MASQUERADE 缺失。根因是 tcpdump/conntrack 分析确认的。

### 坑 3：三层 NAT — 回程路由

新华三 LAN 子网 (192.168.10.0/24) 对 OpenWrt 不可见，默认走 WAN (eth1 → 联通光猫)。必须在 OpenWrt 上添加 `192.168.10.0/24 via 192.168.100.181` 的回程路由。

### 坑 4：新华三 OpenWrt 混淆

新华三 ER3208G3-P-E 的 Web 管理界面使用了 LuCI 框架（路径 `/cgi-bin/luci/`），但实际是 H3C 自研固件（Release 0136P01），不是开源 OpenWrt。不能用 UCI 命令管理。

### 坑 5：浏览器直接导航 Hash 路由不刷新

新华三 Web UI 使用 hash-based SPA 路由（`#admin/...`），直接 URL 导航后页面内容不刷新，必须点击侧边栏菜单触发 JavaScript 渲染。

## 与 OpenClash 共存

| 冲突点 | 状态 |
|--------|------|
| DNS | `--accept-dns=false` 防止 Tailscale 覆写 OpenClash DNS |
| TUN 竞争 | OpenClash 用 tproxy，不用 TUN — 不冲突 |
| 策略路由 | Tailscale table 52 vs Clash fwmark 0x162 — 各自独立 |
| 进程直连 | 建议在 OpenClash 添加 `PROCESS-NAME,tailscaled,DIRECT` 规则 |

## 维护命令

```bash
# SSH 到 OpenWrt
ssh -i <key_path> root@192.168.100.1

# 检查 Tailscale 状态
tailscale status

# 检查 iptables MASQUERADE
iptables -t nat -L POSTROUTING -n -v | grep tailscale0

# 防火墙重启后恢复 Tailscale 规则
/etc/init.d/tailscale restart

# 回滚（如需）
uci delete network.tailscale
uci delete network.route_h3c
# 删除 firewall 中 tailscale zone 和 forwarding
uci commit && /etc/init.d/firewall restart
```

## 当前局限

1. **新华三静态路由可能是冗余的**：默认路由已指向 OpenWrt，即使没有新增的静态路由，理论上也应工作。但添加后更明确。
2. **Tailscale 版本**：已升级至 1.98.4 (2026-06-23)，但 ts-forward MARK 方向未变化，手工 MASQUERADE 仍需保留
3. **OpenWrt 非官方固件**：R22.11.13 是自定义版本，部分 init 脚本不兼容
4. **防火墙重启后需重新启动 Tailscale**：已写入 `/etc/firewall.user` 做持久化

## 深圳/远程办公室访问 new-api (v0.11, 2026-06-25)

北京办公室已通过路由器访问 Tailscale 网络，但深圳办公室无 IT 人员、无 OpenWrt 路由器、公网 IP 动态变化，需要不依赖 Tailscale 客户端的公网接入方案。

### 方案 A: Tailscale Funnel (兜底)

```
深圳浏览器 → https://<hostname>.<tailnet>.ts.net
    → Tailscale Funnel Relay → 加密隧道 → 上海 new-api:3000
```

- 一行命令: `tailscale funnel --bg 3000`（上海服务器上运行）
- 自动 HTTPS 证书，零安全组改动，零 nginx 改动
- **不需要安装任何软件**，任何浏览器直接打开 URL
- 延迟 ~300ms（经 Tailscale relay 中转）
- 回滚: `tailscale funnel reset`

### 方案 B: nginx HTTPS 反代 (推荐日常使用)

```
深圳浏览器 → https://api.vilavi.cn (HTTPS 443)
    → 阿里云安全组 → nginx → new-api:3000
```

- 新增 `/etc/nginx/conf.d/new-api.conf`，未修改现有 frappe-bench.conf
- nginx SNI 按域名区分，与 `ensh.vilavi.cn` (ERPNext) 零冲突
- Let's Encrypt 自动续签证书
- 延迟 ~30ms（直连上海阿里云）
- DNS: Cloudflare A 记录 `api.vilavi.cn` → `<SH_PUBLIC_IP>`

### Codex++ 配置

| 字段 | 值 |
|------|-----|
| Base URL | `https://api.vilavi.cn` |
| API Key | 在 new-api 后台创建的令牌 |

## 见也

- [architecture.md](architecture.md) — 整体架构（服务器+API 流）
- [lan-gateway.md](lan-gateway.md) — 方案 B（fzhpc13 网关）
- [log.md](log.md) — 变更日志
- [../AGENT_HANDOFF.md](../AGENT_HANDOFF.md) — Agent 接手参考
