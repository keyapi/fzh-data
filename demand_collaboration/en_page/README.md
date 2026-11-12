---
type: Guide
title: EN 运营需求协同 Page 部署产物
---

# EN Page / 角色部署

本目录是 `key_test` app 的部署产物，不参与本地 FastAPI 运行。

## 文件落点（测试站/生产）

| 本目录 | 服务器 `apps/key_test/` |
|---|---|
| `demand_collaboration/` | `key_test/key_test/key_test/page/demand_collaboration/` |
| `patches/` | `key_test/patches/` |

`patches.txt` 的 `[post_model_sync]` 追加一行：

```
key_test.patches.v1_0.create_demand_roles
```

Python 包（`core.py` / `scope.py` / `frappe_bridge.py` / `static/`）落在
`key_test/key_test/demand_collaboration/`，方法路径为
`key_test.demand_collaboration.frappe_bridge.*`。

## 部署

```bash
ssh 上海测试-阿里云-FZH-ERPNext-frappe
cd /home/frappe/frappe-bench
git -C apps/key_test checkout -b feature/operator-demand-workbench   # 或从目标基线建
# 拷入包、Page、patches；追加 patches.txt
cd /home/frappe/frappe-bench
sudo -n -u frappe bench --site erpnext.vilavi.cn migrate
sudo -n -u frappe bench --site erpnext.vilavi.cn clear-cache
sudo -n -u frappe bench restart
```

## 首次配置

1. System Manager 通过 `set_scope` 维护 `demand_scope.json`（默认拒绝）。
2. System Manager 通过 `load_baseline` 装载基准 JSON。
3. 测试用户：`Demand Contributor` 与 `Demand Reviewer` 各一个。
4. 浏览器打开 `/app/demand-collaboration` 验收。

未部署生产；生产需单独授权与备份。
