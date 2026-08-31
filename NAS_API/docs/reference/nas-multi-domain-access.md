---
okf: v0.1
type: Reference
title: 群晖 NAS 多域名访问与 QuickConnect 选路
description: 北京办公室 OpenWrt 劫持、OpenWrt ACME 第二张证、DSM 反代、Cloudflare/阿里云 DDNS、联通端口与 QC 直连/中继
tags: [nas, synology, quickconnect, openwrt, dsm, acme, cloudflare, daneey, vilavi]
timestamp: 2026-08-31
resource: NAS_API/AGENT_HANDOFF.md
---

# 群晖 NAS 多域名访问与 QuickConnect 选路

## 背景

FZH 群晖 NAS（QuickConnect ID `fangzhouhui`）需同时满足：

1. **统一入口**：`https://fangzhouhui.quickconnect.cn/` — 群晖自动检测网络，能直连则跳 `fzh.myds.me:11024`，否则走 `cn4` 中继（慢但总能连上）。
2. **深圳/特殊园区**：官方 `fzh.myds.me` 解析可能失败，需阿里云/Cloudflare 自定义域名。
3. **北京办公室**：OpenWrt 域名劫持到 NAS LAN IP，局域网免端口、证书匹配。

**用户政策（2026-08-28）：** 暂不替换 QC 统一入口；自定义域名（`nas.daneey.com`、`nas.vilavi.cn` 等）是补充，因固定域名在部分网络下无法直连，而 QC 有中继兜底。

## 网络拓扑

```
联通光猫 192.168.1.1（公网 123.117.236.65）
├── 端口转发 11024 → 192.168.1.5:11024（通）
├── 端口转发 443 → 192.168.1.5:443（LAN 通，公网不通 — 联通限制）
└── LAN → OpenWrt WAN eth1 192.168.1.3

OpenWrt 192.168.100.1
├── dnsmasq 劫持 → 192.168.100.242
│   fzh.myds.me / nas.daneey.com / nas.vilavi.cn / nas.mxdeals.com
├── DDNS 阿里云 → nas.daneey.com
├── DDNS Cloudflare → nas.vilavi.cn
└── ACME dns_ali / dns_cf（证书导入 DSM，不改 LuCI/nginx）

新华三 192.168.10.1（FZH-5G WiFi）
└── 客户端 DNS 常指向 192.168.10.1（也劫持 myds → .242）

群晖 NAS 双网口
├── eth0 192.168.100.242（OpenWrt LAN）
└── eth1 192.168.1.5（光猫 LAN）
```

## 域名与证书一览

| 域名 | DNS 提供商 | 代理 | 证书 DSM ID | 反代 |
|------|-----------|------|-------------|------|
| `fzh.myds.me` | Synology | — | `RmB4St`（**默认**） | 原生 11024 |
| `nas.daneey.com` | 阿里云 | — | `aJodgl` | 443 + 11024 |
| `nas.vilavi.cn` | Cloudflare | **灰云** | `orAHAw` | 443 + 11024 |
| `nas.mxdeals.com` | 公网解析 | — | 无（仍 `fzh.myds.me` 证） | 仅劫持，未签证；**未**进 DSM 外部访问 DDNS |

### 两条路径：OpenWrt 自定义域 vs QC 登记域

```
路径 A（手动备用 URL）          路径 B（QC 统一入口）
─────────────────────          ─────────────────────
nas.daneey.com / vilavi.cn     fangzhouhui.quickconnect.cn
        │                                │
 OpenWrt DDNS + ACME              群晖 QC 云端 + myds.me
        │                                │
 DSM 第二张证 + 反代               默认证 RmB4St
        │                                │
 用户手动输入 :11024              自动跳 myds:11024 或 cn4
        │                                │
 QC 不会自动跳这里 ◄──────────► QC 只探测群晖登记主机名
```

- **路径 A** 故意**不**写入 DSM「控制面板 → 外部访问 → DDNS」，避免 NAS 与 OpenWrt 重复更新同一记录。
- **路径 B** 的 `fzh.myds.me` 是用户在 DSM 外部访问里配置的 **Synology 提供商** DDNS，与路径 A 无关。
- **不能**通过删除 myds 或「让 mxdeals 优先」使 QC 只跳自定义域；DSM 无 DDNS 优先级 UI。

### 证书流程（新域名标准做法）

1. **OpenWrt** `acme` + DNS-01（`dns_ali` 或 `dns_cf`），`update_uhttpd=0`、`update_nginx=0`。
2. **DSM** `SYNO.Core.Certificate` import，`desc` = 域名，`is_default=false`。
3. **反代** `SYNO.Core.AppPortal.ReverseProxy`：frontend = 新域名 + 443/11024；backend = `127.0.0.1:11024`；`customize_headers`: `Host: fzh.myds.me`。
4. **绑定** `SYNO.Core.Certificate.Service` set：仅 ReverseProxy 对应 service，**不要**动 DSM Desktop Service。

### 铁律：勿改默认 DSM 桌面服务证书

把「DSM 桌面服务」指到新证 → 整个 `:11024` 的默认 SNI 变成新域名 → `fzh.myds.me` 浏览器警告。曾发生并已回滚。

