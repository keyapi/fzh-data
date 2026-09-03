# Click-based Scripts — Agent Handoff

这些脚本使用 Playwright 浏览器自动化实现赛狐操作，已被新的 API 方式逐步替代。
保留作为参考和 fallback（当 API 不可用时）。

## 脚本索引

| 脚本 | 功能 | 状态 |
|------|------|------|
| `sellfox_import_warehouse_restock.py` | 海外仓备货单导入 | 已替代 |
| `sellfox_restock_allocate_ship.py` | 备货单分配库存+发货 | 已替代 |
| `sellfox_restock_receive.py` | 备货单批量SKU收货 | 已替代 |
| `sellfox_import_other_outbound.py` | 其他出库导入 | 参考 |
| `sellfox_import_other_inbound.py` | 其他入库导入 | 参考 |
| `sellfox_import_update.py` | 商品规格更新导入 | 参考 |
| `commodity_import_template.py` | 下载商品导入模板 | 参考 |

## 共享模式

所有脚本使用相同的登录/导航/导入模式：
- `sellfox-profile/` 持久化浏览器登录态
- `launch_persistent_context` 启动浏览器
- JS evaluate 处理 Element UI 隐藏元素
- SPA 预热：先访问 `detailed/index.html` 再导航到目标页面

## 已知问题

1. **侧边栏点击**：必须用 `.menu_title` 不能用 `.menu-item`
2. **搜索残留**：每次启动要点「重置」清除
3. **Element UI 可见性**：Playwright 频繁报 hidden，用 `page.evaluate` 绕过
4. **确认弹窗**：用 JS evaluate 点按钮，不用 Playwright locator

## 对应 API 版本

| 点击版 | API 版 |
|--------|--------|
| `sellfox_import_warehouse_restock.py` | `sellfox_restock_api.py` (Playwright 导入部分) |
| `sellfox_restock_allocate_ship.py` | `sellfox_restock_api.py` (allotStock API) |
| `sellfox_restock_receive.py` | `sellfox_restock_api.py` (receiveList/receive API) |

## 运行方式

```bash
cd click-based
uv run python sellfox_restock_allocate_ship.py --after 00:00
```

注意：`sellfox-profile/` 在父目录，运行时需确保路径正确。
