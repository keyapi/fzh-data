---
title: "ERPNext Work Order Production Data Anomaly Investigation Methodology"
date: 2026-07-10
category: docs/solutions/best-practices/
module: erpnext
problem_type: best_practice
component: tooling
severity: medium
tags:
  - erpnext
  - work-order
  - job-card
  - data-quality
  - investigation
  - one-click-complete
summary: "An 8-step methodology for detecting and classifying ERPNext Work Order production data anomalies caused by the '一键完工' (one-click complete) feature, which creates virtual Job Cards with fake employee HR-EMP-00001 that mask real production quantities."
---

# ERPNext Work Order Production Data Investigation

## Context

In June 2026, we set out to audit ERPNext Work Order production data for the month. The initial query returned 0 results -- the MCP tool was pointed at the test system, not the production instance. After switching to the production API, we discovered 153 Work Orders with `actual_end_date` falling in June 2026.

A deeper look revealed the root cause: the system has a custom "一键完工" (one-click complete) feature that allows an operator to bypass the normal scan-based job reporting workflow. This feature creates virtual Job Cards under a virtual employee (`HR-EMP-00001`) for every operation on the Work Order, filling each with the planned quantity. The entire process completes in under two seconds, leaving behind a characteristic trail of rapid-fire Version records with 17-millisecond iteration intervals.

The person primarily operating this feature was 杨义森 (yangyisen92). His virtual Job Cards and Stock Entries masked actual production quantities reported by real workers on the shop floor. Without a systematic methodology, the ERPNext data would appear to show normal production when in reality the system contained a mix of real and fabricated data.

## Guidance: The 8-Step Investigation Methodology

### Step 1: Product Type Classification

Before examining any Work Order, classify by its item code prefix:

- **`KS` prefix** — Finished goods (成品fg). Assembly products (皮壳 + 内胆 + 充棉). Zero operations on routing, `open_material_qty = 0` is normal.
- **`PK#` prefix** — Semi-finished goods: 皮壳 (leather shell). Multi-operation routing, scan reporting expected.
- **`ND#` prefix** — Semi-finished goods: 内胆 (inner liner). Same as 皮壳.

### Step 2: Legacy Virtual Operations Check

Check operations for "缝制" (sewing) — a legacy operation from the one-click-complete era. Its presence means the BOM/routing was never updated. Flag for correction; the Job Card data for 缝制 is meaningless.

### Step 3: Version / Activity Records

Query `Version` doctype for `ref_doctype = "Work Order"` and `owner = "yangyisen92@dingtalk.com"`. Signature pattern:
- Status: 草稿 → 未开始
- `actual_start_date` and `actual_end_date` set within 1-2 seconds
- `actual_end_date` iterated at ~17ms intervals (programmatic, not human)
- `custom_label_combination` being set

### Step 4: Open Material Quantity Analysis

- **Semi-finished (PK#/ND#)**: `open_material_qty = 0` is **abnormal**. Cutting must issue material. Zero means production data is unreliable.
- **Finished goods (KS)**: `open_material_qty = 0` is **normal**. No cutting operation on routing.

### Step 5: Job Card time_logs.employee

Fetch individual Job Card → check `time_logs[].employee`:
- **`HR-EMP-00001`** = virtual employee (一键完工). Quantities = planned, not real.
- **Other IDs** = real workers. Quantities reflect actual scan-based production.

**API**: `GET /api/resource/Job Card/{name}` → `time_logs[]` child table

### Step 6: Job Card owner (Supplementary Cross-Check)

`owner` field on Job Card (who created the record):
- `yangyisen92@dingtalk.com` → created by 一键完工
- Real user accounts (e.g. `105-prd4qxz8w9`) → normal scan interface

Note: `owner` ≠ `employee`. Employee is in `time_logs` child table (Step 5).

### Step 7: Stock Entry Analysis

Query Stock Entries of type "Manufacture" linked to the Work Order:
- **owner = 杨义森** → item quantities = planned qty (unreliable)
- **owner ≠ 杨义森** → represents real goods receipt. Sum `items[].qty` where `t_warehouse` is set.

### Step 8: Cross-Validation and Classification

Compare four data sources and classify:

| Data Source | What It Represents |
|---|---|
| Real Job Card totals (Step 5) | Actual scan-reported production (lower bound) |
| Stock Entry receipt totals (Step 7) | Actual goods received into warehouse |
| `open_material_qty` (Step 4) | Material issued for cutting (production ceiling) |
| `produced_qty` on Work Order | System-reported output (may be inflated) |

Classification categories:

- **成品fg-正常完工**: KS prefix, 0 ops, open_mat=0. Normal.
- **正常扫码-工序瓶颈**: No 杨义森 records, real JC only. Fully credible.
- **半成品-一键完工**: Semi-finished, all JC virtual (HR-EMP-00001), open_mat=0. Entirely fabricated.
- **混合-真实+虚拟JC**: Both real and virtual JCs, open_mat>0. Use real JC/SE data.
- **混合-非Completed+一键完工**: Status≠Completed, 杨义森 touched. Same as Mixed.

## Why This Matters

The system was silently producing incorrect production data flowing into inventory valuation, cost accounting, and capacity planning. Reports based on `produced_qty` without this methodology would overstate actual production -- in some cases by hundreds of units per Work Order.

Without governance around 一键完工 use and without this detection methodology, the resulting data pollution is invisible.

## When to Apply

- Monthly or quarterly production audits
- Suspicious production figures not matching physical inventory
- Before trusting data in a system where 一键完工 exists
- Post-incident: discrepancy between system and physical inventory

## Examples

### WO-26-00082: The Mixed Case

**Step 1**: `PK#` prefix → semi-finished.

**Step 2**: No "缝制" — routing up to date.

**Step 3**: 杨义森 Version records present.

**Step 4**: `open_material_qty = 298` (credible).

**Step 5**: 98 real-worker JCs from 李清君 (`HR-EMP-00109`) scanning ~185 units in 9 batches. 7 virtual JCs at 300 units.

**Step 6**: 83 JCs owned by 李清君, 14 by sy14, 1 by yj0, 7 by 杨义森. Confirms Step 5.

**Step 7**: 10 Stock Entry batches totaling 216, all by yj0_wq85xz6km (real).

**Step 8 — Cross-validation**:

| Source | Quantity | Credibility |
|---|---|---|
| Real Job Cards (李清君) | ~185 | Real, lower bound |
| Stock Entry receipts | 216 | Real |
| open_material_qty | 298 | Real, ceiling |
| Virtual JCs (HR-EMP-00001) | 300 | Fabricated |
| produced_qty | 285 | Coincidentally close to truth |

**Conclusion**: Actual production ~285 units.

### Tooling

`erpnext/scripts/gen_report.py` implements this methodology as a reusable audit script. It consumes JSON exports from the Frappe API and produces a color-coded multi-sheet Excel workbook with all classification categories.

## Related

- `erpnext/docs/work-order-investigation-methodology.md` — project-specific methodology (Chinese)
- `erpnext/scripts/gen_report.py` — report generation script
