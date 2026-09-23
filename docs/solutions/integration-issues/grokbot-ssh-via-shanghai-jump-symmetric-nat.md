---
okf: v0.1
type: Solution
title: grok-bot（美东）SSH 接入 — 对称 NAT 下的跳板选路与 Tailscale SSH 验证绕过
description: 对端机在对称 NAT 后，本机与它结构性打不成 Tailscale 直连。实测四条通路里只有「经上海跳板」有真收益（~235ms vs DERP 373ms），Vultr 跳板几乎无收益。附 DERP / Peer Relays / check 模式机制，以及用系统 sshd + 公钥绕开浏览器验证的做法。
module: us_openai_api_proxy
date: 2026-09-23
last_updated: 2026-09-23
category: integration-issues
problem_type: integration_issue
component: infrastructure
severity: low
symptoms:
  - "ssh box@100.106.238.40 走 DERP(iad)，RTT 373~384ms，交互明显迟滞"
  - "tailscale ping 报 direct connection not established（直连打不成）"
  - "冷启动首次连接曾 15s 超时，45s 才成功"
  - "Tailscale SSH 每 12h 要求浏览器验证，无法脚本化"
  - "对端机的出口 IP/端口每目标不同，没有固定公网入口"
root_cause: network_topology
resolution_type: configuration_change
tags: [tailscale, ssh, derp, peer-relay, symmetric-nat, proxyjump, check-mode, grok-bot, vultr, aliyun, shanghai]
related_components: [us_openai_api_proxy]
---

# grok-bot（美东）SSH 接入 — 对称 NAT 下的跳板选路与 Tailscale SSH 验证绕过

## Problem

需要从北京办公室的 Windows（`fzhpc13`）SSH 到 Grok Bot 托管的美国东岸机器
（Tailscale 名 `grok-bot`，`100.106.238.40`，用户 `box`）。该机**只在 Tailscale 内可达**
（公网无入站），而它与本机**打不成 Tailscale 直连**，只能走 DERP 中继，RTT 373ms 起，
交互迟滞明显。原始设想是用 Vultr（`100.126.133.106`）做 SSH 跳板，但实测**几乎没有收益**。

## Symptoms

- `tailscale ping grok-bot` → 全程 `via DERP(iad)`，末行 `direct connection not established`。
- 同一台机，Vultr 与上海却能跟它建立**直连**（下面 Investigation 有数据）。
- Tailscale SSH 每次新窗口都要浏览器点一次授权，脚本/自动化不可用。
- 冷启动首次 TCP 连接可能 >15s（低延迟路径建立慢），`ConnectTimeout` 给小了会误判成「不通」。

## Investigation

### 1. 四条通路实测（2026-09-23）

| 路径 | 类型 | RTT |
|------|------|-----|
| 本机 → grok-bot | **DERP(iad)** | 373–384ms |
| 本机 → Vultr `100.126.133.106` | 直连 `149.28.67.226:41641` | 299ms |
| 本机 → 上海 `100.119.28.72` | 直连 `8.133.254.66:41641` | **29–31ms** |
| Vultr → grok-bot | 直连 | 60ms |
| **上海 → grok-bot** | 直连 `184.193.214.38:*` | **199–206ms**（`active; direct`，稳定） |

推论（这是本题要害）：

- **本机→上海（30ms）+ 上海→grok-bot（205ms）≈ 235ms**，比直连 DERP 373ms **快约 138ms（37%）**。
- **本机→Vultr（299ms）+ Vultr→grok-bot（60ms）≈ 359ms**，与 DERP 373ms 基本持平 ⇒
  **Grok Bot 原设想的 Vultr 跳板是绕远路**，只配当备用。
- 反直觉点：**上海到美东（205ms）比北京办公室直连美东（299ms）还快**。本机→Vultr 299ms
  与 DERP 373ms 都是跨太平洋段，而阿里云骨干跑同一段只要 205ms。所以「绕上海」不是绕远，
  是抄近路——**排通路时不要预设「国内中转一定更慢」**。

### 2. 为什么本机打不成直连（结构性的，不是配置问题）

grok-bot 在**对称 NAT** 后：Grok Bot 侧复核 `MappingVariesByDestIP: true`、`PortMapping` 为空，
且实测同一台机对 Vultr 呈现出口 `100.60.155.246:34740`、对上海呈现 `184.193.214.38:*`
（同一对端隔几分钟端口还会变，如 `:41856` → `:8098` → `:19480`）。

