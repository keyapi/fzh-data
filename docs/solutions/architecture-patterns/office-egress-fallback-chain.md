---
okf: v0.1
type: Reference
title: 办公室出口拓扑与应急链路（OpenClash ↔ 上海跳板 ↔ 美国 Vultr）
date: 2026-09-22
last_updated: 2026-10-14
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

### 主线路内部还分了两条：通用线 vs AI 出口

主线路不是一条链，而是**按域名分成两条并行的策略链**：

| 用途 | 链路 | 自动故障转移 |
|---|---|---|
| 通用（兜底 `MATCH` 规则） | `BoostNet`(select) → `自动选择`(**url-test**，定期探测) → 具体节点 | ✅ 会自愈 |
| **AI 域名**（`openai` / `chatgpt` / `anthropic` / `claude.ai` / `oaistatic` / GeoSite `category-ai-chat-!cn` 等） | `AI 出口`(select) → 区域组（`日本` / `美国` / …）(select) → 具体节点 | ❌ **无** |

**关键差别**：通用线折在 url-test 上，节点挂了会自己换；而 **`AI 出口` 这条链从头到尾都是手动 `select`，没有测速、没有兜底** —— 节点一挂，AI 只能人工去面板切。症状因此很有辨识度：**通用线自己好了，AI 线还卡着**。

**两条线还会共用同一批节点**：同一个节点名在 `proxies:` 里只有一个定义，可以被多个策略组同时引用 —— 所以「通用线在用的节点」和「AI 线在用的节点」常常就是**同一台服务器**。日志里记成通用线（`dial BoostNet …`）的掉线，坏的可能正是 AI 正在用的那台。

> Codex / Cursor 走的就是 `AI 出口`：`chatgpt.com`、`ws.chatgpt.com`、`ab.chatgpt.com`、`api.openai.com`、`auth.openai.com`、`persistent.oaistatic.com` 全部命中它的规则（实测日志见下）。

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

### 日常维护窗口与订阅状态（2026-10-13 复核）

- **路由器每天 04:30 自动重启**；**OpenClash 每天 07:00 自动重启**（`crontab`）—— 这两个窗口线必然会短暂断，排查「刚才怎么断了」时先排除它们。
- 订阅**自动更新是关的**（`openclash.config.auto_update='0'`），订阅源文件可能长期不更新 —— 节点是活的，但清单可能偏旧。
- AI 域名在办公室侧的 **DNS 是被污染的**（`nslookup chatgpt.com` 会返回不相干的假 IP），但 Clash 靠 **SNI 嗅探**按域名选路，**不影响使用** —— 别看到假解析结果就以为坏了。
- **2026-10-13 变更**：`AI 出口` 的成员表末尾接入了 `Emergency`，作为 AI 线路全挂时的**人工兜底**（实测切过去出口 = 美国 Vultr `149.28.67.226`，OpenAI 可达；用完要切回）。刻意**没有**把它放进 url-test 自动组 —— 理由与做法见 [那份事故正文](../integration-issues/openclash-overwrite-stale-group-name-orphaned-egress.md)。

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
| 上海服务器（`sh-erpnext-test`） | 走的是自家公网反代 |

> 历史上有过「应急出口被持续占用、主线路恢复后没切回来」的问题，已在 OpenClash 侧修正优先级（见 `us_openai_api_proxy/docs/log.md`）。
>
> ⚠️ **但「修过优先级」≠「接上了」**：2026-10-13 复查发现，`Emergency` 组当时**入向引用为零** —— 没有规则指向它、也没有别的组收编它，链路活着却收不到任何流量。根因是自定义覆写脚本里写死了上一代订阅的组名。详见 [OpenClash 覆写脚本写死策略组名，让自建应急出口长期「活着但没接线」](../integration-issues/openclash-overwrite-stale-group-name-orphaned-egress.md)。
> 也就是说，上表那个「看出口 IP」的判据**只在你能手动选中它时才成立** —— 一个悬空的组，从出口 IP 角度看不出任何异常。

**想查「某个具体应用走的是哪条线」**，别去猜规则顺序 —— 直接按域名 grep 路由器日志，看它实际用了哪个出口（`using 组名[节点名]` 就是答案）：

```bash
grep -E 'chatgpt|openai' /tmp/openclash.log | tail -10
# --> chatgpt.com:443 match DomainSuffix(chatgpt.com) using AI 出口[日本08]
#                                    ^命中哪条规则          ^实际走哪个策略组[哪个节点]
```

> ⚠️ `/tmp/openclash.log` 被 OpenClash 的 watchdog **按大小清空**（日志里会看到 `Log Size Limit, Clean Up All Log Records...`）—— **历史留不住，要回看只能现抓**，别指望事后追溯。

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
- [../integration-issues/openclash-overwrite-stale-group-name-orphaned-egress.md](../integration-issues/openclash-overwrite-stale-group-name-orphaned-egress.md)
  —— 「应急线路」那一侧的延伸：自定义覆写脚本写死上一代订阅的策略组名，导致 `Emergency` 组悬空、链路活着却没流量；含「数入向引用」的定界法与「副本干跑 → 重载 → 端到端换出口」的验证顺序
