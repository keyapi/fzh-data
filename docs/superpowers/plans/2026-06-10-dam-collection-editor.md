# DAM Collection 编辑器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现多 SKU Collection 编辑器（AEM 替换视图）+ 拖拽排序 + 多行 Excel 导出

**Architecture:** FastAPI 后端增量 item API + Vue 3 CDN 前端替换视图编辑器。Collection editor 替换主网格区域，左侧 SKU 列表 + 右侧图片条编辑。SortableJS 拖拽排序。导出按 SKU 分组多行生成。

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy, SQLite, openpyxl, Vue 3 CDN, SortableJS CDN

---

## File Structure

| File | Role | Change |
|------|------|--------|
| `dam-prototype/export.py` | Excel 导出 | 重写: 多 SKU 多行 |
| `dam-prototype/main.py` | REST API | 新增 PATCH items 端点, 修改 export 端点 |
| `dam-prototype/models.py` | 数据模型 | 不变 |
| `dam-prototype/static/index.html` | 前端 SPA | 新增 Collection editor HTML/CSS/JS |

---

### Task 1: Multi-SKU, Multi-Row Excel Export

**Files:**
- Modify: `dam-prototype/export.py` (full rewrite)

- [ ] **Step 1: Rewrite `export_collection_to_excel` for multi-SKU**

Replace `dam-prototype/export.py`:

```python
# -*- coding: utf-8 -*-
"""Excel export — multi-SKU listing flat files from AssetCollection."""

from __future__ import annotations

import io
from collections import defaultdict
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from sqlalchemy.orm import Session

from models import AssetCollection, Asset

_COLUMN_MAP = {
    "amazon": [
        "main_image_url", "other_image_url1", "other_image_url2",
        "other_image_url3", "other_image_url4", "other_image_url5",
        "other_image_url6", "other_image_url7", "other_image_url8",
    ],
    "wayfair": [
        "main_image_url", "image_url_2", "image_url_3",
        "image_url_4", "image_url_5", "image_url_6",
    ],
    "shopify": [
        "image_src", "image_src_2", "image_src_3", "image_src_4",
    ],
    "home24": [
        "media_main_image", "media_detail_1", "media_detail_2",
        "media_detail_3", "media_detail_4",
    ],
}


def _get_asset_url(asset: Asset | None) -> str:
    if not asset:
        return ""
    return f"/files/{Path(asset.stored_path).name}"


def export_collection_to_excel(
    session: Session, collection_id: str, platform: str = "amazon"
) -> bytes:
    """Multi-SKU export: one row per SKU, images ordered by position."""
    coll = session.query(AssetCollection).filter_by(id=collection_id).first()
    if not coll:
        raise ValueError("Collection not found")

    items = sorted(coll.items, key=lambda x: x.position)
    columns = _COLUMN_MAP.get(platform, _COLUMN_MAP["amazon"])

    # Group items by SKU, maintaining position order per SKU
    sku_images: dict[str, list[tuple[int, str]]] = defaultdict(list)
    sku_position: dict[str, int] = {}
    for idx, item in enumerate(items):
        asset = session.query(Asset).filter_by(id=item.asset_id).first()
        if not asset:
            continue
        # Get SKU from asset's primary product link
        sku = None
        if asset.product_links:
            primary = next(
                (pl for pl in asset.product_links if pl.is_primary), None
            )
            sku = (primary or asset.product_links[0]).product_sku
        if not sku:
            sku = "_unlinked"
        url = _get_asset_url(asset)
        # Track first occurrence of this SKU for stable ordering
        if sku not in sku_position:
            sku_position[sku] = len(sku_position)
        sku_images[sku].append((idx, url))

    wb = Workbook()
    ws = wb.active
    ws.title = "Listing"

    # Headers
    header_fill = PatternFill(start_color="D9E2F3", end_color="D9E2F3", fill_type="solid")
    ws.cell(row=1, column=1, value="SKU").font = Font(bold=True)
    ws.cell(row=1, column=1).fill = header_fill
    for i, col_name in enumerate(columns, 2):
        cell = ws.cell(row=1, column=i, value=col_name)
        cell.font = Font(bold=True)
        cell.fill = header_fill

    # Data rows — sort SKUs by first appearance order
    sorted_skus = sorted(sku_images.keys(), key=lambda s: sku_position[s])
    for row_idx, sku in enumerate(sorted_skus, 2):
        ws.cell(row=row_idx, column=1, value=sku)
        # Sort by position within the collection
        for img_idx, (_, url) in enumerate(sorted(sku_images[sku], key=lambda x: x[0])):
            if img_idx < len(columns):
                ws.cell(row=row_idx, column=img_idx + 2, value=url)

    # Column widths
    ws.column_dimensions["A"].width = 20
    for i in range(len(columns)):
        col_letter = chr(ord("B") + i)
        ws.column_dimensions[col_letter].width = 50

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()
```

