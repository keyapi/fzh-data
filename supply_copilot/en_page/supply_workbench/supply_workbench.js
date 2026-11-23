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
  const status = document.createElement('p');
  status.className = 'text-muted';
  status.textContent = '正在读取补货协同工作台…';
  host.appendChild(status);

  frappe.xcall('key_test.demand_collaboration.supply_workbench_static.get_html')
    .then(function (markup) {
      const frame = document.createElement('iframe');
      frame.title = 'USNJ 补货协同工作台';
      frame.setAttribute('sandbox', 'allow-scripts allow-same-origin');
      frame.style.cssText = 'width:100%;height:calc(100vh - 160px);min-height:700px;border:0';
      frame.srcdoc = markup;
      status.remove();
      host.appendChild(frame);
    })
    .catch(function () {
      status.textContent = '工作台加载失败：请确认 System Manager 权限、服务器 private/supply_workbench.html 及服务器日志。';
    });
};
