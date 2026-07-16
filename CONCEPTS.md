# Concepts

Shared domain vocabulary for this project — entities, named processes, and status concepts with project-specific meaning. Seeded with core domain vocabulary, then accretes as ce-compound and ce-compound-refresh process learnings; direct edits are fine. Glossary only, not a spec or catch-all.

## Manufacturing

### 一键完工 (One-Click Complete)
A custom ERPNext feature that completes a Work Order by programmatically creating virtual Job Cards for every operation using employee `HR-EMP-00001`, filling each with the planned quantity. Completes in under two seconds. Designed for scenarios where scan-based reporting is unavailable, but creates fabricated production data when used on Work Orders that have real worker scans.

### 扫码报工 (Scan-Based Job Reporting)
The normal production reporting workflow: workers scan a barcode at each operation station, creating a Job Card with their employee ID and the actual quantity completed. This is the source of truth for production data. Contrasts with 一键完工.

### 成品fg (Finished Goods)
Final assembly products combining 皮壳 (leather shell) + 内胆 (inner liner) + 充棉 (stuffing). Identified by item codes starting with `KS` (no `#`). Have zero operations on the Work Order routing because components are produced as separate semi-finished Work Orders. `open_material_qty = 0` is normal. Currently completed via 一键完工; scan-based workflow is planned.

### 半成品 (Semi-Finished Goods)
Intermediate production items with multi-operation routings. Two subtypes: 皮壳 (leather shell, `PK#` prefix) and 内胆 (inner liner, `ND#` prefix). Require step-by-step scan reporting through each operation. `open_material_qty` must be > 0 if cutting was actually performed.

### 开料 (Material Issuing / Cutting)
The first production operation that issues raw fabric and cuts it to size. The quantity reported here (`open_material_qty`) is the production ceiling — no subsequent operation can produce more than what was cut. A zero value on a semi-finished Work Order means cutting was never reported in the system.

### 虚拟员工 (Virtual Employee)
Employee ID `HR-EMP-00001`, used exclusively by the 一键完工 feature. All Job Cards assigned to this employee are synthetic and reflect planned quantities, not actual production. Detected by checking `time_logs[].employee` on individual Job Card records.

## ERPNext Platform

### Custom App
A Frappe framework application that extends ERPNext with project-specific functionality. Deployed alongside core ERPNext (`erpnext`, `frappe`) in the same bench. Each custom app has its own git repository under `frappe-bench/apps/`. This project has multiple custom apps including `delivery_plan`, `key_oms`, `key_test`, `light_mes`, and `vilavi_pim`.

### Inventory Dimension (库存辅助核算)
ERPNext's stock auxiliary accounting system that adds extra tracking fields (e.g., tracking number, label combination) to stock transactions and Stock Ledger Entries. Configured via the Inventory Dimension doctype. Each dimension maps a reference document to a custom field in transaction line items and a corresponding column in Stock Ledger Entry.

### Version Drift (版本差异)
The gap between the test ERPNext version and the production ERPNext version. Currently the test system runs ERPNext v15.59.0 while production runs v15.43.3. This drift means ERPNext internal APIs (such as `get_inventory_dimensions()`) may return different field sets between the two environments, causing custom app code to work on test but silently fail on production.
