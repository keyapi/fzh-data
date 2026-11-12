---
okf: v0.1
type: Reference
title: 把本地侧应用嵌进 ERPNext Desk Page：Page 路径、空 payload 与 iframe allow-forms
date: 2026-11-12
category: docs/solutions/integration-issues/
module: demand_collaboration
problem_type: integration_issue
component: api-gateway
severity: high
applies_when:
  - "要在 ERPNext 里给一个本地 FastAPI/SQLite 工作台加入口"
  - "用 Desk Page + iframe srcdoc + frappe.xcall 复用登录会话"
  - "页面能显示，但读取 RPC 报 417 JSONDecodeError，或表单提交被浏览器拦截"
tags: [frappe, erpnext, desk-page, iframe, srcdoc, rpc, key_test, allow-forms]
---

# 把本地侧应用嵌进 ERPNext Desk Page

## Context

运营需求协同工作台是本地 FastAPI + SQLite（`demand_collaboration/`）。为了不做第二套登录，选择在 EN 里建一个标准 Desk Page，页面用 iframe `srcdoc` 加载服务端生成的 HTML，内部通过 `window.parent.frappe.xcall` 调同源 whitelisted 方法。首版在测试站跑通，但浏览器验收抓到两个只有在真实 iframe 里才会出现的问题。

## Guidance

### 落点

| 内容 | 路径 |
|---|---|
| Page 记录 + 控制器 | `apps/key_test/key_test/key_test/page/demand_collaboration/demand_collaboration.{json,js}` |
| Python 包 | `apps/key_test/key_test/demand_collaboration/`（方法路径 `key_test.demand_collaboration.frappe_bridge.*`） |

- Page JSON：`name`/`page_name` 用连字符（`demand-collaboration`），`module` 用 Module Def 的真实名字（本仓库是 `key_test`），`standard: Yes`，`roles` 列出允许打开的角色。
- 目录名/文件名用下划线（`demand_collaboration`），URL 用连字符（`/app/demand-collaboration`）。
- `module == app` 时**多一层**：`apps/key_test/key_test/key_test/...`。包根下的 `key_test/page/` 不是标准页同步目录，别放错。
- 控制器用 `frappe.pages['demand-collaboration'].on_page_load`；`get_workbench_html` 返回注入 `window.DEMAND_TRANSPORT` 的 HTML；transport 调 `parent.frappe.xcall(endpoint, {path, method, payload})`。
- 身份只取 `frappe.session.user` / `frappe.get_roles`；不接受客户端传 `actor`/`role`。

### 两个真实坑

**① GET 时 payload 是空字符串，不是 null**

`frappe.xcall` 对 `payload: null` 会编码成空表单字段；bridge 里 `json.loads("")` 抛 `JSONDecodeError`，整请求变 **417**，页面显示“payload必须为JSON对象”。

```python
def _payload(value):
    if isinstance(value, str):
        if not value.strip():
            return {}
        value = json.loads(value)
```

**② iframe sandbox 缺 `allow-forms`，表单提交被浏览器拦截**

`srcdoc` 里的 `<form>` 即使 `onsubmit` 已 `preventDefault`，浏览器仍会先做 sandbox 检查：

```
Blocked form submission ... the form's frame is sandboxed
and the 'allow-forms' permission is not set.
```

修复：

```js
frame.setAttribute('sandbox', 'allow-scripts allow-same-origin allow-forms');
```

### 部署与验证

- 改 `.py` → `bench migrate`（如新增 Page/角色）+ `clear-cache` + **`bench restart`**；只改 JS → `clear-cache` + 浏览器硬刷新。
- 验证顺序：`frappe.get_all('Page', ...)` 有记录 → `/app/demand-collaboration` 能打开 → iframe 内 `row-count` 有值 → 提交一条提案 → 审核端批准 → 发布 → 运营端读快照得 403。
- 测试站浏览器用 **`https://ensh.vilavi.cn`**；`https://erpnext.vilavi.cn` 指向生产（见 `documentation-gaps/agent-system-access-documentation-gap.md` 第三次实例）。

## Why This Matters

stub 测试只能证明路由和身份分支；`srcdoc` 的 sandbox 权限、Frappe 的表单编码都只在真实浏览器出现。本次两个缺陷都属于“页面看起来正常、每个读写都失败”，如果没有真实会话验收会直接带病上线。

## When to Apply

- 任何“本地/独立服务 + EN 只做入口”的嵌入方案。
- 任何用 srcdoc/iframe 承载表单的 Desk Page。
- 任何通过 `frappe.xcall` 传 `payload` 的 bridge。

## Examples

```js
// 控制器
frappe.pages['demand-collaboration'].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({parent: wrapper, title: '运营需求协同', single_column: true});
  frappe.xcall('key_test.demand_collaboration.frappe_bridge.get_workbench_html')
    .then(markup => {
      const frame = document.createElement('iframe');
      frame.setAttribute('sandbox', 'allow-scripts allow-same-origin allow-forms');
      frame.srcdoc = markup;
      page.main.append(frame);
    });
};
```

## Related

- `demand_collaboration/frappe_bridge.py`、`demand_collaboration/en_page/demand_collaboration/`
- `demand_collaboration/docs/review-2026-11-12.md` — 测试站验收记录
- `documentation-gaps/agent-system-access-documentation-gap.md` — 测试站域名与站点目录同名
- `workflow-issues/key-test-login-hook-and-prod-test-divergence.md` — key_test 分支/登录 hook
