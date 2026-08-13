---
okf: v0.1
type: Reference
title: Tongtool ERP2 Orders and Packages
description: Query conventions and verified pitfalls for ERP2 order and merchant package data.
tags: [tongtool, erp2, orders, packages]
timestamp: 2026-08-13
---

# Orders and Packages

## Orders

- MCP tool: erp2_orders_ordersquery.
- Official doc ID: f4371e5d65c242a588ebe05872c8c4f8.
- Resolve sale accounts first. accountCode is a short business code such as RSUS, not a display identifier such as AMZRosoonUS.
- Use at least one bounded order/date condition and a small page size while discovering.
- storeFlag semantics from the Go SDK: 0 active data, 01 active undelivered, 1 roughly 3-15 months, 2 archive older than roughly 15 months. Reconfirm if historical boundaries matter.

## Merchant Packages

- MCP tool: erp2_packages_packagesquery.
- Official doc ID: 0412c0185dce4a9d88714a9eef44932b.
- Live MCP validation required an assign-time or despatch-time range.
- The EN wrapper also contains updateTimeFrom/To, but the public Go SDK models assign/despatch times only. Treat update-time support as unverified until a live schema/call confirms it.
- Package status values seen in the SDK: waitPrint, waitDeliver, delivered, cancel.

## Pagination and Privacy

Use pageNo=1 and the smallest practical pageSize. Continue until the returned count is below page size; record every page count. Keep only aggregate test evidence in git. Never store raw production payloads in docs.
