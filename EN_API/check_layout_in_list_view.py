"""布局类字段带 in_list_view=1 的盘点 / 修复（ERPNext 生产 + 测试）。

背景
----
`Section Break / Column Break / Tab Break / HTML / Table / Table MultiSelect / Button / Image /
Fold / Heading`（以及 `Attach Image`）**不允许进列表视图**。一旦某个字段被标了 `in_list_view=1`，
Frappe 的 `check_in_list_view()`（`frappe/core/doctype/doctype/doctype.py`）就会在该 doctype 的
**任何**元数据写入时抛错：

    'In List View' not allowed for type <fieldtype> in row <合并后字段序号>

被挡住的不只是这个字段本身，而是 Custom Field / Property Setter / DocType / Customize Form 的**全部保存**。
如果某个应用在 `on_session_creation`（每次登录都会跑）里写该 doctype 的元数据，全站用户就会「登录即弹窗」。
2026-10-08 生产 row 197 / 测试 row 196 即为此（`key_test` 登录 hook 写 Item 元数据 + `work_order_task`
fixtures 把 6 个布局类字段标了 in_list_view=1）。

子表例外：`istable=1` 的 doctype 允许 `Button` / `HTML`（此时报错文案是 `In Grid View`）。

用法
----
    uv run python EN_API/check_layout_in_list_view.py                 # 只读盘点 生产+测试
    uv run python EN_API/check_layout_in_list_view.py --host test     # 只盘点测试
    uv run python EN_API/check_layout_in_list_view.py --apply --yes   # 真修（只修 Custom Field）

`--apply` 只改 **Custom Field** 行（用 DB 层 UPDATE，绕开已被挡死的正常保存），改完自动 `clear-cache` 并复查。
应用自带的 **DocField** / **Property Setter** 命中只报告不自动改——那属于应用行为取舍，应回应用仓库改定义。

详见 docs/solutions/integration-issues/layout-field-in-list-view-breaks-metadata-writes.md
"""

from __future__ import annotations

import argparse
import subprocess
import sys

SITE = "erpnext.vilavi.cn"
BENCH_ROOT = "/home/frappe/frappe-bench"
HOSTS = {
    "test": "sh-erpnext-test-frappe",
    "prod": "阿里云-FZH-ERPNext-frappe",
}
# 与 frappe.model.no_value_fields + Attach Image 一致（改这里前先核对 Frappe 源码）
LAYOUT_FIELD_TYPES = (
    "Section Break", "Column Break", "Tab Break", "HTML", "Table",
    "Table MultiSelect", "Button", "Image", "Fold", "Heading", "Attach Image",
)
# 子表里合法的两种
CHILD_TABLE_EXEMPT = ("Button", "HTML")

_FT = ", ".join(f"'{t}'" for t in LAYOUT_FIELD_TYPES)
_EXEMPT = ", ".join(f"'{t}'" for t in CHILD_TABLE_EXEMPT)
_NOT_EXEMPT = f"NOT (dt.istable = 1 AND x.fieldtype IN ({_EXEMPT}))"

COUNTS_SQL = f"""SELECT 'counts' AS kind, 'Custom Field' AS tbl, COUNT(*) AS n FROM `tabCustom Field`
UNION ALL SELECT 'counts', 'DocField', COUNT(*) FROM `tabDocField`
UNION ALL SELECT 'counts', 'Property Setter', COUNT(*) FROM `tabProperty Setter`;"""

# 命中：x.fieldtype 布局类 + in_list_view=1 + 不落在子表豁免里
CUSTOM_HITS_SQL = f"""SELECT 'hit' AS kind, cf.name, cf.dt, cf.fieldtype, cf.idx, dt.istable
  FROM `tabCustom Field` cf JOIN `tabDocType` dt ON dt.name = cf.dt
 WHERE cf.fieldtype IN ({_FT}) AND cf.in_list_view = 1
   AND {_NOT_EXEMPT.replace('x.', 'cf.')};"""

DOCFIELD_HITS_SQL = f"""SELECT 'hit' AS kind, df.parent, df.fieldname, df.fieldtype, df.idx, dt.istable
  FROM `tabDocField` df JOIN `tabDocType` dt ON dt.name = df.parent
 WHERE df.fieldtype IN ({_FT}) AND df.in_list_view = 1
   AND {_NOT_EXEMPT.replace('x.', 'df.')};"""

PS_HITS_SQL = f"""SELECT 'hit' AS kind, ps.doc_type, ps.field_name, ps.property, ps.value, df.fieldtype
  FROM `tabProperty Setter` ps JOIN `tabDocField` df ON df.parent = ps.doc_type AND df.fieldname = ps.field_name
 WHERE ps.property = 'in_list_view' AND ps.value = '1' AND df.fieldtype IN ({_FT})
UNION ALL
SELECT 'hit', ps.doc_type, ps.field_name, ps.property, ps.value, cf.fieldtype
  FROM `tabProperty Setter` ps JOIN `tabCustom Field` cf ON cf.dt = ps.doc_type AND cf.fieldname = ps.field_name
 WHERE ps.property = 'in_list_view' AND ps.value = '1' AND cf.fieldtype IN ({_FT});"""

