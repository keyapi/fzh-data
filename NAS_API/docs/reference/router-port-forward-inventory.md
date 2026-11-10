---
okf: v0.1
type: Reference
title: 联通光猫（ZXHN F4610U）端口转发与网络配置清单
description: 办公室光猫的 16 条端口转发、4 条静态 DHCP 绑定、LAN/PPPoE/WiFi 现状，以及搬家换设备的两种恢复方案
tags: [nas, synology, port-forward, router, unicom, zte, f4610u, network, migration]
timestamp: 2026-11-10
resource: NAS_API/AGENT_HANDOFF.md
---

# 联通光猫（ZXHN F4610U）端口转发与网络配置清单

## 背景

办公室搬迁后仍走中国联通，但很可能更换光猫/路由器。NAS（群晖 `FZH-NAS`）的外网访问完全依赖光猫上的端口转发，规则一旦丢失外网即中断。本文是 2026-11-10 对现网做的只读盘点，用于**备份**与**换设备后重建**。

> 敏感值（管理密码、WiFi 密钥、PPPoE 账号与密码、当前公网 IP）不写入本文，另存在 gitignore 的 `NAS_API/secrets/router-f4610u.local.md`。

## 设备与上行链路

| 项 | 值 |
|---|---|
| 设备 | 中兴 `ZXHN F4610U`（联通定制，C容器；HW `V1.0` / SW `V1.2.0P1T3`） |
| 上行方式 | EPON |
| 光猫 MAC | `64:DB:38:50:1C:0B` |
| 公网 IPv4 | **动态**（会变；以 DDNS 记录为准） |
| PPPoE 连接 | `2_INTERNET_R_VID_3961`，VLAN `3961`，802.1p `0`，AlwaysOn |
| 其它 WAN | `1_TR069_R_VID_3969`（联通远程管理）、`3_IPTV_R_VID_3964`、`5_VOICE_R_VID_3010` |
| DNS（联通下发） | `202.106.195.68` / `202.106.46.151` |
| LAN | `192.168.1.1/24`，DHCP 开，地址池 `.2–.254`，租期 1 天 |
| 配置导出 | **固件无此功能**（管理→设备管理 仅「设备重启」「恢复出厂配置」） |

拓扑：光猫 `192.168.1.1` → OpenWrt WAN `192.168.1.3`（OpenWrt LAN `192.168.100.1`）→ NAS 双网口 `192.168.1.5`（eth1）/ `192.168.100.242`（eth0）。完整访问链路见 [nas-multi-domain-access.md](nas-multi-domain-access.md)。

## 静态 DHCP 绑定（4 条）

换设备后**必须原样重建**，否则端口转发目标与 OpenWrt 上联都会错位。

| IP | MAC | 设备 |
|---|---|---|
| `192.168.1.5` | `90:09:d0:2a:52:32` | **NAS eth1**（全部端口转发的目标） |
| `192.168.1.3` | `72:67:1a:40:88:42` | **OpenWrt WAN** |
| `192.168.1.15` | `b0:22:7a:57:57:4a` | 未在线，设备待确认 |
| `192.168.1.16` | `dc:cd:2f:b7:aa:62` | EPSON 打印机 |

## 端口转发（原 16 条；2026-11-10 删除 `NASMariaDB` 后剩 15 条，全部 → `192.168.1.5`）

"实测"列是 2026-11-10 在内网对 `192.168.1.5` 逐个 TCP 探测的结果。

