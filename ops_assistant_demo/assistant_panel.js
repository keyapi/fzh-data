/* Presentation-only persistence. Permissions and executable actions stay server-owned. */
(() => {
  'use strict';
  const preferenceKey='ops-assistant-panel-v1', historyPrefix='ops-assistant-ui-v1:';
  let installed=false, isOpen=true, width=360, scope=null, resetCount=null, restoring=false, lastState=null;
  let aside, handle, launcher, toggle, contextLine, dragging=false;
  const get=id=>document.getElementById(id);
  const read=(storage,key)=>{try{return JSON.parse(storage.getItem(key)||'null');}catch{return null;}};
  const write=(storage,key,value)=>{try{storage.setItem(key,JSON.stringify(value));}catch{/* Storage denial must not block operations. */}};
  function maxWidth(){return Math.max(320,Math.min(640,window.innerWidth-596));}
  function clamp(value){return Math.round(Math.max(320,Math.min(maxWidth(),Number(value)||360)));}
  function preferences(){try{return read(window.localStorage,preferenceKey);}catch{return null;}}
  function persistPreferences(){try{write(window.localStorage,preferenceKey,{open:isOpen,width});}catch{}}
  function pendingCount(){return (lastState?.proposals||[]).filter(p=>p.status==='pending'&&p.expires_at*1000>Date.now()&&['counter','integration','bank_terminal','bank_parameter','bank_ip'].includes(p.scenario)&&(!p.scenario.startsWith('bank_')||p.version===lastState?.bank?.version)).length+(window.BankTaskUI?.pendingCount||0);}
  function updateContext(){
    if(!installed)return;const view=currentView(),bankPage=/^bank-/.test(view);
    const names={rules:'柜面限额',ticket:'变更申请',audit:'操作审计',integration:'联调配置',knowledge:'知识依据',safety:'安全实测',guide:'演示说明','bank-terminal':'终端注册','bank-parameter':'注册参数','bank-ip':'固定 IP 配置','bank-task':'接入工单'};
    contextLine.textContent='当前页面 · '+(names[view]||'业务操作');
    get('ask-input').placeholder=view==='bank-task'?'例如：核对这份工单并形成整组方案':view==='bank-ip'?'例如：删除最新 IP 配置':view==='bank-parameter'?'例如：把超时改为 75 秒':view==='bank-terminal'?'例如：查一下当前终端':view==='integration'?'例如：超时改为 60 秒，重试 1 次':view==='rules'?'例如：把限额改为 20 万':'描述需要查询或办理的事项';
    const chips=aside.querySelector('.chips');if(chips)chips.hidden=bankPage;
  }
  function paint(){
    if(!installed)return;width=clamp(width);
    document.documentElement.style.setProperty('--assistant-width',width+'px');
    document.documentElement.style.setProperty('--assistant-space',isOpen?width+'px':'0px');
    aside.hidden=!isOpen;handle.hidden=!isOpen;launcher.hidden=isOpen;
    toggle.setAttribute('aria-expanded',String(isOpen));handle.setAttribute('aria-valuenow',String(width));handle.setAttribute('aria-valuemax',String(maxWidth()));
    const count=pendingCount();launcher.textContent=count?`助手 · ${count} 项待确认`:'打开助手';launcher.setAttribute('aria-label',count?`打开助手，${count} 项待确认`:'打开助手');
    updateContext();
  }
  function open(focus=false){install();isOpen=true;paint();persistPreferences();if(focus)get('ask-input')?.focus();}
  function close(){install();save();isOpen=false;paint();persistPreferences();toggle.focus();}
  function small(value,depth=0){
    if(depth>4)return '[较长证据已省略]';if(typeof value==='string')return value.slice(0,1800);if(value===null||typeof value==='number'||typeof value==='boolean')return value;
    if(Array.isArray(value))return value.slice(0,8).map(item=>small(item,depth+1));
    if(value&&typeof value==='object'){const result={};for(const [key,item] of Object.entries(value).slice(0,20)){if(['proposal','digest','approved_digest','password','access_code'].includes(key))continue;result[key]=small(item,depth+1);}return result;}
    return undefined;
  }
  function messages(value){return (Array.isArray(value)?value:[]).filter(m=>m&&!m.transient&&['user','bot','deny','verification','evidence','long-answer','trace','citations','rails'].includes(m.kind)).slice(-60).map(m=>{
    const result={kind:m.kind};for(const key of ['text','values','independent','evidence','citations','rails','trace','items'])if(m[key]!==undefined)result[key]=small(m[key]);return result;
  });}
  function currentView(){return [...document.querySelectorAll('main > section[id^="view-"]')].find(section=>!section.hidden)?.id.replace(/^view-/,'')||'rules';}
  function save(){
    updateContext();
    if(!scope||restoring)return;const context={reset_count:resetCount,messages:messages(log),draft:String(get('ask-input')?.value||'').slice(0,3000),view:currentView(),terminal_id:window.BankUI?.activeTerminalId||null,task_id:lastState?.role==='operator'?window.BankTaskUI?.taskId||null:null};
    // Keep per-tab conversation UI small. No proposal object is stored or revived.
    while(JSON.stringify(context).length>90000&&context.messages.length)context.messages.shift();
    try{write(window.sessionStorage,historyPrefix+scope,context);}catch{}
  }
  function attach(state){
    if(!state||!state.workspace||!state.role)return;install();lastState=state;
    const next=String(state.workspace)+':'+String(state.role),count=Number(state.bank?.reset_count??state.reset_count??0);
    if(next===scope){if(resetCount!==count){resetCount=count;log=[];if(get('ask-input'))get('ask-input').value='';renderLog();save();}paint();return;}
    scope=next;resetCount=count;let stored;try{stored=read(window.sessionStorage,historyPrefix+scope);}catch{}
    restoring=true;
    try{
      if(stored&&stored.reset_count===count){
        log=messages(stored.messages);get('ask-input').value=String(stored.draft||'').slice(0,3000);renderLog();
        if(stored.view==='rehearsal')window.RehearsalUI?.show();
        else if(stored.view==='route-demo')window.RouteUI?.show();
        else if(stored.view==='bank-task'){window.BankTaskUI?.show();if(state.role==='operator'&&stored.task_id)window.BankTaskUI?.restore(stored.task_id);}
        else if(/^bank-(terminal|parameter|ip)$/.test(stored.view||''))window.BankUI?.show(stored.view.replace('bank-',''),stored.terminal_id);
        else if(['rules','ticket','audit','integration','knowledge','safety','guide'].includes(stored.view)&&!(state.role==='reader'&&stored.view==='ticket'))show(stored.view);
      }else{log=[];get('ask-input').value='';renderLog();}
    }finally{restoring=false;}
    paint();save();
  }
  function install(){
    if(installed)return;aside=document.querySelector('aside');if(!aside)return;installed=true;
    const pref=preferences();if(pref){isOpen=pref.open!==false;width=clamp(pref.width);}
    const style=document.createElement('style');style.textContent=`
      :root{--assistant-width:360px;--assistant-space:360px}body{min-width:596px;grid-template-columns:196px minmax(0,1fr) var(--assistant-space)}aside{position:fixed;top:48px;right:0;bottom:0;width:var(--assistant-width);box-shadow:-3px 0 12px rgba(14,48,88,.08)}aside[hidden],aside .chips[hidden]{display:none!important}#assistant-context{padding:8px 14px;color:#42658e;background:#eef4fb;border-bottom:1px solid #d7e3ef;font-size:12px}.mask{inset:48px var(--assistant-space) 0 0}#assistant-toggle{margin-left:0;white-space:nowrap}#assistant-close{margin-left:auto;background:#eef3fa;color:#22456e;border:1px solid #d3dfed;border-radius:4px;padding:5px 9px;cursor:pointer}#assistant-launcher{position:fixed;right:18px;bottom:20px;z-index:2147483647;background:#174b85;color:white;border:1px solid #3975b4;border-radius:24px;box-shadow:0 3px 14px #214d7b33;padding:12px 18px;font:inherit;cursor:pointer}#assistant-resize{position:fixed;top:48px;bottom:0;right:calc(var(--assistant-width) - 4px);width:8px;z-index:2147483647;cursor:col-resize;touch-action:none;background:transparent;border:0;padding:0}#assistant-resize:hover,#assistant-resize:focus-visible{background:#5b91c8;outline:2px solid #174b85;outline-offset:-2px}#assistant-resize[hidden],#assistant-launcher[hidden]{display:none!important}body.assistant-dragging,body.assistant-dragging *{cursor:col-resize!important;user-select:none!important}`;
    document.head.append(style);aside.id='assistant-panel';
    toggle=document.createElement('button');toggle.id='assistant-toggle';toggle.className='pill';toggle.type='button';toggle.textContent='AI 助手';toggle.setAttribute('aria-controls','assistant-panel');toggle.onclick=()=>isOpen?close():open(true);document.querySelector('header').append(toggle);
    const closeButton=document.createElement('button');closeButton.id='assistant-close';closeButton.type='button';closeButton.textContent='收起';closeButton.setAttribute('aria-label','收起 AI 助手');closeButton.onclick=close;aside.querySelector('.ahead').append(closeButton);
    contextLine=document.createElement('div');contextLine.id='assistant-context';aside.querySelector('.ahead').insertAdjacentElement('afterend',contextLine);
    launcher=document.createElement('button');launcher.id='assistant-launcher';launcher.type='button';launcher.onclick=()=>open(true);document.body.append(launcher);
    handle=document.createElement('div');handle.id='assistant-resize';handle.tabIndex=0;handle.setAttribute('role','separator');handle.setAttribute('aria-orientation','vertical');handle.setAttribute('aria-label','调整助手面板宽度');handle.setAttribute('aria-controls','assistant-panel');handle.setAttribute('aria-valuemin','320');document.body.append(handle);
    handle.onpointerdown=event=>{if(event.button!==0)return;dragging=true;handle.setPointerCapture(event.pointerId);document.body.classList.add('assistant-dragging');event.preventDefault();};
    handle.onpointermove=event=>{if(!dragging)return;width=clamp(window.innerWidth-event.clientX);paint();};
    const stop=()=>{dragging=false;document.body.classList.remove('assistant-dragging');persistPreferences();};handle.onpointerup=stop;handle.onpointercancel=stop;handle.onlostpointercapture=stop;
    handle.onkeydown=event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();width=event.key==='Home'?320:event.key==='End'?maxWidth():clamp(width+(event.key==='ArrowLeft'?20:-20));paint();persistPreferences();};
    get('ask-input').addEventListener('input',save);document.addEventListener('click',()=>queueMicrotask(save));window.addEventListener('pagehide',save);window.addEventListener('resize',paint);
    paint();if(typeof opsState!=='undefined'&&opsState)attach(opsState);
  }
  window.AssistantPanel={open,close,attach,save};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install);else install();
})();
