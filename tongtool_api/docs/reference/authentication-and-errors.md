---
okf: v0.1
type: Reference
title: Tongtool Authentication Permissions and Errors
description: Authentication paths, permission behavior, and error interpretation for Tongtool ERP2.0.
tags: [tongtool, erp2, auth, errors]
timestamp: 2026-08-13
---

# Authentication, Permissions, and Errors

## MCP Authentication

The official MCP accepts App credentials directly as custom headers. The MCP service performs downstream Tongtool authentication and presents generated tool schemas. Direct ERP2 API clients instead obtain app_token, resolve partnerOpenId, and sign requests with MD5 over app_token{token}timestamp{unix}{app_secret}.

## Permission Model

One Tongtool application selects one permission family. Both current AI Agent applications are ERP2.0 applications. The MCP advertises a global catalog, so tool visibility does not prove permission. Authorization is determined only when a tool is invoked.

| Code | Meaning | Operational interpretation |
|---|---|---|
| 200 | Success | Request accepted. Inspect datas; an empty list is still success. |
| 519 | Signature error | Direct API signing/auth issue. |
| 523 | Token expired | Refresh direct API authentication. |
| 524 | Unauthorized request | App lacks that endpoint/family, even if MCP listed the tool. |
| 525 | Invalid parameters | Authorization likely passed; compare live MCP schema and docs. |
| 526 | Request frequency exceeded | Back off; do not retry in a tight loop. |
| 527 / 599 | System/internal error | Capture minimal repro and retry later with bounded backoff. |
| MCP -32602 | Invalid tool input | MCP schema rejected the call before the Tongtool business request. |

Never publish raw order or package responses. They can include names, addresses, phone numbers, emails, tracking numbers, and commercial data.

## Rate Limit Scope

The public Go SDK README states that all Tongtool API calls are limited to five per minute. Tongtool's official public error-code document defines 526 as "interface request exceeds the request-count limit", but does not publish the bucket key. A live MCP discriminator test on 2026-08-13 established that two ERP2 Apps for this merchant share the five-call bucket: five primary-App warehouse queries succeeded, then the first secondary-App warehouse query returned 526. Do not use multiple Apps to multiply throughput.