⇒ 每个目标拿到**不同的外部映射**，本机拿不到可复用的对端端点，**直连永远打不成**。
但反过来：**grok-bot 能主动连出去**（连 Vultr、连上海都成功），所以「拿别人当中继」这条一直有路。
另：对端出口 IP 会变（Cloudflare / AWS 等），**不要假设有稳定公网入口**。

### 3. 跳板机可用性

| 主机 | Tailscale | AllowTcpForwarding | PermitOpen |
|------|-----------|--------------------|------------|
| 上海 `sh-erpnext-test` | 1.98.4 | `yes` | `any` |
| Vultr `us-ubuntu-proxy` | 1.102.2 | `yes` | `any` |

两台都够格当 ProxyJump，且**跳板侧无需任何改动**（上海→grok-bot:22 裸 TCP 已验证可达）。

### 4. Tailscale 的三种「中继」及各自边界

- **DERP**：Tailscale 自有官方中继网，目前就是它在兜底（选到 `iad`）。
  自建 DERP 服务器（`derper`）也可行，但要域名 + 证书 + 80/443/3478 + 不能被 NAT，
  且官方现在更推荐下面的 Peer Relays。
- **Peer Relays（对等中继，2026-02 GA）**：用**自己 tailnet 里的节点**当relay，
  选路顺序 = 直连 → 对等中继 → DERP。要求两端 Tailscale ≥1.86（本机 1.102.2 /
  上海 1.98.4 / grok-bot 1.102.4，均满足）。配置 = 中继节点上
  `tailscale set --relay-server-port=<UDP口>` + tailnet ACL 加
  `grants`（app `tailscale.com/cap/relay`，`src`=客户端、`dst`=中继节点）。
  比 ProxyJump 优的地方：**全协议生效**、不经双层 SSH 加密、不依赖打洞。
- **SSH ProxyJump**（`ssh -J`）：OpenSSH 层面的隧道，只对 SSH 生效，但**零基础设施改动**。

**关键边界：三者都只改「传输路径」，不碰 SSH 认证。** 换句话说，
对等中继/DERP 换成近路，**并不会**免掉下一条说的浏览器验证。

### 5. Tailscale SSH 的 check 模式（真正的摩擦点）

对端机原本 `RunSSH: true`，实测连接时回显：

```
# Tailscale SSH requires an additional check.
# To authenticate, visit: https://login.tailscale.com/a/<短时效链接>   ← 不入文档
# Authentication checked with Tailscale SSH.
```

机制（据官方 KB）：默认 `checkPeriod` 为 **12 小时**（可调 1 分钟–168 小时，或 `always`）；
**按「发起设备」计**。所以走 ProxyJump 时发起设备变成**跳板机**，需**单独验跳板机一次**——
这跟「直连验本机」是两笔账。⇒ **只要还开着 Tailscale SSH，跳板方案就省不掉验证。**

## Solution

### 1. 客户端：三段式 ssh config（主路径 + 两条兜底）

追加到 `~/.ssh/config`（**不动任何服务器**，可随时删块回退）：

```
Host grok-bot               # 主：经上海跳板 ≈235ms
    HostName 100.106.238.40
    User box
    IdentityFile ~/.ssh/id_ed25519_grokbot
    IdentitiesOnly yes
    ProxyJump sh-erpnext-test
    ConnectTimeout 60
    ServerAliveInterval 30

Host grok-bot-direct        # 兜底1：不走跳板，DERP ≈373ms
    HostName 100.106.238.40
    User box
    IdentityFile ~/.ssh/id_ed25519_grokbot
    IdentitiesOnly yes
    ConnectTimeout 60

Host grok-bot-via-vultr     # 兜底2：上海线路挂了时走 Vultr ≈360ms
    HostName 100.106.238.40
    User box
    IdentityFile ~/.ssh/id_ed25519_grokbot
    IdentitiesOnly yes
    ProxyJump us-ubuntu-proxy
    ConnectTimeout 60
```

- 用**专用钥匙** `id_ed25519_grokbot`（不复用 Vultr / GitHub / NAS 那几把），
  私钥不入库；公钥由对端写入 `box` 的 `authorized_keys`。
- 跳板直接用现成别名 `sh-erpnext-test` / `us-ubuntu-proxy` 复用其身份文件与 known_hosts。

### 2. 对端：关掉 Tailscale SSH，改走系统 sshd + 公钥

