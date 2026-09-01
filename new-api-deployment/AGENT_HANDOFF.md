# New API 部署项目 — 完整交接文档

> 最终更新: 2026-08-31
> 目标: 在本地 Windows 机器上部署 New API（大模型网关），实现 API Key 分发、多用户额度管控、用量统计、订阅自动重置
>
> **⚠️ 敏感信息**: 密码、Token、API Key 等已移入 `.secrets.env`，请勿提交到 Git

> **⚠️ 本地上/生产双环境**: 本文档主体描述**本地开发部署**（Docker Desktop + SQLite）。
> **生产环境已迁移到上海阿里云服务器**（`api.vilavi.cn`）：Docker Compose 4 服务（new-api / mysql / redis / dingtalk-oidc bridge），数据库为 **MySQL**（`new_api`），SQLite 仅本地开发用。生产服务器操作用 `ssh sh-erpnext-test`，容器管理见下文「九、钉钉 SSO 系统架构」的服管理系统。

---

## 一、系统现状总览

### 运行状态

| 项目 | 当前状态 |
|------|---------|
| Docker Desktop | v29.5.3, WSL2 后端, 安装在 D 盘 |
| New API 容器 | `new-api`，Up，自动重启，SQLite 模式 |
| 端口 | `localhost:3000` |
| 数据持久化 | `D:\docker\new-api\data\one-api.db` |

### Docker 镜像

| 项目 | 值 |
|------|-----|
| 运行时镜像名 | `calciumion/new-api:latest` |
| 镜像拉取源 | **DaoCloud 加速器** `docker.m.daocloud.io/calciumion/new-api:latest` |
| 镜像 digest | `bd30213d8088` |
| 镜像大小 | ~266MB |
| 为何用 DaoCloud | Docker Hub 直连 TLS 握手超时（国内网络限制）|
| 拉取方式 | `docker pull docker.m.daocloud.io/calciumion/new-api:latest` → `docker tag` 重命名 |

> ⚠️ 两个镜像 digest 相同（内容一致），只是拉取渠道不同。如需换源（如阿里云加速器），重新 pull + retag 即可。

### 账号体系

| 用户 | 角色 | 密码（见 `.secrets.env`）| 用途 |
|------|------|------------------------|------|
| `root` | RootUser (100) | `ADMIN_PASSWORD` | 管理员 |
| `limittest` | CommonUser (1) | — | 额度测试用户 |
| `newuser` | CommonUser (1) | `TEST_USER_PASSWORD` | 普通用户 |

### 渠道配置

| 名称 | 类型(代码) | 模型 | 上游地址 | API Key（见 `.secrets.env`）|
|------|-----------|------|---------|---------------------------|
| DeepSeek Test | DeepSeek (43) | `deepseek-v4-flash,deepseek-v4-pro` | `https://api.deepseek.com` | `DEEPSEEK_API_KEY` |

### 当前活跃令牌

见 `.secrets.env` 中 `ADMIN_TOKEN` 和 `TEST_USER_TOKEN`

### Web 后台

> http://localhost:3000 | 管理员: root / 密码见 `.secrets.env`

---

## 二、历史问题与解决方案（新对话快速接手）

### 问题 1：Git Bash 路径翻译导致 Docker 挂载错误
- **表现**: `-v /d/docker/new-api/data:/data` 被 MSYS 翻译为 `D:\Git\Git\data`
- **解决**: 用双斜杠 `//d/docker/new-api/data:/data` 阻止 MSYS 转换
- **或**: 设环境变量 `MSYS2_ARG_CONV_EXCL="*"` 后再执行 docker 命令

### 问题 2：New API 角色值跟 One API 不同
- 注册的用户默认 `role=1`（普通用户），无法访问管理 API
- `RoleRootUser = 100`，`RoleAdminUser = 10`，`RoleCommonUser = 1`
- **解决**: `UPDATE users SET role=100 WHERE id=1`

### 问题 3：管理 API 需要双重认证
- 所有管理 API 必须同时传: `Cookie: session=...` + `New-Api-User: 1`
- 缺少任意一个会返回 `Unauthorized`

### 问题 4：Token Key 不能含连字符
- 手动插入带 `-` 的 Key（如 `sk-test-token-123`）会被中间件截断
- **必须**用系统 `POST /api/token/` 生成的标准 Key（无连字符的随机字符串）

