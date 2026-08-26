---
okf: v0.1
type: HowTo
title: 运维手册
description: US AI Proxy 服务器日常运维操作指南
tags: [operations, monitoring, health-check, ssh]
---
# 运维手册

## 快速登录

```bash
# 管理员 (root)
ssh us-ubuntu-proxy

# 运维同事 (gq-agent, 有限权限)
ssh gq-agent@<UBUNTU_PUBLIC_IP>
```

## 服务检查

### 手动检查
```bash
# 服务状态
ssh us-ubuntu-proxy systemctl status cliproxyapi

# 查看实时日志
ssh us-ubuntu-proxy journalctl -u cliproxyapi -f

# 查看健康检查日志
ssh us-ubuntu-proxy tail -20 /var/log/cliproxy-health.log

# API 快速测试 (从北京)
curl -s --max-time 10 http://<TAILSCALE_IP>:8317/v1/models \
  -H "Authorization: Bearer <API_KEY>" | head -50
```

### 自动检查
- cron 每 5 分钟跑 `/opt/cliproxyapi/health_check.sh`
- 检查项: systemd 是否 active + API 端口是否响应
- 日志: `/var/log/cliproxy-health.log`

## 服务重启

```bash
ssh us-ubuntu-proxy systemctl restart cliproxyapi
```

systemd 配置了 `Restart=always`，崩溃自动重启，无需手动干预。

## 重新登录 ChatGPT OAuth (换账号时)

```bash
# 1. 在北京开 SSH 隧道 (新窗口, 保持不关)
ssh -L 1455:127.0.0.1:1455 -D 1080 us-ubuntu-proxy

# 2. 停服务
ssh us-ubuntu-proxy systemctl stop cliproxyapi

# 3. 启动 OAuth 登录
ssh us-ubuntu-proxy /opt/cliproxyapi/cli-proxy-api --codex-login

# 4. 在北京 Chrome (SOCKS 代理 localhost:1080) 打开输出的 URL
# 5. 完成后 Ctrl+C, 启动服务
ssh us-ubuntu-proxy systemctl start cliproxyapi
```

## 添加同事 Agent 访问 (gq-agent)

```bash
# 管理员执行:
ssh us-ubuntu-proxy "
  adduser --disabled-password gq-agent
  mkdir -p ~gq-agent/.ssh
  echo '<GQ_PUBKEY>' >> ~gq-agent/.ssh/authorized_keys
  chmod 700 ~gq-agent/.ssh
  chmod 600 ~gq-agent/.ssh/authorized_keys
  chown -R gq-agent:gq-agent ~gq-agent/.ssh
"
```

sudo 权限在 `/etc/sudoers.d/gq-agent`:
```
gq-agent ALL=(root) NOPASSWD: /bin/systemctl status cliproxyapi
gq-agent ALL=(root) NOPASSWD: /bin/systemctl restart cliproxyapi
gq-agent ALL=(root) NOPASSWD: /bin/journalctl -u cliproxyapi *
```

## 磁盘/资源检查

```bash
ssh us-ubuntu-proxy "
  echo '=== Disk ===' && df -h /
  echo '=== Memory ===' && free -h
  echo '=== CPU ===' && uptime
  echo '=== Service ===' && systemctl status cliproxyapi --no-pager | head -5
"
```

## 告警

当前无自动告警。可配置:
- **Telegram Bot**: 健康检查连续失败 3 次 → 发 Telegram 消息
- **邮件**: `mail` 命令发送到管理员邮箱

待后续实施。

## GFW 应急翻墙 (个人 Chrome / 备用)

当 SSRDog 订阅失效 + Tailscale 直连被封锁时的应急方案。

### 链路

```
本地 Chrome (SOCKS5 → localhost:1080)
    → SSH 加密隧道 (经上海跳板)
        → 上海服务器 (国内直连)
            → Tailscale (上海↔US direct)
                → US Vultr 服务器
                    → 互联网 (Google/Gmail 等)
```

