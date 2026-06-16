# New API 部署项目 — 交接文档

> 生成时间: 2026-06-16
> 目标: 在本地 Windows 机器上部署 New API（大模型网关），实现 API Key 分发、多用户管控、用量统计

---

## 一、项目目标

1. 在本地 Windows 11 Home 机器上安装 Docker Desktop
2. 使用 Docker 部署 [New API](https://github.com/QuantumNous/new-api)（原 One API 的二次开发版）
3. 配置上游 AI 模型提供商渠道（DeepSeek）
4. 创建多用户、多令牌，实现 API Key 分发与额度管控
5. 验证 API 网关转发、配额扣减、日志记录功能

---

## 二、最终成果

### 系统运行状态

| 项目 | 当前状态 |
|------|---------|
| Docker Desktop | v29.5.3, WSL2 后端, 安装在 D 盘 |
| New API 容器 | `new-api`，Up，自动重启，SQLite 模式 |
| 端口 | `localhost:3000` |
| 数据持久化 | `D:\docker\new-api\data\one-api.db` (572KB) |

### 账号体系

| 用户 | 角色 | 密码 | 配额 |
|------|------|------|------|
| `root` | RootUser (100) | `admin123456` | 9999998 |
| `testuser` | CommonUser (1) | `test123456` | 未充值 |

### 渠道

| 名称 | 类型 | 模型 | 上游地址 |
|------|------|------|---------|
| DeepSeek Test | DeepSeek (43) | `deepseek-chat` | `https://api.deepseek.com` |

### API 令牌

| Token Key | 所属用户 | 额度 | 状态 |
|-----------|---------|------|------|
| `m8EiGG23cZQ0AID2lhYFM3gE7VmwBBq43WeU4wavDWliHGtG` | root | 499999/500000 | ✅ 已验证通过 |

### Web 管理后台

> 访问地址: http://localhost:3000
> 管理员: root / admin123456

---

## 三、部署全过程记录

### Stage 1: Docker Desktop 安装

**目标**: 在 Windows 11 Home 上安装 Docker Desktop（WSL2 后端）

**发现**:
- 机器已有 WSL2 + Ubuntu 发行版（Version 2）
- Docker 和 Docker Compose 均未安装

**执行步骤**:
1. 从 Docker 官网下载 `Docker Desktop Installer.exe`（v4.78.0）
2. 用户选择安装到 D 盘（非默认 C 盘）
3. 以管理员身份运行: `"D:\docker-desktop-installer.exe" install --accept-license --backend=wsl-2`
4. 安装完成，重启电脑

**验证**: `docker --version` → Docker version 29.5.3 ✅

### Stage 2: 部署 New API 容器

**目标**: 拉取 New API 镜像，以 SQLite 模式运行容器，数据持久化到 D 盘

**遇到问题及解决**:

1. **问题**: `docker pull calciumion/new-api:latest` TLS 握手超时
   - **原因**: 国内网络访问 Docker Hub 不稳定
   - **解决**: 使用 DaoCloud 镜像 `docker pull docker.m.daocloud.io/calciumion/new-api:latest`

2. **问题**: Git Bash 路径翻译导致 bind mount 错误
   - **表现**: `-v /d/docker/new-api/data:/data` 被 MSYS 翻译为 `D:\Git\Git\data`
   - **解决**: 使用 `//d/docker/new-api/data`（双斜杠开头）阻止 MSYS 路径转换

3. **最终启动命令**:
   ```bash
   docker run -d --restart always \
     --name new-api \
     -p 3000:3000 \
     -e TZ=Asia/Shanghai \
     -v "//d/docker/new-api/data":/data \
     calciumion/new-api:latest
   ```

**数据文件**: `D:\docker\new-api\data\one-api.db`

### Stage 3: 初始化配置

**目标**: 创建管理员账号、设置权限、配置渠道

**遇到问题及解决**:

1. **问题**: 注册接口密码最短8位，`123456` 太短
   - **解决**: 使用 `admin123456`

2. **问题**: `role=1` 的用户无法访问管理 API（"insufficient privileges"）
   - **原因**: New API 角色定义与原始 One API **不同**
     - `RoleRootUser = 100`
     - `RoleAdminUser = 10`
     - `RoleCommonUser = 1`
     - `RoleGuestUser = 0`
   - **解决**: 通过 sqlite3 直接更新 `UPDATE users SET role=100 WHERE id=1`

3. **问题**: 管理 API 需要同时传 Cookie + `New-Api-User` 头
   - **原因**: 中间件 `authHelper` 对会话身份和 Header 做交叉校验
   - **解决**: 每次 API 请求同时携带:
     ```bash
     -H "Cookie: session=..." \
     -H "New-Api-User: 1"
     ```

4. **问题**: `/api/channel/` POST 请求 panic (nil pointer dereference)
   - **原因**: 请求体缺少 `{"mode":"single","channel":{...}}` 包装层级
   - **正确格式**:
     ```json
     {
       "mode": "single",
       "channel": {
         "type": 43,
         "key": "sk-xxx",
         "name": "DeepSeek",
         "models": "deepseek-chat",
         "base_url": "https://api.deepseek.com"
       }
     }
     ```

5. **问题**: 手动插入数据库的 Token Key 无效
   - **原因**: New API 不验证包含连字符 `-` 的密钥；Token 中间件会截取第一个 `-` 前的片段
   - **解决**: 使用系统 `POST /api/token/` 生成的标准密钥（无连字符的随机字符串）

### Stage 4: 功能测试

**目标**: 验证 API 网关连通性和配额管控

**测试结果**:

1. **API 调用**: `POST /v1/chat/completions` → DeepSeek 正常响应 `"Hello!"` ✅
2. **配额扣减**: 500000 → 499999，系统追踪准确 ✅
3. **Web UI**: HTTP 200，可正常访问后台 ✅
4. **数据持久化**: `one-api.db` 在 D 盘，重启后数据保留 ✅

---

## 四、关键技术要点

### 角色体系（New API vs One API 区别）

| 角色 | New API | One API (原版) |
|------|---------|---------------|
| RootUser | 100 | 1 |
| AdminUser | 10 | 10 |
| CommonUser | 1 | 100 |

### 认证机制

- 管理员 API: Session Cookie + `New-Api-User` 头（用户 ID）
- API 网关: `Authorization: Bearer <token>`（令牌由系统生成）

### 令牌格式

- ✅ 系统生成: `m8EiGG23cZQ0AID2lhYFM3gE7VmwBBq43WeU4wavDWliHGtG`（无连字符）
- ❌ 手动构造: `sk-test-user-token-2024`（含连字符，会被截断）

### 容器管理

```bash
# 查看日志
docker logs -f new-api

# 进入容器
MSYS2_ARG_CONV_EXCL="*" docker exec -it new-api bash

# 查询数据库
MSYS2_ARG_CONV_EXCL="*" docker exec new-api sqlite3 /data/one-api.db "SELECT * FROM users;"

# 重启
docker restart new-api
```

---

## 五、后续待办

- [ ] **修改默认密码**: 生产环境前务必修改 `root/admin123456`
- [ ] **添加更多渠道**: 可按需添加 OpenAI、Claude、通义千问等
- [ ] **配置 Redis**: 提升缓存和性能（可选）
- [ ] **迁移 PostgreSQL**: SQLite 适合测试，生产建议用 PostgreSQL（参考 `docker-compose.yml`）
- [ ] **配置 HTTPS**: 如果对外提供服务，需要反向代理 + SSL
- [ ] **创建更多测试用户**: 验证多用户额度隔离
- [ ] **探索数据看板**: 用量统计、成本分析功能

---

## 六、参考链接

- GitHub 仓库: https://github.com/QuantumNous/new-api
- 官方文档: https://docs.newapi.pro/zh/docs
- Docker Hub: https://hub.docker.com/r/calciumion/new-api