### 问题 5：ModelRatio 被误清空
- 曾因错误调用 PUT option API 导致 ModelRatio 变空字符串
- **恢复**: 从备份文件恢复，用 docker cp + readfile() 写回

### 问题 6：创建令牌（Token）API 始终归当前用户
- `POST /api/token/` 创建的 Token 永远属于当前登录用户
- 要给其他用户创建 Token，只能通过数据库直接 INSERT
- 插入后必须设 `unlimited_quota=1`（余额由订阅/用户额度控制）

### 问题 7：速率限制误伤管理 API
- 开启 `ModelRequestRateLimitEnabled` 后，所有 API（包括登录、管理）都被限流
- **重启容器** `docker restart new-api` 可重置计数器
- 但该功能目前有 Bug，推荐不用

### 问题 8：Python3 在 Git Bash 中路径问题
- Windows 下 Python 的 `python3` 命令找不到 `/tmp` 路径
- **解决**: 使用 Windows 绝对路径 `C:\Users\DEV01\AppData\Local\Temp\` 或直接写文件用 `python`（不带 3）

---

## 三、部署后初始化配置流程

容器启动后，首次访问 `http://localhost:3000` 会显示**系统初始化页面**（数据库检查 → 管理员账号 → 使用模式 → 完成初始化）。

### 方案 A：通过 API 完成初始化（推荐脚本方式）

```bash
# 1. 注册管理员（首次注册用户自动成为管理员，但 role=1 需修正）
curl -s -X POST http://localhost:3000/api/user/register \
  -H "Content-Type: application/json" \
  -d '{"username":"root","password":"<ADMIN_PASSWORD>","password2":"<ADMIN_PASSWORD>","email":"admin@local.dev","verification_code":""}'

# 2. 修正 role（New API 首次注册 role=1，需改为 100）
docker exec new-api sqlite3 /data/one-api.db \
  "UPDATE users SET role=100 WHERE id=1;"

# 3. 完成初始化（将 setup 状态从 false→true）
curl -s -X POST http://localhost:3000/api/setup \
  -H "Cookie: session=<SESS_VAL>" \
  -H "New-Api-User: 1" \
  -H "Content-Type: application/json" \
  -d '{}'

# 4. 验证
curl -s http://localhost:3000/api/status | grep '"setup"'
# → setup: true
```

### 方案 B：通过 Web 页面完成（可视化）

1. 浏览器访问 `http://localhost:3000`
2. 页面自动跳转到初始化向导
3. 依次配置：
   - **数据库检查** → SQLite 模式无需操作，直接下一步
   - **管理员账号** → 填写用户名 `root`、密码
   - **使用模式** → 选**多用户模式**（非自用模式）
   - **完成初始化** → 点击完成，自动跳转到登录页
4. 用刚创建的管理员账号登录
5. **关键**: 登录后进入 **设置 → 运营设置**，勾选**合规确认**，否则订阅功能不可用

> ⚠️ 方案 B 创建的管理员账号 role 是正确的（直接为 100），无需手动修正。

### 初始化后调整额度

```bash
# 方式一：后台页面操作
# 设置 → 运营设置 → 找到用户额度相关配置

# 方式二：API 充值
curl -s -X POST http://localhost:3000/api/user/manage \
  -H "Cookie: session=<SESS_VAL>" -H "New-Api-User: 1" \
  -H "Content-Type: application/json" \
  -d '{"id":<用户ID>,"action":"add_quota","mode":"add","value":500000}'

# 方式三：直接改数据库
MSYS2_ARG_CONV_EXCL="*" docker exec new-api sqlite3 /data/one-api.db \
  "UPDATE users SET quota=500000 WHERE id=2;"
```

### 分发 Token 给用户

```bash
# 1. 为当前用户创建令牌（系统自动生成无连字符的 Key）
curl -s -X POST http://localhost:3000/api/token/ \
  -H "Cookie: session=<SESS_VAL>" -H "New-Api-User: 1" \
  -H "Content-Type: application/json" \
  -d '{"name":"用户令牌名","remain_quota":0,"unlimited_quota":true}'

# 2. 查看生成的 Key（从数据库获取）
MSYS2_ARG_CONV_EXCL="*" docker exec new-api sqlite3 /data/one-api.db \
  "SELECT [key] FROM tokens WHERE name='用户令牌名';"

# 3. 将 Key 复制给用户在客户端配置
# 用户配置示例（Codex++ / Cherry Studio 等）：
#   Base URL: http://localhost:3000
#   API Key: <上面获取的 Key>
#   Model: deepseek-v4-flash

# 4. 如果 Token 需要归属其他用户（API 只能创建给当前用户）
#    通过数据库转移所有权
MSYS2_ARG_CONV_EXCL="*" docker exec new-api sqlite3 /data/one-api.db \
  "UPDATE tokens SET user_id=<目标用户ID> WHERE name='用户令牌名';"
```

