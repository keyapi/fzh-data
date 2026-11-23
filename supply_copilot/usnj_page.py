# -*- coding: utf-8 -*-
"""USNJ 只读决策页生成器（开发工具，不含客户数据）。

输入：
  --snapshot   recommend/batch 产出的快照 JSON（含 rows 数组与 as_of/version）
  --b-dir      可选：B_*.csv 所在目录（B_USNJ归属清单.csv / B_待确认.csv）
  --out        输出 HTML 路径

输出：单文件只读页（决策/A/B/C/D/E/口径 六个页签），无改量/审批/下单入口。
生产部署：把产物放 private/，由 System Manager 权限的 whitelist 方法读取。
"""
from __future__ import annotations

import argparse
import csv
import html
import json
from pathlib import Path


def esc(v):
    return html.escape("" if v is None else str(v))


def i(v):
    try:
        return f"{round(float(v)):,}"
    except Exception:
        return "—"


def badge(r):
    out = []
    if r.get("ownership_pending"):
        out.append('<span class="b warn">归属待确认</span>')
    if r.get("needs_decision"):
        out.append('<span class="b red">需拍板</span>')
    if r.get("special"):
        out.append('<span class="b purple">特殊品</span>')
    if r.get("low_confidence"):
        out.append('<span class="b gray">低置信</span>')
    return "".join(out)


def action(r):
    e = r.get("expedite_qty") or 0
    n = r.get("new_order_qty") or 0
    parts = []
    if e:
        parts.append(f"催已有 {i(e)}")
    if n:
        parts.append(f"新补 {i(n)}")
    extra = ("<br><small>" + " + ".join(parts) + "</small>") if parts else ""
    return esc(r.get("action")) + extra


def extra(r, key):
    v = (r.get("extra") or {}).get(key)
    return i(v) if v not in (None, "") else "—"


def so_lines(r):
    lines = r.get("so_lines") or []
    if not lines:
        return "<p class='muted'>未查到开放 SO 行</p>"
    body = "".join(
        f"<tr><td>{esc(x.get('so'))}</td><td>{esc(x.get('so_line'))}</td>"
        f"<td>{esc(x.get('transaction_date'))}</td><td>{esc(x.get('delivery_date'))}</td>"
        f"<td>{i(x.get('delivered'))} / {i(x.get('open_qty'))}</td>"
        f"<td>{i(x.get('overdue_days'))}</td><td>{esc(x.get('status'))}</td></tr>"
        for x in lines)
    return ("<table class='small'><thead><tr><th>SO</th><th>行</th><th>创建日</th><th>交付日</th>"
            "<th>已交/未交</th><th>逾期</th><th>状态</th></tr></thead><tbody>" + body + "</tbody></table>")


def read_b(b_dir: Path | None, name: str):
    if not b_dir:
        return []
    p = b_dir / name
    if not p.exists():
        return []
    return list(csv.DictReader(p.open(encoding="utf-8-sig")))


def b_table(rows):
    body = "".join(
        f"<tr><td>{esc(x.get('product_id'))}</td><td>{esc(x.get('current_owner'))}</td>"
        f"<td>{esc(x.get('hist_pools'))}</td><td>{esc(x.get('标记'))}</td>"
        f"<td>{esc(x.get('2025总销量'))}</td><td>{esc(x.get('2026总销量'))}</td></tr>"
        for x in rows)
    return ("<table><thead><tr><th>SKU</th><th>current owner</th><th>历史仓</th><th>标记</th>"
            "<th>2025</th><th>2026</th></tr></thead><tbody>" + body + "</tbody></table>")