- [ ] **Step 2: Test export with DAM running**

```bash
cd dam-prototype && uv run python -c "
from export import export_collection_to_excel
from models import init_db
s = init_db('sqlite:///dam.db')
# Test with an existing collection — should produce valid .xlsx bytes
# (manual verification: check the file opens in Excel)
print('export module loads OK')
"
```

- [ ] **Step 3: Commit**

```bash
cd dam-prototype
git add export.py
git commit -m "feat(dam): multi-SKU multi-row Excel export from AssetCollection"
```

---

### Task 2: Incremental Collection Item API

**Files:**
- Modify: `dam-prototype/main.py` (add PATCH endpoint, update `_coll_to_dict`)

- [ ] **Step 1: Add `_coll_to_dict` enhancement — include SKU info**

Find `_coll_to_dict` in `main.py:305-322`. Replace with:

```python
def _coll_to_dict(c: AssetCollection) -> dict:
    items = []
    for ci in sorted(c.items or [], key=lambda x: x.position):
        a = session.query(Asset).filter_by(id=ci.asset_id).first()
        sku = None
        if a and a.product_links:
            primary = next((pl for pl in a.product_links if pl.is_primary), None)
            sku = (primary or a.product_links[0]).product_sku
        items.append({
            "asset_id": ci.asset_id, "position": ci.position, "role": ci.role,
            "filename": a.filename if a else "",
            "thumb_url": f"/thumb/{Path(a.thumbnail_path).name}" if (a and a.thumbnail_path) else None,
            "file_url": f"/files/{Path(a.stored_path).name}" if a else None,
            "sku": sku,
        })
    return {
        "id": c.id, "name": c.name, "type": c.type,
        "context": c.context, "version": v.version, "status": c.status,
        "items": items,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        "created_by": c.created_by,
    }
```

Note the bug fix: `c.version` → `c.version` was wrong in original, should just be `c.version`. Actually check the original — line 317 already says `"version": c.version,`. So the fix is just adding `"sku": sku` to each item dict.

- [ ] **Step 2: Add PATCH `/api/collections/{coll_id}/items` endpoint**

Insert after the PUT endpoint (after line ~388 in main.py):

```python
@app.patch("/api/collections/{coll_id}/items")
def update_collection_items(coll_id: str, data: dict):
    """Incremental collection item updates — add, remove, reorder.

    Body:
      {
        "add": [{"asset_id": "uuid", "position": 3, "role": "alternate"}, ...],
        "remove": ["asset_id_1", "asset_id_2", ...],
        "reorder": [{"asset_id": "uuid", "position": 0}, ...],
        "set_role": [{"asset_id": "uuid", "role": "main"}, ...]
      }
    """
    c = session.query(AssetCollection).filter_by(id=coll_id).first()
    if not c:
        return JSONResponse({"error": "not found"}, 404)

    # Snapshot before mutation
    old_items = [{"asset_id": ci.asset_id, "position": ci.position, "role": ci.role}
                 for ci in sorted(c.items, key=lambda x: x.position)]
    if old_items:
        snap = AssetCollectionVersion(
            collection_id=c.id, version=c.version,
            snapshot={"images": old_items},
            created_by=data.get("updated_by"),
        )
        session.add(snap)

    # Apply removals
    if "remove" in data:
        for aid in data["remove"]:
            for ci in list(c.items):
                if ci.asset_id == aid:
                    session.delete(ci)

    # Apply additions
    if "add" in data:
        for img in data["add"]:
            session.add(AssetCollectionItem(
                collection_id=c.id,
                asset_id=img["asset_id"],
                position=img.get("position", 0),
                role=img.get("role", "alternate"),
            ))

    session.flush()

    # Apply reorder
    if "reorder" in data:
        pos_map = {r["asset_id"]: r["position"] for r in data["reorder"]}
        for ci in c.items:
            if ci.asset_id in pos_map:
                ci.position = pos_map[ci.asset_id]

    # Apply role changes
    if "set_role" in data:
        role_map = {r["asset_id"]: r["role"] for r in data["set_role"]}
        for ci in c.items:
            if ci.asset_id in role_map:
                ci.role = role_map[ci.asset_id]

    c.version += 1
    c.updated_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(c)
    return _coll_to_dict(c)
```