对端机（容器/VM 风格，**无 systemd**）本来就在 `0.0.0.0:22` 跑着**真的 OpenSSH sshd**，
`tailscaled` 只抢占 **tailnet 地址**的 22 —— 所以 Tailscale SSH 一关，系统 sshd 就接管：

1. 公钥写入 `/home/box/.ssh/authorized_keys`（`.ssh` 700、文件 600、owner `box`）。
2. `tailscale set --ssh=false`（`RunSSH` 变 `false`）。
3. sshd 加固：`PasswordAuthentication no` + `PubkeyAuthentication yes`，重载并确认在听 22。
   **这一步必要**：关掉 Tailscale SSH 后，tailnet 内任何节点都能来敲 22，ACL 不再兜底，
   只留公钥才稳。

### 3. 切认证方式后必做：清旧主机密钥

Tailscale SSH 与系统 sshd 是**两把不同的主机密钥**。切换后本机 `known_hosts` 里
对端 IP 的旧条目会触发 `REMOTE HOST IDENTIFICATION HAS CHANGED`：

```bash
ssh-keygen -R 100.106.238.40   # 自动留 known_hosts.old 备份
```

## Why This Works

- **绕开的是认证层，不是传输层**：关 Tailscale SSH 后，端到端变回普通 OpenSSH 公钥认证，
  12 小时浏览器验证彻底消失，且脚本化可用；而传输仍可比走上海跳板，两者互不干扰。
- **跳板选上海而非 Vultr**：跨太平洋那一段由阿里云骨干承载（205ms），
  比办公室出口 + DERP（299–373ms）更好；把最贵的一段交给链路质量最好的那台。
- **ProxyJump 是纯客户端改动**：收益 138ms、零服务器改动、单块删除即回退，性价比最高。

## Prevention

| 规则 | 说明 |
|------|------|
| 对称 NAT 先判再选路 | 先看 `MappingVariesByDestIP` / 对两个不同目标看到的出口是否不同；对称 NAT 下**别浪费时间调直连** |
| 别预设「国内中转更慢」 | 本题上海→美东 205ms < 本机→美东 299ms；排路要实测 |
| `ConnectTimeout` 给足 | 冷启动首次连接可达数十秒，建议 60 |
| peer relay 若启用要 scope | `src` 只写 `fzhpc13`，**绝不用 `*`**（会让全网设备都试着走中继） |
| 别把 ACL `check` 改 `accept` | 会让同 tailnet 其他成员的设备免验直连你所有机器；用公钥绕更干净 |
| 主机密钥切换要清 known_hosts | Tailscale SSH ↔ 系统 sshd 两把钥匙，切换必报 mismatch |
| 文档红线 | 不写 `login.tailscale.com/a/...` 验证 URL、私钥、`.env` 里的 key/token |

## Open Items

- **C 方案（上海做 peer relay）暂缓**：收益是「全协议」而非只 SSH，但要动上海那台生产 ERPNext 机
  + 改 tailnet ACL；待 A 方案用顺后再评估，届时 `src` 只 scope `fzhpc13`。
- 对端是容器/VM 风格：若实例被「Update Computer」重建，**sshd / tailscaled / 公钥都要重装重配**，
  冷启动需重新授权 Tailscale 与重放公钥。
- 上海→对端的直连端口每次会变（对称 NAT），目前每次都能重新打洞成功；若哪天退化成 DERP，
  peer relay 会是更稳的替代。

## Cross-References

- [us_openai_api_proxy/docs/office-lan-access.md](../../../us_openai_api_proxy/docs/office-lan-access.md) — 北京办公室 Tailscale 接入拓扑
- [us_openai_api_proxy/docs/operations.md](../../../us_openai_api_proxy/docs/operations.md) — US 代理运维手册（含 `ssh -D` SOCKS 跳板套路）
- [群晖 NAS 多域名访问 — OpenWrt ACME、DSM 反代与 QuickConnect](nas-multi-domain-access-openwrt-quickconnect.md) — 同属本办公室网络拓扑的另一条线
- Tailscale SSH（check 模式 / `checkPeriod`）：<https://tailscale.com/kb/1193/tailscale-ssh>
- 自定义 DERP 服务器：<https://tailscale.com/kb/1118/custom-derp-servers>
- Peer Relays：<https://tailscale.com/docs/features/peer-relay> ／
  <https://tailscale.com/blog/peer-relays-beta>