# 被豁免（子表 Button/HTML）的行，报告里列出来当「跳过原因」
EXEMPT_SQL = f"""SELECT 'exempt' AS kind, cf.name, cf.dt, cf.fieldtype, dt.istable
  FROM `tabCustom Field` cf JOIN `tabDocType` dt ON dt.name = cf.dt
 WHERE cf.fieldtype IN ({_EXEMPT}) AND cf.in_list_view = 1 AND dt.istable = 1
UNION ALL
SELECT 'exempt', df.parent, df.fieldname, df.fieldtype, dt.istable
  FROM `tabDocField` df JOIN `tabDocType` dt ON dt.name = df.parent
 WHERE df.fieldtype IN ({_EXEMPT}) AND df.in_list_view = 1 AND dt.istable = 1;"""

APPLY_SQL = f"""UPDATE `tabCustom Field` cf JOIN `tabDocType` dt ON dt.name = cf.dt
   SET cf.in_list_view = 0, cf.modified = NOW(), cf.modified_by = 'Administrator'
 WHERE cf.fieldtype IN ({_FT}) AND cf.in_list_view = 1
   AND NOT (dt.istable = 1 AND cf.fieldtype IN ({_EXEMPT}));
SELECT ROW_COUNT() AS updated_rows;"""


def ssh_sql(host: str, sql: str) -> str:
    """在 <host> 上用 bench mariadb 跑 SQL（stdin 传入，避免引号地狱）。"""
    cmd = ["ssh", "-o", "BatchMode=yes", host, f"cd {BENCH_ROOT} && bench --site {SITE} mariadb"]
    p = subprocess.run(cmd, input=sql, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError(f"[{host}] mariadb 退出码 {p.returncode}\n{p.stdout}\n{p.stderr}")
    return p.stdout


def ssh_cmd(host: str, remote: str) -> str:
    cmd = ["ssh", "-o", "BatchMode=yes", host, remote]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (p.stdout + p.stderr).strip()


def rows(out: str) -> list[list[str]]:
    lines = [l for l in out.splitlines() if l.strip() and not l.startswith(("kind", "------"))]
    return [l.split("\t") for l in lines]


def survey(host: str, label: str) -> dict:
    counts = {r[1]: int(r[2]) for r in rows(ssh_sql(host, COUNTS_SQL)) if len(r) >= 3}
    custom = [r for r in rows(ssh_sql(host, CUSTOM_HITS_SQL)) if r and r[0] == "hit"]
    docfield = [r for r in rows(ssh_sql(host, DOCFIELD_HITS_SQL)) if r and r[0] == "hit"]
    ps = [r for r in rows(ssh_sql(host, PS_HITS_SQL)) if r and r[0] == "hit"]
    exempt = [r for r in rows(ssh_sql(host, EXEMPT_SQL)) if r and r[0] == "exempt"]

    print(f"[{label}] {host}  (site {SITE})")
    print(f"  扫描：Custom Field {counts.get('Custom Field', 0)} 行 / DocField {counts.get('DocField', 0)} 行 / "
          f"Property Setter {counts.get('Property Setter', 0)} 行")
    print(f"  命中 Custom Field：{len(custom)} 行 —— 登录弹窗的元凶就是这类，--apply 会清零")
    for r in custom:
        print(f"      - {r[1]}  dt={r[2]}  {r[3]}  idx={r[4]}  (子表={r[5]})")
    print(f"  命中 DocField（应用自带，需回应用仓库改）：{len(docfield)} 行")
    for r in docfield:
        print(f"      - {r[1]}.{r[2]}  {r[3]}  idx={r[4]}  (子表={r[5]})")
    print(f"  命中 Property Setter：{len(ps)} 行")
    for r in ps:
        print(f"      - {r[1]}.{r[2]}  {r[3]}={r[4]}  字段类型={r[5]}")
    print(f"  豁免跳过（子表里的 Button/HTML，Frappe 允许）：{len(exempt)} 行"
          + ("" if not exempt else "\n" + "\n".join(f"      - {r[1]} dt={r[2]} {r[3]}" for r in exempt)))
    print()
    return {"custom": custom, "docfield": docfield, "ps": ps, "exempt": exempt}


def main() -> int:
    ap = argparse.ArgumentParser(description="布局类字段 in_list_view 盘点/修复")
    ap.add_argument("--host", choices=["test", "prod", "both"], default="both")
    ap.add_argument("--apply", action="store_true", help="真写：把命中的 Custom Field 置 in_list_view=0 并清缓存")
    ap.add_argument("--yes", action="store_true", help="--apply 时跳过交互确认")
    args = ap.parse_args()

    hosts = list(HOSTS.items()) if args.host == "both" else [(args.host, HOSTS[args.host])]
    report = {label: survey(host, label) for label, host in hosts}

    if not args.apply:
        total = sum(len(r["custom"]) for r in report.values())
        print(f"dry-run 结束：待修 Custom Field 共 {total} 行。加 --apply --yes 才写。")
        return 1 if total else 0

    for label, host in hosts:
        n = len(report[label]["custom"])
        if not n:
            print(f"[{label}] 无需修复")
            continue
        if not args.yes:
            print(f"[{label}] 将把 {n} 行 Custom Field 的 in_list_view 置 0；确认请加 --yes")
            continue
        out = ssh_sql(host, APPLY_SQL)
        print(f"[{label}] UPDATE -> {rows(out)}")
        print(f"[{label}] clear-cache -> {ssh_cmd(host, f'cd {BENCH_ROOT} && bench --site {SITE} clear-cache >/dev/null 2>&1; echo ok')}")
        left = [r for r in rows(ssh_sql(host, CUSTOM_HITS_SQL)) if r and r[0] == "hit"]
        print(f"[{label}] 复查 Custom Field 命中：{len(left)} 行（应为 0）")
        if left:
            print("      " + ", ".join(r[1] for r in left))
            sys.exit(2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
