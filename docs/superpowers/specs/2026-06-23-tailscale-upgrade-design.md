# Tailscale OpenWrt 升级设计: v1.32.3 → v1.98.4

## 背景

Tailscale Admin Console 安全告警: "Security update available — update to 1.98.4"。
当前 OpenWrt R68S 运行 Tailscale v1.32.3 (2023 年版本)，存在已知安全漏洞。

## 约束

- 升级中断窗口可接受 (约 30 秒)
- 排查修复优先于立即回滚 (但保留回滚能力)
- OpenWrt R22.11.13, kernel 4.19.245, arm64, iptables (firewall3)
- OpenClash 翻墙不能受影响
- 当前手动 MASQUERADE 规则需验证兼容性

## 方案：手动静态二进制替换

`tailscale update` 命令在 v1.32.3 不可用 (需 v1.50+)，唯一方案是下载官方静态二进制手动替换。

### 下载源

`https://pkgs.tailscale.com/stable/tailscale_1.98.4_arm64.tgz`

### 升级步骤

1. 备份当前二进制 + 防火墙配置 + iptables 快照
2. 下载并解压 1.98.4 arm64 tarball
3. 停 tailscaled, 替换 /usr/sbin/tailscale 和 tailscaled
4. 启动, 带着 `--accept-dns=false --accept-routes` 重新 up
5. 检查新版 iptables 规则 (ts-forward, ts-postrouting)
6. 验证我们的 MASQUERADE 规则仍在 POSTROUTING 第一位
7. 手机测试: new-api + 翻墙

### 回滚

替换回备份的旧二进制, 重启 tailscaled, 恢复手工 MASQUERADE 规则。

## 风险

| 风险 | 缓解 |
|------|------|
| 新版 iptables 与手动规则冲突 | 升级后验证, 必要时调整 |
| init 脚本兼容性 | 新版仍是 shell init 脚本, 兼容 |
| DNS 覆写 (1.80+ 已知问题) | `--accept-dns=false` 已缓解 |
| opkg 日后覆盖 | 锁定 opkg 或接受 |

## 验证清单

- [ ] `tailscale version` → 1.98.4
- [ ] `iptables -t nat -L POSTROUTING` 有 MASQUERADE on tailscale0
- [ ] `tailscale status` 所有节点可见
- [ ] 手机 `http://100.119.28.72:3000/` 可访问
- [ ] 手机翻墙正常