## Cloudflare nas.vilavi.cn

- Zone `vilavi.cn`；A 记录 **仅 DNS（灰云）** → 当前公网 IP，TTL 120。
- Token 权限：**Zone DNS Edit + Zone Read**（账户级 DNS Firewall token 无效）。
- OpenWrt `ddns.nas_vilavi`：`update_script=/usr/lib/ddns/update_cloudflare_com_v4.sh`，`username=Bearer`，`dns_server=1.1.1.1`（避免劫持污染 DDNS 自检）。
- ACME 需 `CF_Token` + `CF_Zone_ID`；首次生产证遇 CAA 查 `.cn` 超时，已在 `nas.vilavi.cn` 加 CAA `issue letsencrypt.org` 后成功。
- **不用** Container `jeessy-ddns-go-1`（历史阿里云方案）；**不用** DSM 外部访问自定义 DDNS。

## 外网可达性（2026-08-28 探测）

| URL | 手机流量 / 外网 | OpenWrt WiFi（劫持） |
|-----|----------------|---------------------|
| `https://nas.daneey.com:11024/` | 通 | 通 |
| `https://nas.vilavi.cn:11024/` | 通 | 通 |
| `https://nas.daneey.com/`（443） | 不通 | 通（劫持） |
| `https://nas.vilavi.cn/`（443） | 不通 | 通（劫持） |
| `https://fzh.myds.me:11024/` | 依赖园区 DNS | 通 |

公网 443/80 对 `123.117.236.65` 多地 TCP 超时；11024 通。联通光猫虚拟主机已加 443 转发仍无效 → **搁置**，外网继续用 `:11024`。

## QuickConnect 直连 vs cn4 中继

**机制：** 浏览器打开 QC 页 → JS 向 `cnc.quickconnect.cn` 探测 → 能连 `fzh.myds.me:11024` 则直连，否则 `fangzhouhui.cn4.quickconnect.cn`。

**直连前提（办公室）：** 客户端把 `fzh.myds.me` 解析到 `192.168.100.242`（OpenWrt 劫持），且能 TLS 到 11024。

**走中继的常见原因：**

| 场景 | 原因 |
|------|------|
| 光猫 WiFi（无劫持） | 解析公网 IP → NAT 回环失败 |
| Chrome 安全 DNS | 绕过劫持 → 公网 IP → 回环失败；Edge/手机正常 |
| 未完成群晖中国实名 | API `check-item-permission`；页上提示绑定手机 |
| 深圳 | `myds.me` 解析失败 → QC 跳 myds 后仍打不开 |

**验证（2026-08-28）：** 手机 FZH-5G 与手机流量均 QC → `fzh.myds.me:11024`；台式机 Chrome 仍 cn4，`ipconfig /flushdns` 无效，换 Edge 正常。

### DSM 外部访问 DDNS 常见问题（2026-08-31）

| 问题 | 答案 |
|------|------|
| daneey/vilavi 是否只在 NAS 加了证？ | 否。OpenWrt DDNS + ACME + DSM 反代全栈；证只是其中一步。 |
| 改外部访问 DDNS 能否让 QC 跳 daneey？ | 不能指望；当前未写入 DSM DDNS，QC 也不跳它们。 |
| 删 `fzh.myds.me` 或 mxdeals 优先？ | 无优先开关；删 myds 高风险，不会可靠变成只跳 mxdeals。 |
| 深圳 QC 打不开？ | QC 仍跳 myds；用路径 A 书签 `nas.daneey.com:11024` 等。 |

### 中国区 QC（调研摘要）

2023 年起国内 `*.direct.quickconnect.cn` 关闭 IPv4 公网解析，外网 QC 多经中继；官方建议有公网 IP 时用 **自建 DDNS + 端口转发**（路径 A），而非依赖 QC 直连。

## 阶段性成果

- [x] `nas.daneey.com` 外网 + 办公室 HTTPS（独立 LE 证）
- [x] `nas.vilavi.cn` 外网 + 办公室 HTTPS（Cloudflare + LE 证）
- [x] OpenWrt 劫持四域名
- [x] 默认 `fzh.myds.me` 证书未破坏
- [ ] 深圳 `fzh.myds.me` / QC 统一入口后的可达性（备用路径 A 书签）
- [ ] 公网 443（联通）
- [ ] 台式机 Chrome QC 直连
- [ ] `nas.mxdeals.com` 独立证书（全栈后仍不保证 QC 改跳）

## 未决议题

- `fangzhouhui.quickconnect.cn` 办公室 Chrome → cn4（安全 DNS）
- 是否在**不删 myds** 前提下做 QC 跳转对照实验（改 DSM DDNS 前）

## 相关文件

- Agent：[../AGENT_HANDOFF.md](../AGENT_HANDOFF.md)
- Solutions：[../../docs/solutions/integration-issues/nas-multi-domain-access-openwrt-quickconnect.md](../../docs/solutions/integration-issues/nas-multi-domain-access-openwrt-quickconnect.md)
- 办公室 Tailscale：[../../us_openai_api_proxy/docs/office-lan-access.md](../../us_openai_api_proxy/docs/office-lan-access.md)
