---
okf: v0.1
type: Reference
title: 非 git 部署目录且服务器副本领先分支：用 patch 叠加，不整文件覆盖
date: 2026-11-06
category: developer-experience
module: pb_orders
problem_type: developer_experience
component: tooling
severity: medium
applies_when:
  - "要热修 /opt/pb-orders 这类不是 git 仓库的部署副本"
  - "服务器上的源码比本地分支新（已有 API Key / 幂等 / 订单号等功能）"
  - "不想为了一个小功能把服务器已有改动回退"
tags: [deployment, patch, docker-compose, line-endings, gspread]
---

# 非 git 部署目录且服务器副本领先分支：用 patch 叠加，不整文件覆盖

## Context

`sh-erpnext-test:/opt/pb-orders` 是**代码副本**，不是 git 仓库；它的 `service.py` /
`repository.py` / `tasks.py` 比本地分支新（已经包含 API Key、幂等键、通途订单号占用登记）。
直接 scp 整文件覆盖，会把服务器上这些未合并的功能一起回退；但只改文档、不发代码，功能又上不了线。

## Guidance（本学习沉淀的做法）

1. **先比基线，再决定能不能整文件覆盖**：
   - 本地：`git show HEAD:<file> > /tmp/base/<file>`
   - 服务器：`scp` 下来后 `diff --strip-trailing-cr`
   - 只有“服务器 == 本地基线”的文件才允许整文件复制；有差异的文件必须走补丁。
2. **先备份**（沿用部署目录已有习惯）：

   ```bash
   cd /opt/pb-orders
   tar -czf pb_orders-code.bak-$(date +%Y%m%d-%H%M%S).tar.gz \
     --exclude=pb_orders/data --exclude=pb_orders/runtime pb_orders
   ```

3. **生成补丁并只叠加本次改动**：

   ```bash
   git diff HEAD -- <changed files> > /tmp/fix.patch
   ```

4. **处理行尾**：服务器文件常是 CRLF，本地 `git diff` 是 LF，`patch` 会报
   `Hunk #N FAILED ... (different line endings)`。先把目标文件归一为 LF：

   ```bash
   python3 -c 'import sys;p=sys.argv[1];b=open(p,"rb").read().replace(b"\r\n",b"\n");open(p,"wb").write(b)' <file>
   ```

5. **先 dry-run，再 apply；对 fuzz 的 hunk 逐段读结果**：

   ```bash
   patch -p1 --dry-run --forward < /tmp/fix.patch
   patch -p1 --forward < /tmp/fix.patch
   ```

   本次 `service.py` 有一个 hunk 以 `fuzz 2` 落位，必须人工确认插入点没有错位。
6. **新文件单独上传**，不要塞进补丁；目录不存在先建。
7. **两边一起重建**：PB 是 web + worker 两个容器，只重启 web 不会更新 worker：

   ```bash
   cd /opt/pb-orders/pb_orders
   docker compose build --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
   docker compose up -d
   ```

8. **验收四件套**：
   - `docker compose ps` 两容器 healthy；
   - 公网入口返回 303 跳 OIDC（未登录的正常表现）；
   - 在容器内跑一段纯逻辑测试（映射/冲突/拦截）；
   - 只读挂载的数据文件从容器内能读到新内容。

## Why This Matters

- 整文件覆盖 = 静默回退服务器功能；热修后才发现 API Key 或幂等失效，代价远大于打补丁。
- 行尾与 patch fuzz 是两个最容易被忽略的失败点：前者让所有 hunk 直接失败，后者让代码“能跑但插错位置”。
- 服务器数据目录是 `:ro` 挂载，**不能从容器里改**；要改宿主文件，容器会即时看到。

## When to Apply

- 部署目录不是 git 仓库（代码副本、tar 备份式部署）。
- 服务器副本领先本地分支，或含未合并功能。
- 需要小范围热修但不想重建整条发布链。

## Examples

本次实际顺序：备份 → 归一 LF → dry-run（service.py 有 fuzz）→ apply → 上传新模块/映射 → `py_compile` →
`docker compose build/up -d` → 容器内验证映射与冲突 → 公网 303 → 数据文件回读。

补充：如果同时要更新 Google Sheet 缓存，`gspread.open("名称")` 会走 Drive API，
在出口抖动时容易 `SSLError`；用已知 spreadsheet id 走 `open_by_key(id)` 并加 5-8 次重试更稳。

## Related

- `pb_orders/docs/reference/server-deployment-architecture.md` §11.4
- `pb_orders/docs/reference/pb-arc-foam-cylinder-sku-migration.md` §8
- `docs/solutions/developer-experience/gh-pr-edit-projects-classic-workaround.md`
- PR #336