| # | 名称 | 协议 | 外网 | 内网 | 实测 | 判定 |
|---|---|---|---|---|---|---|
| 1 | NAS11023 | TCP | 11023 | 11023 | nginx，返回跳转到 `:11024` 的小页面 | 留（便捷入口） |
| 2 | NAS11024 | TCP | 11024 | 11024 | DSM HTTPS | **必须留** |
| 3 | NASDrivePC6690 | TCP | 6690 | 6690 | Synology Drive 同步 | **必须留** |
| 4 | NASDriveApp5000 | TCP | 5000 | 5000 | 内网 5000 **未监听** | 死规则（记录，换设备时处理） |
| 5 | NASHTTP | TCP | 11025 | 80 | Synology Web Station | 留 |
| 6 | NASHTTP80 | TCP | 80 | 80 | Web Station 在，但**公网被联通封** | 留（公网无效） |
| 7 | NASNFS2049 | TCP+UDP | 2049 | 2049 | **未监听** | 死规则（记录，换设备时处理） |
| 8 | NASNFS111 | TCP+UDP | 111 | 111 | **未监听** | 死规则（记录，换设备时处理） |
| 9 | NASNFS892 | TCP+UDP | 892 | 892 | **未监听** | 死规则（记录，换设备时处理） |
| 10 | NASminio9000 | TCP | 9000 | 9000 | MinIO API | 留 |
| 11 | NASminio9090 | TCP | 9090 | 9090 | MinIO Console | 留 |
| 12 | NASFTP11021 | TCP | 11021 | 11021 | FTP（明文） | 留 |
| 13 | NASMariaDB | TCP | 13306 | 13306 | MariaDB `10.11.6` | **已删除**（2026-11-10） |
| 14 | NASphpMyAdmin | TCP | 19201 | 19201 | phpMyAdmin（HTTPS） | 留 |
| 15 | NAS WebDav 15006 | TCP | 15006 | 15006 | Apache WebDAV | 留 |
| 16 | NASHTTPS443 | TCP | 443 | 443 | DSM 服务在，**公网被联通封** | 留（公网无效） |

补充：
- NAS SSH 监听 `31022`，**未做转发**（仅内网可达）。迁移时不要顺手加。
- `80`/`443` 公网不通是联通侧限制，规则保留无害但不要指望生效。

### 安全备注

- `13306` MariaDB 直接暴露公网，是本清单最高风险项。**已关闭**（2026-11-10 在光猫虚拟主机配置中删除该规则）；迁移时不再重建。
- `19201` phpMyAdmin、`11021` FTP（明文）、`15006` WebDAV 是常见爆破/拖库目标，建议强密码 + 必要时限制来源 IP。
- 路由器管理密码与 WiFi 密码当前相同，等于所有连过 WiFi 的人都知道路由器密码。换设备时建议改掉。

## 其它配置现状

| 模块 | 现状 | 是否需要迁移 |
|---|---|---|
| 动态 DNS（DDNS） | **未启用**（DDNS 在 OpenWrt 上做） | 否 |
| DMZ | **未启用** | 否 |
| ALG | TFTP/RTSP/PPTP/L2TP/IPSEC/FTP 开，SIP/H323 关（默认） | 否（默认值） |
| 网页过滤 / MAC 过滤 / 端口过滤 | **全部为空** | 否 |
| 防火墙 | SPI、DoS 防护均关闭（默认态） | 否 |
| 无线 2.4G | SSID `hZRG`，WPA/WPA2-PSK + AES | 若继续用光猫 WiFi 则需重建 |
| 无线 5G | SSID `hZRG_5G`，WPA/WPA2-PSK + AES | 同上 |

## 路由器页面地址（日后复查）

```
登录         http://192.168.1.1/                       （无用户名，仅密码）
主框架       http://192.168.1.1/unicom.html
虚拟主机     getpage.gch?pid=1002&nextpage=BJ_app_virtual_conf_t.gch
DMZ          getpage.gch?pid=1002&nextpage=app_dmz_conf_t.gch
DDNS         getpage.gch?pid=1002&nextpage=app_ddns_conf_t.gch
ALG          getpage.gch?pid=1002&nextpage=sec_fw_alg_t.gch
LAN/DHCP     getpage.gch?pid=1002&nextpage=net_dhcp_dynamic_t.gch
静态绑定     getpage.gch?pid=1002&nextpage=BJ_net_dhcp_static_t.gch
宽带(PPPoE)  getpage.gch?pid=1002&nextpage=BJ_net_user_wan_conf_t.gch
WLAN 2.4G    getpage.gch?pid=1002&nextpage=net_wlan_basic_t1.gch
WLAN 5G      getpage.gch?pid=1002&nextpage=net_wlan_basic_t2.gch
WAN 状态     getpage.gch?pid=1002&nextpage=status_ethwan_if_t.gch
```

