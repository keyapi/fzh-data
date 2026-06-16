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
  -H "Authorization: Bearer m8EiGG23cZQ0AID2lhYFM3gE7VmwBBq43WeU4wavDWliHGtG" \
  -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"hi"}],"stream":false,"max_tokens":10}'
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

## 6. 关键配置信息

| 项目 | 值 |
|------|-----|
| 管理后台 | http://localhost:3000 |
| 管理员 | root / admin123456 |
| DeepSeek Key | sk-8832c70267b14492a7e5afdbf8e3f953 |
| 数据目录 | D:\docker\new-api\data\ |
| 日志目录 | D:\docker\new-api\logs\ |
| 数据库文件 | D:\docker\new-api\data\one-api.db |
| 有效 Admin Token | m8EiGG23cZQ0AID2lhYFM3gE7VmwBBq43WeU4wavDWliHGtG |
