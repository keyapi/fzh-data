# New API 快速上手指南

> 新对话接手用：最简命令集

---

## 1. 验证环境

```bash
docker --version
docker ps --filter name=new-api
curl -s http://localhost:3000/api/status | python -c "import sys,json; d=json.load(sys.stdin)['data']; print(f'v{d[\"version\"]} setup={d[\"setup\"]}')"
```

## 2. 管理 API 认证

```bash
# 登录获取 session cookie
curl -s -c /tmp/na-cookies.txt -b /tmp/na-cookies.txt \
  -X POST http://localhost:3000/api/user/login \
  -H "Content-Type: application/json" \
  -d '{"username":"root","password":"admin123456"}' > /dev/null

# 提取 session 值
SESS_VAL=$(grep session /tmp/na-cookies.txt | awk '{print $NF}')
```

> 所有管理 API 请求必须同时携带:
> ```bash
> -H "Cookie: session=$SESS_VAL"
> -H "New-Api-User: 1"
> ```

## 3. 常用管理操作

```bash
# 管理员认证头
AUTH="-H \"Cookie: session=$SESS_VAL\" -H \"New-Api-User: 1\""

# 查看渠道
eval curl -s "http://localhost:3000/api/channel/?p=1&page_size=10" $AUTH

# 查看用户
eval curl -s "http://localhost:3000/api/user/?p=1&page_size=10" $AUTH

# 给用户充值
eval curl -s -X POST http://localhost:3000/api/user/manage $AUTH \
  -H "Content-Type: application/json" \
  -d '{"id":1,"action":"add_quota","mode":"add","value":10000000}'

# 创建令牌
eval curl -s -X POST http://localhost:3000/api/token/ $AUTH \
  -H "Content-Type: application/json" \
  -d '{"name":"MyToken","remain_quota":500000,"unlimited_quota":false}'
```

## 4. API 网关测试

```bash
# 使用管理员令牌
curl -s http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer HiaKpzR410JQiMh73YwlYpgjGrE66vXjgR1dECgl0A8KPznC" \
  -d '{"model":"deepseek-v4-flash","messages":[{"role":"user","content":"hi"}],"stream":false,"max_tokens":10}'
```

## 5. 数据库查询

```bash
# 查询用户
MSYS2_ARG_CONV_EXCL="*" docker exec new-api sqlite3 /data/one-api.db "SELECT id, username, role, quota, status FROM users;"

# 查询令牌（注意 key 是保留字，要用 [] 包围）
MSYS2_ARG_CONV_EXCL="*" docker exec new-api sqlite3 /data/one-api.db "SELECT id, user_id, name, [key], remain_quota, used_quota FROM tokens;"

# 查询渠道
MSYS2_ARG_CONV_EXCL="*" docker exec new-api sqlite3 /data/one-api.db "SELECT id, name, type, models, base_url FROM channels;"

# 查询日志
MSYS2_ARG_CONV_EXCL="*" docker exec new-api sqlite3 /data/one-api.db "SELECT created_at, username, token_name, model_name, prompt_tokens, completion_tokens FROM logs ORDER BY id DESC LIMIT 10;"
```

## 6. 订阅套餐管理

```bash
# 查看所有套餐
curl -s "http://localhost:3000/api/subscription/admin/plans" \
  -H "Cookie: session=\$SESS_VAL" -H "New-Api-User: 1"

# 创建套餐（月度重置）
curl -s -X POST "http://localhost:3000/api/subscription/admin/plans" \
  -H "Cookie: session=\$SESS_VAL" -H "New-Api-User: 1" \
  -H "Content-Type: application/json" \
  -d '{"plan":{"title":"套餐名","total_amount":500000,"quota_reset_period":"monthly","duration_unit":"month","duration_value":1,"price_amount":0}}'

# 分配套餐给用户
curl -s -X POST "http://localhost:3000/api/subscription/admin/users/{user_id}/subscriptions" \
  -H "Cookie: session=\$SESS_VAL" -H "New-Api-User: 1" \
  -H "Content-Type: application/json" \
  -d '{"plan_id":2}'

# 查看用户订阅状态
curl -s "http://localhost:3000/api/subscription/admin/users/{user_id}/subscriptions" \
  -H "Cookie: session=\$SESS_VAL" -H "New-Api-User: 1"
```