def build(snapshot_path: Path, b_dir: Path | None) -> str:
    snap = json.loads(snapshot_path.read_text(encoding="utf-8"))
    rows = snap["rows"]

    rows_html = []
    for r in rows:
        rows_html.append(f"""
<tr>
<td><strong>{esc(r.get('sku'))}</strong><br><small>{esc(r.get('customer') or '归属待确认')} · {esc(r.get('physical_form'))} · {esc(r.get('uom'))}</small></td>
<td>{action(r)}</td><td>{i(r.get('coverage'))} 天</td><td>{esc(r.get('reason'))}</td><td>{badge(r)}</td>
</tr>
<tr class="detail"><td colspan="5">
<div class="grid">
<div><b>C 当前可发</b><br>{i(r.get('c_qty'))}</div>
<div><b>E 按时供给</b><br>{i(r.get('e_qty'))}</div>
<div><b>EN 已发运/待发</b><br>{extra(r,'EN已发运量')} / {extra(r,'EN待发量')}</div>
<div><b>PO / SO</b><br>{extra(r,'PO追加(去重)')} / {extra(r,'SO已下')}</div>
<div><b>CG 抵扣</b><br>{extra(r,'CG可调拨抵扣')}</div>
<div><b>预测 q50</b><br>{i(r.get('forecast'))}</div>
<div><b>q50/q90/q95</b><br>{i(r.get('q50'))}/{i(r.get('q90'))}/{i(r.get('q95'))}</div>
<div><b>模型</b><br>{esc(r.get('model') or '—')}</div>
</div>
<div class="chain"><span>SO 管线 <b>{i(r.get('so_open_qty'))}</b></span>
<span>近期 <b>{i(r.get('so_recent_open_qty'))}</b></span><span>历史 <b>{i(r.get('so_history_open_qty'))}</b></span>
<span>生产 <b>未接入</b></span><span>DN <b>未接入</b></span><span>通途 PO <b>未接入</b></span></div>
<details><summary>SO 明细（W1 截至 {esc(r.get('so_source_as_of') or '—')}，不加入建议量）</summary>{so_lines(r)}</details>
</td></tr>""")

    b1 = read_b(b_dir, "B_USNJ归属清单.csv")
    b2 = read_b(b_dir, "B_待确认.csv")

    a_rows = sorted({(r.get('sku'), r.get('physical_form'), r.get('uom'), r.get('customer')) for r in rows})
    a_html = "".join(f"<tr><td>{esc(x[0])}</td><td>{esc(x[1])}</td><td>{esc(x[2])}</td><td>{esc(x[3])}</td></tr>" for x in a_rows)
    d_html = "".join(
        f"<tr><td>{esc(r.get('sku'))}</td><td>{i(r.get('forecast'))}</td><td>{i(r.get('q50'))}</td>"
        f"<td>{i(r.get('q90'))}</td><td>{i(r.get('q95'))}</td><td>{esc(r.get('model') or '—')}</td></tr>" for r in rows)
    e_html = "".join(
        f"<tr><td>{esc(r.get('sku'))}</td><td>{i(r.get('c_qty'))}</td><td>{extra(r,'EN已发运量')}</td>"
        f"<td>{extra(r,'EN待发量')}</td><td>{extra(r,'PO追加(去重)')}</td><td>{extra(r,'SO已下')}</td>"
        f"<td>{extra(r,'CG可调拨抵扣')}</td><td>{i(r.get('so_recent_open_qty'))}</td>"
        f"<td>{i(r.get('so_history_open_qty'))}</td></tr>" for r in rows)

    summary = {k: sum(1 for r in rows if r.get(k)) for k in
               ("needs_decision", "low_confidence", "special", "ownership_pending")}

    doc = "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><title>USNJ 补货决策（只读）</title><style>"
    doc += "body{font-family:'Microsoft YaHei',Arial,sans-serif;margin:0;background:#f4f7f9;color:#16324a}"
    doc += "header{background:#16324a;color:#fff;padding:18px 28px}header h1{margin:0;font-size:22px}header p{margin:6px 0 0;color:#cfe0ea}"
    doc += "main{padding:20px 28px}.cards{display:flex;gap:12px;margin-bottom:16px}.card{background:#fff;border-radius:8px;padding:12px 16px;flex:1;border-left:4px solid #19a08c}.card b{font-size:24px;display:block}"
    doc += "nav button{border:0;background:#e3edf2;padding:10px 16px;margin-right:6px;border-radius:6px;cursor:pointer;font-size:14px}nav button.active{background:#16324a;color:#fff}"
    doc += "section{display:none;background:#fff;border-radius:8px;padding:16px;margin-top:12px}section.active{display:block}table{width:100%;border-collapse:collapse;font-size:13px}"
    doc += "th,td{padding:8px;border-bottom:1px solid #e1ebf0;text-align:left;vertical-align:top}th{background:#16324a;color:#fff}tr.detail td{background:#f8fbfc}"
    doc += ".grid{display:grid;grid-template-columns:repeat(8,1fr);gap:8px;margin:8px 0}.grid div{background:#fff;border:1px dashed #cbd8df;border-radius:6px;padding:6px}"
    doc += ".chain{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}.chain span{background:#eef5f8;border-radius:6px;padding:6px 10px}.b{display:inline-block;padding:2px 6px;border-radius:4px;font-size:11px;margin:1px}"
    doc += ".b.red{background:#fde8e8;color:#a12}.b.warn{background:#fff1d6;color:#8a5a00}.b.purple{background:#efe6ff;color:#5b2b9a}.b.gray{background:#e8edf0;color:#456}.small{font-size:12px}.muted{color:#6b7f8c}details summary{cursor:pointer;color:#19a08c;margin:4px 0}</style></head><body>"
    doc += f"<header><h1>USNJ 补货决策（只读）</h1><p>数据包 {esc(snap.get('version') or snap.get('source_name'))} · as_of {esc(snap.get('as_of'))} · {len(rows)} 行 · 不直接下单；采购/运营需复核</p></header><main>"
    doc += f"<div class='cards'><div class='card'><b>{summary['needs_decision']}</b>需拍板</div><div class='card'><b>{summary['low_confidence']}</b>低置信</div><div class='card'><b>{summary['special']}</b>特殊品</div><div class='card'><b>{summary['ownership_pending']}</b>归属待确认</div><div class='card'><b>{len(rows)}</b>建议行</div></div>"
    doc += "<nav><button class='active' data-t='home'>决策</button><button data-t='a'>A SKU宇宙</button><button data-t='b'>B 归属</button><button data-t='c'>C 库存</button><button data-t='d'>D 预估</button><button data-t='e'>E 供给</button><button data-t='method'>口径</button></nav>"
    doc += "<section id='home' class='active'><table><thead><tr><th>SKU / 客户 / 形态</th><th>建议</th><th>覆盖</th><th>原因</th><th>标记</th></tr></thead><tbody>" + "".join(rows_html) + "</tbody></table></section>"
    doc += f"<section id='a'><h3>A SKU 宇宙（{len(a_rows)} 个 SKU×形态×UOM）</h3><table><thead><tr><th>SKU</th><th>形态</th><th>UOM</th><th>客户</th></tr></thead><tbody>{a_html}</tbody></table></section>"
    doc += f"<section id='b'><h3>B 归属清单（{len(b1)} 个 current USNJ）</h3>{b_table(b1)}<h3>归属待确认（{len(b2)} 个）</h3>{b_table(b2)}</section>"
    doc += f"<section id='c'><h3>C 库存（当前可发，不含在途；CG 为下游缓冲不可回拨）</h3><table><thead><tr><th>SKU</th><th>C</th><th>EN已发运</th><th>EN待发</th><th>PO</th><th>SO</th><th>CG</th><th>近期SO</th><th>历史SO</th></tr></thead><tbody>{e_html}</tbody></table></section>"
    doc += f"<section id='d'><h3>D 预估（q50 中位，不是补货量；D5 v6.8）</h3><table><thead><tr><th>SKU</th><th>预测 q50</th><th>q50</th><th>q90</th><th>q95</th><th>模型</th></tr></thead><tbody>{d_html}</tbody></table></section>"
    doc += f"<section id='e'><h3>E 供给（SO/EN/PO/C/CG；SO 不加入建议量）</h3><table><thead><tr><th>SKU</th><th>C</th><th>EN已发运</th><th>EN待发</th><th>PO</th><th>SO</th><th>CG</th><th>近期SO</th><th>历史SO</th></tr></thead><tbody>{e_html}</tbody></table></section>"
    doc += "<section id='method'><h3>口径与限制</h3><ul><li>这是历史回放，不是今天的执行建议；页面显示数据包 as_of。</li><li>C = 当前可发，不含在途；E = 按时供给；CG = 下游缓冲，不可回拨。</li><li>SO 是 EN 分公司生产/交付单；通途 PO 是 DN 后采购入库；两者不能相加替代。</li><li>SO 管线未加入建议量；生产/DN/通途 PO 尚未接入。</li><li>缺失=未知，不补 0；无改量、审批、下单入口。</li></ul></section></main>"
    doc += "<script>document.querySelectorAll('nav button').forEach(function(b){b.onclick=function(){document.querySelectorAll('nav button').forEach(function(x){x.classList.remove('active')});b.classList.add('active');document.querySelectorAll('section').forEach(function(s){s.classList.remove('active')});document.getElementById(b.dataset.t).classList.add('active');window.scrollTo(0,0)}});</script></body></html>"
    return doc


def main(argv=None):
    ap = argparse.ArgumentParser(description="USNJ 只读决策页生成器")
    ap.add_argument("--snapshot", required=True, help="快照 JSON 路径")
    ap.add_argument("--b-dir", default=None, help="B_*.csv 目录（可选）")
    ap.add_argument("--out", required=True, help="输出 HTML 路径")
    args = ap.parse_args(argv)

    doc = build(Path(args.snapshot), Path(args.b_dir) if args.b_dir else None)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    print(out, len(doc))


if __name__ == "__main__":
    main()
