---
title: "ERPNext Workflow Operations: Cross-System Management Guide"
date: 2026-07-03
category: architecture-patterns
module: frappe_workflow
problem_type: architecture_pattern
component: development_workflow
severity: medium
applies_when:
  - "Copying workflows between ERPNext environments (production to test)"
  - "Building new approval workflows from scratch for any DocType"
  - "Debugging workflow state transitions that fail silently"
  - "Setting up rejection/fallback paths in approval chains"
  - "Aligning workflow dependencies (States, Actions, Roles, Translations) across systems"
tags:
  - erpnext
  - workflow
  - approval
  - design-pattern
  - cross-environment
  - frappe-v15
  - role-permissions
---

# ERPNext Workflow Operations: Cross-System Management Guide

## Context

ERPNext (v15) workflows span four interlinked DocTypes and two systems. Production (`erpnext.vilavi.cn`) runs live business workflows; test (`ensh.vilavi.cn`) is the staging ground for new workflow development. The two systems have different access methods: production requires REST API with token auth, while test has the FAC MCP tool suite. This document captures patterns learned from copying the Purchase Receipt workflow V3 from production to test, and from building a new Delivery Note (销售出库单) approval workflow from scratch in test.

## Guidance

### 1. Workflow Dependency Layers

Every Workflow has four layers of dependencies that must exist before creation:

| Layer | DocType | Purpose |
|-------|---------|---------|
| 1 | Workflow State | Defines state names referenced by workflow states |
| 2 | Workflow Action Master | Defines action names referenced by transitions |
| 3 | Role | Defines who can edit at each state and who can execute each transition |
| 4 | Workflow | The main document linking states, transitions, and roles together |

**The creation order is strict.** You cannot create a Workflow referencing a state, action, or role that does not yet exist.

**Gap discovery pattern:**

```python
# After fetching production workflow JSON via REST API:
wf = resp.json()["data"]
states_needed = {s["state"] for s in wf["states"]}
actions_needed = {t["action"] for t in wf["transitions"]}
roles_needed = {s["allow_edit"] for s in wf["states"]} | {t["allowed"] for t in wf["transitions"]}

# Then check each against test system via FAC MCP list_documents
# Create missing ones in dependency order
```

**Real example:** Copying Purchase Receipt V3 required creating 7 Workflow States, 4 Workflow Action Masters, and 1 Role (Purchase Receipt Operator) in test before the workflow itself.

### 2. FAC MCP vs REST API Division

Production and test use different access methods:

| Operation | Production (REST API) | Test (FAC MCP) |
|-----------|----------------------|----------------|
| Query Workflow | `GET /api/resource/Workflow/{name}` | `get_document("Workflow", name)` |
| Create Workflow (with child tables) | `POST /api/resource/Workflow` with JSON body | `create_document("Workflow", {...})` |
| Create dependencies | `POST /api/resource/{doctype}` | `create_document(doctype, {...})` |
| Execute workflow actions | Workflow action API | `run_workflow(doctype, name, action)` |
| List documents | `GET /api/resource/{doctype}` with filters | `list_documents(doctype, filters)` |

**REST API call example (production):**

```python
import requests, json

session = requests.Session()
session.headers["Authorization"] = f"token {api_key}:{api_secret}"
session.headers["Accept"] = "application/json"
resp = session.get(
    "https://erpnext.vilavi.cn/api/resource/Workflow/采购入库 退库 和 取消 审批V3"
)
wf = resp.json()["data"]  # Full JSON with states and transitions child tables
```

**FAC MCP create example (test):**

```python
create_document("Workflow", {
    "workflow_name": "销售出库单审批",
    "document_type": "Delivery Note",
    "is_active": 1,
    "send_email_alert": 1,
    "states": [
        {"state": "Draft", "doc_status": "0", "allow_edit": "Workflow Stock User"},
        {"state": "待财务主管确认报税", "doc_status": "0", "allow_edit": "Finance Supervisor"},
    ],
    "transitions": [
        {"state": "Draft", "action": "Submit", "next_state": "待财务主管确认报税",
         "allowed": "Workflow Stock User"},
    ]
})
```

Note that `create_document` accepts child tables directly as arrays -- FAC MCP handles the relational wiring internally.

### 3. Naming Conventions

**Roles with workflow prefix:**
- English name: `Workflow-` prefix (e.g., `Workflow Stock User`, `Workflow Supply Chain Manager`)
- Chinese display name (via Translation doctype): `审批流-` prefix (e.g., `审批流-仓管员`, `审批流-供应链经理`)

**Existing roles without prefix (not renamed due to risk):**
- `Finance Supervisor`, `Chief Financial Officer` -- used across workflows, created before the naming convention

**Workflow States:** Chinese names directly, descriptive of the approval stage:
- `待财务主管确认报税`, `待仓库确认`, `供应链经理已拒绝`

**Workflow Actions:** Chinese or English, reuse existing where possible:
- `Approve`, `Reject`, `Submit` -- system defaults
- `取消`, `批准取消`, `返回` -- custom Chinese actions as needed

### 4. Translation Management

Role display names in the Chinese UI are managed through the `Translation` doctype:

```python
create_document("Translation", {
    "language": "zh",
    "source_text": "Workflow Supply Chain Manager",
    "translated_text": "审批流-供应链经理"
})
```

Both production and test systems should have aligned translations. Create the translation right after creating the Role.

### 5. Workflow Design Patterns

After studying four active production workflows, three consistent patterns emerged:

**Rejection State Pattern:**
- `allow_edit` = the APPROVER who rejected (they can annotate/correct the document)
- `Submit` transition (from rejected back to review) = the UPSTREAM role who re-submits
- Example: `财务主管已拒绝` state — allow_edit=`Finance Supervisor`, Submit allowed=`Workflow Stock User`

