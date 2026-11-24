/* Standard Page in the existing key_test app. The server returns only the fixed
 * private generator artifact; never accept script or markup from a URL/user. */
frappe.pages['supply-planning'].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({parent: wrapper, title: '供应链计划工作台', single_column: true});
  const main = page.main.get ? page.main.get(0) : page.main;
  wrapper.classList.add('supply-planning-page');
  main.classList.add('supply-planning-main');
  const container = document.createElement('div');
  container.className = 'supply-planning-surface';
  main.appendChild(container);
  const shadow = container.attachShadow({mode: 'open'});
  const hostStyle = document.createElement('style');
  hostStyle.textContent = `
    .supply-planning-page .supply-planning-main {padding:0!important;margin:0!important;border:0;box-sizing:border-box;min-height:0;}
    .supply-planning-page .supply-planning-surface {height:100%;min-height:0;min-width:0;}
    .supply-planning-page.supply-fit,.supply-planning-page .supply-fit {
      min-height:0!important;min-width:0;overflow:hidden;overflow:clip;margin-bottom:0!important;padding-bottom:0!important;
    }`;
  wrapper.appendChild(hostStyle);
  const status = document.createElement('p');
  status.textContent = '正在读取供应链计划工作台…';
  shadow.appendChild(status);
  const ancestors = [];
  for (let node = main.parentElement; node; node = node.parentElement) {
    ancestors.push(node);
    if (node === wrapper) break;
  }
  let mounted = false, pending = 0, observer = null, runtime = null, previousHeight = -1;
  function fit() {
    pending = 0;
    if (!mounted || !main.getClientRects().length) return;
    const rect = main.getBoundingClientRect();
    const viewport = window.visualViewport;
    const bottom = viewport ? Math.min(innerHeight, viewport.offsetTop + viewport.height) : innerHeight;
    const height = Math.max(0, Math.floor(bottom - rect.top));
    if (height !== previousHeight) { main.style.height = height + 'px'; previousHeight = height; }
    container.style.setProperty('--swb-host-left', rect.left + 'px');
    container.style.setProperty('--swb-host-bottom', Math.max(0, innerHeight - bottom) + 'px');
    container.style.setProperty('--swb-host-width', rect.width + 'px');
    container.style.setProperty('--swb-host-height', height + 'px');
  }
  function scheduleFit() { if (mounted && !pending) pending = requestAnimationFrame(fit); }
  function mount() {
    if (mounted) { scheduleFit(); return; }
    mounted = true;
    ancestors.forEach(node => node.classList.add('supply-fit'));
    window.addEventListener('resize', scheduleFit);
    window.addEventListener('orientationchange', scheduleFit);
    if (window.visualViewport) window.visualViewport.addEventListener('resize', scheduleFit);
    if (typeof ResizeObserver === 'function') {
      observer = new ResizeObserver(scheduleFit);
      ancestors.forEach(node => observer.observe(node));
      wrapper.querySelectorAll('.page-head').forEach(node => observer.observe(node));
      document.querySelectorAll('.navbar').forEach(node => observer.observe(node));
    }
    if (runtime) runtime.resume();
    scheduleFit();
  }
  function unmount() {
    mounted = false;
    if (pending) cancelAnimationFrame(pending);
    pending = 0;
    window.removeEventListener('resize', scheduleFit);
    window.removeEventListener('orientationchange', scheduleFit);
    if (window.visualViewport) window.visualViewport.removeEventListener('resize', scheduleFit);
    if (observer) observer.disconnect();
    observer = null;
    const dialog = shadow.querySelector('dialog[open]');
    if (dialog) dialog.close();
    if (runtime) runtime.pause();
    ancestors.forEach(node => node.classList.remove('supply-fit'));
  }
  wrapper.supplyPlanningMount = mount;
  wrapper.supplyPlanningUnmount = unmount;
  if (frappe.router && frappe.router.on) {
    frappe.router.on('change', function () {
      if (frappe.get_route()[0] === 'supply-planning') mount(); else unmount();
    });
  }
  mount();

  function createRuntime(surface) {
    const listeners = [], observers = [];
    let active = true;
    function on(target, type, fn, options) {
      listeners.push({target, type, fn, options});
      if (active) target.addEventListener(type, fn, options);
    }
    function off(target, type, fn, options) {
      target.removeEventListener(type, fn, options);
      const index = listeners.findIndex(item => item.target === target && item.type === type && item.fn === fn);
      if (index >= 0) listeners.splice(index, 1);
    }
    function eventProxy(target) {
      return new Proxy(target, {get(object, key) {
        if (key === 'addEventListener') return (type, fn, options) => on(target, type, fn, options);
        if (key === 'removeEventListener') return (type, fn, options) => off(target, type, fn, options);
        const value = Reflect.get(object, key, object);
        return typeof value === 'function' ? value.bind(object) : value;
      }});
    }
    const viewportProxy = window.visualViewport ? eventProxy(window.visualViewport) : null;
    const windowProxy = new Proxy(eventProxy(window), {get(object, key) {
      return key === 'visualViewport' ? viewportProxy : object[key];
    }});
    // No fallback to the host document: all content selection and focus are local.
    const documentProxy = {
      getElementById: id => shadow.getElementById(id),
      querySelector: selector => shadow.querySelector(selector),
      querySelectorAll: selector => shadow.querySelectorAll(selector),
      addEventListener: (...args) => shadow.addEventListener(...args),
      removeEventListener: (...args) => shadow.removeEventListener(...args),
      createElement: tag => document.createElement(tag),
      documentElement: surface, body: surface, readyState: 'complete',
      get activeElement() { return shadow.activeElement; }
    };
    class ScopedResizeObserver {
      constructor(fn) { this.observer = new ResizeObserver(fn); this.targets = []; observers.push(this); }
      observe(target, options) {
        this.targets.push({target, options});
        if (active) this.observer.observe(target, options);
      }
      disconnect() { this.observer.disconnect(); this.targets = []; }
    }
    return {
      documentProxy, windowProxy, ScopedResizeObserver,
      pause() {
        active = false;
        listeners.forEach(item => item.target.removeEventListener(item.type, item.fn, item.options));
        observers.forEach(item => item.observer.disconnect());
      },
      resume() {
        if (active) return;
        active = true;
        listeners.forEach(item => item.target.addEventListener(item.type, item.fn, item.options));
        observers.forEach(item => item.targets.forEach(({target, options}) => item.observer.observe(target, options)));
      }
    };
  }

  frappe.xcall('key_test.demand_collaboration.supply_planning_static.get_parts')
    .then(function (parts) {
      if (!parts || !['html', 'css', 'js'].every(key => typeof parts[key] === 'string')) {
        throw new Error('工作台片段格式不正确');
      }
      const style = document.createElement('style');
      style.textContent = parts.css.replace(/:root/g, ':host').replace(/html,body\{/g, ':host{')
        .replace(/(^|[}\n])body\{/g, '$1.supply-planning-root{') + `
        :host {display:block;height:100%;min-height:0;min-width:0;}
        .supply-planning-root {height:100%;min-height:0;min-width:0;overflow:hidden;overflow:clip;}
        .app-shell {height:100%;}
        dialog.sheet {left:var(--swb-host-left);right:auto;bottom:var(--swb-host-bottom);
          width:var(--swb-host-width);max-height:var(--swb-host-height);
          height:min(90dvh,var(--swb-host-height));}
        @media(max-height:480px){dialog.sheet{height:var(--swb-host-height);}}
        noscript{display:none;}`;
      const surface = document.createElement('div');
      surface.className = 'supply-planning-root';
      surface.innerHTML = parts.html;
      // Only the inert JSON data script may be present in injected HTML.
      if ([...surface.querySelectorAll('script')].some(script => script.type !== 'application/json')) {
        throw new Error('工作台 HTML 含非数据脚本');
      }
      runtime = createRuntime(surface);
      shadow.replaceChildren(style, surface);
      // This trusted generated script executes with a local document facade.
      // The Desk CSP must permit Function; errors are shown, never bypassed.
      const execute = new Function('document', 'window', 'ResizeObserver', 'requestAnimationFrame', parts.js);
      execute(runtime.documentProxy, runtime.windowProxy, runtime.ScopedResizeObserver, window.requestAnimationFrame.bind(window));
      if (!mounted) runtime.pause();
      scheduleFit();
    })
    .catch(function (error) {
      if (runtime) runtime.pause();
      status.textContent = '工作台加载失败：' + error.message + '。请检查 System Manager 权限、固定私有产物和 Desk CSP。';
      shadow.replaceChildren(status);
    });
};
frappe.pages['supply-planning'].on_page_show = function (wrapper) {
  if (wrapper.supplyPlanningMount) wrapper.supplyPlanningMount();
};
frappe.pages['supply-planning'].on_page_hide = function (wrapper) {
  if (wrapper.supplyPlanningUnmount) wrapper.supplyPlanningUnmount();
};