> ⚠️ 令牌 Key 不能含连字符，必须用系统自动生成
> ⚠️ 用于订阅管控的 Token 必须设 `unlimited_quota=true`

---

## 三、订阅套餐系统（核心功能）

### 解决的问题
不用手动给用户充值，每个用户在时间窗口内获得固定额度，用完停，到时间自动重置。

### 已配置套餐

| ID | 名称 | 额度 | 重置周期 | 价格 | 状态 |
|----|------|------|---------|------|------|
| 2 | Monthly Basic | 500,000 | 每月 (monthly) | 免费 | ✅ 启用 |
| 7 | 5Min-0.10RMB | 6,849（≈ ¥0.10）| 每5分钟 (custom=300s) | 免费 | ✅ 启用 |

### 已分配用户

| 用户 | 套餐 |
|-----|------|
| root | Monthly Basic (ID=2) |
| root | 5Min-0.10RMB (ID=7) |
| limittest | 5Min-0.10RMB (ID=7) |

### 关键规则
1. **令牌必须设 `unlimited_quota=true`** — 额度由订阅（或用户余额）控制
2. 订阅 + 用户直接额度**双检查**，两者都需要足够
3. 预扣费额 ≈ 68 额度/次（取决于模型），调用结束后退返差额
4. 额度不够时返回 `insufficient_user_quota` 错误

### API 操作命令

```bash
# 创建套餐
POST /api/subscription/admin/plans
{"plan":{"title":"套餐名","total_amount":500000,
         "quota_reset_period":"custom","quota_reset_custom_seconds":300,
         "duration_unit":"month","duration_value":12,"price_amount":0}}

# 分配套餐给用户
POST /api/subscription/admin/users/{user_id}/subscriptions
{"plan_id": <PLAN_ID>}

# 查看用户订阅
GET /api/subscription/admin/users/{user_id}/subscriptions
```

### 重置周期有效值
- `"never"` — 不重置
- `"daily"` — 每天
- `"weekly"` — 每周
- `"monthly"` — 每月
- `"custom"` — 自定义（配合 `quota_reset_custom_seconds`）

### 开启前置条件
Web 后台 → 设置 → 运营设置 → 勾选**合规确认**（`payment_setting.compliance_confirmed`）

---

## 四、定价配置

> **⚠️ 2026-08-17 起 DeepSeek 实行峰谷分时计价，DeepSeek 的 ModelRatio 不再是静态值。**
> 生产环境由 `deepseek_time_pricing.py`（cron 准点触发）按北京时间在高峰/空闲两档间自动切换。
> 详见 [docs/solutions/tooling-decisions/new-api-deepseek-time-based-pricing-automation.md](../docs/solutions/tooling-decisions/new-api-deepseek-time-based-pricing-automation.md)。
> 本节以下静态值为历史参考（分时切换前的定价），不可作为当前生产值。

### DeepSeek V4 官方价格映射（分时计价前，历史参考）

**DeepSeek-V4-Flash:**
| 项目 | 官方价格 | New API 参数 |
|-----|---------|-------------|
| 输入（缓存未命中） | ¥1.00 / 1M tokens | ModelRatio = 0.068493 |
| 输出 | ¥2.00 / 1M tokens | CompletionRatio = 2 |
| 输入（缓存命中） | ¥0.02 / 1M tokens | CacheRatio = 0.02 |

**DeepSeek-V4-Pro:**
| 项目 | 官方价格 | New API 参数 |
|-----|---------|-------------|
| 输入（缓存未命中） | ¥3.00 / 1M tokens | ModelRatio = 0.205479 |
| 输出 | ¥6.00 / 1M tokens | CompletionRatio = 2 |
| 输入（缓存命中） | ¥0.025 / 1M tokens | CacheRatio = 0.008333 |

