---
okf: v0.1
type: Explanation
title: 北京办公室全员访问 Tailscale API 方案
description: 5 种方案让办公室所有电脑无需安装 Tailscale 即可访问上海 new-api 和美国 CLIProxyAPI
tags: [tailscale, openwrt, lan, subnet, office-network]
---
# 北京办公室全员访问 Tailscale API 方案

## 目标

办公室所有电脑能访问 Tailscale 网络内的 API 服务：

| 服务 | Tailscale IP | 端口 |
|------|-------------|------|
| US CLIProxyAPI (ChatGPT) | `<US_TS_IP>` | 8317 |
| 上海 new-api (API 分发) | `<SH_TS_IP>` | 3000 |

现状：只有装过 Tailscale 的电脑（fzhpc13、fzh-dev01）能访问这些 Tailscale IP。
目标：办公室全员无需装 Tailscale 即可访问。

## 方案全景

| 方案 | 做法 | 复杂度 | 电脑需Tailscale | 稳定性 | 安全 | 当前状态 |
|------|------|--------|:--:|--------|------|---------|
| **A: OpenWrt 路由** | 路由器装 Tailscale + 静态路由 | 中 | 不需要 | ⭐⭐⭐ | ⭐⭐⭐ | ⭐ 优先试验 |
| **B: PC 网关** | fzhpc13 做 Tailscale 网关 | 低 | 不需要 | ⭐⭐ | ⭐⭐ | 已有基础 |
| **C: 公网直连** | 阿里云安全组放行端口 | 极低 | 不需要 | ⭐⭐⭐ | ⭐ | 测试可用 |
| **D: 每台装 Tailscale** | 所有 PC 装 Tailscale | 零 | 需要 | ⭐⭐⭐ | ⭐⭐⭐ | 推广难 |
| **E: Subnet Router** | 反方向: Tailscale→LAN | 中 | 需要(远程) | ⭐⭐⭐ | ⭐⭐⭐ | 另一方向 |

---

## 方案 A: OpenWrt 路由器装 Tailscale + 静态路由 ⭐ 推荐

### 原理

```
┌─────────────────────────────────────────────┐
│                 北京办公室                    │
│                                              │
│  同事PC ─┐                                   │
│  同事PC ─┤─→ OpenWrt 路由器 (Tailscale) ─→ Tailscale 网络
│  同事PC ─┘    192.168.x.1                     │  100.x.x.x
│                静态路由: 100.64.0.0/10 →      │
│                tailscale0                     │  上海 new-api
│                                              │  美国 CLIProxyAPI
└─────────────────────────────────────────────┘
```

路由器上加一条静态路由，所有 LAN 流量去往 Tailscale CGNAT (100.64.0.0/10) 的包都转发到 tailscale0 接口。办公室电脑不需要任何改动。

### 前提条件

- OpenWrt 路由器，arm64 架构
- 剩余存储空间 > 10MB（Tailscale 包约 8MB）
- 路由器已能正常翻墙（有 OpenClash）

### 部署步骤

```bash
# 1. 安装 Tailscale
opkg update
opkg install tailscale

# 2. 启动 + 关键参数
tailscale up \
  --accept-routes \
  --accept-dns=false \
  --snat-subnet-routes=true

# 浏览器打开输出的认证 URL，用微软账户授权

# 3. 添加静态路由: LAN → Tailscale CGNAT
ip route add 100.64.0.0/10 dev tailscale0

# 4. OpenWrt 防火墙: 允许 LAN → tailscale0 转发
# LuCI → Network → Firewall → Traffic Rules → 新增:
#   Source: lan
#   Destination: tailscale0 (或 100.64.0.0/10)
#   Action: accept
# 或命令行:
iptables -I FORWARD -i br-lan -o tailscale0 -j ACCEPT
iptables -I FORWARD -i tailscale0 -o br-lan -m state --state RELATED,ESTABLISHED -j ACCEPT

# 5. 持久化（OpenWrt 重启后保留）
# 静态路由写入 /etc/rc.local 或 LuCI → Network → Static Routes
# 防火墙规则在 LuCI 中添加即自动持久化
```

### 验证

```bash
# 在任意一台办公室电脑上（不需要装 Tailscale）:
curl http://<SH_TS_IP>:3000
curl http://<US_TS_IP>:8317/v1/models \
  -H "Authorization: Bearer <API_KEY>"
```

### 注意事项

