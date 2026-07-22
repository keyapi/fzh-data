# AGENT_HANDOFF.md — dingtalk_robot

> 面向 AI Agent（Claude Code / WorkBuddy / Codex CLI）的技术交接文档。

## 模块定位

钉钉自定义机器人通知工具。提供一个零依赖 Python 脚本，通过 HMAC-SHA256 加签方式调用钉钉 webhook，发送 markdown 格式消息。

## send_dingtalk.py

### 环境变量

```
DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=xxx
DINGTALK_SECRET=SECxxx
```

### 签名算法

```
timestamp = str(round(time.time() * 1000))
string_to_sign = f"{timestamp}\n{secret}"
sign = base64(url_encode(hmac_sha256(secret, string_to_sign)))
url = f"{webhook}&timestamp={timestamp}&sign={sign}"
```

### 调用方式

```bash
cd dingtalk/dingtalk_robot && uv run python send_dingtalk.py
```

脚本从 `os.environ` 读取凭证，发送一条默认测试消息。

### 程序化调用

```python
from send_dingtalk import send_dingtalk_message

result = send_dingtalk_message(
    text="## 通知标题\n\n消息内容，支持 markdown。",
    title="通知标题"  # 可选，钉钉通知栏显示
)
assert result["errcode"] == 0
```

## 钉钉机器人限制

- 每分钟最多 20 条消息
- 仅支持 text / markdown / link / feedCard / actionCard 消息类型
- **不支持直接发送文件**（图片/excel 等需走企业自建应用 + 媒体上传）
- 加签模式下不需要 IP 白名单

## 安全注意事项

- `.env` 必须在 `.gitignore` 中
- webhook 和 secret 不要在日志/对话中打印
- 消息内容不要包含敏感信息（密码、token 等）
- webhook 泄露 = 任何人可往群里发消息，需及时在钉钉群设置中重置

## 相关文件

| 文件 | 说明 |
|------|------|
| `README.md` | 人读说明 |
| `钉钉自定义机器人配置指引_给管理员.md` | 管理员操作步骤 |
| `钉钉自定义机器人配置指引_给同事.md` | 同事操作手册（含 WorkBuddy 提示词） |
| `send_dingtalk.py` | Python 发送脚本 |
