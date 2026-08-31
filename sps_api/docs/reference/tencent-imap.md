---
okf: v0.1
type: Reference
title: 腾讯企业邮箱 IMAP 检索特性与可用写法
description: 腾讯企业邮箱 IMAP 上 SEARCH 对 FROM/SUBJECT 静默失效、日期条件可用；正确做法 = 服务端日期过滤 + 客户端字段过滤
tags: [imap, tencent-exmail, email, python]
timestamp: 2026-08-18
---

# 腾讯企业邮箱 IMAP 检索特性

## 结论

腾讯企业邮箱（`imap.exmail.qq.com`）在 `us@mxdeals.com` 上实测（2026-08-18）：

- **字符串条件（FROM / SUBJECT / TEXT / HEADER）被服务端静默忽略** → SEARCH 返回整箱。
- **标记 / 日期条件（ALL / UNSEEN / SINCE / BEFORE）有效**。
- 因此**不能依赖 `FROM "xxx"` 服务端过滤**，正确姿势：
  1. 服务端用 `SINCE/BEFORE` 把范围缩小到日期窗口；
  2. 客户端对窗口内邮件头做字段过滤。

## 实测数据

| 检索条件 | 返回数 | 说明 |
|---|---|---|
| `ALL` | 6598 | 整箱大小 |
| `UNSEEN` | 3300 | 有效（未读） |
| `FROM "amkudrle@spscommerce.com"` | 6598 | **被忽略**，等同 ALL |
| `SUBJECT "SPS"` | 6598 | **被忽略** |
| `SINCE 25-Jun-2025 BEFORE 10-Jul-2025` | 78 | 有效（日期窗口） |
| `SINCE 01-Jan-2025` | ~1966 | 有效 |

## 可用写法（Python imaplib）

```python
import imaplib
from email import policy
from email.parser import BytesParser

imap = imaplib.IMAP4_SSL('imap.exmail.qq.com', 993)
imap.login('user@domain', 'pass')        # 凭据不写进代码
imap.select('INBOX')

# 1) 服务端日期过滤（FROM/SUBJECT 会被忽略，别用）
status, data = imap.search(None, 'SINCE 25-Jun-2025 BEFORE 10-Jul-2025')
seqs = data[0].split()

# 2) 客户端过滤：一次拉「逗号分隔的精确序号」避免范围过大
st, d2 = imap.fetch(','.join(s.decode() for s in seqs),
                    '(BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE)])')
for part in d2:
    if not isinstance(part, tuple):
        continue
    msg = BytesParser(policy=policy.default).parsebytes(part[1])
    blob = (str(msg.get('from', '')) + ' ' + str(msg.get('subject', ''))).lower()
    if 'spscommerce.com' in blob:
        print(msg.get('date'), msg.get('subject'))
```

## 坑位记录

- **序号 vs UID**：`imap.search()` 返回序号；要用 UID 必须 `imap.uid('search', ...)` 且 fetch 也用 `imap.uid('fetch', ...)`，混用会取不到邮件。
- **范围 fetch 陷阱**：`fetch('a:b', ...)` 拉 a~b **全部**邮件。若少量匹配序号零散分布，用 `first:last` 会拉中间上千封导致超时（本会话实测 78 封匹配却超时，就是这个原因）。应改用**逗号分隔的精确序号列表**一次拉取。
- **文件夹名含空格**：`select('Sent Messages')` 报 `Select parameters!`，需 `select('"Sent Messages"')`。
- **登录频率限制**：短时间多次登录会 `Login fail ... login frequency limited`，稍等重试。
- **HTML 正文**：用 `email` 解析后取 text/plain；无则对 text/html 去标签（`html.parser.HTMLParser`，注意需显式 `from html.parser import HTMLParser`）。
- **Windows 上 `python3` 是 Store 存根**（静默退出码 49），用 `python`（真实解释器）。
- **凭据管理**：账号密码/授权码一律走环境变量（`IMAP_USER/IMAP_PASS/IMAP_SERVER`），不写进代码/文件。

## 相关脚本

- `sps_api/read_sps_mail.py` —— 封装上述写法：列出窗口内邮件、`--sender` 过滤提示、`--full N` 打印全文。凭据从环境变量读取。
