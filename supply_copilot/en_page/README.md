---
type: Guide
title: Supply Workbench EN 接入产物
---

# Supply Workbench（/app/supply-workbench）EN 接入产物

本目录只放**部署产物模板**，不含任何客户数据或生成的 HTML。

- 页面生成器：`supply_copilot/workbench_page.py`（单文件 HTML，8 页签）
- EN 白名单读取：`supply_workbench_static.py`
- Desk Page 定义：`supply_workbench/supply_workbench.json` + `.js`

页面是只读演示页：数据全部内嵌，提案只存浏览器 `localStorage`
（键 `supply-workbench:proposals:v1`），不发起网络请求、不写 EN。

## 生成 HTML（在私有目录执行，产物不入库）

```bash
uv run python -m supply_copilot.workbench_page \
  --snapshot <snapshot.json> \
  --baseline <baseline.json> \
  --b-dir <B_*.csv 目录> \
  --out <私有目录>/supply_workbench.html
```

## 部署步骤（测试机先行）

假设 `key_test` app 已在 bench 中安装（当前生产页 `usnj-supply-copilot` 同样位于该 app）。

1. **生成并上传 HTML**（只读、单文件）：

   ```bash
   scp <私有目录>/supply_workbench.html <服务器>:~/frappe-bench/sites/erpnext.vilavi.cn/private/supply_workbench.html
   # 服务器上确保属主正确
   sudo chown frappe:frappe ~/frappe-bench/sites/erpnext.vilavi.cn/private/supply_workbench.html
   ```

2. **放入白名单方法**：把 `supply_workbench_static.py` 复制到 app 的
   `key_test/demand_collaboration/supply_workbench_static.py`
   （模块路径必须是 `key_test.demand_collaboration.supply_workbench_static`）。

3. **放入 Desk Page**：把 `supply_workbench/` 目录复制到
   `key_test/page/supply_workbench/`，即
   `key_test/page/supply_workbench/supply_workbench.json` 与 `.js`。

4. **迁移并刷新**：

   ```bash
   bench --site <site> migrate          # 注册 Standard Page（module: key_test）
   bench --site <site> clear-cache
   bench restart                        # 撞 long worker 时避开高峰期
   ```

5. 用 System Manager 账号打开 `/app/supply-workbench`，确认页签可切换、
   运营协同左右联动。

6. 测试站验证通过后，按项目发布链路合并到生产 app 仓库再部署生产
   （测试分支 → main → 生产 `git pull upstream` → migrate → clear-cache → restart）。

## 权限

`get_html()` 仅对 System Manager 开放；未登录或权限不足抛 `PermissionError`；
`private/supply_workbench.html` 不存在时抛 `NotFoundError`。方法不接受任何路径参数。

## 回滚

1. 从 Desk 删除 Page：`bench --site <site> console` 后执行
   `frappe.delete_doc("Page", "supply-workbench")`；或直接在 Page 列表中删除。
2. 删除 app 内文件：`key_test/page/supply_workbench/` 与
   `key_test/demand_collaboration/supply_workbench_static.py`。
3. 删除站点私有文件：`sites/<site>/private/supply_workbench.html`。
4. `bench --site <site> clear-cache && bench restart`。

回滚只移除新页面；`usnj-supply-copilot` 与 `demand-collaboration` 两页不受影响。