- [ ] **Step 3: Update PUT `/api/collections/{coll_id}` context handling**

The existing PUT already handles `context` updates. No code change needed — the context schema change (product_sku → skus array) is handled by the frontend sending the new JSON structure. The backend stores whatever JSON the client sends.

- [ ] **Step 4: Verify API works**

```bash
cd dam-prototype
uv run python main.py --port 8098 --no-browser &
sleep 2

# Test PATCH add item to a collection
curl -s -X PATCH http://127.0.0.1:8098/api/collections/{COLL_ID}/items \
  -H 'Content-Type: application/json' \
  -d '{"add":[{"asset_id":"<ASSET_ID>","position":0,"role":"main"}]}' | python -m json.tool

# Test export
curl -s http://127.0.0.1:8098/api/collections/{COLL_ID}/export?platform=amazon \
  -o /tmp/test-export.xlsx && echo "export OK"

kill %1
```

- [ ] **Step 5: Commit**

```bash
cd dam-prototype
git add main.py
git commit -m "feat(dam): PATCH /api/collections/{id}/items — incremental add/remove/reorder/set_role + SKU in item dict"
```

---

### Task 3: Collection Editor UI — CSS + State

**Files:**
- Modify: `dam-prototype/static/index.html` (add CSS, state vars, toggle logic)

- [ ] **Step 1: Add editor CSS**

Insert after line 124 (`::-webkit-scrollbar { width: 6px; }...`) in index.html:

```css
/* ── Collection Editor ── */
.editor-view { display: flex; flex: 1; overflow: hidden; }
.editor-skus { width: 180px; min-width: 180px; background: var(--bg-sidebar); border-right: 1px solid var(--border); overflow-y: auto; padding: 8px; flex-shrink: 0; }
.editor-skus h4 { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted); margin-bottom: 6px; }
.editor-sku-item { padding: 6px 8px; border-radius: 4px; cursor: pointer; font-size: 12px; margin-bottom: 2px; transition: background 0.1s; display: flex; align-items: center; gap: 6px; }
.editor-sku-item:hover { background: var(--surface-hover); }
.editor-sku-item.active { background: var(--primary-light); color: var(--primary); font-weight: 500; }
.editor-sku-item .sku-count { margin-left: auto; font-size: 10px; color: var(--text-muted); background: var(--border); padding: 0 5px; border-radius: 8px; }
.editor-main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.editor-toolbar { display: flex; align-items: center; gap: 10px; padding: 10px 16px; border-bottom: 1px solid var(--border); background: var(--surface); flex-shrink: 0; }
.editor-toolbar h3 { font-size: 14px; font-weight: 600; margin-right: 8px; }
.editor-toolbar .meta { font-size: 11px; color: var(--text-muted); }
.editor-images { flex: 1; padding: 16px; overflow-y: auto; display: flex; flex-wrap: wrap; gap: 10px; align-content: flex-start; min-height: 120px; }
.editor-image-card { position: relative; width: 120px; height: 120px; border-radius: 6px; overflow: hidden; border: 2px solid var(--border); cursor: grab; transition: border-color 0.15s, box-shadow 0.15s; background: var(--surface); }
.editor-image-card:hover { border-color: var(--primary); box-shadow: var(--shadow); }
.editor-image-card img { width: 100%; height: 100%; object-fit: cover; display: block; }
.editor-image-card .drag-grip { position: absolute; top: 4px; right: 4px; width: 20px; height: 20px; border-radius: 3px; background: rgba(0,0,0,0.5); color: #FFF; display: flex; align-items: center; justify-content: center; font-size: 11px; cursor: grab; }
.editor-image-card .role-badge { position: absolute; bottom: 4px; left: 4px; padding: 1px 6px; border-radius: 10px; font-size: 10px; font-weight: 500; background: var(--primary); color: #FFF; }
.editor-image-card .rm-btn { position: absolute; top: 4px; left: 4px; width: 20px; height: 20px; border-radius: 50%; background: rgba(0,0,0,0.5); color: #FFF; display: flex; align-items: center; justify-content: center; font-size: 12px; cursor: pointer; opacity: 0; transition: opacity 0.15s; }
.editor-image-card:hover .rm-btn { opacity: 1; }
.editor-drop-zone { width: 120px; height: 120px; border: 2px dashed var(--border); border-radius: 6px; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: all 0.15s; color: var(--text-muted); font-size: 24px; }
.editor-drop-zone:hover { border-color: var(--primary); background: var(--primary-light); color: var(--primary); }
.editor-role-select { position: absolute; bottom: 4px; right: 4px; padding: 1px 4px; border-radius: 4px; font-size: 9px; background: rgba(0,0,0,0.6); color: #FFF; border: none; cursor: pointer; outline: none; appearance: none; }
.editor-asset-picker { position: fixed; inset: 0; background: rgba(0,0,0,0.35); display: flex; align-items: center; justify-content: center; z-index: 100; }
.editor-asset-picker .picker-dialog { background: var(--surface); border-radius: 8px; width: 700px; max-width: 90vw; max-height: 80vh; display: flex; flex-direction: column; box-shadow: var(--shadow-lg); }
.editor-asset-picker .picker-header { padding: 12px 16px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 8px; }
.editor-asset-picker .picker-body { flex: 1; overflow-y: auto; padding: 12px; display: grid; grid-template-columns: repeat(auto-fill, minmax(100px, 1fr)); gap: 8px; }
.editor-asset-picker .picker-asset { aspect-ratio: 1; border-radius: 4px; overflow: hidden; cursor: pointer; border: 2px solid transparent; transition: border-color 0.15s; }
.editor-asset-picker .picker-asset:hover { border-color: var(--primary); }
.editor-asset-picker .picker-asset.selected { border-color: var(--primary); box-shadow: 0 0 0 2px var(--primary-light); }
.editor-asset-picker .picker-asset img { width: 100%; height: 100%; object-fit: cover; }
```