**Mid-flow doc_status=0 Pattern:**
- All states before final approval keep `doc_status=0` (allows editing by the designated role)
- Only the final Approved state has `doc_status=1` (triggers actual document submission)
- Cancelled state has `doc_status=2`
- This prevents premature validation failures -- for Delivery Note, stock validation only runs at doc_status=1

**Simple Rejection Pattern (no cascades):**
- Each rejection creates a single-step loop: reject → re-submit back to same approver
- Avoid multi-step rollback cascades unless business logic requires upstream re-verification

### 6. Cross-System Alignment Procedure

1. **Export from production** via REST API: fetch the workflow JSON with all child table data
2. **Compare with test**: use FAC MCP `list_documents` to check what already exists
3. **Create missing records** in test in dependency order: States → Actions → Roles → Translations → Workflow
4. **Verify counts match**: compare state count, transition count, and role assignments

The session that prompted this guide performed a full alignment: 21 Workflow States + 4 Workflow Action Masters + 14 Roles + 15 Translations were created in test to match production.

### 7. Common Pitfalls

**Administrator does not auto-include workflow roles.**
User `Administrator` must have workflow roles (Workflow Stock User, Finance Supervisor, etc.) explicitly assigned. Without them, workflow action buttons are invisible in the UI. Workflow transitions are gated on Role, not system permissions.

**FAC App bug with WorkflowTransitionError.**
In Frappe v15, `frappe.exceptions.WorkflowTransitionError` does not exist. When a workflow Approve triggers doc submission and validation fails, FAC throws `AttributeError` instead of propagating the real error (e.g., "insufficient stock"). If you see an AttributeError during a workflow action, check the underlying document's submit validation first.

**Stock validation blocks doc_status=1 transitions.**
When Approved state has `doc_status=1`, the underlying document's `on_submit` validation runs. For Delivery Note, stock must be available. Test with items that have actual inventory.

**Chinese URL encoding.**
Python `requests` library handles URL encoding automatically. Curl and other tools do not. When using curl, manually percent-encode Chinese characters.

**workflow_data and workflow_builder_id are non-functional.**
These store visual builder canvas coordinates. They can be null/empty in copied workflows without affecting any functional behavior.

### 8. Workflow Testing Strategy

1. Create a test document with items that have actual stock (for submittable doctypes)
2. Walk every transition using `run_workflow` via FAC MCP
3. Verify `next_available_actions` at each state match expected transitions
4. Test both approval and rejection paths
5. Test cancellation from Approved state
6. Verify doc_status progression: 0 throughout intermediate states, 0→1 at Approved, 1→2 at Cancelled

Example test sequence for Delivery Note workflow:

```python
# Create test document with stock-backed item
create_document("Delivery Note", {"customer": "...", "items": [{"item_code": "IN-STOCK-ITEM", "qty": 1}]})

# Walk full path
run_workflow("Delivery Note", "DN-xxxx", "Submit")  # Draft → 待财务主管确认报税 (doc=0)
run_workflow("Delivery Note", "DN-xxxx", "Approve")  # → 待供应链经理确认运费 (doc=0)
run_workflow("Delivery Note", "DN-xxxx", "Approve")  # → Approved (doc=1)
run_workflow("Delivery Note", "DN-xxxx", "取消")      # → 已取消 (doc=2)

# Test rejection path
run_workflow("Delivery Note", "DN-yyyy", "Reject")   # → 财务主管已拒绝
run_workflow("Delivery Note", "DN-yyyy", "Submit")   # → 待财务主管确认报税 (re-submit)
```

## Why This Matters

Workflows in ERPNext are fragile to set up and expensive to debug. Missing dependencies create silent failures. Missing roles hide action buttons with no error message. The doc_status field silently controls whether document validation runs. Following these patterns creates workflows that behave consistently across environments.

## When to Apply

- Copying an existing production workflow to the test system
- Building a new approval workflow from scratch for any DocType
- Troubleshooting invisible workflow action buttons
- Debugging workflow transition failures in FAC MCP
- Adding new roles to an existing workflow
- Aligning workflow translations between production and test

## Examples

**Copying Purchase Receipt V3 from production to test:**

1. Fetch: `GET /api/resource/Workflow/采购入库 退库 和 取消 审批V3` from production
2. Extract: 7 states, 4 actions, 1 role needed (plus 7 States, 3 Actions, 1 Role already exist)
3. Create missing dependencies in order: States → Actions → Role
4. Create the Workflow with full states and transitions child tables
5. Verify: 9 states + 11 transitions, matching production

**Building a Delivery Note approval workflow from scratch:**

1. Study 4 production workflows for design patterns
2. Define 7 states: Draft, 待财务主管确认报税, 财务主管已拒绝, 待供应链经理确认运费, 供应链经理已拒绝, Approved, 已取消
3. Define 8 transitions with role assignments (each rejected state loops back via Submit by upstream role)
4. Create new dependencies: 3 Workflow States, 1 Role, 1 Translation
5. Create the Workflow
6. Test all paths with stock-backed test items -- all 8 transitions verified

## Related

- [ERPNext Workflow Configuration Field Reference](../erpnext-workflow-configuration.md) -- all DocType fields and behavior rules
- [Workflow Copy: Purchase Receipt Prod to Test](../workflow-copy-prod-to-test.md) -- step-by-step copy procedure
- [FAC Dev Notes](../../fac-dev-notes.md) -- Lessons 62-72 covering FAC MCP quirks and patterns
- [Production Workflow JSON](../../../EN_API/workflow_prod_output.json) -- example production workflow export
- [API Credential Template](../../../EN_API/.env.example) -- `.env` file format for PROD_/TEST_ API keys
