# dingtalk_robot — 钉钉自定义机器人通知 + 文件附件发送

> 给同事 WorkBuddy 配置钉钉通知推送，支持文本消息 + 文件附件（通过 ERPNext 中转）。

## 背景

同事在自己电脑上使用 WorkBuddy agent，需要定时推送通知和 Excel 报表到钉钉。本模块提供：

1. **文本通知**：通过钉钉自定义机器人 webhook 发送 markdown 消息
2. **文件附件**：上传文件到 ERPNext → 用钉钉 ActionCard 推送下载链接

## 文件说明

| 文件 | 用途 |
|------|------|
| `钉钉自定义机器人配置指引_给管理员.md` | 管理员操作步骤（备用） |
| `钉钉自定义机器人配置指引_给同事.md` | 同事完整操作手册 |
| `send_dingtalk.py` | 发钉钉消息（markdown / ActionCard） |
| `upload_to_erpnext.py` | 上传文件到 ERPNext，返回公开下载 URL |
| `send_file_card.py` | 上传 + 发卡片，一步完成 |
| `.env.example` | 环境变量模板 |

## 快速开始（同事用）

1. 钉钉建群 → 加自定义机器人（选加签），拿到 webhook + secret
2. 确认 ERPNext API Key（My Settings → API Access）
3. 在 `.env` 里填入凭证
4. WorkBuddy 生成 Excel 后运行：
   ```bash
   cd dingtalk/dingtalk_robot && python send_file_card.py report.xlsx
   ```

详细步骤见 `钉钉自定义机器人配置指引_给同事.md`。

## 技术栈

- Python 3 标准库（`send_dingtalk.py` 零依赖）
- `requests`（`upload_to_erpnext.py`，项目已有）
- 钉钉自定义机器人 webhook API（加签 + ActionCard）
- ERPNext REST API（token 认证 + multipart 文件上传）