注意：直接在新标签页打开 `getpage.gch?...` 会 400（校验 Referer），必须从 `unicom.html` 的 `mainFrame` 内跳转。

## 搬家前要确认的事

1. **公网 IPv4 是硬性前提**（2026-11-10 确认）：装机时明确要求"需要公网 IP 做端口映射"。若新址给的是运营商大内网（CGNAT），下面两套方案全部失效，NAS 只能退回 QuickConnect `cn4` 中继。
2. **宽带账号/密码不用自己准备**：由联通上门或远程配置好；装机时只需确认能进端口映射页。
3. 确认新光猫型号，以及能否拿到超级管理员权限（联通定制固件普通账号可能进不去端口映射页）。
4. 备份 NAS 侧 DSM 配置与 OpenWrt `/etc/config`。

## 待办

- [x] **关闭 13306（MariaDB）**：2026-11-10 已在光猫「虚拟主机配置」删除 `NASMariaDB` 规则，现网剩 15 条转发。
- [ ] **4 条死规则**（`5000` / `2049` / `111` / `892`）：**只记录，暂不动**。等换新光猫/路由器时一并处理，不在现网做删除。
- [ ] 换设备时改掉路由器管理密码 / WiFi 密码（当前二者相同）。

## 恢复方案 A：在新光猫/路由器上重建（快，约 1 小时）

1. LAN 设为 `192.168.1.1/24`，DHCP 池 `.2–.254`
2. 建 4 条静态绑定（见上）
3. 配 PPPoE（由联通配置）
4. 建 11 条转发（跳过 4 条死规则与已关闭的 `13306`）
5. 若继续用光猫 WiFi：SSID `hZRG` / `hZRG_5G`，WPA2-PSK + AES，**换新密码**
6. 按下方验证清单逐项测试

## 恢复方案 B：转发下沉到 OpenWrt（长期一劳永逸）

1. 新光猫二选一：**桥接**（OpenWrt 直接 PPPoE，需联通改）或 **路由模式 + DMZ 指向 OpenWrt WAN IP**（只需一条规则）
2. OpenWrt 上按 11 条有效端口建 `firewall.redirect`（UCI 可导出备份），目标改为 `192.168.100.242`
3. NAS 的 `eth1` 可拔掉，架构变单臂
4. 重新验证 QC 直连、DSM 反代（`:11024` + `Host: fzh.myds.me`）、两张第二证书

收益：以后换任何路由器只需在光猫上配一条 DMZ，端口清单随 OpenWrt 配置一起备份。
代价：需动现网并重走访问链路验证，[nas-multi-domain-access.md](nas-multi-domain-access.md) 里的证书/反代铁律仍然适用。

## 验证清单（迁移后用手机流量测，勿用办公室 WiFi）

| 目标 | 期望 |
|---|---|
| `https://nas.daneey.com:11024/` | DSM 登录页 |
| `https://nas.vilavi.cn:11024/` | DSM 登录页 |
| `https://fangzhouhui.quickconnect.cn/` | 能进入（直连或 `cn4` 中继） |
| Synology Drive 客户端 | 能同步（6690） |
| MinIO `9000` / phpMyAdmin `19201` / WebDAV `15006` / FTP `11021` | 均有响应 |
| MariaDB `13306` | **应当连不上**（规则已按决定移除） |

同时确认 OpenWrt DDNS 已把 `nas.daneey.com` / `nas.vilavi.cn` 更新到新公网 IP。

## 相关文件

- Agent：[../../AGENT_HANDOFF.md](../../AGENT_HANDOFF.md)
- 访问架构：[nas-multi-domain-access.md](nas-multi-domain-access.md)
- 本地密钥与页面快照：`NAS_API/secrets/router-f4610u.local.md`（gitignore，不入库）
