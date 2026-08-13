---
okf: v0.1
type: Reference
title: Tongtool ERP2 MCP Tool Catalog
description: Practical catalog of ERP2 MCP areas confirmed or prioritized for future automation.
tags: [tongtool, erp2, mcp, tools]
timestamp: 2026-08-13
---

# ERP2 MCP Tool Catalog

The 2026-08-13 MCP session exposed 212 tools globally. This document tracks useful ERP2 areas rather than duplicating volatile generated schemas. Always inspect the current MCP schema before calling.

| Area | Confirmed examples | Intended use | Risk |
|---|---|---|---|
| Base data | merchant sale accounts, platforms/sites, warehouses | Resolve codes before business queries | Read-only |
| Orders | erp2_orders_ordersquery, FBA and Shopify order queries | Order audit and synchronization | PII, pagination |
| Merchant packages | erp2_packages_packagesquery, tracking number query | Package, shipping, and freight audit | PII, time-window rules |
| Products | goods query, category query, goods logs | SKU and category consistency | Large result sets |
| Inventory | stock query, stock change query, FBA stock | Stock reconciliation | Warehouse/SKU semantics |
| Purchasing | suppliers, quotes, purchase orders, suggestions | Procurement analysis and automation | Writes require approval |
| Finance | account funds, PayPal, platform disbursement | Cost and settlement audit | Sensitive financial data |

Mutation tools may also be listed: create/update products, purchase orders, stock operations, order changes, and shipping execution. Listing is not authorization to run them. Require explicit user confirmation and a narrow test scope.
