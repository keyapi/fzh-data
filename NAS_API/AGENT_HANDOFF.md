# NAS_API — Agent Handoff

> 群晖 DSM API / SSH 运维入口。凭证在 `NAS_API/.env`（gitignore）。

## 设备

| 项 | 值 |
|---|---|
| 主机名 | FZH-NAS |
| QuickConnect ID | `fangzhouhui` |
| 默认 DSM 证书 CN | `fzh.myds.me`（archive `RmB4St`，**勿改默认绑定**） |
| DSM HTTPS | `:11024`（外网/反代主端口） |
| SSH | `192.168.1.5:31022`（光猫侧）/ 经 OpenWrt LAN `192.168.100.242:11024` |
| 双网口 | `eth0` `192.168.100.242`（OpenWrt LAN）；`eth1` `192.168.1.5`（光猫 LAN） |
| 公网 IP | `123.117.236.65`（联通，会变；以 DDNS 为准） |

## 访问域名（2026-08 现状）

| 域名 | DNS | 证书来源 | 用途 |
|------|-----|----------|------|
| `fzh.myds.me` | 群晖 Synology DDNS | DSM 默认 Let's Encrypt | 官方 DDNS；QC 直连目标 |
| `nas.daneey.com` | 阿里云（OpenWrt DDNS） | OpenWrt ACME `dns_ali` → DSM 第二张证 `aJodgl` | 深圳/外网备用；**推荐** |
| `nas.vilavi.cn` | Cloudflare 灰云 A（OpenWrt DDNS） | OpenWrt ACME `dns_cf` → DSM 第二张证 `orAHAw` | 深圳/外网备用 |
| `nas.mxdeals.com` | 公网解析 | 无独立证（仍出示 `fzh.myds.me`） | 仅 OpenWrt 劫持到 LAN；未签独立证；**未**进 DSM 外部访问 DDNS |
| `fangzhouhui.quickconnect.cn` | 群晖 CDN | — | **统一入口**；自动选直连或 `cn4` 中继 |

**政策（用户确认）：** 对外仍宣传 `https://fangzhouhui.quickconnect.cn/` 作为统一入口（群晖中继兜底）。自定义域名是补充，不能替代 QC 的「环境自适应」能力。

## 两条路径（勿混）

| | OpenWrt 自定义域（daneey/vilavi） | QC 登记域（myds） |
|--|-----------------------------------|-------------------|
| DNS | OpenWrt DDNS | DSM 外部访问 Synology DDNS |
| 证+反代 | OpenWrt ACME → DSM 第二张证 | 默认证 `RmB4St` |
| QC 自动跳 | **否** — 用户手动 `:11024` | **是** — 探测 myds 或 cn4 |
| DSM 外部访问 DDNS | **故意不写** | `fzh.myds.me` 保留，**勿删** |

改 DSM DDNS 列表**不能**让 QC 跳 daneey/vilavi；无「mxdeals 优先」开关。

## OpenWrt（北京办公室）

- SSH：`root@192.168.100.1`（密钥 `~/.ssh/id_rsa_openwrt`）
- `dhcp.@domain` 劫持 → `192.168.100.242`：`fzh.myds.me`、`nas.daneey.com`、`nas.vilavi.cn`、`nas.mxdeals.com`
- DDNS：`ddns.myddns_ipv4` 阿里云 → `nas.daneey.com`；`ddns.nas_vilavi` Cloudflare → `nas.vilavi.cn`
- ACME：`acme.nas_daneey`（`dns_ali`）、`acme.nas_vilavi`（`dns_cf` + `CF_Zone_ID`）；`update_uhttpd=0`、`update_nginx=0`
- Cloudflare `nas.vilavi.cn`：**必须灰云**（橙云只代理 80/443，`:11024` 会废）

## DSM 证书铁律

1. **永远不要**把「DSM 桌面服务」默认证书从 `RmB4St`（`fzh.myds.me`）换成其他证——否则 `:11024` 全站 SNI 都会变。
2. 新域名：OpenWrt 签 LE → `SYNO.Core.Certificate` import（`is_default=false`）→ 反代 443/11024 → `SYNO.Core.Certificate.Service` **仅绑 ReverseProxy 服务**。
3. 反代后端 `127.0.0.1:11024`，`customize_headers` 必须 `Host: fzh.myds.me`（否则 nginx 400 环回）。

## 光猫端口转发（联通）

| 外网 | 内网 | 状态 |
|------|------|------|
| 11024 | 192.168.1.5:11024 | 通（外网/手机可用） |
| 443 | 192.168.1.5:443 | **公网不通**（联通限制或远程管理占用）；LAN 反代 443 仅办公室劫持可用 |
| 80 | 192.168.1.5:80 | 公网不通 |

因此外网 `https://nas.daneey.com/`（无端口）和 `https://nas.vilavi.cn/` 目前不可用；用 `:11024`。

## QuickConnect 直连 vs 中继

- **直连：** QC 页 JS 探测 `fzh.myds.me:11024` 成功 → 跳转 `https://fzh.myds.me:11024/`
- **中继：** 探测失败 → `https://fangzhouhui.cn4.quickconnect.cn/`
- 办公室 OpenWrt 劫持下，客户端 DNS 必须解析到 `192.168.100.242`；Chrome「安全 DNS」会绕过劫持 → 解析公网 IP → NAT 回环失败 → cn4
- 光猫 WiFi（无劫持）：预期走 cn4（用户接受）
- **深圳：** `fzh.myds.me` 解析仍可能失败（园区 DNS）；QC 跳 myds 后打不开——**未解决**；可用 `nas.daneey.com:11024` 或 `nas.vilavi.cn:11024`

## 未决 / 搁置

- [ ] 深圳 `fzh.myds.me` 解析/访问
- [ ] 联通光猫 443 公网转发
- [ ] 台式机 Chrome QC → cn4（Edge/手机正常；查 Chrome 安全 DNS）
- [ ] `nas.mxdeals.com` 独立证书（DNSPod）
- [ ] QC 实名/手机绑定（`account.synology.cn`）对选路的影响

## 文档

- OKF 主文档：[docs/reference/nas-multi-domain-access.md](docs/reference/nas-multi-domain-access.md)
- Solutions：[docs/solutions/integration-issues/nas-multi-domain-access-openwrt-quickconnect.md](../docs/solutions/integration-issues/nas-multi-domain-access-openwrt-quickconnect.md)
- 办公室拓扑：[us_openai_api_proxy/docs/office-lan-access.md](../us_openai_api_proxy/docs/office-lan-access.md)

## API 代码

- `NAS_API/synology.py` — DSM Web API 封装（读 `.env` 的 `NAS_URL` / 凭证）
