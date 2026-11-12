/* Copy into an installed app's demand-collaboration Desk Page script.
 * This is a Page controller, NOT a schema/permission installer.
 * Assumes package installed as key_test.demand_collaboration.
 */
frappe.pages['demand-collaboration'].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: '运营需求协同',
    single_column: true
  });
  const host = page.main.get ? page.main.get(0) : page.main;
  const status = document.createElement('p');
  status.textContent = '正在读取需求协同工作台…';
  host.appendChild(status);
  frappe.xcall('key_test.demand_collaboration.frappe_bridge.get_workbench_html')
    .then(function (markup) {
      const frame = document.createElement('iframe');
      frame.title = '运营需求协同';
      frame.setAttribute('sandbox', 'allow-scripts allow-same-origin allow-forms');
      frame.style.cssText = 'width:100%;height:calc(100vh - 160px);min-height:700px;border:0';
      frame.srcdoc = markup;
      status.remove();
      host.appendChild(frame);
    })
    .catch(function () {
      status.textContent = '工作台加载失败：请确认需求协同角色、安装路径及服务器日志。';
    });
};