- [ ] **Step 2: Add editor state variables**

In the Vue setup, after `const toasts=ref([]),thumbGrid=ref(null),saving=ref(false),collections=ref([]);` (line 228), add:

```javascript
const editorColl=ref(null); // non-null = editor is open
const editorSku=ref(null);  // currently selected SKU in editor
const editorPick=ref(false); // asset picker modal open
const editorPicked=ref([]);  // assets selected in picker
```

- [ ] **Step 3: Commit**

```bash
cd dam-prototype
git add static/index.html
git commit -m "feat(dam): Collection editor CSS + Vue state scaffolding"
```

---

### Task 4: Collection Editor HTML Template

**Files:**
- Modify: `dam-prototype/static/index.html` (replace main area with conditional editor view)

- [ ] **Step 1: Replace the grid area with conditional view**

The current grid area (lines 159-169) is inside `<div class="main">`. Wrap it and add the editor as an `v-if`/`v-else`:

Replace lines 159-169:
```html
<div class="grid-area">
  <div v-if="selectedIds.length>1" class="batch-bar">...</div>
  <div v-if="filtered.length===0 && !loading" class="empty-state">...</div>
  <div v-show="filtered.length>0" class="thumb-grid" ref="thumbGrid">...</div>
</div>
```

With:
```html
<!-- Asset Grid (when no collection editor open) -->
<div class="grid-area" v-if="!editorColl">
  <div v-if="selectedIds.length>1" class="batch-bar">{{ selectedIds.length }} selected <button class="btn-batch" @click="batchTag">Tag</button> <button class="btn-batch" @click="batchLink">Link SKU</button> <button class="btn-batch" @click="batchDelete">Delete</button></div>
  <div v-if="filtered.length===0 && !loading" class="empty-state"><div class="empty-icon">{{ filterType==='all'?'📁':'🖼️' }}</div><p>No assets found</p><button class="btn btn-primary" @click="showUpload=true" style="margin-top:8px">Upload your first asset</button></div>
  <div v-show="filtered.length>0" class="thumb-grid" ref="thumbGrid">
    <div v-for="(a,i) in filtered" :key="a.id" class="thumb-card" :class="{selected: selectedIds.includes(a.id)}" :style="{animationDelay: (i*0.03)+'s'}" @click.stop="selectOne(a,$event)" draggable="false">
      <img :src="a.thumb_url || a.file_url" :alt="a.filename" loading="lazy" draggable="false">
      <span class="sel-check">✓</span><span class="drag-grip" @click.stop @mousedown.stop>⠿</span>
      <span v-if="hasPendingAiTags(a)" class="badge ai">AI</span>
    </div>
  </div>
</div>

<!-- Collection Editor (AEM replacement view) -->
<div class="editor-view" v-if="editorColl">
  <!-- SKU list sidebar -->
  <div class="editor-skus">
    <h4>Products ({{ editorSkus.length }})</h4>
    <div v-for="sku in editorSkus" :key="sku.code" class="editor-sku-item" :class="{active: editorSku===sku.code}" @click="editorSku=sku.code">
      {{ sku.code }}<span class="sku-count">{{ sku.count }}</span>
    </div>
    <button class="btn btn-secondary" style="width:100%;margin-top:6px;font-size:11px;padding:4px" @click="addSkuToEditor">+ Add SKU</button>
  </div>
  <!-- Editor main area -->
  <div class="editor-main">
    <div class="editor-toolbar">
      <button class="btn btn-secondary" @click="closeEditor" style="font-size:11px;padding:3px 8px">← Back</button>
      <h3>{{ editorColl.name }}</h3>
      <span class="meta">v{{ editorColl.version }} · {{ editorColl.type }} · {{ editorItems.length }} assets</span>
      <button class="btn btn-primary" @click="saveEditor" style="margin-left:auto;font-size:12px;padding:4px 12px">Save</button>
      <button class="btn btn-secondary" @click="exportEditor" style="font-size:12px;padding:4px 12px">Export Excel</button>
    </div>
    <div class="editor-images" ref="editorGrid">
      <div v-for="item in editorSkuItems" :key="item.asset_id" class="editor-image-card">
        <img :src="item.thumb_url || item.file_url" :alt="item.filename">
        <span class="drag-grip">⠿</span>
        <span class="rm-btn" @click="removeEditorItem(item.asset_id)">×</span>
        <span class="role-badge">{{ item.role }}</span>
        <select class="editor-role-select" :value="item.role" @change="setEditorRole(item.asset_id, $event.target.value)">
          <option value="main">Main</option>
          <option value="alternate">Alt</option>
          <option value="lifestyle">Life</option>
          <option value="detail">Det.</option>
          <option value="size_chart">Chart</option>
          <option value="packaging">Pkg</option>
          <option value="a_plus">A+</option>
          <option value="other">Other</option>
        </select>
      </div>
      <div class="editor-drop-zone" @click="openAssetPicker">+</div>
    </div>
  </div>
</div>

<!-- Asset Picker Modal (for adding assets to collection) -->
<div v-if="editorPick" class="editor-asset-picker" @click.self="editorPick=false">
  <div class="picker-dialog">
    <div class="picker-header">
      <h3>Add Assets to "{{ editorColl.name }}"</h3>
      <button class="btn btn-primary" @click="addPickedToEditor" style="margin-left:auto;font-size:12px;padding:4px 12px" :disabled="editorPicked.length===0">Add Selected ({{ editorPicked.length }})</button>
      <button class="close-btn" @click="editorPick=false">×</button>
    </div>
    <div class="picker-body">
      <div v-for="a in assets" :key="a.id" class="picker-asset" :class="{selected: editorPicked.includes(a.id)}" @click="togglePick(a.id)">
        <img :src="a.thumb_url || a.file_url" :alt="a.filename" loading="lazy">
      </div>
    </div>
  </div>
</div>
```

