---
okf: v0.1
type: Explanation
title: 经验教训
description: 部署过程中的经验教训和避坑指南
tags: [lessons, pitfalls, tips]
---
# 经验教训

## Lesson 1: Tailscale 国内下载需要 winget

国内 Windows 优先用 `winget install Tailscale.Tailscale` 而非直接 curl 官方链接。

## Lesson 2: Tailscale P2P 打洞中美可行

北京↔US P2P 直连 215ms，先试直连再决定是否部署中继，不要提前过度设计。

## Lesson 3: Vultr Web 控制台是万能兜底

云端虚拟机永远有厂商控制台（浏览器 VNC），不需要第三方远程软件做初始化。

## Lesson 4: 免费 ChatGPT 账号几乎不可用

免费账号只有 `gpt-5.4-mini`，很快限额。Plus/Pro/Team 才可用。

## Lesson 5: CLIProxyAPI 绑定内网 IP 而非 0.0.0.0

`host: "<Tailscale IP>"` 防止端口暴露公网被扫描。

## Lesson 6: 共享 Windows 机器需评估资源

Tailscale + CLIProxyAPI 极轻量，但共享机器的其他因素（多用户 RDP）可能导致问题。

## Lesson 7: 文档即基础设施

OKF v0.1 规范、AGENT_HANDOFF.md 确保 Agent 接手丝滑，敏感信息用 .env 隔离。

## Lesson 8: Ping 通 != TCP 端口通 (Windows 防火墙)

从底层往上排查：ICMP ping → TCP 端口 → HTTP 应用层。

## Lesson 9: 代理进程须常驻

面向用户的代理/转发服务必须在首次验证后立即注册为持久化服务（systemd / NSSM）。

## Lesson 10: Windows Server 多用户 RDP 冲突 Tailscale

Windows 多用户 RDP 时，第一个登入用户独占 Tailscale GUI socket。`tailscale up --unattended` 绑定系统级，或直接用 Linux。

## Lesson 11: 服务器重启后所有手动进程都会丢失

所有服务必须注册为系统级自启。P2P 打洞重启后可能退化到 DERP relay。

## Lesson 12: Linux 比 Windows Server 更适合做转发服务

无 GUI 开销、systemd 原生、SSH 运维简单、Tailscale 无 session 冲突。1C2G 足够。

## Lesson 13: LAN 网关降低同事接入成本

Tailscale → 网关代理 → 纯 HTTP，接入门槛每降一步，推广阻力小一个量级。

## Lesson 14: Tailscale P2P 打洞重启后可能退化为 DERP

P2P 直连是 bonus，架构设计始终以 DERP relay 兜底为前提。

## Lesson 15: 善用 `tailscale up --unattended`

服务器环境始终用 unattended 模式，避免用户 session 绑定。

## Lesson 16: SSH SOCKS 代理解决无 GUI 服务器 OAuth

一条 SSH 命令 `-L 1455:... -D 1080` 同时解决回调隧道 + US IP 问题。

## Lesson 17: systemd 让运维降维

`Restart=always` 崩溃自愈，`journalctl -u xxx -f` 实时日志，`systemctl enable` 开机自启零配置。

## Lesson 18: Tailscale 新机器入网只需 2 条命令

`curl ... | sh` + `tailscale up`，浏览器授权 2 分钟搞定。

## Lesson 19: 敏感信息分层管理

| 层级 | 位置 | 内容 |
|------|------|------|
| L1 | Git 文档 | 占位符 `<VAR>` |
| L2 | `.env` (gitignore) | 真实值 |
| L3 | `~/.ssh/config` | SSH 密钥路径 |
| L4 | Tailscale 控制台 | 机器列表 |

## Lesson 20: Tailscale MagicDNS 会破坏国内服务器 DNS

**问题**：`tailscale up` 后系统 DNS 全部超时。`/etc/resolv.conf` 被设为 `foreign` 模式，DNS Domain 被改为 `tailxxxx.ts.net`。

**原因**：Tailscale MagicDNS 接管了 systemd-resolved，但国内阿里云 ECS 的 DNS 服务器（100.100.2.x）要求特定网络环境。MagicDNS 的覆盖导致 systemd-resolved 无法正确转发查询。

**解决**：`tailscale up --accept-dns=false --accept-routes`。禁用 MagicDNS 接管，保留系统原有 DNS。

**教训**：国内云服务器部署 Tailscale 时务必加 `--accept-dns=false`，否则 DNS 秒挂。

