# New API 部署项目 — 完整交接文档

> 最终更新: 2026-06-22
> 目标: 在本地 Windows 机器上部署 New API（大模型网关），实现 API Key 分发、多用户额度管控、用量统计、订阅自动重置
>
> **⚠️ 敏感信息**: 密码、Token、API Key 等已移入 `.secrets.env`，请勿提交到 Git

---

## 一、系统现状总览

### 运行状态

| 项目 | 当前状态 |
|------|---------|
| Docker Desktop | v29.5.3, WSL2 后端, 安装在 D 盘 |
| New API 容器 | `new-api`，Up，自动重启，SQLite 模式 |
| 端口 | `localhost:3000` |
| 数据持久化 | `D:\docker\new-api\data\one-api.db` |

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

### DeepSeek V4 官方价格映射

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
**后台**: 设置 → 运营设置 → 模型定价 / 缓存读取比例 / 缓存创建比例
**数据库直接更新**: 用 `docker cp` 传入 JSON 文件 + `readfile()` 写回

### 同步脚本
`sync_pricing.py` — 修改顶部定价数字后运行

---

## 五、价格相关配置项详解

| 配置项 | 作用 | 当前 deepseek 值 |
|--------|------|-----------------|
| `ModelRatio` | 输入 token 基础单价 | flash=0.068493, pro=0.205479 |
| `CompletionRatio` | 输出 token 相对输入的倍率 | flash=2, pro=2 |
| `CacheRatio` | 缓存命中 token 相对输入的倍率 | flash=0.02, pro=0.008333 |
| `CreateCacheRatio` | 创建缓存时的倍率 | （未设，用默认） |
| `ImageRatio` | 图片 token 倍率 | （无关） |
| `AudioRatio` | 音频 token 倍率 | （无关） |

**日志中缓存相关字段**: `cache_tokens`（命中量）、`cache_ratio`（缓存倍率）、`prompt_cache_hit_tokens`

---

## 六、数据库常用查询

> 注意：Git Bash 下需加 `MSYS2_ARG_CONV_EXCL="*"` 前缀

```bash
# 用户
MSYS2_ARG_CONV_EXCL="*" docker exec new-api sqlite3 /data/one-api.db \
  "SELECT id, username, role, quota, used_quota FROM users;"

# 令牌（key 是保留字，要用 [] 包围）
MSYS2_ARG_CONV_EXCL="*" docker exec new-api sqlite3 /data/one-api.db \
  "SELECT id, user_id, name, [key], remain_quota, unlimited_quota FROM tokens;"

# 订阅
MSYS2_ARG_CONV_EXCL="*" docker exec new-api sqlite3 -separator " | " /data/one-api.db \
  "SELECT u.username, p.title, s.amount_total, s.amount_used,
          datetime(s.next_reset_time,'unixepoch')
   FROM user_subscriptions s
   JOIN users u ON s.user_id=u.id
   JOIN subscription_plans p ON s.plan_id=p.id;"

# 日志
MSYS2_ARG_CONV_EXCL="*" docker exec new-api sqlite3 -separator " | " /data/one-api.db \
  "SELECT datetime(created_at,'unixepoch'), username, token_name,
          model_name, prompt_tokens, completion_tokens, quota
   FROM logs ORDER BY id DESC LIMIT 10;"

# 定价
MSYS2_ARG_CONV_EXCL="*" docker exec new-api sqlite3 /data/one-api.db \
  "SELECT json_extract(value, '$.deepseek-v4-flash'),
          json_extract(value, '$.deepseek-v4-pro')
   FROM options WHERE key='ModelRatio';"

# 写回 JSON 文件到配置（文件需提前 docker cp 到容器内 /tmp/）
MSYS2_ARG_CONV_EXCL="*" docker exec new-api sqlite3 /data/one-api.db \
  "UPDATE options SET value=readfile('/tmp/filename.json') WHERE key='ConfigKey';"
```

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

- [ ] **修改默认密码**: 生产环境前务必修改默认密码
- [ ] **添加更多渠道**: 可按需添加 OpenAI、Claude、通义千问等
- [ ] **配置 Redis**: 提升缓存和性能（`-e REDIS_CONN_STRING=...`）
- [ ] **迁移 PostgreSQL**: SQLite 适合测试，生产建议用 PostgreSQL
- [ ] **配置 HTTPS**: 如果对外提供服务，需要反向代理 + SSL
- [ ] **PR #5006**: 渠道亲和力支持到 Key 级别（Open，未合并）
- [ ] **Issue #4963**: 缓存命中率统计看板（未实现，可考虑自己开发）

---

## 九、参考链接

- GitHub 仓库: https://github.com/QuantumNous/new-api
- 官方文档: https://docs.newapi.pro/zh/docs
- Docker Hub: https://hub.docker.com/r/calciumion/new-api
- DeepSeek 定价: https://api-docs.deepseek.com/zh-cn/quick_start/pricing
- 本地脚本: `sync_pricing.py`
- 本地敏感信息: `.secrets.env`（请勿提交）