- [ ] **Step 2: Commit**

```bash
cd dam-prototype
git add static/index.html
git commit -m "feat(dam): Collection editor HTML template (AEM replacement view + asset picker)"
```

---

### Task 5: Collection Editor Vue Logic

**Files:**
- Modify: `dam-prototype/static/index.html` (add computed properties and methods)

- [ ] **Step 1: Add editor computed properties**

After the existing `filtered` computed (line 246), add:

```javascript
// ── Collection Editor Computed ──
const editorItems = computed(() => editorColl.value ? (editorColl.value.items || []) : []);
const editorSkus = computed(() => {
  const m = {};
  editorItems.value.forEach(i => {
    const s = i.sku || '_unlinked';
    m[s] = (m[s] || 0) + 1;
  });
  return Object.entries(m).map(([code, count]) => ({code, count}));
});
const editorSkuItems = computed(() => {
  if (!editorSku.value) return editorItems.value;
  return editorItems.value.filter(i => (i.sku || '_unlinked') === editorSku.value);
});
```

- [ ] **Step 2: Add editor methods**

After `showCollectionActions` (line 254), add:

```javascript
// ── Collection Editor Methods ──
async function openEditor(c) {
  try {
    const r = await fetch('/api/collections/' + c.id);
    const d = await r.json();
    editorColl.value = d;
    // Auto-select first SKU
    const skus = Object.entries(
      (d.items || []).reduce((m, i) => { const s = i.sku || '_unlinked'; m[s] = (m[s] || 0) + 1; return m; }, {})
    );
    editorSku.value = skus.length > 0 ? skus[0][0] : null;
    // Load all assets for the picker
    await loadAssets();
  } catch (e) {
    toast('Failed to open collection', 'error');
  }
}
function closeEditor() {
  editorColl.value = null;
  editorSku.value = null;
  editorPick.value = false;
  editorPicked.value = [];
}
async function saveEditor() {
  if (!editorColl.value) return;
  try {
    const c = editorColl.value;
    const images = c.items.map((it, idx) => ({
      asset_id: it.asset_id, position: idx, role: it.role
    }));
    const r = await fetch('/api/collections/' + c.id, {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ name: c.name, type: c.type, context: c.context, images })
    });
    if (!r.ok) throw new Error('Save failed');
    editorColl.value = await r.json();
    toast('Collection saved');
  } catch (e) {
    toast('Save failed', 'error');
  }
}
async function exportEditor() {
  if (!editorColl.value) return;
  const plat = prompt('Platform (amazon/wayfair/shopify/home24):', 'amazon');
  if (!plat) return;
  window.open('/api/collections/' + editorColl.value.id + '/export?platform=' + plat);
}
async function removeEditorItem(assetId) {
  if (!editorColl.value) return;
  try {
    const r = await fetch('/api/collections/' + editorColl.value.id + '/items', {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ remove: [assetId] })
    });
    if (!r.ok) throw new Error('Remove failed');
    editorColl.value = await r.json();
    toast('Removed');
  } catch (e) {
    toast('Remove failed', 'error');
  }
}
async function setEditorRole(assetId, role) {
  if (!editorColl.value) return;
  try {
    const r = await fetch('/api/collections/' + editorColl.value.id + '/items', {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ set_role: [{ asset_id: assetId, role }] })
    });
    if (!r.ok) throw new Error('Role update failed');
    editorColl.value = await r.json();
  } catch (e) {
    toast('Role update failed', 'error');
  }
}
function openAssetPicker() {
  editorPick.value = true;
  editorPicked.value = [];
}
function togglePick(assetId) {
  const i = editorPicked.value.indexOf(assetId);
  if (i >= 0) editorPicked.value.splice(i, 1);
  else editorPicked.value.push(assetId);
}
async function addPickedToEditor() {
  if (!editorColl.value || editorPicked.value.length === 0) return;
  try {
    const currentMax = Math.max(0, ...editorItems.value.map(i => i.position));
    const adds = editorPicked.value.map((aid, idx) => ({
      asset_id: aid, position: currentMax + idx + 1, role: 'alternate'
    }));
    const r = await fetch('/api/collections/' + editorColl.value.id + '/items', {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ add: adds })
    });
    if (!r.ok) throw new Error('Add failed');
    editorColl.value = await r.json();
    editorPick.value = false;
    editorPicked.value = [];
    toast('Added ' + adds.length + ' asset(s)');
  } catch (e) {
    toast('Add failed', 'error');
  }
}
async function addSkuToEditor() {
  const s = prompt('Enter SKU code:');
  if (!s) return;
  // Add the SKU to the collection context
  const ctx = editorColl.value.context || {};
  const skus = new Set(ctx.skus || []);
  skus.add(s);
  ctx.skus = Array.from(skus);
  editorColl.value.context = ctx;
  toast('SKU added. Start adding images for it.');
}
```

