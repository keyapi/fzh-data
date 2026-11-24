---
type: Guide
title: Supply Workbench EN 接入产物
---

# Supply Workbench（/app/supply-workbench）EN 接入产物

本目录只放**部署产物模板**，不含任何客户数据或生成的 HTML。

- 页面生成器：`supply_copilot/workbench_page.py`（单文件 HTML，四个一级视图：
  工作台 / 证据链 / 分析方法 / 口径；分析方法内含 A–E 五张表）
- EN 白名单读取：`supply_workbench_static.py`
- Desk Page 定义：`supply_workbench/supply_workbench.json` + `.js`

页面是只读演示页：数据全部内嵌，提案只存浏览器 `localStorage`
（键 `supply-workbench:proposals:v2`；旧键 `…:proposals:v1` 只读展示，不迁移）。
刷新保留；清理浏览器数据或换浏览器看不到本浏览器的提案。页面不发起网络请求、不写 EN。
顶部常驻横幅写「静态演示 · 数据快照 <as_of> · 提案只存本浏览器 · 不上传/不审批/不写 EN」，
服务可用 / 库存实时 / 建议可执行三者分开标识，不用绿色暗示采购资格。

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

4. **按顺序刷新**（只做文件落盘 + reload-doc + clear-cache，**不以全量 migrate 收尾**）：

   ```bash
   # Page 记录变更后：重载该 Page
   bench --site erpnext.vilavi.cn reload-doc key_test page supply_workbench
   bench --site erpnext.vilavi.cn clear-cache

   # 仅当新增 Python 模块需要加载（白名单方法未被识别）时才重启 web：
   sudo supervisorctl restart frappe-bench-web:frappe-bench-frappe-web
   ```

   普通 Page/静态 HTML 部署不需要 `bench migrate`，也不要跑全量 `bench migrate`。

5. 用 System Manager 账号打开 `/app/supply-workbench`，确认四个一级视图可切换、
   工作台左右联动（建议只读 / 基准可演示提案）、证据链逐行区块齐全、
   分析方法 A–E 字段完整、演示横幅与 CSP 均正常（浏览器控制台无 CSP 拒绝记录）。

6. 测试站验证通过后，按项目发布链路合并到生产 app 仓库再部署生产
   （测试分支 → main → 生产 `git pull upstream` → 放入新增文件 →
   `reload-doc` + `clear-cache`；仅新增 Python 模块需要加载时才用
   `sudo supervisorctl restart frappe-bench-web:frappe-bench-frappe-web`；
   不以全量 `bench migrate` 收尾）。

## 权限

`get_html()` 仅对 System Manager 开放；未登录或权限不足抛 `PermissionError`；
`private/supply_workbench.html` 不存在时抛 `NotFoundError`。方法不接受任何路径参数。

## 回滚（恢复同名旧记录/旧文件，禁止整库回滚）

1. 恢复同名旧 Page 记录：若部署前备份过同名 Page JSON，用其恢复；若原本不存在，
   则删除本次新增的 Page：
   `bench --site erpnext.vilavi.cn execute frappe.delete_doc --args '["Page","supply-workbench"]'`。
2. 恢复同名旧文件：把 `private/supply_workbench.html`、`key_test/page/supply_workbench/`、
   `key_test/demand_collaboration/supply_workbench_static.py` 恢复为备份内容；备份为
   `not-present` 的则删除对应新增文件。不得改动其它既有文件。
3. `bench --site erpnext.vilavi.cn clear-cache`；仅当 Python 模块需要重新加载时才
   `sudo supervisorctl restart frappe-bench-web:frappe-bench-frappe-web`。
4. **明确禁止**：整库还原（数据库备份恢复）、对整个 bench 或 app 做 git checkout、
   用全量 `bench migrate` 作为回滚手段。回滚只能逐项恢复同名记录/文件。
5. 回滚后再打开 `usnj-supply-copilot` 与测试站 `demand-collaboration`，确认两页
   行为与部署前一致。
