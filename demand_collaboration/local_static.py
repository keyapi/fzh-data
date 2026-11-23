"""Build a static, self-contained mirror of the local demand workbench page.

Reuses `demand_collaboration/static/index.html` unchanged, embeds a captured
`/api/state` snapshot, and replaces the HTTP transport with a localStorage-backed
stand-in so proposals can be demonstrated inside EN without a backend.

No customer data is written to this file's source; the captured state is passed
in at build time and only lands in the generated private HTML.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

BANNER = """
<div id="demo-bar">
  <div class="demo-text"><strong>演示模式</strong> · 需求基准 2026-11-11 / USNJ 建议 2026-11-13 / 实时库存快照 2026-11-23 05:17 · 提案只保存在本浏览器，不上传、不审批、不写 EN</div>
  <div class="demo-role">
    <button type="button" data-demo-role="operator" class="active">运营视角</button>
    <button type="button" data-demo-role="reviewer">审核视角（模拟）</button>
  </div>
</div>
<style>
#demo-bar{position:sticky;top:0;z-index:9999;display:flex;gap:16px;align-items:center;justify-content:space-between;
  background:#a8582b;color:#fff;padding:8px 16px;font-size:12px;line-height:1.4}
#demo-bar .demo-text{max-width:78%}
#demo-bar .demo-role{display:flex;gap:6px;flex-shrink:0}
#demo-bar .demo-role button{border:1px solid rgba(255,255,255,.6);background:transparent;color:#fff;
  padding:4px 10px;border-radius:4px;cursor:pointer;font-size:12px}
#demo-bar .demo-role button.active{background:#fff;color:#a8582b}
.help{display:none !important}
</style>
<script>
(function(){
  const DATA = JSON.parse(document.getElementById('demo-state').textContent);
  const PKEY = 'demand-workbench:proposals:v1';
  const PUBKEY = 'demand-workbench:publications:v1';
  const ROLEKEY = 'demand-workbench:demo-role';
  function loadList(key){ try { const v = JSON.parse(localStorage.getItem(key) || '[]'); return Array.isArray(v) ? v : []; } catch(e){ return []; } }
  function save(key, list){ try { localStorage.setItem(key, JSON.stringify(list)); } catch(e){} }
  function currentRole(){ try { return localStorage.getItem(ROLEKEY) === 'reviewer' ? 'reviewer' : 'operator'; } catch(e){ return 'operator'; } }
  function buildState(){
    return Object.assign({}, DATA, {
      actor: {name: '演示'},
      role: currentRole(),
      proposals: loadList(PKEY),
      publications: loadList(PUBKEY)
    });
  }
  window.DEMAND_TRANSPORT = async function(path, options){
    options = options || {};
    const method = (options.method || 'GET').toUpperCase();
    let body = null;
    try { body = options.body ? JSON.parse(options.body) : null; } catch(e){}
    if (method === 'GET' && path === '/api/state') return buildState();
    if (method === 'POST' && path === '/api/proposals') {
      const list = loadList(PKEY);
      const existing = list.find(p => p.id === body.id);
      if (existing) return existing;
      const proposal = Object.assign({}, body, {
        status: 'submitted', revision: 1, author: '演示',
        created_at: new Date().toISOString()
      });
      list.push(proposal); save(PKEY, list); return proposal;
    }
    let decision = path.match(/^\\/api\\/proposals\\/([^/]+)\\/decision$/);
    if (method === 'POST' && decision) {
      const list = loadList(PKEY);
      const id = decodeURIComponent(decision[1]);
      const proposal = list.find(p => p.id === id);
      if (!proposal) throw new Error('提案不存在');
      if (body && body.revision !== undefined && body.revision !== proposal.revision) {
        throw new Error('状态已变化，请刷新后重试');
      }
      proposal.status = body.status;
      proposal.revision = (proposal.revision || 1) + 1;
      save(PKEY, list); return proposal;
    }
    if (method === 'POST' && path === '/api/publish') {
      const pubs = loadList(PUBKEY);
      const pub = {
        id: 'demo-pub-' + (pubs.length + 1),
        baseline_version: body.baseline_version,
        as_of: body.as_of,
        created_at: new Date().toISOString(),
        proposals: loadList(PKEY).filter(p => p.status === 'approved')
      };
      pubs.push(pub); save(PUBKEY, pubs); return pub;
    }
    let download = path.match(/^\\/api\\/publications\\/([^/]+)\\/download/);
    if (method === 'GET' && download) {
      const id = decodeURIComponent(download[1]);
      const pub = loadList(PUBKEY).find(p => p.id === id);
      if (!pub) throw new Error('快照不存在');
      return pub;
    }
    throw new Error('演示页面不支持该操作：' + path);
  };
  window.DEMO_SET_ROLE = function(role){
    try { localStorage.setItem(ROLEKEY, role); } catch(e){}
    if (typeof load === 'function') load();
    document.querySelectorAll('[data-demo-role]').forEach(b =>
      b.classList.toggle('active', b.dataset.demoRole === role));
  };
  document.addEventListener('DOMContentLoaded', function(){
    document.querySelectorAll('[data-demo-role]').forEach(b =>
      b.addEventListener('click', () => window.DEMO_SET_ROLE(b.dataset.demoRole)));
  });
})();
</script>
"""


def sha256_b64(text: str) -> str:
    return base64.b64encode(hashlib.sha256(text.encode('utf-8')).digest()).decode('ascii')


def build(base_html: str, state: dict) -> str:
    if '<body>' not in base_html or '<script>' not in base_html:
        raise ValueError('base page missing expected <body>/<script> markers')
    payload = json.dumps(state, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    data_tag = '<script type="application/json" id="demo-state">' + payload + '</script>'

    banner_markup = BANNER.split('<style>', 1)[0]
    banner_style = '<style>' + BANNER.split('<style>', 1)[1].split('<script>', 1)[0]
    transport_js = BANNER.split('<script>', 1)[1].rsplit('</script>', 1)[0]

    head, rest = base_html.split('<script>', 1)
    app_js, tail = rest.split('</script>', 1)
    csp = (
        "default-src 'none'; style-src 'unsafe-inline'; "
        f"script-src 'sha256-{sha256_b64(transport_js)}' 'sha256-{sha256_b64(app_js)}'; "
        "img-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'"
    )
    csp_meta = '<meta http-equiv="Content-Security-Policy" content="' + csp + '">'

    out = head.replace('<title>需求协同 · 运营工作台</title>',
                       '<title>订货协同工作台（演示）</title>', 1)
    out = out.replace('</title>', '</title>' + csp_meta + banner_style, 1)
    out = out.replace('<body>', '<body>' + banner_markup, 1)
    out += data_tag + '<script>' + transport_js + '</script>' + '<script>' + app_js + '</script>' + tail
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description='本地工作台 → EN 静态镜像生成器')
    parser.add_argument('--base-html', required=True, type=Path, help='demand_collaboration/static/index.html')
    parser.add_argument('--state', required=True, type=Path, help='抓取的 /api/state JSON')
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args(argv)

    base = args.base_html.read_text(encoding='utf-8')
    state = json.loads(args.state.read_text(encoding='utf-8'))
    doc = build(base, state)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(doc, encoding='utf-8')
    print(args.out, len(doc))


if __name__ == '__main__':
    main()
