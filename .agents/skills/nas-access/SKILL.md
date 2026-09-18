---
name: nas-access
description: |
  群晖 NAS 多域名访问、QuickConnect 直连/中继、OpenWrt DNS 劫持、DSM 第二张证书与反代。
  触发词：NAS、群晖、QuickConnect、myds.me、daneey、vilavi.cn、mxdeals、
  fangzhouhui、cn4、11024、DSM 证书、反代、OpenWrt 劫持、深圳 NAS。
---

# NAS 多域名访问

## 何时加载

- 用户问 NAS / 群晖 / QuickConnect / DSM 外网访问
- 证书警告、`fzh.myds.me`、自定义域名、`cn4` 中继
- OpenWrt 劫持、ACME、Cloudflare/阿里云 DDNS

## 必读

1. [NAS_API/AGENT_HANDOFF.md](../../NAS_API/AGENT_HANDOFF.md) — 速查表与铁律
2. [NAS_API/docs/reference/nas-multi-domain-access.md](../../NAS_API/docs/reference/nas-multi-domain-access.md) — 完整参考
3. [docs/solutions/integration-issues/nas-multi-domain-access-openwrt-quickconnect.md](../../docs/solutions/integration-issues/nas-multi-domain-access-openwrt-quickconnect.md) — 问题/解法记录

## 铁律（30 秒）

1. **不要**改 DSM 默认证书（`RmB4St` / `fzh.myds.me`）的「桌面服务」绑定。
2. 新域名：OpenWrt ACME → DSM import 第二张证 → 反代 443+11024 → 只绑 ReverseProxy。
3. 反代 `Host: fzh.myds.me`。
4. Cloudflare `nas.vilavi.cn` 必须**灰云**。
5. 外网 URL 默认带 `:11024`（443 公网未通）。
6. 统一入口仍是 `fangzhouhui.quickconnect.cn`（用户政策）；自定义域名是补充。
7. daneey/vilavi **不要**写进 DSM「外部访问→DDNS」；QC **不会**自动跳它们。
8. **勿删** `fzh.myds.me`（默认证 + QC 登记）；无 mxdeals 优先选项。

## 凭证

- `NAS_API/.env`（gitignore）：`NAS_URL`、`NAS_SSH_*`
- OpenWrt SSH：`~/.ssh/id_rsa_openwrt` → `root@192.168.100.1`
- Cloudflare token：在 OpenWrt UCI / `NAS_API/.env` 的 `CF_API_TOKEN`（勿提交 git）

## 未决

- 深圳 `myds.me` 解析
- 台式机 Chrome QC → cn4（安全 DNS）
- 公网 443
