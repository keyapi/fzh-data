/* Synthetic bank operation pages. Backend state remains the sole authority. */
(() => {
  'use strict';
  const specs = {
    terminal: {title:'终端注册', plural:'terminals', fields:[
      ['terminal_code','终端编号'],['terminal_name','终端名称'],['tenant_code','租户编号'],['max_concurrency','最大并发数','number'],['protocol','协议','select',['HTTPS','HTTP']],['encoding','字符编码','select',['UTF-8','GBK']],['endpoint','服务地址'],['sign_method','签名方式','select',['HMAC-SHA256','RSA-SHA256','NONE']],['callback_mode','回调方式','select',['SYNC','ASYNC']],['environment','环境','select',['test']]], columns:['terminal_code','terminal_name','tenant_code','max_concurrency','protocol']},
    parameter: {title:'注册参数', plural:'parameters', fields:[['terminal_id','所属终端','terminal'],['name','参数名称'],['value','参数值'],['value_type','值类型','select',['text','number','secret']],['note','参数说明']], columns:['terminal_id','name','value','value_type','note']},
    ip: {title:'固定 IP 配置', plural:'ip_configs', fields:[['terminal_id','所属终端','terminal'],['tenant_code','租户编号'],['tenant_id','租户 ID'],['front_address','前置地址'],['front_port','前置端口','number'],['client_address','客户端地址'],['client_port','客户端端口','number']], columns:['terminal_id','tenant_code','front_address','front_port','client_address','client_port']}
  };
  const defaults = {
    terminal:{terminal_code:'DEMO-T003',terminal_name:'演示渠道终端',tenant_code:'DEMO-3101',max_concurrency:10,protocol:'HTTPS',encoding:'UTF-8',endpoint:'https://192.0.2.30:8443/demo',sign_method:'HMAC-SHA256',callback_mode:'SYNC',environment:'test'},
    parameter:{name:'response_mode',value:'SYNC',value_type:'text',note:'演示响应模式'},
    ip:{tenant_code:'DEMO-3101',tenant_id:'DEMO-TENANT-01',front_address:'203.0.113.20',front_port:443,client_address:'198.51.100.20',client_port:8443}
  };
  let bank=null, current='terminal', installed=false, loading=null, loadingEpoch=null, activeTerminal=null, renderedReset=null;
  const pages={terminal:1,parameter:1,ip:1}, selected={}, filters={}, restored={}, pageSize=6;
  const el=id=>document.getElementById(id), escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const label=(entity,key)=>specs[entity].fields.find(f=>f[0]===key)?.[1]||key;
  const terminalName=id=>{const t=bank?.terminals?.find(t=>String(t.id)===String(id));return t?`${t.terminal_code} · ${t.terminal_name}`:String(id||'—');};
  function display(entity,key,value,record={}) {return key==='terminal_id'?terminalName(value):key==='value'&&record.value_type==='secret'?'••••••（模拟密钥）':String(value??'—');}
  function input(entity,field) {
    const [key,title,type,options]=field,id=`bank-${entity}-${key}`;
    if(type==='select'||type==='terminal')return `<label>${title}<select id="${id}" name="${key}">${type==='terminal'?'':options.map(v=>`<option value="${escape(v)}">${escape(v==='test'?'测试 / 模拟':v)}</option>`).join('')}</select></label>`;
    return `<label>${title}<input id="${id}" name="${key}" type="${type==='number'?'number':'text'}" ${type==='number'?'min="0" step="1"':''} autocomplete="off" /></label>`;
  }
  function install() {
    if(installed)return;installed=true;
    const css=document.createElement('style');css.textContent=`
      .bank-view .bank-tabs{display:flex;background:#153d70;color:white;padding:10px 16px;font-weight:600;border-radius:3px 3px 0 0;gap:14px}
      .bank-view .bank-tabs span+span{border-left:1px solid #6683a5;padding-left:14px}.bank-view .bank-tools{display:flex;align-items:end;gap:12px;padding:13px;background:#f4f7fb;flex-wrap:wrap}.bank-view .bank-tools label{display:grid;gap:5px}
      .bank-view .bank-table{width:100%;border-collapse:collapse}.bank-table th{background:#e5edf7;border:1px solid #d2deeb;white-space:nowrap}.bank-table td{border-bottom:1px solid #d7e0eb;padding:11px}.bank-table tr[data-id]{cursor:pointer}.bank-table tr[data-selected=true]{background:#e6f0fc;box-shadow:inset 3px 0 #2473bc}
      .bank-view .bank-editor{margin-top:18px;border:1px solid #d0ddea;background:white}.bank-view .bank-editor h2{margin:0;background:#e5edf7;padding:11px 15px;border-left:4px solid #19548e;font-size:15px}.bank-view .bank-form{padding:16px;display:grid;grid-template-columns:repeat(2,minmax(150px,1fr));gap:13px 22px}.bank-form label{display:grid;gap:6px;font-size:13px}.bank-form input,.bank-form select{width:100%;box-sizing:border-box;padding:9px;border:1px solid #b7c8da;border-radius:3px;font-size:14px}.bank-view .bank-actions{display:flex;gap:10px;padding:0 16px 16px;flex-wrap:wrap}.bank-view .bank-message{margin:12px 0;padding:12px;border-left:4px solid #4b7fae;background:#eef4fb;overflow-wrap:anywhere}.bank-view .bank-message.error{border-color:#c54444;background:#fff0f0}.bank-view .bank-message.success{border-color:#228253;background:#edf8f1}.bank-view .bank-pagebar{display:flex;gap:10px;align-items:center;justify-content:end;padding:10px}.bank-view .bank-scroll{overflow:auto}.bank-view [data-bank-confirm]{background:#176839;color:white;border:0;padding:10px 16px;border-radius:4px}.bank-view .bank-pending{padding:14px;background:#fff7e5;border:1px solid #e9d29e;margin-top:12px}.bank-view .bank-pending p{margin:0 0 10px}.bank-view input:disabled,.bank-view select:disabled{background:#f3f5f8;color:#52677b}@media(max-width:800px){.bank-view .bank-form{grid-template-columns:1fr}.bank-view .bank-tools{align-items:stretch}}`;
    document.head.append(css);
    const nav=document.querySelector('nav'),heading=document.createElement('h2');heading.textContent='渠道接入（模拟）';nav.append(heading);
    for(const [entity,spec] of Object.entries(specs)){
      const button=document.createElement('button');button.type='button';button.id=`nav-bank-${entity}`;button.textContent=spec.title;button.onclick=()=>{if(busy)return;const terminalId=activeTerminalId();showBank(entity,terminalId);};nav.append(button);
      const section=document.createElement('section');section.id=`view-bank-${entity}`;section.hidden=true;section.className='bank-view';
      section.innerHTML=`<div class="crumb">科技运营 / 渠道接入 / ${spec.title}</div><div class="page-head"><h1>${spec.title}</h1></div><p class="notice">全模拟业务数据 · 保存前核对具体差异 · 后台岗位权限校验 · 保存后独立读回</p><div class="bank-tabs"><span>${spec.title}列表</span><span>测试 / 模拟</span></div><div class="bank-tools">${entity==='terminal'?'<label>终端名称或编号<input id="bank-terminal-search" placeholder="按编号 / 名称筛选" /></label>':`<label>所属终端<select id="bank-${entity}-filter"><option value="">全部终端</option></select></label>`}<button type="button" id="bank-${entity}-query">查询</button><button type="button" id="bank-${entity}-new">新增</button><button class="solid" type="button" id="bank-${entity}-assistant">让助手${entity==='terminal'?'新增终端':entity==='parameter'?'修改参数':'配置 IP'}</button><span id="bank-${entity}-count" class="muted"></span></div><div class="bank-scroll"><table class="bank-table"><thead><tr>${spec.columns.map(key=>`<th>${label(entity,key)}</th>`).join('')}<th>操作</th></tr></thead><tbody id="bank-${entity}-rows"></tbody></table></div><div class="bank-pagebar"><button type="button" id="bank-${entity}-prev">上一页</button><span id="bank-${entity}-page"></span><button type="button" id="bank-${entity}-next">下一页</button></div><div class="bank-editor"><h2 id="bank-${entity}-editor-title">新增${spec.title}</h2><form class="bank-form" id="bank-${entity}-form">${spec.fields.map(f=>input(entity,f)).join('')}<label>操作说明<input id="bank-${entity}-reason" value="演示渠道接入维护" /></label></form><div class="bank-actions"><button class="solid" type="button" id="bank-${entity}-save">准备保存</button><button type="button" id="bank-${entity}-discard">清空 / 新建</button><span class="muted">准备只填写；批准一次后才保存。</span></div></div><div class="bank-pending" id="bank-${entity}-pending" hidden><p id="bank-${entity}-diff"></p><button type="button" data-bank-confirm="${entity}">确认保存</button> <button type="button" data-bank-cancel="${entity}">取消</button></div><div class="bank-message" id="bank-${entity}-message" hidden></div>`;
      document.querySelector('main').append(section);
      el(`bank-${entity}-query`).onclick=async()=>{if(busy)return;busy=true;try{await spotlight(el(`bank-${entity}-query`),'查询当前后台数据',120);filters[entity]=entity==='terminal'?el('bank-terminal-search').value.trim():el(`bank-${entity}-filter`).value;pages[entity]=1;await load();await spotlight(el(`bank-${entity}-rows`),'查询结果',450);}catch(err){message(entity,err.message,true);}finally{busy=false;clearAim();renderApproval();}};
      el(`bank-${entity}-new`).onclick=()=>newRecord(entity);el(`bank-${entity}-discard`).onclick=()=>newRecord(entity);
      el(`bank-${entity}-form`).onsubmit=e=>e.preventDefault();el(`bank-${entity}-save`).onclick=()=>prepare(entity);
      el(`bank-${entity}-prev`).onclick=()=>{if(busy)return;pages[entity]=Math.max(1,pages[entity]-1);render();};el(`bank-${entity}-next`).onclick=()=>{if(busy)return;pages[entity]++;render();};
      section.querySelector('[data-bank-confirm]').onclick=()=>approve(pending(entity));section.querySelector('[data-bank-cancel]').onclick=()=>cancel(pending(entity));
      el(`bank-${entity}-assistant`).onclick=()=>ask(example(entity),entity);
      if(entity==='parameter')el('bank-parameter-value_type').onchange=()=>{el('bank-parameter-value').type=el('bank-parameter-value_type').value==='secret'?'password':'text';};
    }
  }
  function activeTerminalId(){if(current==='terminal')return selected.terminal||activeTerminal||bank?.terminals?.[0]?.id||null;return el(`bank-${current}-terminal_id`)?.value||activeTerminal||bank?.terminals?.[0]?.id||null;}
  function showBank(entity,terminalId=null) {
    install();if(!specs[entity])entity='terminal';current=entity;
    if(terminalId&&bank?.terminals?.some(t=>String(t.id)===String(terminalId))){activeTerminal=String(terminalId);if(entity!=='terminal'){const record=(bank[specs[entity].plural]||[]).find(r=>r.id===selected[entity]);if(record&&String(record.terminal_id)!==activeTerminal)fill(entity,{...defaults[entity],terminal_id:activeTerminal});filters[entity]=activeTerminal;pages[entity]=1;el(`bank-${entity}-terminal_id`).value=activeTerminal;el(`bank-${entity}-filter`).value=activeTerminal;}}
    document.querySelectorAll('main > section[id^="view-"]').forEach(section=>section.hidden=section.id!==`view-bank-${entity}`);
    document.querySelectorAll('nav button').forEach(button=>button.toggleAttribute('aria-current',button.id===`nav-bank-${entity}`));
    load().catch(err=>message(entity,err.message,true));
  }
  async function load(){if(loading&&loadingEpoch===opsEpoch)return loading;const requestEpoch=opsEpoch;loadingEpoch=requestEpoch;const flight=(async()=>{const data=await opsFetch('/api/bank/state');if(requestEpoch!==opsEpoch)return bank;bank=data.bank;if(data.state)opsState=data.state;render();renderApproval();return bank;})();loading=flight;try{return await flight;}finally{if(loading===flight)loading=null;}}
  function pending(entity){return (opsState?.proposals||[]).filter(p=>p.status==='pending'&&p.scenario===`bank_${entity}`&&p.version===bank?.version&&p.expires_at*1000>Date.now()).at(-1);}
  function fill(entity,record={}) {
    selected[entity]=record.id||null;el(`bank-${entity}-editor-title`).textContent=(record.id?'编辑':'新增')+specs[entity].title;
    if(entity===current){const terminalId=entity==='terminal'?record.id:record.terminal_id;if(terminalId)activeTerminal=terminalId;}
    if(entity==='parameter')el('bank-parameter-value').type=record.value_type==='secret'?'password':'text';
    for(const [key] of specs[entity].fields){const input=el(`bank-${entity}-${key}`);input.value=record[key]??(key==='terminal_id'?bank?.terminals?.[0]?.id:'')??'';}
    if(entity==='parameter')el('bank-parameter-value').type=record.value_type==='secret'?'password':'text';
  }
  function newRecord(entity){if(busy)return;fill(entity,{...defaults[entity],terminal_id:filters[entity]||bank?.terminals?.[0]?.id});message(entity,'填写后点“准备保存”，核对差异后批准。');render();}
  function render() {
    if(!installed)return;if(opsState?.bank)bank=opsState.bank;if(!bank)return;
    const reset=renderedReset!==null&&bank.reset_count!==renderedReset;renderedReset=bank.reset_count;
    if(activeTerminal&&!bank.terminals?.some(t=>String(t.id)===String(activeTerminal)))activeTerminal=bank.terminals?.[0]?.id||null;
    for(const [entity,spec] of Object.entries(specs)){
      if(entity!=='terminal'&&filters[entity]&&!bank.terminals?.some(t=>String(t.id)===String(filters[entity])))filters[entity]='';
      const optionHTML=(bank.terminals||[]).map(t=>`<option value="${escape(t.id)}">${escape(t.terminal_code)} · ${escape(t.terminal_name)}</option>`).join('');
      if(entity!=='terminal')for(const id of [`bank-${entity}-terminal_id`,`bank-${entity}-filter`]){const select=el(id),old=select.value;select.innerHTML=(id.endsWith('-filter')?'<option value="">全部终端</option>':'')+optionHTML;if([...select.options].some(o=>o.value===old))select.value=old;}
      if(reset||(selected[entity]&&!(bank[spec.plural]||[]).some(record=>record.id===selected[entity]))){selected[entity]=null;restored[entity]=null;fill(entity,{...defaults[entity],terminal_id:activeTerminal||bank.terminals?.[0]?.id});}
      let rows=bank[spec.plural]||[];if(filters[entity])rows=rows.filter(record=>entity==='terminal'?`${record.terminal_code} ${record.terminal_name}`.toLowerCase().includes(filters[entity].toLowerCase()):String(record.terminal_id)===filters[entity]);
      const totalPages=Math.max(1,Math.ceil(rows.length/pageSize));pages[entity]=Math.min(pages[entity],totalPages);
      el(`bank-${entity}-rows`).innerHTML=rows.slice((pages[entity]-1)*pageSize,pages[entity]*pageSize).map(record=>`<tr data-id="${escape(record.id)}" data-selected="${selected[entity]===record.id}">${spec.columns.map(key=>`<td>${escape(display(entity,key,record[key],record))}</td>`).join('')}<td><button type="button" class="link" data-edit="${escape(record.id)}">${role()==='operator'?'修改':'查看'}</button>${role()==='operator'?` <button type="button" class="link" data-delete="${escape(record.id)}">删除</button>`:''}</td></tr>`).join('')||`<tr><td colspan="${spec.columns.length+1}" class="empty">没有记录${bank.terminals?.length?'，可新增模拟配置':'，请先注册终端'}</td></tr>`;
      el(`bank-${entity}-rows`).querySelectorAll('tr[data-id]').forEach(tr=>{tr.onclick=event=>{if(busy||event.target.closest('[data-delete]'))return;const record=(bank[spec.plural]||[]).find(r=>r.id===tr.dataset.id);fill(entity,record);render();};});
      el(`bank-${entity}-rows`).querySelectorAll('[data-delete]').forEach(button=>button.onclick=()=>prepare(entity,'delete',button.dataset.delete));
      el(`bank-${entity}-page`).textContent=`第 ${pages[entity]} / ${totalPages} 页`;el(`bank-${entity}-count`).textContent=`${rows.length} 条`;
      el(`bank-${entity}-prev`).disabled=busy||pages[entity]===1;el(`bank-${entity}-next`).disabled=busy||pages[entity]===totalPages;
      for(const suffix of ['new','save','discard','assistant'])el(`bank-${entity}-${suffix}`).disabled=busy||role()!=='operator';
      el(`bank-${entity}-form`).querySelectorAll('input,select').forEach(input=>input.disabled=busy||role()!=='operator');
      if(!el(`bank-${entity}-${spec.fields[0][0]}`).value)fill(entity,{...defaults[entity],terminal_id:bank.terminals?.[0]?.id});
      const p=pending(entity);el(`bank-${entity}-pending`).hidden=!p||role()!=='operator';if(p){el(`bank-${entity}-diff`).textContent=describe(p);if(restored[entity]!==p.id){const record=(bank[spec.plural]||[]).find(r=>r.id===p.record_id)||{};fill(entity,{...record,...(p.values||{}),id:p.record_id||null});restored[entity]=p.id;}}else restored[entity]=null;
      el(`view-bank-${entity}`).querySelector('[data-bank-confirm]').disabled=busy;el(`view-bank-${entity}`).querySelector('[data-bank-cancel]').disabled=busy;
    }
  }
  function message(entity,text,error=false,success=false){const box=el(`bank-${entity}-message`);box.hidden=false;box.className='bank-message'+(error?' error':success?' success':'');box.textContent=String(text||'');}
  function describe(p,compact=false){const entity=p.entity||p.scenario?.replace('bank_','');if(!specs[entity])return '请核对待确认修改';const action={create:'新增',update:'修改',delete:'删除'}[p.action]||'修改';const record={...((bank?.[specs[entity].plural]||[]).find(r=>r.id===p.record_id)||{}),...(p.values||{})};const changes=p.changes||[],valueType=changes.find(c=>c.field==='value_type');if(valueType?.after==='secret'||valueType?.before==='secret')record.value_type='secret';const shown=compact&&changes.length>3?changes.slice(0,3):changes;const details=shown.map(c=>`${label(entity,c.field)}：${display(entity,c.field,c.before,record)} → ${display(entity,c.field,c.after,record)}`).join('；');if(compact&&entity==='ip'&&p.action==='delete'){return '删除固定 IP · '+record.front_address+':'+record.front_port+' → '+record.client_address+':'+record.client_port+'。允许后仅删除这一条记录。';}if(compact){const identity=entity==='terminal'?record.terminal_code||record.terminal_name:terminalName(record.terminal_id);return `${action}${specs[entity].title}${identity?' · '+identity:''}，${changes.length}项字段。${details||'核对页面记录'}${changes.length>3?'；其余'+(changes.length-3)+'项请在页面核对':''}。允许后才保存。`;}return `${action}${specs[entity].title}。${details||'核对页面记录'}。批准后才保存模拟数据。`;}
  async function prepare(entity,action,recordId) {
    if(busy)return;busy=true;render();try{
      const values={};for(const [key,,type] of specs[entity].fields)values[key]=type==='number'?Number(el(`bank-${entity}-${key}`).value):el(`bank-${entity}-${key}`).value.trim();
      if(entity==='parameter'&&selected[entity]){const original=(bank.parameters||[]).find(record=>record.id===selected[entity]);if(original?.value_type==='secret'&&values.value_type==='secret'&&values.value===original.value)delete values.value;}
      const data=await opsFetch('/api/bank/propose',{entity,action:action||(selected[entity]?'update':'create'),record_id:recordId||selected[entity]||null,values:action==='delete'?{}:values,reason:el(`bank-${entity}-reason`).value.trim()});
      if(data.state){opsState=data.state;renderOps();}if(data.bank)bank=data.bank;
      if(data.proposal){await preview(data.proposal);push({kind:'bot',text:'已准备，请核对后允许保存。（人工操作，不调用模型）'});}else message(entity,data.message||'当前已是目标值，无需重复保存。');
    }catch(err){message(entity,err.message,true);push({kind:'deny',text:err.message});}finally{busy=false;clearAim();render();renderApproval();}
  }
  async function preview(p){const entity=p.entity||p.scenario.replace('bank_','');restored[entity]=p.id;showBank(entity);await load();const record=(bank[specs[entity].plural]||[]).find(r=>r.id===p.record_id)||{};fill(entity,record);selected[entity]=p.record_id||null;if(entity==='parameter'&&(p.values?.value_type==='secret'||record.value_type==='secret'))el('bank-parameter-value').type='password';
    if(p.action!=='delete'){const values=p.action==='update'?Object.fromEntries((p.changes||[]).map(c=>[c.field,c.after])):p.values||Object.fromEntries((p.changes||[]).map(c=>[c.field,c.after]));const entries=Object.entries(values).filter(([key])=>el(`bank-${entity}-${key}`));const budget=1100/Math.max(1,entries.length);for(const [key,value] of entries){const input=el(`bank-${entity}-${key}`);await spotlight(input,`填写${label(entity,key)} · 尚未保存`,70,120);if(input.tagName==='SELECT')input.value=String(value);else await typeVisible(input,String(value),budget);}if(entity==='parameter')el('bank-parameter-value').type=el('bank-parameter-value_type').value==='secret'?'password':'text';}
    else{const row=[...el(`bank-${entity}-rows`).querySelectorAll('[data-id]')].find(row=>row.dataset.id===p.record_id);await spotlight(row||el(`bank-${entity}-rows`),'待删除记录 · 尚未删除',350);}
    if(p.reason)el(`bank-${entity}-reason`).value=p.reason;message(entity,'尚未保存。核对差异后，在对话里允许或点“确认保存”。');render();renderApproval();
  }
  async function approve(p){if(!p||busy)return;busy=true;const entity=p.entity||p.scenario.replace('bank_','');showBank(entity);render();try{await spotlight(el(`view-bank-${entity}`).querySelector('[data-bank-confirm]'),'已获批准 · 后台核对权限后执行',150);const data=await opsFetch('/api/ops/execute',{proposal_id:p.id,digest:p.digest});if(data.state){opsState=data.state;renderOps();}else await loadOps();await load();const verification=data.verification||data.readback;
      if(!verification||verification.passed===false)throw new Error('未收到后台读回证据，请刷新核对；不能宣称核验成功');
      const text=data.code==='ALREADY_EXECUTED'?'该操作已处理，未重复写入。':p.action==='delete'?'记录已删除，并从后台独立核验。':'已保存，并从后台独立核验。';message(entity,text,false,true);push({kind:'verification',text,values:`${specs[entity].title} · ${p.action==='delete'?'记录已移除':'已保存模拟配置'}`,independent:!!data.verification,evidence:verification});selected[entity]=null;await spotlight(el(`bank-${entity}-message`),text,800);
    }catch(err){message(entity,err.message,true);push({kind:'deny',text:err.message});}finally{busy=false;clearAim();render();renderApproval();}}
  async function cancel(p){if(!p||busy)return;busy=true;const entity=p.entity||p.scenario.replace('bank_','');try{await spotlight(el(`view-bank-${entity}`).querySelector('[data-bank-cancel]'),'取消本次操作 · 不保存',120);await opsFetch('/api/ops/cancel',{proposal_id:p.id});await loadOps();await load();message(entity,'已取消，后台记录未改变。');push({kind:'bot',text:'已取消，未保存。'});}catch(err){message(entity,err.message,true);}finally{busy=false;clearAim();render();renderApproval();}}
  function example(entity){const terminal=bank?.terminals?.find(t=>String(t.id)===el(`bank-${entity}-terminal_id`)?.value)||bank?.terminals?.[0];if(entity==='terminal')return '新增测试终端 DEMO-T003，名称“演示渠道终端”，租户 DEMO-3101，最大并发 10，协议 HTTPS，编码 UTF-8，服务地址 https://192.0.2.30:8443/demo，签名 HMAC-SHA256，回调 SYNC。';if(!terminal)return '请先注册一个模拟终端。';return entity==='parameter'?`为终端 ${terminal.terminal_code} 将 timeout_seconds 参数改为 75，值类型 number，说明“演示请求超时秒数”。`:`为终端 ${terminal.terminal_code} 新增固定 IP 配置，租户编号 DEMO-3101，租户 ID DEMO-TENANT-01，前置地址 203.0.113.20 端口 443，客户端地址 198.51.100.20 端口 8443。`;}
  function scenarioFor(text,fallback){if(/\bIP\b|固定\s*IP|前置地址|客户端地址/i.test(text))return 'ip';if(/注册参数|timeout_seconds|参数名称|参数值/.test(text))return 'parameter';if(/终端注册|注册终端|新增终端|终端编号|终端名称|最大并发/.test(text))return 'terminal';if(/限额|金额|柜面|单笔|联调/.test(text))return null;if(!el(`view-bank-${current}`)?.hidden)return current;if(/重试|超时/.test(text))return null;return fallback||null;}
  async function ask(text,entity=current){if(busy)return;if(typeof window.askBank==='function')return window.askBank(text,entity);push({kind:'deny',text:'助手接入尚未完成，请使用页面人工操作；保存仍需批准。'});}
  window.BankUI={install,show:showBank,load,render,preview,approve,cancel,scenarioFor,ask,describe,get activeTerminalId(){return activeTerminalId();},get state(){return bank;}};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install);else install();
})();