### 步骤 1: 启动 SSH 隧道 (Git Bash)

```bash
ssh -i ~/.ssh/id_ed25519_us_proxy -o StrictHostKeyChecking=accept-new \
    -D 1080 -J sh-erpnext-test root@100.126.133.106
```

保持终端窗口不关。如果断了重新跑。

### 步骤 2: 启动 Chrome (PowerShell)

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
    --proxy-server="socks5://127.0.0.1:1080" `
    --user-data-dir="$env:TEMP\chrome-proxy"
```

用这个独立 Chrome 窗口访问 Google/Gmail/SSRDog。

### 前置条件

- 上海服务器 (`sh-erpnext-test`) 能 SSH（国内线路一般不受影响）
- 上海 → 美国 Tailscale 连通（上海有 Tailscale，通常不受 GFW 影响）
- 本地有 `~/.ssh/id_ed25519_us_proxy` 密钥

### 诊断

```bash
# 检查上海 Tailscale 状态
ssh sh-erpnext-test "tailscale status | grep vultr"

# 检查上海→美国连通性
ssh sh-erpnext-test "ping -c 3 100.126.133.106"

# 测试完整链路
ssh -i ~/.ssh/id_ed25519_us_proxy -o StrictHostKeyChecking=accept-new \
    -J sh-erpnext-test root@100.126.133.106 "curl -s --max-time 5 https://www.google.com -o /dev/null -w '%{http_code}'"
```

## GFW 应急翻墙 (办公室全员 / OpenWrt+OpenClash)

当 SSRDog 订阅失效时，通过上海 SSH SOCKS5 隧道为办公室全员提供代理。

### 链路

```
办公室设备 (192.168.10.x, 无任何配置)
    → 新华三 → OpenWrt (OpenClash TPROXY)
        → OpenClash 通过 Tailscale 连接到上海 SOCKS5
            → 上海 SSH 持久化隧道 (systemd)
                → Tailscale (上海→US direct)
                    → US Vultr → 互联网
```

### 部署架构

| 组件 | 位置 | 配置 |
|------|------|------|
| SOCKS5 出口 | US Vultr | `ssh -D` via SSH 服务 |
| SSH 隧道 | 上海 (100.119.28.72) | systemd service `socks5-tunnel`, 绑定 Tailscale IP:1080 |
| iptables 访问控制 | 上海 | 仅允许 OpenWrt Tailscale IP (100.124.94.69) 访问 :1080 |
| OpenClash 代理节点 | OpenWrt | SOCKS5 → 100.119.28.72:1080 |
| OpenClash 策略 | OpenWrt | Emergency 组 → Auto fallback 首位 |

### OpenClash 配置要点

配置位置：`/etc/openclash/config/SSRDogAnyTLS.yaml`

1. **新增 SOCKS5 节点**（proxy 列表首行）：
   ```yaml
   - { name: SH-Tailscale-US, type: socks5, server: 100.119.28.72, port: 1080 }
   ```

2. **新增 Emergency 策略组**（proxy-groups 里）：
   ```yaml
   - { name: Emergency, type: select, proxies: [SH-Tailscale-US, DIRECT] }
   ```

3. **Auto fallback 末尾放 Emergency**（SSRDog 优先，Emergency 兜底）：
   ```yaml
   - { name: Auto, type: fallback, proxies: [...原 SSRDog 节点, Emergency] }
   ```

4. **MATCH 规则保持原始值**（不修改为 Emergency）：
   ```yaml
   - 'MATCH,SSRDOG'
   ```
   > Auto fallback 会按顺序测试：SSRDog 国家组 → Emergency。SSRDog 正常时自动选中 SSRDog，全挂时才走 Emergency。

### 应急启动步骤

