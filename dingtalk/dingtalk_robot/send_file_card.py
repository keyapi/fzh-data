"""
上传文件到 ERPNext → 通过钉钉机器人发 ActionCard 卡片（带下载按钮）。

用法:
    cd dingtalk/dingtalk_robot && python send_file_card.py report.xlsx

环境变量:
    DINGTALK_WEBHOOK  — 钉钉机器人 webhook 地址
    DINGTALK_SECRET    — 钉钉加签 secret
    ERP_API_KEY        — ERPNext API Key
    ERP_API_SECRET     — ERPNext API Secret
    ERP_URL            — ERPNext 服务器地址 (可选, 默认生产环境)
"""

import os
import sys
from datetime import datetime
from pathlib import Path

from send_dingtalk import send_action_card
from upload_to_erpnext import upload_file_to_erpnext


def send_file_to_dingtalk(
    file_path: str | Path,
    title: str | None = None,
    text: str | None = None,
) -> dict:
    """上传文件到 ERPNext 并通过钉钉 ActionCard 发送下载链接。

    Args:
        file_path: 本地文件路径
        title:     卡片标题，默认使用文件名
        text:      卡片正文 (markdown)，默认生成时间戳信息

    Returns:
        钉钉 API 响应 dict
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    # 1. 上传到 ERPNext，获取公开 URL
    file_url = upload_file_to_erpnext(file_path)
    filename = path.name
    file_size_kb = path.stat().st_size / 1024

    # 2. 构造卡片内容
    if title is None:
        title = f"📊 {filename}"
    if text is None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        text = (
            f"## 📊 {filename}\n\n"
            f"> 生成时间：{now}\n\n"
            f"> 文件大小：{file_size_kb:.1f} KB\n\n"
            f"点击下方按钮下载文件。"
        )

    # 3. 通过钉钉 ActionCard 发送下载链接
    return send_action_card(
        title=title,
        text=text,
        buttons=[{"title": "📥 下载文件", "actionURL": file_url}],
    )


# ── CLI ──────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"用法: python {Path(__file__).name} <文件路径> [标题] [正文]")
        print(f"示例: python {Path(__file__).name} report.xlsx '今日报表' '点击下载今日数据'")
        sys.exit(1)

    kwargs = {}
    if len(sys.argv) > 2:
        kwargs["title"] = sys.argv[2]
    if len(sys.argv) > 3:
        kwargs["text"] = sys.argv[3]

    result = send_file_to_dingtalk(sys.argv[1], **kwargs)
    print(result)
    assert result["errcode"] == 0, f"发送失败: {result}"
    print("OK — 文件已上传并推送卡片到钉钉群")