### 峰谷分时定价（当前生产生效）

DeepSeek 官方 2026-08-17 起：高峰（周一至周五 9-12/14-18 北京）为闲时的 2 倍。

| 模型 | 高峰 ModelRatio | 闲时 ModelRatio | CompletionRatio | CacheRatio |
|------|----------------|----------------|-----------------|-----------|
| deepseek-v4-flash | 0.205479 | 0.102740 | 3.0 | 0.033333 |
| deepseek-v4-flash-vision-exp | 0.205479 | 0.102740 | 3.0 | 0.033333 |
| deepseek-v4-pro | 0.616438 | 0.308219 | 3.0 | 0.033333 |

cron 切换：`0 9/12/14/18 * * 1-5` + `0 0 * * 0,6` 保险 + `*/30 * * * *` 兜底。脚本幂等，只 patch DeepSeek 三个模型。

### 计算公式
```
显示价格(¥/1M) = ModelRatio × 1,000,000 / 500,000 × 7.3
               = ModelRatio × 14.6
```

### 存放位置
- `ModelRatio` — options 表，key=`ModelRatio`
- `CompletionRatio` — options 表，key=`CompletionRatio`
- `CacheRatio` — options 表，key=`CacheRatio`

### 更新方式
**生产（分时自动）**: `/opt/new-api/deepseek_time_pricing.py`，cron 触发，直写 MySQL options 表（Redis 无缓存，即时生效）。
**手动**: 后台 设置 → 运营设置 → 模型定价；或直接 UPDATE MySQL options 表。

### 同步脚本
- `deepseek_time_pricing.py` — **分时定价自动切换**（当前生产核心脚本）
- `sync_pricing.py` — 修改顶部定价数字后运行（只 PRINT 计算结果，不写库；分时脚本内部已复用其公式）

---

## 五、价格相关配置项详解

| 配置项 | 作用 | 当前 deepseek 值（分时） |
|--------|------|-----------------|
| `ModelRatio` | 输入 token 基础单价 | flash=0.205479(高峰)/0.102740(闲时), pro=0.616438(高峰)/0.308219(闲时) |
| `CompletionRatio` | 输出 token 相对输入的倍率 | flash=3, pro=3 |
| `CacheRatio` | 缓存命中 token 相对输入的倍率 | flash=0.033333, pro=0.033333 |
| `CreateCacheRatio` | 创建缓存时的倍率 | （未设，用默认） |
| `ImageRatio` | 图片 token 倍率 | （无关） |
| `AudioRatio` | 音频 token 倍率 | （无关） |

**日志中缓存相关字段**: `cache_tokens`（命中量）、`cache_ratio`（缓存倍率）、`prompt_cache_hit_tokens`

---

## 六、数据库常用查询

> **生产（上海服务器）**: 数据库是 MySQL。**MySQL root 密码不硬编码在文档/脚本里**，存于服务器 `/opt/new-api/.secrets.env`（环境变量 `MYSQL_ROOT_PASSWORD`）。执行查询前先 `source /opt/new-api/.secrets.env`。
> **本地开发**: 用 sqlite3 `/data/one-api.db`（Git Bash 下加 `MSYS2_ARG_CONV_EXCL="*"` 前缀）。
> 以下给出生产 MySQL 写法。

```bash
# 生产 MySQL 查询模板（密码来自 .secrets.env，不经命令行）
source /opt/new-api/.secrets.env
MYSQL() { docker exec -e "MYSQL_PWD=$MYSQL_ROOT_PASSWORD" new-api-mysql \
            mysql -uroot --default-character-set=utf8mb4 new_api -N -B -e "$1"; }

# 用户
MYSQL "SELECT id, username, display_name, role, quota, used_quota FROM users;"

# 令牌（key 是保留字，用反引号包围）
MYSQL "SELECT id, user_id, name, \`key\`, remain_quota, unlimited_quota FROM tokens;"

# 订阅（含套餐名）
MYSQL "SELECT u.username, p.title, s.amount_total, s.amount_used,
              FROM_UNIXTIME(s.next_reset_time)
       FROM user_subscriptions s
       JOIN users u ON s.user_id=u.id
       JOIN subscription_plans p ON s.plan_id=p.id;"

# 日志（最近 10 条）
MYSQL "SELECT FROM_UNIXTIME(created_at), username, token_name,
              model_name, prompt_tokens, completion_tokens, quota
       FROM logs ORDER BY id DESC LIMIT 10;"

# 定价（ModelRatio JSON，含全模型）
MYSQL "SELECT value FROM options WHERE \`key\`='ModelRatio';"

# 更新定价（手动，一般由分时脚本自动做）
MYSQL "UPDATE options SET value='{\"...\":...}' WHERE \`key\`='ModelRatio';"
```