```bash
# 1. 确认链路
ssh sh-erpnext-test "tailscale status | grep vultr"  # 应显示 active

# 2. 启动上海 SSH 隧道 (systemd 托管)
ssh sh-erpnext-test systemctl start socks5-tunnel

# 3. 确认 SOCKS5 端口监听
ssh sh-erpnext-test "ss -tlnp | grep 1080"  # 应在 100.119.28.72:1080

# 4. 测试代理
ssh sh-erpnext-test "curl -x socks5h://100.119.28.72:1080 https://www.google.com -o /dev/null -w '%{http_code}'"  # 应返回 200

# 5. 确认 OpenWrt 能连到上海
ssh root@192.168.100.1 "ping -c 2 100.119.28.72"

# 6. 确认 OpenClash 运行
ssh root@192.168.100.1 "/etc/init.d/openclash status"

# 7. 查看实时代理日志
ssh root@192.168.100.1 "tail -f /tmp/openclash.log | grep SH-Tailscale-US"
```

### 订阅更新后 Emergency 持久化机制

**问题**：SSRDog 订阅链接有效期仅 5 分钟，需手动粘贴新链接到 OpenClash GUI 更新。每次更新会重新生成配置文件，覆盖手动添加的 Emergency 配置。

**方案**：使用 OpenClash 的 `openclash_custom_overwrite.sh` 脚本（`/etc/openclash/custom/`），在每次配置重新生成后自动注入 Emergency 代理组。

**脚本逻辑**（已部署于 2026-07-02，2026-07-03 修复）：
1. 检查配置中是否已有 `SH-Tailscale-US` 节点（幂等，已有则跳过）
2. 注入 SOCKS5 代理节点 + Emergency 策略组
3. Emergency 放入 Auto fallback **末尾**（SSRDog 优先，全部失败才兜底）
4. **不修改 MATCH 规则**（保持原始 `MATCH,SSRDOG`）
5. 同时处理两个路径：`/etc/openclash/config/` 和 `/etc/openclash/`（覆盖 Clash 实际加载的路径）

**用户操作流程**：
1. 登录 SSRDog 后台 → 复制最新订阅链接（5分钟内有效）
2. OpenClash LuCI → 配置管理 → 粘贴订阅链接 → 更新配置
3. OpenClash 自动重启 → overwrite 脚本自动注入 Emergency
4. 不需要任何额外操作，Emergency 代理组自动出现

### 回滚步骤

```bash
# 1. 恢复 OpenClash 原配置
ssh root@192.168.100.1 "cp /etc/openclash/config/SSRDogAnyTLS.yaml.bak /etc/openclash/config/SSRDogAnyTLS.yaml"

# 2. 重启 OpenClash
ssh root@192.168.100.1 /etc/init.d/openclash restart

# 3. (可选) 停止上海隧道
ssh sh-erpnext-test systemctl stop socks5-tunnel
```

### 上海 SSH 隧道 systemd service

`/etc/systemd/system/socks5-tunnel.service`:

```ini
[Unit]
Description=SSH SOCKS5 Tunnel to US Vultr via Tailscale
After=network-online.target tailscaled.service
Wants=network-online.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/ssh -N -D 100.119.28.72:1080 \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -o ExitOnForwardFailure=yes \
    -o StrictHostKeyChecking=accept-new \
    -i /root/.ssh/id_ed25519_us_proxy_tunnel \
    root@100.126.133.106
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 日常运维

#### 上海 SSH 隧道

```bash
# 查看状态（是否运行、运行多久）
ssh sh-erpnext-test systemctl status socks5-tunnel

# 查看最近日志
ssh sh-erpnext-test journalctl -u socks5-tunnel -n 20 --no-pager

# 启动
ssh sh-erpnext-test systemctl start socks5-tunnel

# 停止（⚠️ 办公室翻墙会断）
ssh sh-erpnext-test systemctl stop socks5-tunnel

# 重启
ssh sh-erpnext-test systemctl restart socks5-tunnel