- **性能**: 路由器 ARM CPU 只做路由转发，不做 WireGuard 加密（Tailscale 已加密），性能影响极小
- **翻墙共存**: Tailscale 和 OpenClash 互不冲突，Tailscale 只是加了一张虚拟网卡和一条路由
- **`--accept-dns=false`**: 关键！不让 Tailscale 改路由器 DNS，否则 OpenClash 可能受影响
- **存储**: 如果空间不足，用 [GuNanOvO/openwrt-tailscale](https://github.com/GuNanOvO/openwrt-tailscale) 的精简版 (< 8MB)

---

## 方案 B: fzhpc13 做 Tailscale 网关

### 原理

fzhpc13 已有 Tailscale，启用了 IP 转发后可以作为 LAN 内其他设备的 Tailscale 网关。

```
同事PC ─→ fzhpc13 (网关, Tailscale) ─→ Tailscale 网络
           192.168.x.xxx
```

### fzhpc13 上的操作

```powershell
# 启用 IP 转发
Set-NetIPInterface -Forwarding Enabled

# 或通过注册表:
# HKLM\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\IPEnableRouter = 1
```

### OpenWrt 上的操作

在路由器上加静态路由，让所有去 Tailscale 的流量经过 fzhpc13：

```
目的网络: 100.64.0.0/10
网关: <fzhpc13_LAN_IP>
```

### 优缺点

| 优点 | 缺点 |
|------|------|
| 已部分实现 (lite_lan_proxy.py) | fzhpc13 关机则全办公室断 |
| 配置简单 | Windows IP 转发不如 Linux 稳定 |
| 不需要动路由器 | 只能转发 TCP，不如方案 A 透明 |

### 当前状态

`lite_lan_proxy.py` 已在 fzhpc13 上跑，转发 :3000 → CLIProxyAPI。这是方案 B 的简化版——只能转发单个端口，不是完整路由。

---

## 方案 C: 公网直连

### 做法

阿里云安全组放行端口 3000，同事直接访问 `http://<SH_PUBLIC_IP>:3000`。

### 优缺点

| 优点 | 缺点 |
|------|------|
| 零部署 | 公网暴露，无加密 |
| 延迟最低 (~30ms) | 需额外安全措施（IP 白名单/HTTPS） |

### 建议

如果选这个，至少加 IP 白名单（只允许办公室公网 IP）或配置 nginx 反代 + HTTPS。

---

## 方案 D: 每台电脑装 Tailscale

```powershell
winget install Tailscale.Tailscale
tailscale up
```

最直接的方案，但每台电脑需要安装、认证、管理。适合技术人员（< 5 台），不适合全员推广。

---

## 方案 E: Tailscale Subnet Router（反方向）

Tailscale 的标准"子网路由"功能解决的是**相反方向**的问题：

```
远程 Tailscale 设备 ─→ 路由器(Subnet Router) ─→ LAN 设备(无 Tailscale)
```

让出差/远程的同事能访问办公室局域网设备。不是"LAN 访问 Tailscale"的方向，但将来可能需要。

---

## 推荐实施顺序

```
1. 方案 A (OpenWrt 路由) — 一劳永逸，优先试验
2. 如果路由器空间/性能不够 → 方案 B (fzhpc13 网关)
3. 如果只需快速测试 → 方案 C (公网，加 IP 白名单)
4. 将来有远程访问 LAN 需求 → 方案 E (Subnet Router)
```

## 验证清单

- [ ] 办公室任意电脑 `ping <SH_TS_IP>` 能通
- [ ] 办公室任意电脑 `curl http://<SH_TS_IP>:3000` 返回 new-api 页面
- [ ] 办公室任意电脑 `curl http://<US_TS_IP>:8317/v1/models` 返回模型列表
- [ ] 路由器重启后规则/路由仍然生效

## 相关资源

- [Tailscale on OpenWrt 官方包](https://openwrt.org/packages/pkgdata/tailscale)
- [Tailscale Subnet Router 文档](https://tailscale.com/docs/features/subnet-routers)
- [OpenWrt Tailscale 精简版](https://github.com/GuNanOvO/openwrt-tailscale)

## 见也

- [architecture.md](architecture.md) — 整体架构
- [lessons/lessons-learned.md](lessons/lessons-learned.md) — Lesson 24 (国内 Tailscale 延迟), Lesson 26 (Docker+Tailscale)
