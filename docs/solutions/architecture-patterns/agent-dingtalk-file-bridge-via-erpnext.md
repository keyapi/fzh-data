---
title: "Agent-to-DingTalk File Delivery via ERPNext Bridge"
date: 2026-07-23
category: architecture-patterns/
module: dingtalk_robot
problem_type: architecture_pattern
component: tooling
severity: medium
applies_when:
  - "Non-developer users need AI agents to send file attachments to DingTalk"
  - "Enterprise app credentials (AppKey/AppSecret) must not be shared with end-user agents"
  - "An ERPNext or similar self-hosted file server is already available"
  - "DingTalk custom robot webhook is already configured for text notifications"
tags: [dingtalk, erpnext, file-sharing, agent-integration, action-card, webhook, non-developer]
---

# Agent-to-DingTalk File Delivery via ERPNext Bridge

## Context

A non-developer colleague using WorkBuddy (Tencent desktop AI agent) needed scheduled
Excel reports delivered as file attachments to a DingTalk group. The initial approach
using only a DingTalk custom robot webhook worked for text/markdown notifications, but
DingTalk custom robots **cannot send file attachments** — they only support text,
markdown, link, actionCard, and feedCard message types.

The colleague's WorkBuddy agent proposed using a DingTalk enterprise internal bot
(AppKey + AppSecret + media/upload API), which would require sharing enterprise-level
credentials with the colleague's local machine. This was rejected on security grounds:
AppKey/AppSecret grants application-level access (potentially including member read
permissions), and storing it on a non-developer's personal computer is a significant
security risk.

## Guidance

Use a **self-hosted file server as a bridge** — upload the file there, then deliver
the download link via a DingTalk ActionCard message through the existing custom robot
webhook. No new credentials are needed beyond what the user already has.

```
┌──────────────┐     POST /api/method/upload_file      ┌─────────────┐
│  WorkBuddy   │ ─────────────────────────────────────→ │   ERPNext   │
│  (colleague) │     Authorization: token {user_key}    │  (company)  │
└──────┬───────┘                                       └──────┬──────┘
       │                                                      │
       │  file_url: /files/report.xlsx                        │
       │ ←──────────────────────────────────────────────────── │
       │                                                      │
       │  POST webhook (actionCard)                           │
       │  singleURL: https://erpnext.vilavi.cn/files/...      │
       │ ──────────────────────────────→   ┌──────────┐      │
       │                                  │ DingTalk  │      │
       │                                  │   Group   │      │
       │                                  └──────────┘      │
       │                                                      │
  User clicks card button → browser downloads from ERPNext   │
```

### Key properties

1. **Credentials are scoped and independent**: DingTalk webhook credentials only send
   messages; ERPNext API key is per-user (not application-level). A compromised
   webhook can only spam one group; a compromised ERPNext key can only access what
   that user can access.

2. **Data stays on company infrastructure**: Files never touch DingTalk servers or
   third-party services. The file is on the company's own ERPNext instance.

3. **Zero new infrastructure**: The ERPNext REST API (`/api/method/upload_file`)
   already exists. The custom robot webhook already supports ActionCard messages.

### Implementation

Three Python scripts, all under `dingtalk/dingtalk_robot/`:

**`upload_to_erpnext.py`** — upload file, return public URL:
```python
from upload_to_erpnext import upload_file_to_erpnext
url = upload_file_to_erpnext("report.xlsx")
# → "https://erpnext.vilavi.cn/files/abc123.xlsx"
```

**`send_dingtalk.py`** — send ActionCard with download button:
```python
from send_dingtalk import send_action_card
send_action_card(
    title="Report Ready",
    text="## Report generated\n\nClick to download.",
    buttons=[{"title": "Download", "actionURL": file_url}],
)
```

**`send_file_card.py`** — one-command pipeline:
```bash
python send_file_card.py report.xlsx "Report" "Click to download"
```

## Why This Matters

The alternative — sharing enterprise DingTalk AppKey/AppSecret — carries serious risks:
- Application-level credentials can send messages to any group the bot is in
- If the app has excessive permissions (common in practice), member info can be read
- A non-developer's personal machine is a weak link in the security chain
- Revocation means resetting an enterprise app credential, affecting all users

With the ERPNext bridge:
- Each credential has minimal blast radius
- The colleague's ERPNext API key is user-scoped and revocable independently
- No enterprise admin actions needed after initial setup
- The pattern generalizes: any self-hosted file server (NAS, MinIO, Nginx) works

## When to Apply

- When a non-developer user needs an AI agent to deliver file attachments to DingTalk
- When the organization already has a self-hosted file server (ERPNext, NAS, etc.)
- When sharing enterprise application credentials is unacceptable
- When the files are non-sensitive enough for public-but-obscure URLs, OR the file
  server supports authenticated downloads

## Examples

### Before (rejected approach): Enterprise bot credentials
```python
# Requires AppKey + AppSecret — enterprise-level, too risky to share
DING_APPKEY = "dingxxx"       # ⚠️ enterprise credential
DING_APPSECRET = "yyy"        # ⚠️ enterprise credential
# → upload to DingTalk media API → send via corpconversation/send
```

### After (implemented): ERPNext bridge
```python
# DINGTALK_WEBHOOK + DINGTALK_SECRET — only sends to one group
# ERP_API_KEY + ERP_API_SECRET — user-level, not enterprise
from send_file_card import send_file_to_dingtalk
send_file_to_dingtalk("report.xlsx", "Today's Report", "Click to download")
```

## Related

- [dingtalk_robot module](../../dingtalk/dingtalk_robot/README.md)
- [DingTalk custom robot message types](https://open.dingtalk.com/document/robots/custom-robot-access)
- [ERPNext REST API — file upload](../../.agents/skills/frappe-core-api/references/rest-api-reference.md)
