---
okf: v0.1
type: Reference
title: 办公室出口拓扑与应急链路（OpenClash ↔ 上海跳板 ↔ 美国 Vultr）
date: 2026-09-22
category: architecture-patterns
module: us_openai_api_proxy
problem_type: architecture_pattern
component: tooling
severity: medium
applies_when:
  - "要判断『现在这条流量走的哪条线』（主订阅 / 应急 / 直连）"
  - "排查出口相关故障：海外服务不通、速度异常、疑似被忘了切换的临时线路"
  - "回答任何网络/出口/Tailscale 问题之前"
tags: [network-topology, egress, openclash, tailscale, socks5, fallback, vultr]
related_components: [us_openai_api_proxy, NAS_API, openwrt, sh-erpnext-test]
---

# 办公室出口拓扑与应急链路（OpenClash ↔ 上海跳板 ↔ 美国 Vultr）

## Context

本仓库多份文档分别记录了出口链路的**某一端**，但没有一处把它们串起来：

| 已存在的文档 | 覆盖哪一端 |
|---|---|
| [us_openai_api_proxy/docs/office-lan-access.md](../../../us_openai_api_proxy/docs/office-lan-access.md) | 办公室内网 → OpenWrt → Tailscale |
| [us_openai_api_proxy/docs/operations.md](../../../us_openai_api_proxy/docs/operations.md) | 美国 Vultr 上的代理运维、`ssh -D` 跳板套路 |
| [us_openai_api_proxy/docs/log.md](../../../us_openai_api_proxy/docs/log.md) | 应急出口的历次变更 |
| [NAS_API/docs/reference/nas-multi-domain-access.md](../../../NAS_API/docs/reference/nas-multi-domain-access.md) | NAS 的多域名访问 |

**后果**：2026-09-22 排查「Tailscale/翻墙」问题时，因为没有先读这些文档，
把项目里早就记录好的方案当成新发现讲了一遍。本篇就是那个缺的串线图。

## Guidance

### 三条出口路径

| 路径 | 链路 | 何时用 |
|---|---|---|
| **主线路（日常）** | 办公室 → OpenWrt/OpenClash → 订阅节点（香港/日本/新加坡/美国…）→ 出海 | 默认 |
| **应急线路** | 办公室 → OpenWrt/OpenClash → **Tailscale** → 上海服务器 → **SSH SOCKS** → 美国 Vultr → 出海 | 订阅失效 / 主线路故障时人工切换 |
| **公网直连** | 办公室 → `https://api.vilavi.cn`（NGINX，不经代理） | 访问自家服务（new-api 等），延迟 ~30ms |

### 应急线路的两端（这是最容易找不到的一段）

**OpenClash 侧**（OpenWrt，配置文件在 `/etc/openclash/`）里它就是一个普通 socks5 节点：

```yaml
- name: SH-Tailscale-US
  type: socks5
  server: <上海服务器 Tailscale IP>
  port: 1080
```

挂在一个 `type: select` 的**策略组 `Emergency`** 下 —— 所以是**人工切换**，不是自动故障转移。

**上海服务器侧**，`1080` 由 systemd 单元 `socks5-tunnel.service` 提供：

```
ssh -N -D <tailscale-ip>:1080 ... root@<美国 Vultr 的 Tailscale IP>
```

即 `ssh -D`（动态转发）= 标准 SOCKS5 代理，出口是美国那台机器。

> 两端各自都「只是普通配置」，**唯一把它们连起来的信息是 `port: 1080` 这个数字**。
> 排查时先 `ss -ltnp | grep 1080` 找到宿主进程，再回看 OpenClash 里哪个节点指向它。

### 重启存活（2026-09-22 实测：会自愈）

| 组件 | 状态 |
|---|---|
| 上海 `socks5-tunnel.service` | `enabled`；`After=network-online.target tailscaled.service`；`Restart=always` + `RestartSec=10` |
| 上海 `tailscaled` / `docker` / `nginx` | 均 `enabled` |
| OpenWrt | `/etc/rc.d/` 下有 `S80tailscale`、`S99openclash`；MASQUERADE 规则在 `/etc/firewall.user` |

⚠️ `After=tailscaled.service` 只保证**服务已启动**，不保证**已连上 tailnet**。
启动顺序不利时 `ssh` 会因 `ExitOnForwardFailure=yes` 立刻退出，
但因为 `Restart=always`，约 10 秒后自动重试成功 —— **会自愈，但可能有十几秒空窗**。

### 怎么判断「现在走的是哪条线」

**最快的方法：看出口 IP，不要翻配置。**

```bash
curl -s https://api.ipify.org
```

| 出口 IP | 含义 |
|---|---|
| 运营商 IP（如北京联通 `123.117.232.176`） | 直连，或该流量未进代理 |
| 订阅节点 IP（香港/日本/…，每次可能不同） | **主线路** —— 正常状态 |
| 美国 Vultr IP（`149.28.67.226`） | **应急线路仍被占用** —— 要切回去 |
| 上海服务器 IP（`8.133.254.66`） | 走的是自家公网反代 |

> 历史上有过「应急出口被持续占用、主线路恢复后没切回来」的问题，
> 已在 OpenClash 侧修正优先级（见 `us_openai_api_proxy/docs/log.md`）。
> 上表就是复查它的手段。

## Why This Matters

- 这条链跨了 **4 台设备**（办公室路由 / 上海云机 / 美国云机 / 出口节点），
  任何一段出问题症状都相似（"海外服务不通"），没有串线图就只能逐台猜；
- 应急线路是**人工切换**的，所以「忘了切回来」是一个真实的、有历史的问题；
- 出口 IP 是最省事的判据：一次 `curl` 就能定界，不用登三台机器。

## When to Apply

- 排查任何「海外服务不通 / 变慢 / 出口异常」；
- 有人问「我们现在翻墙走哪条线」「某某服务器能不能访问外网」；
- **回答网络类问题之前** —— 先读本篇 + Context 里列的四份文档，再去现场探测。

## Examples

一次完整的定界（实测于 2026-09-22）：

```bash
# 1) 我走的是哪条线？
$ curl -s https://api.ipify.org
<订阅节点 IP>          # 实测是东京的节点 → 主线路，应急线路没被占用 ✓

# 2) 上海服务器能不能出海？（直连 vs 应急隧道）
$ ssh <sh-alias> 'curl -s -o /dev/null -w "%{http_code}" https://registry-1.docker.io/v2/'
000                   # → 直连失败
$ ssh <sh-alias> 'curl -s -o /dev/null -w "%{http_code}" \
    --socks5-hostname <tailscale-ip>:1080 https://registry-1.docker.io/v2/'
401                   # → 经应急隧道通了（401 是 Docker Hub 的正常未认证响应）

# 3) Tailscale 到底走直连还是中继？
$ tailscale status | grep -E 'direct|relay'
```

## Related Issues

- [../tooling-decisions/tailscale-relay-vs-public-https-china.md](../tooling-decisions/tailscale-relay-vs-public-https-china.md)
  —— Tailscale 从 relay 变 direct 的根因（UDP 41641）与两种环境的差异
- [../tooling-decisions/tailscale-2026-capabilities.md](../tooling-decisions/tailscale-2026-capabilities.md)
  —— Peer Relays / Tailcat 等新能力对本拓扑的适用性
- `us_openai_api_proxy/docs/office-lan-access.md` —— 办公室网络逐级拓扑与 OpenWrt/新华三配置