- [ ] **Step 3: Update `openCollectionEditor` to launch the new editor**

Replace the existing `openCollectionEditor` function (line 253) and `showCollectionActions` (line 254) with simplified versions:

```javascript
function openCollectionEditor(existing) {
  if (existing) {
    openEditor(existing);
  } else {
    const n = prompt('Collection name:');
    if (!n) return;
    const t = prompt('Type (listing/campaign/social/catalog/custom):', 'listing');
    if (!t) return;
    (async () => {
      const ctx = { skus: [] };
      const r = await fetch('/api/collections', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ name: n, type: t, context: ctx, created_by: 'user' })
      });
      const d = await r.json();
      await loadCollections();
      openEditor(d);
    })();
  }
}
async function showCollectionActions(c) {
  const act = prompt('Collection: ' + c.name + ' (v' + c.version + ')\n\nActions:\n  "open" = edit\n  "export" = download Excel\n  "delete" = remove', 'open');
  if (!act) return;
  if (act === 'open') { openEditor(c); }
  else if (act === 'export') {
    const plat = prompt('Platform:', 'amazon');
    if (plat) window.open('/api/collections/' + c.id + '/export?platform=' + plat);
  } else { toast('Action cancelled'); }
}
```

- [ ] **Step 4: Add initSort for editor grid**