# 测试代理是否正常
ssh sh-erpnext-test "curl -x socks5h://100.119.28.72:1080 -s --max-time 10 https://www.google.com -o /dev/null -w '%{http_code}'"
# 正常输出: 200
```

隧道特性：
- **开机自启**：`systemctl enable socks5-tunnel`（已设置）
- **崩溃自愈**：`Restart=always`，SSH 断开 10 秒后自动重连
- **存活检测**：`ServerAliveInterval=30` + `ServerAliveCountMax=3`，90 秒无响应判定断开

#### 办公室翻墙状态

```bash
# 查看 OpenClash 是否在走 Emergency 代理
ssh -i ~/.ssh/id_rsa_openwrt root@192.168.100.1 \
  "tail -20 /tmp/openclash.log | grep -oE 'Emergency\[|SSRDOG\[' | sort | uniq -c"
```

输出中 `Emergency[` 数量 > 0 说明应急线路正在工作。

#### 链路全检（一键脚本）

```bash
echo "=== 1. 上海 Tailscale 状态 ==="
ssh sh-erpnext-test "tailscale status | grep vultr"

echo "=== 2. 上海 SSH 隧道 ==="
ssh sh-erpnext-test systemctl is-active socks5-tunnel

echo "=== 3. SOCKS5 端口 ==="
ssh sh-erpnext-test "ss -tlnp | grep 1080"

echo "=== 4. 代理 Google 可达 ==="
ssh sh-erpnext-test "curl -x socks5h://100.119.28.72:1080 -s --max-time 10 https://www.google.com -o /dev/null -w '%{http_code}'"

echo "=== 5. OpenClash 运行状态 ==="
ssh -i ~/.ssh/id_rsa_openwrt root@192.168.100.1 "ps | grep 'clash -d' | grep -v grep | head -1"

echo "=== 6. 办公室流量线路 ==="
ssh -i ~/.ssh/id_rsa_openwrt root@192.168.100.1 \
  "tail -10 /tmp/openclash.log | grep -oE 'Emergency\[|SSRDOG\[' | sort | uniq -c"
```

## 翻墙流量机制与额度 (2026-08-25)

### 什么流量走代理 / 直连

办公室翻墙路由由 **OpenClash 规则**决定，与机场（SSRDog/BoostNet）无关：

```
国内 IP（china_ip_route）→ iptables 直连，不进 Clash（不耗额度）
国外 IP → 重定向进 Clash
  ↓ Clash 规则逐条匹配
  ChinaMax / 钉钉 / sellfox 等 → DIRECT（不耗额度）
  其余 → Match → 代理组（BoostNet）→ 消耗额度
```

- 钉钉、国内视频会议、国内网站 → DIRECT，**不消耗机场额度**
- YouTube / Google / ChatGPT / 国外网站 → 走代理，**消耗额度**
- 国内服务的国外 CDN（如某些 .com 域名解析到国外 IP）→ 规则上无法区分，会走代理（属正常，不是故障）

### 已知 DIRECT 例外

- **`45.63.1.166`（Vultr RDP 服务器）→ DIRECT**：BoostNet 对该服务器 3389 的 RDP 不通（香港/美国节点都试过，普通网页正常，疑似 BoostNet 屏蔽 RDP；直连光猫/US 服务器/应急线路都能正常 RDP）。故自定义规则加 `IP-CIDR,45.63.1.166/32,DIRECT` 直连。若以后换机场后 RDP 正常，可移除此规则。

### 机场额度怎么算

- 机场（BoostNet/SSRDog）按**经过其节点的字节数**计费，OpenClash 决定发什么给节点
- 不同机场只是"账户额度 + 节点"不同，**路由规则完全一样**（同一份 OpenClash 配置）

### 实测结果 (2026-08-25, BoostNet)

- 启用 2 小时内消耗约 840MB（上行 141MB + 下行 698MB），**属正常偏高**；主要被 **YouTube 视频流**吃掉（活动连接快照 ~30%），其次 Wayfair 工作平台（~21%）
- 活动连接快照分析：**未发现国内 IP 误走代理**，国内流量正确直连
- 历史参照：SSRDog 每月约 280G（同一套规则）→ BoostNet 400G/月 有 ~40% 余量
- **若额度消耗异常快，优先排查 YouTube/视频用量**（最大头）

### 查看当前流量构成

```bash
# 当前活动连接（每个连接的 host / 出口策略 / 上下行字节）
ssh -i ~/.ssh/id_rsa_openwrt root@192.168.100.1 \
  "wget -qO- --header='Authorization: Bearer 123456' http://127.0.0.1:9090/connections"
```

> 把返回的 JSON 下载到本地，用 python 按 `metadata.host` / `chains[0]` / `upload` / `download` 聚合，即可得到按域名和策略的流量占比。

## AI 出口切换（按国家分组，2026-08-25）

### 为什么加

老板 ChatGPT 网页在香港出口打不开（同一个香港节点，不同 OpenAI 账号结果不同——OpenAI 按账号/地区/风控判定），而日本/美国出口对大多数账号都友好。BoostNet 订阅**没有**按国家分组（只有 `自动选择`/`故障转移`/全节点扁平列表），所以通过覆写脚本动态生成了国家组 + AI 出口主组。

### 结构

```
AI 规则（GEOSITE,openai / chatgpt.com 等 14 条）→ AI 出口
AI 出口（select）: 自动选择 / 日本 / 美国 / 香港 / 新加坡 / 台湾 / 故障转移
  ├── 自动选择（url-test，BoostNet 原生）
  ├── 日本（select: 日本01-08）
  ├── 美国（select: 美国01-04）
  ├── 香港（select: 香港01-012）
  ├── 新加坡 / 台湾（select）
  └── 故障转移（fallback，BoostNet 原生）
```

- 默认 `AI 出口 → 自动选择`（通常选到香港07），日常体验不变
- 需要日本/美国出口时，把 `AI 出口` 切到对应国家组

### 如何切换

**Zashboard / OpenClash 面板**：代理组 → `AI 出口` → 选择 `日本`（或 `美国`）。

**API 方式**：
```bash
# 查看当前 AI 出口
ssh root@192.168.100.1 "wget -qO- --header='Authorization: Bearer 123456' http://127.0.0.1:9090/proxies/AI%20%E5%87%BA%E5%8F%A3 | grep -o '\"now\":\"[^\"]*\"'"

# 切到日本
ssh root@192.168.100.1 "curl -s -X PUT 'http://127.0.0.1:9090/proxies/AI%20%E5%87%BA%E5%8F%A3' -H 'Authorization: Bearer 123456' -d '{\"name\":\"日本\"}' -o /dev/null -w '%{http_code}'"

# 切回自动选择
ssh root@192.168.100.1 "curl -s -X PUT 'http://127.0.0.1:9090/proxies/AI%20%E5%87%BA%E5%8F%A3' -H 'Authorization: Bearer 123456' -d '{\"name\":\"自动选择\"}' -o /dev/null -w '%{http_code}'"
```

### 持久化与注意

- 国家组 + AI 出口 + 14 条 AI 规则都由 `openclash_custom_overwrite.sh` 的 `add_country_groups()` 注入，**订阅更新/重启不覆盖**（节点名变化时按前缀自动跟随）
- **AI 规则不放自定义规则文件**：OpenClash 合并自定义规则时会校验目标组是否存在，`AI 出口` 组由覆写脚本后创建，放规则文件会被丢弃（实测）。所以 AI 规则在脚本里注入
- 切换是**全局**的（所有 AI 流量都走同一出口），无法只让老板走日本、其他人走香港
- 重启后 `AI 出口` 会重置为默认（自动选择）——若需要记住手动选择，可开启 `store-selected`（未启用）

## 见也

- [../AGENT_HANDOFF.md](../AGENT_HANDOFF.md) — Agent 参考
- [architecture.md](architecture.md) — 架构设计
- [lessons/lessons-learned.md](lessons/lessons-learned.md) — 经验教训
