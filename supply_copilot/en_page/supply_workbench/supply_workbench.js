/* Desk Page controller for /app/supply-workbench.
 * Deployed inside the trusted key_test app as
 *   key_test/page/supply_workbench/supply_workbench.js
 * The markup is a static, self-contained HTML file served by a System Manager
 * whitelisted method, then injected with iframe srcdoc. No data writes.
 */
frappe.pages['supply-workbench'].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: 'USNJ 补货协同工作台',
    single_column: true
  });
  const host = page.main.get ? page.main.get(0) : page.main;
  wrapper.classList.add('swb-desk-page');
  host.classList.add('swb-embed-host');
  const style = document.createElement('style');
  style.textContent = `
    .swb-desk-page.swb-fit-ancestor,.swb-desk-page .swb-fit-ancestor {
      min-height:0!important;min-width:0;overflow:clip;
      margin-bottom:0!important;padding-bottom:0!important;
    }
    .swb-desk-page .swb-embed-host {
      box-sizing:border-box;padding:0!important;margin:0!important;border:0;min-height:0;
    }
    .swb-desk-page .swb-embed-frame {
      display:block;width:100%;height:100%;min-height:0;border:0;
    }`;
  wrapper.appendChild(style);
  let pending = 0;
  let observer = null;
  let mounted = false;
  let previousHeight = -1;
  const ancestors = [];
  for (let node = host.parentElement; node; node = node.parentElement) {
    ancestors.push(node);
    if (node === wrapper) break;
  }
  function fit() {
    pending = 0;
    if (!mounted || !host.getClientRects().length) return;
    const top = host.getBoundingClientRect().top;
    const viewport = window.visualViewport;
    const bottom = viewport ? Math.min(window.innerHeight, viewport.offsetTop + viewport.height) : window.innerHeight;
    const height = Math.max(0, Math.floor(bottom - top));
    if (height !== previousHeight) {
      previousHeight = height;
      host.style.height = height + 'px';
    }
  }
  function scheduleFit() {
    if (mounted && !pending) pending = requestAnimationFrame(fit);
  }
  function mount() {
    if (mounted) { scheduleFit(); return; }
    mounted = true;
    ancestors.forEach(node => node.classList.add('swb-fit-ancestor'));
    window.addEventListener('resize', scheduleFit);
    window.addEventListener('orientationchange', scheduleFit);
    if (window.visualViewport) window.visualViewport.addEventListener('resize', scheduleFit);
    if (typeof ResizeObserver === 'function') {
      observer = new ResizeObserver(scheduleFit);
      // Header/ancestor changes can move the host without changing the frame contents.
      ancestors.forEach(node => observer.observe(node));
      wrapper.querySelectorAll('.page-head').forEach(node => observer.observe(node));
    }
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
    ancestors.forEach(node => node.classList.remove('swb-fit-ancestor'));
  }
  wrapper.swbMount = mount;
  wrapper.swbUnmount = unmount;
  if (frappe.router && frappe.router.on) {
    frappe.router.on('change', function () {
      if (frappe.get_route()[0] === 'supply-workbench') mount(); else unmount();
    });
  }
  mount();
  const status = document.createElement('p');
  status.className = 'text-muted';
  status.textContent = '正在读取补货协同工作台…';
  host.appendChild(status);

  frappe.xcall('key_test.demand_collaboration.supply_workbench_static.get_html')
    .then(function (markup) {
      const frame = document.createElement('iframe');
      frame.title = 'USNJ 补货协同工作台';
      frame.setAttribute('sandbox', 'allow-scripts allow-same-origin');
      frame.className = 'swb-embed-frame';
      frame.srcdoc = markup;
      status.remove();
      host.appendChild(frame);
      scheduleFit();
    })
    .catch(function () {
      status.textContent = '工作台加载失败：请确认 System Manager 权限、服务器 private/supply_workbench.html 及服务器日志。';
    });
};

frappe.pages['supply-workbench'].on_page_show = function (wrapper) {
  if (wrapper.swbMount) wrapper.swbMount();
};
frappe.pages['supply-workbench'].on_page_hide = function (wrapper) {
  if (wrapper.swbUnmount) wrapper.swbUnmount();
};