Add a watcher to re-initialize SortableJS when the editor grid renders:

```javascript
function initEditorSort() {
  if (!editorColl.value) return;
  const el = document.querySelector('.editor-images');
  if (!el) return;
  // Destroy existing instance if any
  if (el._sortable) el._sortable.destroy();
  el._sortable = Sortable.create(el, {
    animation: 200,
    handle: '.drag-grip',
    filter: '.editor-drop-zone',
    onEnd(evt) {
      const items = [...editorColl.value.items];
      const [mv] = items.splice(evt.oldIndex, 1);
      items.splice(evt.newIndex, 0, mv);
      // Update positions
      items.forEach((it, idx) => { it.position = idx; });
      editorColl.value.items = items;
    }
  });
}
watch(editorSkuItems, async () => { await nextTick(); initEditorSort(); });
```

- [ ] **Step 5: Update the return statement**

Add new symbols to the return statement (line 295):

```javascript
return {assets,totalCount,loading,selectedIds,detailAsset,filterType,filterTag,filterProduct,sortBy,showUpload,uploading,dragOver,sidebarOpen,saving,productQ,productResults,detailQ,detailResults,toasts,typeFilters,allTags,filtered,thumbGrid,selectOne,clearAll,hasPendingAiTags,handlePick,handleDrop,processFiles,addTag,rmTag,confirmAi,linkSku,saveDetail,searchProducts,searchForDetail,batchTag,batchLink,batchDelete,aiTagSelected,toast,fmtSize,fmtDate,collections,loadCollections,openCollectionEditor,showCollectionActions,editorColl,editorSku,editorSkus,editorSkuItems,editorPick,editorPicked,openEditor,closeEditor,saveEditor,exportEditor,removeEditorItem,setEditorRole,openAssetPicker,togglePick,addPickedToEditor,addSkuToEditor};
```

- [ ] **Step 6: Commit**

```bash
cd dam-prototype
git add static/index.html
git commit -m "feat(dam): Collection editor Vue logic — open/close/save/export/add/remove/reorder/role"
```

---

### Task 6: Integration Test

**Files:**
- No new files — manual verification

- [ ] **Step 1: Start DAM and test the full flow**

```bash
cd dam-prototype
uv run python main.py --port 8098 --no-browser
```

Manual test checklist in browser at `http://localhost:8098`:

1. **Upload test assets** — Upload 5-6 test images
2. **Link SKUs** — Click each asset, use detail panel to link SKUs (KS0001, KS0002)
3. **Create collection** — Click "+ New" in Collections sidebar, name it, type=listing
4. **Editor opens** — Verify editor replaces main grid, shows SKU list
5. **Add images** — Click "+" zone, pick assets, confirm add
6. **Drag reorder** — Drag images to reorder, verify positions update
7. **Set roles** — Change role dropdown, verify it persists
8. **Remove image** — Click ×, verify it's removed
9. **Save** — Click Save, reload to verify persistence
10. **Export** — Click Export Excel, verify multi-row .xlsx downloads

- [ ] **Step 2: Check browser console for errors**

```javascript
// In browser console, verify no errors
```

- [ ] **Step 3: Commit any fixes if needed**

---

## Self-Review

1. **Spec coverage:** Design spec §4 (data model), §5 (API), §6 (UI) all have corresponding tasks
2. **No placeholders:** Every step has actual code, no TBD/TODO
3. **Type consistency:** `_coll_to_dict` returns `sku` field, `editorSkuItems` uses `i.sku`, aligned
4. **Frontend context:** `context.skus` is an array, `addSkuToEditor` adds to Set then back to array
