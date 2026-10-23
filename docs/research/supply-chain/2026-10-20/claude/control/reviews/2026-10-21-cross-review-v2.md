---
okf: v0.1
type: Review
title: DN/WO/JC/SE v2 交叉复审（49a142e0）
date: 2026-10-21
reviewer: codex
verdict: fail
---

**Verdict: FAIL — `49a142e0` requires rework.**

All references are in `g1_contract/g1b_dn_wo_jc_se.py`:

- **P1 — :611, :657:** Different SE units still aggregate: `10 EA + 2 BOX` produces WO finished quantity `12`, while C2 completeness and audit/evidence flags remain true. Partition quantities by UOM.
- **P1 — :553, :573:** A child with an invalid `is_finished_item` flag is omitted from finished-row validation. SE/WO can remain conserved and evidence complete. Propagate unresolved children to parent validation.
- **P2 — :689, :746:** A matched JC group with malformed operations counts as matched but emits no disposition. Preserve it as an explicit invalid record.

Verified v2 hashes, zip contents, input hashes, stable replay, and all 2,040 disposition rows. **73 strictly read-only tests passed.** Accepted SO evidence was untouched; no production queries occurred.

Updated statuses: `G1B-DN-WO-JC-SE → ready`; `G1B-CROSS-REVIEW → waiting`.

Read-only deviation: two earlier tests created and cleaned temporary files. Source and evidence files were unchanged.