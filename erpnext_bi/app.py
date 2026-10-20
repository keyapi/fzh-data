# -*- coding: utf-8 -*-
"""EN 生产 BI 看板 — FastAPI 实时看板。

链路: 下单(SO) → 工序(裁剪/缝制/检查/包装, 来自作业卡) → 销售(出库, DN)
每个订单/产品展示各工序完成数量 + 最后记录时间。

运行: uv run uvicorn erpnext_bi.app:app --host 0.0.0.0 --port 8099 --log-level info
数据来自 EN 生产 API, 带内存缓存(TTL 300s); 全量刷新约 20s(3.5 万张作业卡)。
"""
from __future__ import annotations

import threading
import time

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .en_client import EnClient

app = FastAPI(title="EN 生产 BI 看板")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
_CLIENT = EnClient()

_CACHE: dict = {"ts": 0.0, "payload": None, "ttl": 300}
_LOCK = threading.Lock()


def get_data(force: bool = False) -> dict:
    now = time.time()
    if not force and _CACHE["payload"] and now - _CACHE["ts"] < _CACHE["ttl"]:
        return _CACHE["payload"]
    with _LOCK:  # 防止并发刷新重复打 EN API
        now = time.time()
        if not force and _CACHE["payload"] and now - _CACHE["ts"] < _CACHE["ttl"]:
            return _CACHE["payload"]
        data = _CLIENT.fetch_all()
        payload = {
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "counts": data["counts"],
            "order_count": len(data["orders"]),
            "orders": data["orders"],
        }
        _CACHE["payload"] = payload
        _CACHE["ts"] = time.time()
        return payload


@app.get("/api/orders")
def api_orders(refresh: bool = Query(False)):
    return JSONResponse(get_data(force=refresh))


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(DASHBOARD_HTML)


