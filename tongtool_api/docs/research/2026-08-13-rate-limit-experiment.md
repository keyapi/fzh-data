---
okf: v0.1
type: Research
title: Tongtool MCP Rate Limit Experiment 2026-08-13
description: Minimal read-only experiment to distinguish a 5/minute limit and per-App versus shared behavior.
tags: [tongtool, erp2, mcp, rate-limit]
timestamp: 2026-08-13
---

# MCP Rate-Limit Experiment - 2026-08-13

## Question

Does Tongtool MCP or ERP2 enforce the remembered 5 requests/minute limit, and is any limit isolated per App or shared across Apps?

## Prior Evidence

- Private EN app: configurable client-side default of 5/minute, plus retries for server code 526.
- Public Go SDK README: "all API call frequency is five per minute" and its code retries HTTP 429/business 526.
- Official Tongtool public error-code document: 526 means "interface request exceeds the request-count limit". The official AI-service MCP guide documents streamable HTTP and header authentication but not a separate MCP quota.

## Safety Protocol

- Read-only, minimal base-data endpoint.
- Stop after enough calls to test the 5/minute hypothesis.
- Record transport result separately from Tongtool business code.
- Do not store returned business records or credentials.

## Reproduction

Use a clean window and run the discriminator below only when a renewed live check is necessary:

```text
uv run python tongtool_api/test_mcp_rate_limit.py --mode discriminate --cooldown-seconds 65
```

The script waits before MCP initialization, makes five primary-App and one secondary-App warehouse queries with `pageNo=1` and `pageSize=1`, then emits per-request and aggregate JSON only. The expected discriminator is five `200` results followed by one `526`. A `524` result is an authorization finding, not rate-limit evidence.

## Result

### Connectivity

| App | Endpoint | Business code | Interpretation |
|---|---|---|---|
| Primary | ERP2 merchant platform base-data query | 200 | ERP2 MCP access works. |
| Secondary | Some BaseData endpoints | 524 | ERP2 authorization is granular by child interface; tool visibility and top-level ERP2 selection do not guarantee every endpoint. |
| Secondary | Warehouse query | 200 | The second MCP/App is working for this authorized ERP2 endpoint. |

### Primary-App Burst

The primary App had one successful connectivity call, followed immediately by a six-call burst. Within the same minute the burst produced four additional 200 responses, then two 526 responses. Total successful business calls before throttling: five.

This reproduces a server-side 5 requests/minute boundary for the tested primary App. The 526 appears inside a successful MCP transport response, so callers must inspect Tongtool business codes rather than HTTP status alone.

### Per-App Versus Shared Discriminator

After a 65-second cool-down, five primary-App warehouse queries returned 200 in the same minute. The very first secondary-App warehouse query, using separate App credentials and the same authorized endpoint, then returned 526. This proves that MCP calls consume the same upstream Tongtool quota and that the quota is shared across these two Apps. The live test cannot distinguish whether Tongtool keys the shared bucket by merchant, tenant, or another broader identity, but it definitively is not per App for this merchant.

An earlier alternating sequence produced secondary-App 524 responses after its first success. The isolated secondary-App run immediately afterwards produced five 200 responses and then a sixth 526. Treat that earlier 524 behavior as an authorization/session anomaly, not rate-limit evidence; 526 is the only observed limit signal.

### Operational Policy

Throttle the combined merchant workload to at most five upstream ERP2 business calls per rolling minute, cache base data, use bounded pagination, and back off on 526. Do not assume two Apps double throughput.