> **⚠️ 凭证安全**: 曾误将 MySQL root 密码与钉钉 APP_SECRET 硬编码进脚本并提交到公开仓库（PR 审查发现）。修复后脚本统一从 `/opt/new-api/.secrets.env` 读取（`MYSQL_ROOT_PASSWORD`、`DINGTALK_APP_KEY`、`DINGTALK_APP_SECRET`）。新脚本禁止硬编码凭证。

本地 SQLite 写法参考（历史，仅本地开发）：`docker exec new-api sqlite3 /data/one-api.db "..."`，Git Bash 需 `MSYS2_ARG_CONV_EXCL="*"` 前缀。

---

## 七、容器管理

```bash
# 重启（重置所有内存计数器）
docker restart new-api

# 查看日志
docker logs -f new-api

# 进入容器
MSYS2_ARG_CONV_EXCL="*" docker exec -it new-api bash

# 复制文件到容器
docker cp 本地文件路径 new-api:/tmp/
```

---

## 八、后续待办

- [x] **钉钉 SSO 登录**: 已通过 OIDC Bridge 实现，见 `new-api-dingtalk-oidc/`
- [x] **新用户自动配置**: 登录后自动绑 Daily-20RMB + 创建 Default 令牌（套餐现含 Daily-20/30/50RMB）
- [x] **离职自动封号**: Stream 模式实时 + 每日兜底检查
- [x] **Docker Compose 统一管理**: 4 个服务由一个 compose 文件管理
- [x] **DeepSeek 峰谷分时定价**: `deepseek_time_pricing.py` cron 自动切换（2026-08-28 部署）
- [ ] **修改默认密码**: 生产环境前务必修改默认密码
- [ ] **添加更多渠道**: 可按需添加 OpenAI、Claude、通义千问等

---

## 九、钉钉 SSO 系统架构

```
浏览器 → api.vilavi.cn (nginx)
  ├─ /          → new-api:3000
  ├─ /oidc/*    → new-api-dingtalk-oidc:8086 → 钉钉 OAuth API
  └─ /api/user/register → 403 (封堵密码注册)

cron 每分钟 → auto-bind: 绑套餐 + 建令牌
cron 每日 3 点 → offboarding-check: 离职兜底
cron 0 9/12/14/18 工作日 + 0 0 周末 + */30 → deepseek_time_pricing: 分时切价
Stream 实时 → user_leave_org → 即刻封号
```

### 钉钉应用配置

- 类型: 第三方企业应用
- 权限: Contact.User.Read + qyapi_get_member
- 回调: `https://api.vilavi.cn/oidc/callback`
- 事件订阅: Stream 模式, `user_leave_org`

### 服管理系统

```bash
cd /opt/new-api && docker compose ps    # 查看 4 个服务
cd /opt/new-api && docker compose restart bridge  # 重启桥接器
cd /opt/new-api-dingtalk-oidc && docker build -t new-api-dingtalk-oidc .  # 更新镜像
crontab -l  # 查看定时任务
```

---

## 十、参考链接

- GitHub 仓库: https://github.com/QuantumNous/new-api
- 官方文档: https://docs.newapi.pro/zh/docs
- Docker Hub: https://hub.docker.com/r/calciumion/new-api
- DeepSeek 定价: https://api-docs.deepseek.com/zh-cn/quick_start/pricing
- 本地脚本: `sync_pricing.py`, `deepseek_time_pricing.py`, `auto-bind-subscription.py`, `offboarding-check.py`
- 桥接器: `../new-api-dingtalk-oidc/main.py` + `stream_listener.py`
- 方案文档: `../docs/solutions/integration-issues/dingtalk-sso-new-api-oidc-bridge.md`
- 方案文档: `../docs/solutions/tooling-decisions/new-api-deepseek-time-based-pricing-automation.md`（分时定价）
- 本地敏感信息: `.secrets.env`（请勿提交）
