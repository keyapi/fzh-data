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
（键 `supply-workbench:proposals:v1`）。刷新保留；清理浏览器数据或换浏览器
看不到本浏览器的提案。页面不发起网络请求、不写 EN。

## 安全策略（CSP）

生成的 HTML 在 `<head>` 首部带 `Content-Security-Policy` meta：

```
default-src 'none'; style-src 'unsafe-inline'; connect-src 'none';
form-action 'none'; base-uri 'none'; img-src data:;
script-src 'sha256-<内联脚本1>' 'sha256-<内联脚本2>'
```

- `script-src` **只用 sha256 哈希**，没有 `unsafe-inline`；两个内联 `<script>`
  的哈希由生成器按内容计算（数据块一并列入，无害）。页面无内联 `on*`
  事件属性，交互全部 `addEventListener`。
- 无任何外链资源（无 `<link>`、无 `src=`/`href=`）。
- **不要手工编辑生成的 HTML**：改动任一内联脚本都会让哈希失配、整页脚本被浏览器拒绝；
  任何改动都应改生成器后重新生成。

## 生成 HTML（在私有目录执行，产物不入库）

```bash
uv run python -m supply_copilot.workbench_page \
  --snapshot <snapshot.json> \
  --baseline <baseline.json> \
  --b-dir <B_*.csv 目录> \
  --out <私有目录>/supply_workbench.html
```

## 部署前备份

在 `~/frappe-bench` 下执行：

```bash
mkdir -p /tmp/supply-workbench-backup
# 1. key_test app 当前 HEAD 与工作区状态
cd ~/frappe-bench/apps/key_test
git rev-parse HEAD | tee /tmp/supply-workbench-backup/key_test.HEAD
git status --porcelain | tee /tmp/supply-workbench-backup/key_test.status
cd ~/frappe-bench
# 2. 同名 Page doc（若不存在会报错，记录报错即可）
bench --site <site> execute frappe.client.get \
  --args '{"doctype":"Page","name":"supply-workbench"}' \
  > /tmp/supply-workbench-backup/Page.supply-workbench.json 2>/tmp/supply-workbench-backup/Page.err || true
# 3. 旧 private HTML 的 sha256 与副本（若不存在则记录 not-present）
if [ -f sites/<site>/private/supply_workbench.html ]; then
  sha256sum sites/<site>/private/supply_workbench.html | tee /tmp/supply-workbench-backup/old_html.sha256
  cp -a sites/<site>/private/supply_workbench.html /tmp/supply-workbench-backup/
else
  echo "not-present" | tee /tmp/supply-workbench-backup/old_html.sha256
fi
```

## 部署步骤（测试机先行）

假设 `key_test` app 已在 bench 中安装（当前生产页 `usnj-supply-copilot` 同样位于该 app）。
部署**只新增以下路径**，不修改任何既有文件：

- `key_test/page/supply_workbench/supply_workbench.json`（新增）
- `key_test/page/supply_workbench/supply_workbench.js`（新增）
- `key_test/demand_collaboration/supply_workbench_static.py`（新增）
- `sites/<site>/private/supply_workbench.html`（新增）

1. **上传 HTML**（只读、单文件）：

   ```bash
   scp <私有目录>/supply_workbench.html <服务器>:~/frappe-bench/sites/<site>/private/supply_workbench.html
   sudo chown frappe:frappe ~/frappe-bench/sites/<site>/private/supply_workbench.html
   ```

2. **放入白名单方法**：把 `supply_workbench_static.py` 复制到
   `key_test/demand_collaboration/supply_workbench_static.py`
   （模块路径必须是 `key_test.demand_collaboration.supply_workbench_static`）。

3. **放入 Desk Page**：把 `supply_workbench/` 目录复制到
   `key_test/page/supply_workbench/`。

4. **按顺序刷新**（先 reload-doc，再清缓存，必要时才重启）：

   ```bash
   bench --site <site> reload-doc key_test page supply_workbench
   bench --site <site> clear-cache
   # 仅当 JS 未生效或长时间 long worker 撞车时才重启，并避开高峰期
   bench restart
   ```

5. 用 System Manager 账号打开 `/app/supply-workbench`，确认 8 页签、运营协同
   左右联动、演示横幅与 CSP 均正常（浏览器控制台无 CSP 拒绝记录）。

6. 测试站验证通过后，按项目发布链路合并到生产 app 仓库再部署生产
   （测试分支 → main → 生产 `git pull upstream` → migrate → clear-cache → restart）。

## 权限

`get_html()` 仅对 System Manager 开放；未登录或权限不足抛 `PermissionError`；
`private/supply_workbench.html` 不存在时抛 `NotFoundError`。方法不接受任何路径参数。

## 回滚（只撤新增项）

1. 删除新增 Page doc：
   `bench --site <site> execute frappe.delete_doc --args '["Page","supply-workbench"]'`，
   或在 Desk Page 列表中删除。
2. 删除新增 app 文件：`key_test/page/supply_workbench/` 与
   `key_test/demand_collaboration/supply_workbench_static.py`。
3. 删除新增私有文件：`sites/<site>/private/supply_workbench.html`。
4. `bench --site <site> clear-cache`；仅在需要时 `bench restart`。
5. 恢复 `key_test` 到备份的 HEAD（仅当部署过程改动过 app 文件）：
   `cd apps/key_test && git checkout <备份 HEAD>`。

回滚不得触碰 `usnj-supply-copilot`、测试站 `demand-collaboration` 或其它既有
Page/接口；回滚后再打开这两页确认行为与部署前一致。
