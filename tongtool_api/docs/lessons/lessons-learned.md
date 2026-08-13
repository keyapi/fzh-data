---
okf: v0.1
type: LessonsLearned
title: Tongtool ERP2 Lessons Learned
description: Durable rules derived from Tongtool ERP2 integration and MCP testing.
tags: [tongtool, erp2, lessons]
timestamp: 2026-08-13
---

# Lessons Learned

1. MCP tool visibility is not permission evidence; invoke a minimal read-only call and interpret 524.
2. A 525 error is useful: authentication and permission likely passed, so inspect parameters rather than rotating credentials.
3. Display account names and accountCode are different identifiers. Query base data first.
4. Do not transplant fields between wrappers. Package update-time support in the EN code conflicts with the observed MCP/Go models and needs live confirmation.
5. The EN 5/minute throttle is locally configurable, the Go SDK README says all API calls are five/minute, and a 2026-08-13 MCP discriminator test proved the two Apps share this merchant's bucket. Coordinate the total workload; do not allocate five calls to each App.
6. Cache and bounded pagination reduce API load, but cache keys must include all query parameters.
7. Raw order/package responses contain PII. Commit schemas, counts, and redacted findings only.
8. Mutation tools require explicit scope confirmation even when the App has permission.
9. Date every live-behavior claim because Tongtool docs and generated schemas can change.
