---
okf: v0.1
type: Reference
title: nas_mcp 部署 — 上海 EN 测试 VPS（Docker + nginx 反代）
description: 在 sh-erpnext-test 上以 Docker 跑 nas_mcp（只绑回环），复用现有 nginx conf.d 路径块对外；含端口选择、备份、nginx -t 校验与回滚
tags: [nas, mcp, deploy, nginx, docker, vps]
timestamp: 2026-09-21
---

# nas_mcp 部署（上海 EN 测试 VPS）

**目标**：把 `nas_mcp` 跑在 `sh-erpnext-test`（`api.vilavi.cn`），
由**现有 nginx** 反代成公网 HTTPS 路径，接给 ChatGPT。

## 0. 不干扰已有服务 —— 先确认基线

部署前先记录现状，部署后对比：

```bash
ssh sh-erpnext-test 'docker ps --format "{{.Names}}\t{{.Ports}}"'
```

**已知在跑**（2026-09-21 侦察）：

| 容器 | 端口 |
|---|---|
| `new-api` | `0.0.0.0:3000` |
| `new-api-dingtalk-oidc` | `127.0.0.1:8086` |
| `sellfox-api-proxy` | `127.0.0.1:8400` |
| `new-api-redis` / `new-api-mysql` | 内部 |

**→ 本模块选 `127.0.0.1:8402`**（8400 已被 sellfox 占用；8402 空闲）。
**主机侧端口不冲突、不占用 3000/8400/8086。**

## 1. 放置代码

```bash
ssh sh-erpnext-test
sudo mkdir -p /opt/nas-mcp && cd /opt/nas-mcp
# 从仓库取（或 git clone 后只取 nas_mcp/ 与 NAS_API/）
# 需要这两棵目录：nas_mcp/（服务） + NAS_API/（DSM 客户端，Dockerfile 里 COPY）
```

> ⚠️ Dockerfile 会 `COPY NAS_API/ ./NAS_API/` —— **必须一起带上**，否则起不来。

## 2. 凭证（**只在环境变量里**）

在 `/opt/nas-mcp/` 建 `.env`（`chmod 600`，**不要提交**）：

```ini
NAS_URL=https://fzh.myds.me:11024
NAS_USERNAME=<MCP 专用账号>
NAS_PASSWORD=<NAS 专用账号密码>
NAS_ALLOWED_ROOTS=/FZH共享文件夹,/产品信息
NAS_ROOT_FOLDER=/FZH共享文件夹
NAS_MCP_TOKEN=<自己生成一个长随机串>
```

> - **账号**：用为 MCP 单独建的受限账号（当前 `<MCP 专用账号>`）。
>   **真正的权限边界在 NAS 侧这个账号的文件夹权限上**；路径护栏是第二道。
> - **令牌**：`openssl rand -hex 32` 生成。这是 ChatGPT 连接器里要填的那个。

## 3. 构建与启动

```bash
cd /opt/nas-mcp
sudo docker build -f nas_mcp/Dockerfile -t nas-mcp:0.1.0 .

# --network host 让容器直接绑宿主 127.0.0.1:8402（与 sellfox-api-proxy 同一做法）
sudo docker run -d --name nas-mcp --restart unless-stopped \
  --network host \
  --env-file /opt/nas-mcp/.env \
  nas-mcp:0.1.0
```

**验证（宿主上）**：

```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:8402/mcp \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $NAS_MCP_TOKEN" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
# 期望 200
```

## 4. nginx 反代（**先备份、先 `nginx -t`**）

现状：所有 server 块在 `/etc/nginx/conf.d/new-api.conf`（`sites-enabled/` 为空）。
参照已有的 `/sellfox/admin` 写法加一段：

```nginx
    # nas-mcp（只读）
    location /nas/mcp {
        proxy_pass http://127.0.0.1:8402/mcp;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        # MCP 可能需要长连接/流式
        proxy_read_timeout 300s;
        proxy_buffering off;
    }
```

**操作顺序（务必照做）**：

```bash
sudo cp /etc/nginx/conf.d/new-api.conf /etc/nginx/conf.d/new-api.conf.bak-$(date +%Y%m%d)
# ...编辑加入上面的 location...
sudo nginx -t                      # ★ 必须先通过
sudo systemctl reload nginx        # ★ reload 不是 restart，不断已有连接
```

**回滚**：把 `.bak-*` 覆盖回去 → `nginx -t` → `reload`。

## 5. 从外部验证

```bash
# 从外部主机（本机也行）
curl -sS -o /dev/null -w '%{http_code}\n' -X POST https://api.vilavi.cn/nas/mcp \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $NAS_MCP_TOKEN" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
# 期望 200；不带令牌应 401
```

## 6. 接进 ChatGPT

建连接器：

| 字段 | 值 |
|---|---|
| 连接 | 服务器 URL |
| URL | `https://api.vilavi.cn/nas/mcp` |
| 身份验证 | **访问令牌 / API 密钥** |
| 标头方案 | **持有者 (Bearer)** |
| 令牌 | `NAS_MCP_TOKEN` 的值 |

> 该路线**已于 2026-09-21 实测可用**（日志见 `openai-mcp/1.0.0` 带 `Authorization` 头完成全流程）。

## 7. DSM 侧的两件事（别忘）

1. **给 `<MCP 专用账号>` 这个账号配好文件夹权限** —— 这是真正的权限边界。
   ⚠️ 注意 DSM 上各共享文件夹是**彼此独立的顶层目录**：给账号开了 `/产品信息` 之后，
   **还必须把 `/产品信息` 加进 `NAS_ALLOWED_ROOTS` 并重启容器**，否则仍会被路径护栏拒（实测踩过）。
2. **若 DSM 开了 Auto Block**：把 VPS 出口 IP（`sh-erpnext-test` 的 EIP，数值在该机取）加白名单，否则几次失败就被封
3. **账号不要开 2FA** —— DSM API 不支持 2FA，开了就连不上

## 已知风险

| 风险 | 说明 |
|---|---|
| DSM 会话过期 | 客户端会重新登录；若频繁报错先看是不是会话 |
| 出口 IP 变动 | 该机出口是 EIP；若换 IP 要同步 DSM 白名单 |
| 速度 | 瓶颈是**办公室上行带宽**，不是 VPS。工具只返回元数据/小文本，**不要让它搬大文件** |