## Lesson 21: shim-signed GRUB 交互提示阻塞 apt

**问题**：Ubuntu 22.04 上 `apt-get install` docker 时被 shim-signed 的 GRUB 设备选择交互提示卡死，`DEBIAN_FRONTEND=noninteractive` 无效。

**原因**：已知 Ubuntu Bug (#2080297)，shim-signed 的 postinst 脚本硬编码了 EFI 分区路径，与阿里云 ECS 的实际分区不匹配。

**解决**：
```bash
echo "grub-efi-amd64 grub-efi/install_devices multiselect /dev/nvme0n1p2" | debconf-set-selections
```
然后用 `dpkg --configure -a` 修复。

**教训**：阿里云 Ubuntu 上装 Docker 前，先 `dpkg --configure -a` 确认没有残留的 broken package。

## Lesson 22: 阿里云内网镜像不可盲目依赖

**问题**：`mirrors.cloud.aliyuncs.com` 解析到内网 IP `100.100.2.148` 但 TCP 超时不可达。

**原因**：阿里云 ECS 内网镜像仅在特定区域/可用区内可达，跨区域或网络变更后可能失效。

**解决**：换清华镜像 `mirrors.tuna.tsinghua.edu.cn`。国内服务器部署时准备至少 2 个备选镜像源。

**教训**：`/etc/apt/sources.list` 里永远备一个非阿里云的镜像源。

## Lesson 23: Docker 镜像在国内必须用代理拉取

**问题**：Docker Hub (`registry-1.docker.io`) 从国内被完全阻断，TLS 握手超时。公共镜像加速器（如 `docker.1ms.run`）不稳定。

**解决**：DaoCloud 代理 `docker.m.daocloud.io`：
```bash
docker pull docker.m.daocloud.io/library/mysql:8.0
docker tag docker.m.daocloud.io/library/mysql:8.0 mysql:8.0
```
Compose 中加 `pull_policy: never` 防止重复拉取。

**教训**：国内 Docker 部署三步走：① 配置 Daocloud mirror ② 手动 `docker pull` + `docker tag` ③ Compose `pull_policy: never`。

## Lesson 24: Tailscale 两台国内机器之间延迟可能反而更高

**问题**：北京和上海两台国内机器，Tailscale IP 间延迟极高（200ms+），而公网 IP 直连仅 30ms。

**原因**：双 NAT（办公网 + 阿里云 VPC）导致 P2P 打洞失败，流量绕道境外 DERP（东京/纽约）来回。

**方案优先级**：
1. 尝试 Peer Relays（`tailscale set --relay-server-port 3478`，UDP 中继）
2. 自建国内 DERP（需国内 VPS + 备案域名）
3. 接受 DERP relay（API 调用场景 200ms 延迟可接受）
4. 公网直连（放弃 Tailscale 加密，不推荐）

**教训**：Tailscale 在国内两台云服务器之间的延迟不一定优于公网。P2P 打洞受 NAT 类型影响极大。对于 API 分发场景（new-api），可以接受 DERP 延迟。

## Lesson 25: docker-compose 文件必须自包含，不能假设默认行为

**问题**：docker-compose.yml 里配了 MySQL 容器，但没给 new-api 传 `SQL_DSN` 环境变量。new-api 检测不到 MySQL 就静默降级为内置 SQLite，初始化页面弹出"数据库警告：您正在使用 SQLite"。

**根因**：没有从官方 docker-compose.yml 出发。官方文件里有完整的 `SQL_DSN` 配置（默认 PostgreSQL，MySQL 注释掉），我们按 `docker run` 教程里的单容器思路自己写 compose，漏掉了数据库连接参数。

**修复**：加一行环境变量 `SQL_DSN=root:pass@tcp(mysql:3306)/new_api`。

**现状**：MySQL 模式已正常，GQ 已完成管理员初始化，不换 PostgreSQL。

**教训**：部署开源项目第一步永远是拉原版 docker-compose.yml，在上面改，不要按教程里的 `docker run` 单容器命令自己拼 compose。`docker run -e KEY=VALUE` 的参数在 compose 里就是 `environment:` 段，一一对应。漏一个就翻车。

## Lesson 26: Docker bridge 容器无法访问宿主机 Tailscale 网络

**问题**：new-api Docker 容器（bridge 网络）无法访问 US Ubuntu 的 Tailscale IP `100.126.133.106:8317`。宿主机能通，容器不通。

**根因**：Docker bridge 网络的容器有独立的网络命名空间，`tailscale0` 虚拟网卡在宿主机上，容器内看不到。即使宿主机开启了 IP forwarding，回程路由也有问题——应答包会被 Tailscale 的路由表 52 劫持，走 `tailscale0` 而不是 `docker0`。

这是 Tailscale + Docker 的**经典已知冲突**，2025 年 Docker 28 的网络变更加剧了问题。

**社区 4 种标准方案**：

| 方案 | 做法 | 适用场景 |
|------|------|---------|
| **MASQUERADE** ✅ | `iptables -t nat -I POSTROUTING -s <docker子网> -o tailscale0 -j MASQUERADE` | Tailscale 在宿主机 |
| DOCKER-USER 链 | `iptables -I DOCKER-USER -j ts-forward` | Tailscale 官方推荐 (Docker 28+) |
| Sidecar 模式 | Tailscale 单独容器，app 容器 `network_mode: "service:tailscale"` | Tailscale 也容器化 |
| host 网络 | `network_mode: host` | 简单但 MySQL auth_socket 可能冲突 |

**我们选 MASQUERADE**——Tailscale 直接跑在宿主机（非容器化），这是社区推荐的标准做法，不是 hack。

**持久化**：iptables 规则重启后会丢失，需要 `apt install iptables-persistent && netfilter-persistent save`。

**相关链接**：
- [Tailscale Docker stateful filtering 官方文档](https://tailscale.com/docs/reference/messages/client/docker-stateful-filtering)
- [moby/moby#49498: Docker 28 stops containers communicating with tailscale network](https://github.com/moby/moby/issues/49498)
- [tailscale/tailscale#15401: container cannot reach other containers by name](https://github.com/tailscale/tailscale/issues/15401)
- [tailscale/tailscale#14008: External DNS SERVFAIL with Tailscale on Docker host](https://github.com/tailscale/tailscale/issues/14008)
- [tailscale/tailscale#13367: No connectivity from docker container when tailscale exit-node is set](https://github.com/tailscale/tailscale/issues/13367)

---

### Lesson 27: OpenClash "绕过中国大陆IP" 关闭导致国内应用 UDP 卡顿 (v0.9, 2026-06-24)

**现象**：小会议室电脑开钉钉视频会议卡顿，关掉 OpenWrt 路由器后正常。

**根因**：OpenClash 的 `china_ip_route` 开关是**关闭的** (`0`)。这意味着所有流量（包括国内 IP）都进入 Clash 内核处理。在 `redir-host + tproxy` 模式下，UDP 流量被 TPROXY 劫持到 `127.0.0.1:7895`，代理节点对 UDP 转发延迟高、丢包严重。钉钉视频会议使用 UDP (WebRTC) 做媒体传输，即使服务器是国内阿里云 IP，UDP 包仍然通过代理节点中转。

**修复**（两处改动）：

1. **开启 "绕过中国大陆IP"**：
   ```bash
   uci set openclash.config.china_ip_route='1'
   uci commit openclash
   ```
   开启后 OpenClash 在 iptables 层面插入 `match-set china_ip_route dst RETURN` 规则，国内 IP 流量不进 Clash 内核。效果验证：
   - NAT TCP: 254 pkts RETURN (绕过) vs 188 REDIRECT (进Clash)
   - MANGLE UDP: 471 pkts RETURN vs 73 TPROXY

2. **添加钉钉域名 DIRECT 规则**（双重保险，在 `/etc/openclash/custom/openclash_custom_rules.list`）：
   ```yaml
   - DOMAIN-SUFFIX,dingtalk.com,DIRECT
   - DOMAIN-SUFFIX,dingtalk.cn,DIRECT
   - DOMAIN-SUFFIX,dingtalkapps.com,DIRECT
   - DOMAIN-SUFFIX,alicdn.com,DIRECT
   - DOMAIN-KEYWORD,dingtalk,DIRECT
   ```

**前置条件**（均已满足）：
- DNS 劫持已开启 (`enable_redirect_dns=1`)
- 国内 IP 段文件已存在 (`/etc/openclash/china_ip_route.ipset`, 4293 条, 152KB)
- 国内 DNS 服务器已配置 (114.114.114.114, 119.29.29.29, doh.pub)

**为什么之前关着**：该功能在某些旧版本中可能有兼容性问题或性能影响，但 v0.47.088 + Mihomo alpha 内核已经稳定。开启后翻墙功能不受影响——只有 `china_ip_route` 匹配的国内 IP 走直连，其余仍进 Clash 代理。

**回滚**（如需）：
```bash
uci set openclash.config.china_ip_route='0' && uci commit openclash
cp /etc/openclash/custom/openclash_custom_rules.list.bak /etc/openclash/custom/openclash_custom_rules.list
/etc/init.d/openclash restart
```
（规则文件的 `.bak` 备份在执行修改时已自动创建）

**当前 OpenClash 配置关键参数**：
| 参数 | 值 | 说明 |
|------|-----|------|
| `en_mode` | `redir-host` | 运行模式 |
| `china_ip_route` | **1** (已改为) | 绕过中国大陆IP |
| `enable_redirect_dns` | `1` | DNS 劫持 |
| `enable_udp_proxy` | `1` | UDP 代理 |
| `lan_ac_mode` | `0` | 局域网访问控制 |
| Mihomo 内核 | `alpha-g8f2d84f` | 最新 alpha |
| 软件版本 | `v0.47.088` | — |

---

### Lesson 28: OpenClash 代理失效导致全办公室外网瘫痪 + SSH SOCKS 应急 (v0.10, 2026-06-25)

**现象**：办公室 FZH-5G WiFi 下所有设备无法访问外网，翻墙线路全部失效。本地电脑 SSH 到 US 服务器秒断（`Connection closed by remote host`）。

**诊断过程**：

1. **切换 WiFi 直连光猫**（绕过 OpenWrt/OpenClash）→ SSH 恢复正常 → 确认问题在 OpenClash
2. **检查 OpenClash NAT iptables 链**：
   - `match-set china_ip_route dst` → RETURN（中国 IP 正常直连）✓
   - `REDIRECT tcp ... redir ports :7892`（非中国 IP TCP 全部劫持到 Clash）← 这是根因
3. **US 服务器公网 IP 不在中国 IP 段**（`<US_PUBLIC_IP>`）→ 被 iptables REDIRECT → 进入 Clash → 走失效代理 → 连接秒断
4. **应急方案**：SSH SOCKS 隧道（`ssh -D 1080 us-ubuntu-proxy`）走 Tailscale 内网 `100.x.x.x`，不经过 OpenClash → 成功翻墙
5. **最终修复**：更新 OpenClash 代理订阅链接（ssrdog 新链接）

**根因链路**：

```
设备 → FZH-5G WiFi → 新华三 → OpenWrt iptables:
  目标 IP 检查:
    ✓ 中国 IP (china_ip_route) → RETURN → 联通直连 → 正常
    ✗ 非中国 IP → REDIRECT :7892 → Clash 内核 → 失效代理 → 连接秒断
```

这包括 SSH（TCP 22 到国外 IP）、浏览器访问国外网站、API 调用等所有非中国流量。

**教训**：

1. **代理订阅是单点故障**：订阅过期 → 所有非中国流量全死。建议设置订阅自动更新 + 健康检查告警。
2. **Tailscale 内网是救命稻草**：Tailscale 使用自己的 WireGuard 隧道，流量不经过 OpenClash iptables 劫持。SSH 配置应优先使用 Tailscale 内网 IP（100.x.x.x），公网 IP 做备用。
3. **诊断利器**：切换 WiFi 直连光猫是快速排除 OpenWrt/OpenClash 问题的方法。中国 IP 直连正常 + 国外 IP 全断 = 代理失效。
4. **SSH 不应依赖翻墙**：关键服务器（US Ubuntu）的 SSH 应通过 Tailscale 内网 IP 访问，确保翻墙挂掉时仍可达。
5. **OpenClash china_ip_route 已确认正常工作**：中国 IP 的 TCP 和 UDP 都正确 RETURN，不受代理状态影响。

**SSH Config 优化**（双路 fallback）：

```
Host us-ubuntu-proxy          ← 主：Tailscale 内网，不依赖翻墙
    HostName <US_TS_IP>

Host us-ubuntu-proxy-pub      ← 备：公网 IP，需要翻墙正常
    HostName <US_PUBLIC_IP>
```

> 敏感 IP 值见 `.env`（gitignored），以上用占位符。

**相关**：Lesson 27 (OpenClash china_ip_route), `../.env` (US 服务器 IP)


## Lesson 29: 钉钉 OAuth 接入 new-api（SSO 单点登录）

**日期**：2026-06-25

**背景**：公司内部使用 new-api 作为大模型 API 网关，每个新同事入职都需要管理员手动创建账号。目标是通过钉钉扫码登录实现自动创建账号（SSO），省去手动开账号的繁琐工作。

**调研结论**：

1. **全网无现成方案**：没有任何人为 new-api 或 one-api 做过钉钉 OAuth 集成，没有相关 PR/Issue/fork。

2. **new-api 有两套 OAuth 扩展机制**：
   - 内置 Provider（GitHub、OIDC、飞书、微信等）— 硬编码
   - **自定义 Provider**（`controller/custom_oauth.go`）— 支持动态注册任意 OAuth/OIDC provider，含 OIDC Discovery

3. **钉钉 → OIDC 桥接方案对比**：
   - [dingtalk-oidc](https://github.com/maggch97/dingtalk-oidc)：Go 实现，功能完整但作者声明 99% AI 生成、无安全保证，密钥每次重启重新生成，内存状态
   - [Logto connector](https://www.npmjs.com/package/@logto/connector-dingtalk-web)：需部署整套 Logto，杀鸡用牛刀
   - [APISIX dingtalk-auth](https://docs.apiseven.com/hub/dingtalk-auth)：网关级方案，未使用 APISIX

**最终方案**：自写 OIDC 桥接代理（~220 行 FastAPI）+ new-api 自定义 OAuth

**架构**：
```
浏览器 → new-api (Custom OAuth) → OIDC Bridge (FastAPI) → 钉钉 OAuth v2 API
```

**钉钉 OAuth v2 端点**（第三方企业应用）：
- 授权页：`https://login.dingtalk.com/oauth2/auth`
- 换 token：`POST https://api.dingtalk.com/v1.0/oauth2/userAccessToken`
- 用户信息：`GET https://api.dingtalk.com/v1.0/contact/users/me`

**OIDC Bridge 关键设计决策**：
- 固定 RSA 密钥对（持久化到文件），不像 dingtalk-oidc 每次重启换密钥，确保 id_token 签名稳定
- SQLite 存 state/code/token（不像 dingtalk-oidc 存内存），重启不丢会话
- `ALLOWED_CORP_ID` 限定只能本公司员工登录
- 不需要暴露公网端口（仅 new-api 容器内部访问）

**new-api 配置方式**：
- 后台 → 自定义 OAuth → 添加提供商 → 填入 discovery URL → 自动填充

**代码位置**：`new-api-dingtalk-oidc/main.py`

**待办**：在钉钉开放平台创建第三方企业应用 → 获取 AppKey/AppSecret → 配置回调域名 → 填入 docker-compose 环境变量 → 启动 → new-api 后台配置

**参考链接**：
- new-api 仓库：https://github.com/Calcium-Ion/new-api
- dingtalk-oidc（参考）：https://github.com/maggch97/dingtalk-oidc
- 钉钉 OAuth2 文档：https://open.dingtalk.com/document/orgapp/obtain-user-token

## Lesson 29: Tailscale MagicDNS 冷启动无上游导致全线 DNS 挂 (2026-07-27)

**问题**：US Vultr 服务器内核升级重启后，所有 DNS 查询返回 SERVFAIL。`/etc/resolv.conf` 被 Tailscale 设为 `nameserver 100.100.100.100`，日志刷屏 `dns: resolver: forward: no upstream resolvers set, returning SERVFAIL`。

**原因**：Tailscale MagicDNS 接管了系统 DNS，但 tailnet 未配置上游解析器。重启后 tailscaled 冷启动，尝试回退读取系统 DNS → systemd-resolved 返回 `500 Internal Server Error`（因 resolv.conf 被 Tailscale 自己设成 foreign 模式）→ 找不到上游 → 全部查询 SERVFAIL。

重启前正常运行一个月未暴露，因长期运行的 tailscaled 缓存了 DNS 状态。重启后状态丢失才暴露。

**修复**：
1. `tailscale set --accept-dns=false` 禁用 MagicDNS
2. systemd-resolved 配置持久化上游 DNS（Vultr DNS + Cloudflare 备用）
3. `ln -sf /run/systemd/resolve/stub-resolv.conf /etc/resolv.conf`

**教训**：不需要 MagicDNS 的节点（只用 IP 通信的出口节点）务必设 `--accept-dns=false`。即使服务器不在中国，MagicDNS 冷启动也可能失败。Tailscale 官方 Issue #15471 / #14252 记录了完全相同的问题。

**诊断命令**：
```bash
tailscale dns status                          # 查看 MagicDNS 状态和上游解析器
journalctl -u tailscaled | grep -i "dns\|SERVFAIL"  # 查看 DNS 错误
```
