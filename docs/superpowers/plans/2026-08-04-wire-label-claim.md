---
okf: v0.1
type: Plan
title: Wire label claim into create_label
description: Connect preflight+claim+transition to the production create_label path; remove fictional address fallbacks; add CANCELLED terminal and transition edges
timestamp: 2026-08-04
---

# Wire Label Claim Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `LabelService.create_label()` actually use the #134 safety primitives so concurrent/uncertain purchases cannot bypass claim.

**Architecture:** LabelService owns coarse operation lifecycle (`RESERVED→SENT→SUCCEEDED|FAILED_*|UNKNOWN_BLOCKED`). Carrier services accept `operation_id` for label rows and refuse fictional ship-from/to fallbacks. Cancel confirmed → label `is_active=false` + operation `CANCELLED`.

**Tech Stack:** Python, pytest, SQLite, existing PackageRepository / LabelService.

## File map

| File | Responsibility |
|------|----------------|
| `tests/sellfox_shipping/test_label_acquisition_safety.py` | New failing tests first |
| `sellfox_shipping/package_repository.py` | Transition edge table + CANCELLED |
| `sellfox_shipping/label_service.py` | Wire preflight/claim/transition; cancel releases op |
| `sellfox_shipping/carriers/vite/shipment.py` | No fictional addresses; pass operation_id |
| `sellfox_shipping/docs/*` + AGENT_HANDOFF + CONCEPTS | Honest status |

## Tasks

### Task 1: Failing tests

- [ ] Active label blocks claim
- [ ] create_label mocks carrier: claims op, ends SUCCEEDED, label has operation_id
- [ ] create_label carrier 502 after SENT → UNKNOWN_BLOCKED, second create blocked
- [ ] Invalid transition raises
- [ ] Cancel → CANCELLED → reclaim generation 2
- [ ] `_build_ship_from/to` raise on missing fields (no Belmont/Customer/0000)

### Task 2: Repository state machine

- [ ] `ALLOWED_LABEL_OPERATION_TRANSITIONS` + enforce in `transition_label_operation`
- [ ] Update cancel safety test to CANCELLED

### Task 3: Wire LabelService + Vite address guards

- [ ] `create_label`: preflight → claim → SENT → carrier → SUCCEEDED / classify errors
- [ ] `cancel_label`: after carrier success, transition linked op to CANCELLED
- [ ] Pass `operation_id` into vite/lizard insert paths
- [ ] Remove fictional fallbacks in vite `_build_ship_*`

### Task 4: Docs + verify

- [ ] Update blueprint SUCCEEDED vs unique-index wording; HANDOFF; log; CONCEPTS
- [ ] `uv run pytest tests/sellfox_shipping -q`
- [ ] Commit + PR based on #134