> ⚠️ 令牌必须设 `unlimited_quota=true`，实际额度由订阅系统控制

## 7. 定价查询与更新

```bash
# 查看当前 ModelRatio（deepseek 相关）
MSYS2_ARG_CONV_EXCL="*" docker exec new-api sqlite3 /data/one-api.db \
  "SELECT json_extract(value, '$.deepseek-v4-flash'), json_extract(value, '$.deepseek-v4-pro')
   FROM options WHERE key='ModelRatio';"

# 查看 CompletionRatio
MSYS2_ARG_CONV_EXCL="*" docker exec new-api sqlite3 /data/one-api.db \
  "SELECT json_extract(value, '$.deepseek-v4-flash'), json_extract(value, '$.deepseek-v4-pro')
   FROM options WHERE key='CompletionRatio';"

# 查看 CacheRatio
MSYS2_ARG_CONV_EXCL="*" docker exec new-api sqlite3 /data/one-api.db \
  "SELECT json_extract(value, '$.deepseek-v4-flash'), json_extract(value, '$.deepseek-v4-pro')
   FROM options WHERE key='CacheRatio';"

# 更新定价（复制 JSON 文件到容器后执行）
docker cp 本地文件路径 new-api:/tmp/
MSYS2_ARG_CONV_EXCL="*" docker exec new-api sqlite3 /data/one-api.db \
  "UPDATE options SET value=readfile('/tmp/filename.json') WHERE key='ConfigKey';"
docker restart new-api
```

定价换算公式: `显示价格(¥/1M) = ModelRatio × 1,000,000 / 500,000 × 7.3`

## 8. 创建用户+令牌完整流程（新用户接入步骤）

```bash
# 1. 登录
curl -s -c /tmp/cookies.txt -X POST http://localhost:3000/api/user/login \
  -H "Content-Type: application/json" \
  -d '{"username":"root","password":"admin123456"}'
SESS=$(grep session /tmp/cookies.txt | awk '{print $NF}')
AUTH="-H \"Cookie: session=$SESS\" -H \"New-Api-User: 1\""

# 2. 创建用户
curl -s -X POST http://localhost:3000/api/user/ $AUTH \
  -H "Content-Type: application/json" \
  -d '{"username":"新用户名","password":"密码123456","group":"default","quota":0}'

# 3. 为用户充值（如不使用订阅模式）
curl -s -X POST http://localhost:3000/api/user/manage $AUTH \
  -H "Content-Type: application/json" \
  -d '{"id":用户ID,"action":"add_quota","mode":"add","value":500000}'

# 4. 创建令牌（⚠️ 只能用当前登录用户，不能指定其他用户）
curl -s -X POST http://localhost:3000/api/token/ $AUTH \
  -H "Content-Type: application/json" \
  -d '{"name":"用户令牌名","remain_quota":0,"unlimited_quota":true}'

# 5. 分配订阅套餐（可选，替代手动充值）
curl -s -X POST http://localhost:3000/api/subscription/admin/users/用户ID/subscriptions $AUTH \
  -H "Content-Type: application/json" \
  -d '{"plan_id":7}'
```

> ⚠️ 令牌 Key 不能含连字符，需用系统自动生成
> ⚠️ 如果 Token 用于订阅管控，必须设 `unlimited_quota=true`

## 9. 关键配置信息

| 项目 | 值 |
|------|-----|
| 管理后台 | http://localhost:3000 |
| 管理员 | root / admin123456 |
| DeepSeek Key | sk-8832c70267b14492a7e5afdbf8e3f953 |
| 数据目录 | D:\docker\new-api\data\ |
| 日志目录 | D:\docker\new-api\logs\ |
| 数据库文件 | D:\docker\new-api\data\one-api.db |
| 有效 Admin Token | HiaKpzR410JQiMh73YwlYpgjGrE66vXjgR1dECgl0A8KPznC |
| 测试用户 Token | BTJlbnLTgvsSJbQvPuWv3ruKCYgdw4AJkLlUWfbotniXdvux |
| 定价同步脚本 | D:\Claude Demo\fzh-data\new-api-deployment\sync_pricing.py |
