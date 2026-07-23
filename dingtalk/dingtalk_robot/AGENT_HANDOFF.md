# AGENT_HANDOFF.md — dingtalk_robot

> 面向 AI Agent（WorkBuddy / Claude Code / Codex CLI）的技术交接文档。

## 模块定位

钉钉自定义机器人通知 + 文件附件发送。通过 ERPNext 做文件中转，用钉钉 ActionCard 卡片推送下载链接。

## 脚本清单

| 脚本 | 功能 | 入口 |
|------|------|------|
| `send_dingtalk.py` | 发钉钉消息（markdown / ActionCard） | `send_markdown()` `send_action_card()` |
| `upload_to_erpnext.py` | 上传文件到 ERPNext，返回公开 URL | `upload_file_to_erpnext()` |
| `send_file_card.py` | 上传 + 发卡片，一步完成 | `send_file_to_dingtalk()` |

## 数据流

```
Excel 文件
  │
  ▼
upload_to_erpnext.py
  │  POST /api/method/upload_file
  │  Header: Authorization: token {ERP_API_KEY}:{ERP_API_SECRET}
  │  Body: multipart file + is_private=0
  ▼
ERPNext 返回 file_url (/files/xxx.xlsx)
  │
  ▼
send_dingtalk.py → send_action_card()
  │  msgtype: actionCard
  │  singleTitle: "下载文件"
  │  singleURL: https://erpnext.vilavi.cn/files/xxx.xlsx
  ▼
钉钉群卡片消息 (用户点击卡片 → 浏览器下载)
```

## 环境变量

```
DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=xxx
DINGTALK_SECRET=SECxxx
ERP_API_KEY=xxx
ERP_API_SECRET=xxx
ERP_URL=https://erpnext.vilavi.cn    # 可选，默认生产环境
```

## API 参考

### send_action_card()

```python
from send_dingtalk import send_action_card

send_action_card(
    title="报表已生成",
    text="## 今日数据报表\n\n点击下方按钮下载。",
    buttons=[
        {"title": "📥 下载 Excel", "actionURL": "https://erpnext.vilavi.cn/files/xxx.xlsx"},
    ],
)
```

单按钮时自动使用 `singleTitle/singleURL` 模式，多按钮时使用 `btns` 列表。

### upload_file_to_erpnext()

```python
from upload_to_erpnext import upload_file_to_erpnext

url = upload_file_to_erpnext("report.xlsx")
# → "https://erpnext.vilavi.cn/files/abc123.xlsx"
```

### send_file_to_dingtalk()

```python
from send_file_card import send_file_to_dingtalk

result = send_file_to_dingtalk(
    "report.xlsx",
    title="今日报表",
    text="## 今日数据汇总\n\n点击下载。",
)
assert result["errcode"] == 0
```

CLI:
```bash
cd dingtalk/dingtalk_robot
python send_file_card.py report.xlsx "今日报表" "点击下载"
```

## 钉钉机器人限制

- 自定义机器人每分钟最多 20 条消息
- actionCard 按钮 URL 必须可公网访问（ERPNext 生产环境满足）
- ActionCard 不支持直接在钉钉内预览文件，用户点击按钮跳转浏览器下载
- 文件留在公司 ERPNext 服务器，不会上传到钉钉或第三方

## 安全

- ERPNext API Key 是**用户级别**的，非企业应用级别，泄露影响面小
- 文件通过 `is_private=0` 上传为公开文件，任何知道 URL 的人可下载
- 如需私密文件，改 `is_private=1`，但钉钉链接将无法直接下载（需登录）