# ──────────────────────────────────────────────────────────────
# 前端看板 (单页, 内联 CSS/JS, 数据由 /api/orders 拉取)
# ──────────────────────────────────────────────────────────────
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>EN 生产 BI 看板</title>
<style>
  :root{
    --bg:#f5f7fa; --card:#fff; --line:#e3e8ef; --text:#1f2733; --muted:#6b7785;
    --blue:#2f6fed; --green:#1f9d55; --orange:#e08a00;
  }
  *{box-sizing:border-box}
  body{margin:0;font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
       background:var(--bg);color:var(--text);font-size:14px}
  header{padding:18px 24px;background:var(--card);border-bottom:1px solid var(--line)}
  h1{margin:0;font-size:20px}
  .sub{color:var(--muted);font-size:12px;margin-top:4px}
  .bar{display:flex;align-items:center;gap:12px;margin-top:10px;flex-wrap:wrap}
  .cards{display:flex;gap:12px;flex-wrap:wrap;padding:16px 24px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:10px;
        padding:12px 16px;min-width:120px}
  .card .k{color:var(--muted);font-size:12px}
  .card .v{font-size:20px;font-weight:600;margin-top:4px}
  .toolbar{padding:0 24px 12px;display:flex;gap:10px;align-items:center}
  input[type=text]{padding:8px 12px;border:1px solid var(--line);border-radius:8px;min-width:260px}
  button{padding:8px 14px;border:1px solid var(--line);border-radius:8px;background:#fff;cursor:pointer}
  button:hover{background:#eef2f7}
  table{width:100%;border-collapse:collapse;background:var(--card)}
  th,td{padding:9px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top;white-space:nowrap}
  th{background:#f0f3f8;color:var(--muted);font-weight:600;position:sticky;top:0;z-index:1}
  .wrap{padding:0 24px 32px;overflow-x:auto}
  .order-row{cursor:pointer}
  .order-row:hover{background:#f7faff}
  .base{font-weight:600}
  .splits{color:var(--muted);font-size:12px}
  .badge{display:inline-block;background:#eef2f7;color:var(--muted);border-radius:6px;
          padding:1px 8px;font-size:11px;margin:1px 2px 1px 0}
  .qty{font-weight:600}
  .t{display:block;color:var(--muted);font-size:11px;margin-top:2px}
  .zero{color:#c2c9d2}
  .detail td{background:#fafcff}
  .detail table th{position:static;background:#f4f7fb}
  .muted{color:var(--muted)}
  .empty{padding:40px;text-align:center;color:var(--muted)}
  .loading{padding:60px;text-align:center;color:var(--muted);font-size:15px}
</style>
</head>
<body>
<header>
  <h1>EN 生产 BI 看板</h1>
  <div class="sub">链路: 下单(销售订单) → 裁剪 → 缝制 → 检查(质检) → 包装 → 销售(出库) ｜
    工序数量/时间取自作业卡(各工序最后记录时间) ｜ 销售数量=SO 回写已发数量, 时间=最后出库日期 ｜
    数据实时取自 EN 生产环境, 缓存 5 分钟</div>
  <div class="bar">
    <span class="muted">更新时间: <b id="updated">—</b></span>
    <span class="muted" id="counts"></span>
  </div>
</header>

<section class="cards" id="cards"></section>

<div class="toolbar">
  <input type="text" id="q" placeholder="按订单号 / 客户 / 物料 过滤…" oninput="render()">
  <button onclick="load(true)">↻ 强制刷新</button>
  <span class="muted" id="hint"></span>
</div>

<div class="wrap">
  <table id="tbl">
    <thead>
      <tr>
        <th>订单号(基础)</th><th>客户</th><th>拆分单</th><th>下单日期</th>
        <th>下单</th><th>裁剪</th><th>缝制</th><th>检查</th><th>包装</th><th>销售</th><th>状态</th>
      </tr>
    </thead>
    <tbody id="tbody"></tbody>
  </table>
  <div class="loading" id="loadmsg">数据加载中… 首次加载约 20 秒（需拉取 3 万+ 张作业卡），请稍候</div>
  <div class="empty" id="empty" style="display:none">无匹配订单</div>
</div>

<script>
let DATA = null;
const OPS = [['裁剪','裁剪'],['缝制','缝制'],['质检','检查'],['包装','包装']];

async function load(force){
  document.getElementById('hint').textContent = force ? '刷新中…(约 20 秒)' : '';
  const q = force ? '?refresh=1' : '';
  try{
    const res = await fetch('api/orders'+q, {cache:'no-store'});
    if(!res.ok) throw new Error('HTTP '+res.status);
    DATA = await res.json();
    document.getElementById('updated').textContent = DATA.updated_at || '—';
    const c = DATA.counts||{};
    document.getElementById('counts').textContent =
      'SO物料行 '+(c.so_rows??'—')+' ｜ 工单 '+(c.work_orders??'—')+
      ' ｜ 作业卡 '+(c.job_cards??'—')+' ｜ 出库行 '+(c.dn_rows??'—');
    document.getElementById('loadmsg').style.display='none';
    document.getElementById('hint').textContent = '';
    render();
  }catch(e){
    document.getElementById('loadmsg').textContent = '加载失败: '+e.message+'，请稍后刷新页面重试';
  }
}

function opCell(ops, key){
  const s = ops && ops[key];
  if(!s || !s.qty) return '<span class="zero">—</span>';
  return '<span class="qty">'+fmt(s.qty)+'</span><span class="t">'+(s.t||'')+'</span>';
}
function soldCell(qty, t){
  if(!qty) return '<span class="zero">—</span>';
  return '<span class="qty">'+fmt(qty)+'</span><span class="t">'+(t||'')+'</span>';
}

function render(){
  if(!DATA) return;
  const q = (document.getElementById('q').value||'').trim().toLowerCase();
  const tbody = document.getElementById('tbody');
  tbody.innerHTML = '';

  // 汇总卡
  let tO=0,tS=0; const tOps={};
  DATA.orders.forEach(o=>{
    tO+=o.ordered; tS+=o.sold_qty;
    OPS.forEach(([k])=>{ if(o.ops&&o.ops[k]) tOps[k]=(tOps[k]||0)+o.ops[k].qty; });
  });
  document.getElementById('cards').innerHTML =
    card('进行中订单', DATA.order_count) +
    card('总下单', fmt(tO)) +
    OPS.map(([k,label])=>card('总'+label, fmt(tOps[k]||0))).join('') +
    card('总销售', fmt(tS), 'var(--green)');

  const filtered = DATA.orders.filter(o =>
    !q || o.base_so.toLowerCase().includes(q) ||
    (o.customer||'').toLowerCase().includes(q) ||
    o.splits.join(' ').toLowerCase().includes(q) ||
    o.items.some(it=>(it.item_code||'').toLowerCase().includes(q)||(it.item_name||'').toLowerCase().includes(q)));

  document.getElementById('empty').style.display = filtered.length? 'none':'block';

  filtered.forEach((o, idx) => {
    const tr = document.createElement('tr');
    tr.className = 'order-row';
    tr.innerHTML =
      '<td class="base">'+o.base_so+' <span class="muted">▾</span></td>'+
      '<td>'+(o.customer||'')+'</td>'+
      '<td class="splits">'+o.splits.length+' 张</td>'+
      '<td>'+(o.order_date||'—')+'</td>'+
      '<td class="qty">'+fmt(o.ordered)+'</td>'+
      OPS.map(([k])=>'<td>'+opCell(o.ops,k)+'</td>').join('')+
      '<td>'+soldCell(o.sold_qty,o.sold_t)+'</td>'+
      '<td>'+o.statuses.map(s=>'<span class="badge">'+s+'</span>').join('')+
        (o.delivery_statuses.length? ' <span class="badge" style="background:#e8f3ec;color:#1f9d55">'+o.delivery_statuses.join('/')+'</span>':'')+'</td>';
    tr.onclick = ()=>toggle(idx);
    tbody.appendChild(tr);

    const dr = document.createElement('tr');
    dr.id = 'd'+idx; dr.className='detail'; dr.style.display='none';
    const items = o.items.map(it =>
      '<tr><td>'+it.item_code+'</td><td class="muted">'+(it.item_name||'')+'</td>'+
      '<td>'+(it.ordered? '<span class="qty">'+fmt(it.ordered)+'</span>':'<span class="zero">—</span>')+'</td>'+
      OPS.map(([k])=>'<td>'+opCell(it.ops,k)+'</td>').join('')+
      '<td>'+soldCell(it.sold_qty,it.sold_t)+'</td>'+
      '<td class="muted" style="font-size:11px">'+otherOps(it.ops)+'</td></tr>'
    ).join('');
    dr.innerHTML = '<td colspan="11"><table>'+
      '<thead><tr><th>物料</th><th>名称</th><th>下单</th><th>裁剪</th><th>缝制</th><th>检查</th><th>包装</th><th>销售</th><th>其他工序</th></tr></thead>'+
      '<tbody>'+items+'</tbody></table>'+
      '<div class="muted" style="font-size:11px;padding:6px 2px">拆分单: '+o.splits.join(' , ')+'</div></td>';
    tbody.appendChild(dr);
  });
}

// 4 大工序之外的工序 (翻面/拷边/锁扣眼等) 汇总展示
function otherOps(ops){
  if(!ops) return '';
  const main = new Set(OPS.map(([k])=>k));
  return Object.entries(ops).filter(([k,s])=>!main.has(k)&&s.qty)
    .map(([k,s])=>k+' '+fmt(s.qty)+' ('+(s.t||'').slice(0,10)+')').join('； ');
}

function toggle(idx){
  const d = document.getElementById('d'+idx);
  d.style.display = d.style.display==='none' ? 'table-row' : 'none';
}

function card(k,v,c){
  return '<div class="card"><div class="k">'+k+'</div><div class="v" style="'+(c?'color:'+c:'')+'">'+v+'</div></div>';
}
function fmt(n){ return (Math.round(n*100)/100).toLocaleString(); }

load(false);
</script>
</body>
</html>
"""
