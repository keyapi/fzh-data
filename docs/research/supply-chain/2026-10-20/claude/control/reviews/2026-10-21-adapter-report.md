---
okf: v0.1
type: Review
title: DN/WO/JC/SE 适配器复审（22ae9a1e）
date: 2026-10-21
reviewer: codex
verdict: requires-fixes
---

Reviewed committed HEAD **`22ae9a1e`** on `docs/supply-chain-integration-handoff`. All three files match that commit; findings are **not provisional**. **Requires fixes before adapter acceptance.**

Paths below are relative to `docs/research/supply-chain/2026-10-20/claude/experiments/g1_contract/`.

| # | Severity | File:line | Finding and next action |
|---|---|---|---|
| 1 | P1 | `g1b_dn_wo_jc_se.py:603`, `:813` | **C1 can pass despite individual line failures.** Opposite discrepancies cancel within a UOM; rounding also hides differences such as `0.004`. Reproduced two mismatched lines with `audit_ok=true`. Require every eligible line to pass at full precision before aggregating. Spec `g1b_dn_wo_jc_se.md:66` promises per-line conservation. |
| 2 | P1 | `g1b_dn_wo_jc_se.py:229` | **DN joins override invalid explicit references.** A non-empty, nonexistent `so_line_id` falls back to unique item matching; an exact line reference also accepts a conflicting item. Both reproduced as conserved. Allow fallback only when the reference is absent, and validate item identity. This contradicts spec `g1b_dn_wo_jc_se.md:40`. |
| 3 | P1 | `g1b_dn_wo_jc_se.py:258`, `:375`, `:563`, `:781` | **Same-unit guarantees are incomplete.** Missing DN UOM is accepted; SE finished rows in `EA` and `BOX` are summed and marked conserved; association/window summaries also combine units. Require known compatible units and partition every quantity aggregate by UOM. |
| 4 | P1 | `g1b_dn_wo_jc_se.py:321`, `:694` | **SE enrichment ignores parent metadata.** Cached lines are accepted while cached `docstatus`, `work_order`, and entry type are ignored. A cancelled detail belonging to another WO reproduced as conserved. Validate metadata and source/time compatibility before merging; preserve drift as unverified. |
| 5 | P1 | `g1b_dn_wo_jc_se.py:378`, `:427`, `:820` | **Incomplete SE coverage can appear complete or conserved.** Upstream `se_query_error` is ignored: a failed query with an empty SE set reproduced both flags true. A missing-detail SE alongside a matching valid SE leaves its WO conserved. Propagate query completeness and every unresolved submitted SE into WO/C2 and evidence status; distinguish known subtotals from complete totals. |
| 6 | P1 | `g1b_dn_wo_jc_se.py:185`, `:363`, `:488`, `:803` | **C4 does not prove every input has exactly one disposition.** Non-dict rows disappear before input counting; JC groups for absent WOs disappear; duplicate SE line IDs pass audit. All reproduced. Count raw inputs, retain rejected/orphan records, and validate child-key uniqueness. Spec `g1b_dn_wo_jc_se.md:69` overstates current coverage. |
| 7 | P2 | `g1b_dn_wo_jc_se.py:254`, `:265`; `test_g1b_dn_wo_jc_se.py:180` | **Signed returns lack a normalization contract.** A return quantity of `-2` is excluded as invalid instead of reducing shipments; the test only covers positive return quantities. Define and validate the source sign convention, then test signed returns without double subtraction. |
| 8 | P2 | `g1b_dn_wo_jc_se.py:753`, `:758`, `:990` | **HTTP budget excludes probes and undercounts pagination.** `--max-http` only controls enrichment; each paginated probe is logged as one request. Share a request-level budget across enrichment, probe pages, and retries; report exhaustion explicitly. Spec `g1b_dn_wo_jc_se.md:34` states an upper bound of 500. |
| 9 | P2 | `g1b_dn_wo_jc_se.py:918`, `:997`; `test_g1b_dn_wo_jc_se.py:374` | **Final payload checksum is invalid.** `payload_sha256` is calculated before adding `stable_sha256`. Reproduced failure when hashing the final manifest after removing only its payload hash. Finalize fields before computing the checksum and test the final output shape. |

Validation: **33 existing tests passed**, plus in-memory counterexamples. Two tests that write temporary files were skipped to honor read-only scope.

No source files changed, no production queries made, and the accepted SO gate was untouched. **`G1B-ADAPTER-REVIEW` is now `completed`** through the requested status updater; completion records the review, not adapter acceptance.