---
okf: v0.1
type: Solution
title: EN 服务器 git push 报 Permission denied (publickey) —— 密钥没问题，是 GitHub SSH 链路间歇性阻断
description: 测试机、生产机、本地 Windows 访问 GitHub SSH 都间歇失败（22/443 端口、亚洲与美国节点均复现），而密钥与账户登记逐字节一致、无部署密钥冲突、主机密钥真实；HTTPS 路径稳定。含三步判定法与一键 HTTPS 回退脚本，避免把链路抖动误判成密钥丢失而反复换 key。
module: EN_API
date: 2026-11-05
last_updated: 2026-11-05
category: integration-issues
problem_type: integration_issue
component: infrastructure
severity: low
symptoms:
  - "git push 报 git@github.com: Permission denied (publickey)"
  - "同一把钥匙有时能通（ssh -T 返回 Hi <user>!），有时被拒"
  - "换 443 端口 / 换 GitHub 节点 IP 仍然间歇失败"
  - "本地 Windows 用另一把钥匙同样间歇失败"
root_cause: network
resolution_type: workaround
tags: [git, ssh, github, permission-denied, network, key_test, erpnext, https-fallback]
related_components: [key_test]
---

# EN 服务器 git push 报 Permission denied (publickey)

## Problem

2026-11-04 在 EN 测试机 `~/frappe-bench/apps/key_test` 上 `git push` 失败：

```
git@github.com: Permission denied (publickey).
fatal: Could not read from remote repository.
```

`main` 领先 `origin/main` 2 个提交，但推不上去。当晚同事重试即推送成功
（`main == origin/main == 1dadfeb`）。

## 排查结论

| 检查项 | 结果 |
|--------|------|
| 服务器私钥 ↔ 公钥 | `ssh-keygen -y` 派生结果与 `.pub` 完全一致 |
| 该公钥是否登记在 GitHub 账户 | **是**，与 GitHub API 返回的公钥串**逐字节一致** |
| 部署密钥冲突 | 无（keyapi 下 9 个仓库的 deploy key 全为 0） |
| GitHub 主机密钥 | 真实（`SHA256:+DiY3...`，非中间人） |
| SSH 认证成功率 | 22 端口 5/10、443 端口 3/10、换美国节点仍 1 晚后 8/8 —— **时通时不通** |
| 本地 Windows（**另一把**钥匙） | 同样间歇失败 ⇒ 与单机、单钥匙无关 |
| HTTPS 路径 | **5/5 全通**，`git push --dry-run` 成功 |

## Root cause

大陆出口访问 GitHub SSH 的**链路抖动/间歇阻断**，不是密钥或 git 配置故障。
表现很迷惑：TCP 能连、主机密钥是 GitHub 真的、但认证阶段被拒。
过一段时间（本次约数小时）会自行恢复。

## 判定法（下次照做，别急着换 key）

1. `ssh -T git@github.com` 连试 **3 次**
   —— 只要任意一次返回 `Hi <user>! You've successfully authenticated`，
   说明密钥完全正常，**不要动 `~/.ssh`、不要重新登记 key**。
2. `git ls-remote origin HEAD` 重试；通了直接 `git push`。
3. 仍不通再用 HTTPS 回退（见下），推完自动切回 SSH。

> 反例：看到 `Permission denied (publickey)` 就判定"密钥丢了/被删了"。
> 本次证据显示密钥在账户上是好的 —— 结论应为「链路问题 + 重试」。

## Resolution

### A. 直接重试

多数情况隔几分钟重试即可。`git push` 是单次连接，不必改任何配置。

### B. HTTPS 回退（一键，自动恢复 remote）

脚本：`EN_API/git_push_https.sh`（测试机上部署为 `/home/frappe/git-push-https.sh`）

```bash
# 在测试机上，任意目录
~/git-push-https.sh ~/frappe-bench/apps/key_test
# 先试跑（不改远端）：
~/git-push-https.sh ~/frappe-bench/apps/key_test --dry-run
```

脚本做的事：把 `origin` 从 `git@github.com:...` 临时换成 `https://github.com/...` →
`git push` → **退出时用 `trap` 自动换回 SSH 地址**。
手动版等价命令：

```bash
cd ~/frappe-bench/apps/key_test
git remote set-url origin https://github.com/keyapi/key_test.git
git push
git remote set-url origin git@github.com:keyapi/key_test.git
```

## 注意

- **测试机** `~/.git-credentials` 里有可用的 `keyapi` PAT（`ghp_`，scope `repo`，无过期），
  所以 HTTPS 回退开箱可用。
- **生产机没有存 token**，要用 HTTPS 必须先放一份凭证（单独决策，别顺手做）。
- 本文档只写 SSH 别名，**不写 EN 服务器 IP、不写任何 token/密钥**。
- 其他 keyapi 仓库（`key_oms` / `vilavi_pim` / `work_order_task` / `delivery_plan`）
  同样是 SSH 远端，会出同样的问题；本次只处理 key_test。

## 相关

- [`../../../EN_API/docs/reference/en-server-access.md`](../../../EN_API/docs/reference/en-server-access.md)
  —— 服务器访问入口与常见坑（本文已作为第 4 条挂入）
- [`../../../docs/solutions/workflow-issues/key-test-login-hook-and-prod-test-divergence.md`](../workflow-issues/key-test-login-hook-and-prod-test-divergence.md)
  —— key_test 的生产/测试分支割裂与发布链路
