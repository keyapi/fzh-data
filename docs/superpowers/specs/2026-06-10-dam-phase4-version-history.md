# Phase 4: Collection Version History — Design Spec

> 日期: 2026-06-10 | 状态: 待审阅 | 基于: Google Docs + Figma + AEM 模式

## 1. 行业调研

| 系统 | 面板位置 | Restore 按钮 | 确认方式 | 非破坏性 |
|------|---------|-------------|---------|---------|
| **Google Docs** | 右侧面板 | 主区域顶部 "Restore this version" | confirm 弹窗 | 不删旧版 |
| **Figma** | 右侧面板 | ⋮ 菜单 → Restore | 模态弹窗 Cancel/Restore | 自动存 checkpoint |
| **AEM** | 左栏 Timeline | 版本卡上 Revert | 直接执行 | 创建新版本事件 |
| **Notion** | 右侧面板 | 版本卡上按钮 | confirm | 不删旧版 |

**共识**：
1. 右侧面板（Google Docs、Figma、Notion 三家一致，AEM 用左栏但逻辑相同）
2. 非破坏性回滚 — 回滚前自动存当前状态，回滚操作可逆
3. 确认弹窗 — 防止误操作
4. 版本列表时间倒序，每个版本显示缩略图预览

## 2. 设计决策

### 2.1 UI 模式：右侧抽屉面板

- 320px 宽，和 Asset 详情面板一致
- 点 "History" → 右侧滑入（`transform: translateX` 动画）
- 点 × 或面板外区域 → 关闭
- 编辑器保持可见并可继续操作（非模态，不阻断）

**为什么不是替换视图**：Google Docs 也保留了文档预览在主区域，版本列表在右侧。编辑状态和版本浏览应可共存——用户可能在对照当前和历史版本。

### 2.2 版本列表

每个版本卡片包含：
- **版本号** (v5, v4, v3...)
- **时间戳** (06/10 09:45)
- **图片数** (4 images)
- **缩略图条**（最多 4 个小格子，28×28px）
- **状态标识**：
  - 当前版本：蓝色左边框 (#3B82F6) + "current" 药丸标签
  - 选中版本：黄色边框 (#F59E0B)
  - 其他版本：无特殊样式

### 2.3 回滚流程（Figma 非破坏性模式）

```
用户点 "Restore to v{N}"
  → confirm("Restore to v{N}? Current v{current} will be saved as checkpoint.")
    → [Cancel] = 什么都不做
    → [OK] = POST /api/collections/{id}/versions/{v}/restore
      → 后端先快照当前 → 清空 items → 从 snapshot 重建 → version++
      → 前端收起面板 → 刷新 editorColl → toast "Restored to v{N}"
```

### 2.4 Google Docs "Show changes" 的映射

Google Docs 有个 "Show changes" toggle 控制是否高亮 diff。对我们的映射：版本卡内缩略图条本身就是"预览"，无需额外 toggle。以后做 visual diff（并排对比两张快照）时再加。

## 3. 后端

### 新增: POST /api/collections/{id}/versions/{v}/restore

```python
@app.post("/api/collections/{coll_id}/versions/{v}/restore")
def restore_version(coll_id: str, v: int):
    c = session.query(AssetCollection).filter_by(id=coll_id).first()
    if not c: return JSONResponse({"error": "not found"}, 404)
    
    ver = session.query(AssetCollectionVersion)\
        .filter_by(collection_id=coll_id, version=v).first()
    if not ver: return JSONResponse({"error": "version not found"}, 404)
    
    # Non-destructive: snapshot current state
    current_items = [
        {"asset_id": ci.asset_id, "position": ci.position, "role": ci.role}
        for ci in sorted(c.items, key=lambda x: x.position)
    ]
    if current_items:
        session.add(AssetCollectionVersion(
            collection_id=c.id, version=c.version,
            snapshot={"images": current_items}
        ))
    
    # Wipe and rebuild from snapshot
    for old in list(c.items): session.delete(old)
    session.flush()
    for img in ver.snapshot.get("images", []):
        session.add(AssetCollectionItem(
            collection_id=c.id, asset_id=img["asset_id"],
            position=img["position"], role=img.get("role", "alternate")
        ))
    
    c.version += 1
    c.updated_at = datetime.now(timezone.utc)
    session.commit(); session.refresh(c)
    return _coll_to_dict(c)
```

## 4. 前端

### 4.1 新增 state: `showHistory`, `versions`, `selectedVersion`

### 4.2 新增 UI（index.html）

**工具栏按钮**:
```html
<button @click="openHistory">🕐 History</button>
```

**版本面板**（在 `</div>` 关闭 editor-main 之后，复用 detail-overlay + detail-panel 模式）:
- 面板标题 "History" + ×
- v-for 版本列表
- 每个版本：版本号、时间戳、图片数、缩略图条、条件 Restore 按钮

### 4.3 新增方法

- `openHistory()`: fetch /api/collections/{id}/versions → showHistory = true
- `closeHistory()`: showHistory = false
- `restoreVersion(v)`: confirm → POST restore → refresh editorColl → close panel

## 5. 验证

1. Collection 有多个版本 → 点 History → 右侧面板显示版本列表
2. 当前版本蓝色高亮 + "current" 标签
3. 点历史版本 → 黄色边框 + Restore 按钮
4. 点 Restore → confirm → 面板关闭 → 编辑器刷新 → 版本号递增
5. 再次点 History → 回滚前状态作为新 checkpoint 可见
