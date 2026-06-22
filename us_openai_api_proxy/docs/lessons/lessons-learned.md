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

