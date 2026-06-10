# AssetCollection + Version Management + Excel Export

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build AssetCollection CRUD with version snapshots on save, and Excel export for channel-specific flat files.

**Architecture:** Add 5 API endpoints to `main.py` for collection CRUD + export. New `export.py` module generates platform-specific Excel using openpyxl. Frontend gets a simple list panel + drag-drop editor for collections. Version snapshots auto-created on each save via `AssetCollectionVersion`.

**Tech Stack:** FastAPI, SQLAlchemy (existing models), openpyxl, Vue 3 CDN (existing frontend).

---

### Scope Check

This covers one subsystem: AssetCollection lifecycle. Excel export depends on collection. Single plan is appropriate.

### File Structure

- Modify: `dam-prototype/main.py` — add 5 collection API endpoints + import export module
- Create: `dam-prototype/export.py` — Excel generation logic
- Modify: `dam-prototype/static/index.html` — add collection list panel + editor dialog

---

### Task 1: Collection CRUD API

**Files:**
- Modify: `dam-prototype/main.py:after line ~250`

- [ ] **Step 1: Add list collections endpoint**

After the product search endpoints, add:

```python
# ── AssetCollection APIs ──────────────────────────────

@app.get("/api/collections")
def list_collections(type: str | None = None, product_sku: str | None = None):
    q = session.query(AssetCollection)
    if type: q = q.filter(AssetCollection.type == type)
    if product_sku:
        q = q.filter(AssetCollection.context.contains(product_sku))
    collections = q.order_by(AssetCollection.updated_at.desc()).limit(50).all()
    return {"collections": [_coll_to_dict(c) for c in collections]}


def _coll_to_dict(c: AssetCollection) -> dict:
    items = []
    for ci in (c.items or []):
        a = session.query(Asset).filter_by(id=ci.asset_id).first()
        items.append({
            "asset_id": ci.asset_id,
            "position": ci.position,
            "role": ci.role,
            "filename": a.filename if a else "",
            "thumb_url": f"/thumb/{Path(a.thumbnail_path).name}" if (a and a.thumbnail_path) else None,
        })
    return {
        "id": c.id, "name": c.name, "type": c.type,
        "context": c.context, "version": c.version, "status": c.status,
        "items": sorted(items, key=lambda x: x["position"]),
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        "created_by": c.created_by,
    }
```

- [ ] **Step 2: Restart server and test GET**

```bash
curl http://127.0.0.1:8098/api/collections
```

Expected: `{"collections": []}`

- [ ] **Step 3: Add create collection endpoint**

```python
@app.post("/api/collections")
def create_collection(data: dict):
    c = AssetCollection(
        name=data.get("name", "Untitled"),
        type=data.get("type", "custom"),
        context=data.get("context", {}),
        version=1,
        status="draft",
        created_by=data.get("created_by"),
    )
    session.add(c)
    session.commit()
    session.refresh(c)
    return _coll_to_dict(c)
```

- [ ] **Step 4: Add update collection (with version snapshot)**

```python
@app.put("/api/collections/{coll_id}")
def update_collection(coll_id: str, data: dict):
    c = session.query(AssetCollection).filter_by(id=coll_id).first()
    if not c: return JSONResponse({"error": "not found"}, 404)

    # Snapshot current version before changing
    old_items = [{"asset_id": ci.asset_id, "position": ci.position, "role": ci.role}
                 for ci in sorted(c.items, key=lambda x: x.position)]
    if old_items:
        snap = AssetCollectionVersion(
            collection_id=c.id, version=c.version,
            snapshot={"images": old_items},
            created_by=data.get("updated_by"),
        )
        session.add(snap)

    # Update fields
    if "name" in data: c.name = data["name"]
    if "type" in data: c.type = data["type"]
    if "context" in data: c.context = data["context"]
    if "status" in data: c.status = data["status"]

    # Replace items
    if "images" in data:
        for old in c.items:
            session.delete(old)
        session.flush()
        for img in data["images"]:
            session.add(AssetCollectionItem(
                collection_id=c.id,
                asset_id=img["asset_id"],
                position=img["position"],
                role=img.get("role", "alternate"),
            ))

    c.version += 1
    c.updated_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(c)
    return _coll_to_dict(c)
```

- [ ] **Step 5: Add get single collection + version history**

```python
@app.get("/api/collections/{coll_id}")
def get_collection(coll_id: str):
    c = session.query(AssetCollection).filter_by(id=coll_id).first()
    if not c: return JSONResponse({"error": "not found"}, 404)
    return _coll_to_dict(c)


@app.get("/api/collections/{coll_id}/versions")
def get_collection_versions(coll_id: str):
    versions = session.query(AssetCollectionVersion)\
        .filter_by(collection_id=coll_id)\
        .order_by(AssetCollectionVersion.version.desc()).all()
    return {"versions": [
        {"id": v.id, "version": v.version, "snapshot": v.snapshot,
         "created_at": v.created_at.isoformat() if v.created_at else None}
        for v in versions
    ]}
```

- [ ] **Step 6: Restart and test CRUD**

```bash
# Create
curl -X POST http://127.0.0.1:8098/api/collections \
  -H 'Content-Type: application/json' \
  -d '{"name":"Test Collection","type":"listing","context":{"product_sku":"KS0001","channel":"amazon"}}'

# List
curl http://127.0.0.1:8098/api/collections

# Update with images (use actual asset IDs from /api/assets)
curl -X PUT http://127.0.0.1:8098/api/collections/<id> \
  -H 'Content-Type: application/json' \
  -d '{"images":[{"asset_id":"<uuid>","position":0,"role":"main"}]}'

# Check versions
curl http://127.0.0.1:8098/api/collections/<id>/versions
```

Expected: Create returns collection with version=1. Update bumps version=2, old snapshot saved.

- [ ] **Step 7: Commit**

```bash
git add dam-prototype/main.py
git commit -m "feat(dam): add AssetCollection CRUD API with version snapshots"
```

---

### Task 2: Excel Export Module

**Files:**
- Create: `dam-prototype/export.py`
- Modify: `dam-prototype/main.py` — add export endpoint

- [ ] **Step 1: Create export.py**

```python
# export.py
"""Excel export — generate channel-specific flat files from AssetCollection."""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
import io
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from sqlalchemy.orm import Session

from models import AssetCollection, Asset, PlatformPreset

_COLUMN_MAP = {
    "amazon": {
        "main": "main_image_url",
        "alternate": "other_image_url1", "alternate2": "other_image_url2",
        "alternate3": "other_image_url3", "alternate4": "other_image_url4",
        "alternate5": "other_image_url5", "alternate6": "other_image_url6",
        "alternate7": "other_image_url7", "alternate8": "other_image_url8",
    },
    "wayfair": {
        "main": "main_image_url", "alternate": "image_url_2",
        "alternate2": "image_url_3", "alternate3": "image_url_4",
        "alternate4": "image_url_5", "alternate5": "image_url_6",
    },
    "shopify": {
        "main": "image_src", "alternate": "image_src_2",
        "alternate2": "image_src_3", "alternate3": "image_src_4",
    },
    "home24": {
        "main": "media_main_image", "alternate": "media_detail_1",
        "alternate2": "media_detail_2", "alternate3": "media_detail_3",
        "alternate4": "media_detail_4",
    },
}


def export_collection_to_excel(session: Session, collection_id: str, platform: str = "amazon") -> bytes:
    """Generate platform-specific Excel file from AssetCollection. Returns bytes."""
    coll = session.query(AssetCollection).filter_by(id=collection_id).first()
    if not coll: raise ValueError("Collection not found")

    # Build ordered URL list from collection items
    items = sorted(coll.items, key=lambda x: x.position)
    image_urls = []
    for item in items:
        asset = session.query(Asset).filter_by(id=item.asset_id).first()
        if asset:
            file_name = Path(asset.stored_path).name
            # In production, use public URL; for prototype, use file path
            url = f"/files/{file_name}"
            image_urls.append(url)

    # Map to platform columns
    col_map = _COLUMN_MAP.get(platform, _COLUMN_MAP["amazon"])

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"

    # Header
    headers = ["SKU"] + list(col_map.values())
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="D9E2F3", end_color="D9E2F3", fill_type="solid")

    # Data row
    sku = (coll.context or {}).get("product_sku", "")
    ws.cell(row=2, column=1, value=sku)
    for i, url in enumerate(image_urls):
        col_name = list(col_map.values())[i] if i < len(col_map) else None
        if col_name:
            col_idx = headers.index(col_name) + 1
            ws.cell(row=2, column=col_idx, value=url)

    # Auto-width
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = 40

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()
```

- [ ] **Step 2: Add export endpoint to main.py**

After collection endpoints:

```python
from export import export_collection_to_excel

@app.get("/api/collections/{coll_id}/export")
def export_collection(coll_id: str, platform: str = "amazon"):
    try:
        data = export_collection_to_excel(session, coll_id, platform)
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=listing-{platform}-{coll_id[:8]}.xlsx"},
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, 404)
```

Add import at top: `from fastapi.responses import Response`

- [ ] **Step 3: Install openpyxl if needed**

```bash
cd D:/Work/赛狐/Cursor && uv add openpyxl
```

- [ ] **Step 4: Test export**

```bash
# Create a collection with images first (via API), then:
curl -OJ http://127.0.0.1:8098/api/collections/<id>/export?platform=amazon
```

Expected: Downloads an .xlsx file. Open in Excel — should have columns SKU | main_image_url | other_image_url1 | ...

- [ ] **Step 5: Commit**

```bash
git add dam-prototype/export.py dam-prototype/main.py
git commit -m "feat(dam): add Excel export from AssetCollection"
```

---

### Task 3: Frontend — Collection List Panel

**Files:**
- Modify: `dam-prototype/static/index.html` — add sidebar section for collections

- [ ] **Step 1: Add "Collections" section below the existing sidebar**

In the sidebar after the SORT section, add:

```html
<div class="sidebar-section">
  <h3>Collections</h3>
  <button class="btn btn-primary" style="width:100%;font-size:12px;padding:4px" @click="openCollectionEditor()">+ New Collection</button>
  <div v-for="c in collections" :key="c.id" class="filter-radio" style="margin-top:4px" @click="loadCollection(c.id)">
    {{ c.name || 'Untitled' }} <span style="font-size:10px;color:var(--text-muted)">v{{ c.version }}</span>
  </div>
</div>
```

- [ ] **Step 2: Add Vue state and methods for collections**

In the Vue setup, add:

```javascript
const collections = ref([]);

async function loadCollections() {
  try {
    const r = await fetch('/api/collections');
    const d = await r.json();
    collections.value = d.collections || [];
  } catch(e) { console.error(e); }
}

function openCollectionEditor(coll) {
  // Phase 3b: full editor with drag-drop
  const name = prompt('Collection name:', coll ? coll.name : '');
  if (!name) return;
  const type = prompt('Type (listing/campaign/social/catalog/custom):', coll ? coll.type : 'listing');
  if (!type) return;

  (async () => {
    if (coll) {
      await fetch('/api/collections/' + coll.id, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name, type}),
      });
    } else {
      await fetch('/api/collections', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name, type, context: {}, created_by: 'user'}),
      });
    }
    await loadCollections();
    toast('Collection saved');
  })();
}

async function loadCollection(collId) {
  const r = await fetch('/api/collections/' + collId);
  const c = await r.json();
  // Show items in grid — simple approach: filter assets by collection item IDs
  if (c.items && c.items.length) {
    const itemIds = new Set(c.items.map(i => i.asset_id));
    detailAsset.value = assets.value.find(a => itemIds.has(a.id)) || null;
  }
  toast(`Loaded: ${c.name} (v${c.version}, ${(c.items||[]).length} images)`);
}
```

- [ ] **Step 3: Call loadCollections on mount**

In `onMounted`:
```javascript
onMounted(async () => {
  await loadAssets();
  await loadCollections();
  nextTick(initSort);
  document.addEventListener('keydown', onKey);
});
```

- [ ] **Step 4: Return new state in setup return**

```javascript
return {
  // ... existing ...
  collections, openCollectionEditor, loadCollection, loadCollections,
};
```

- [ ] **Step 5: Reload and verify**

Open `http://127.0.0.1:8098`. Sidebar shows "Collections" section with "+ New Collection" button.

- [ ] **Step 6: Commit**

```bash
git add dam-prototype/static/index.html
git commit -m "feat(dam): add collection list panel to frontend"
```

---

## Self-Review

**1. Spec coverage:**
- Collection CRUD API → Task 1 ✅
- Version management (snapshot on save) → Task 1 Step 4 ✅
- Excel export → Task 2 ✅
- Frontend collection list → Task 3 ✅
- Frontend full editor with drag-drop → Deferred to Phase 3b (separate plan — needs significant UI work)

**2. Placeholder scan:**
No TBD or TODO found. All code is concrete.

**3. Type consistency:**
- `_coll_to_dict` returns items with `asset_id`, `position`, `role` → matches `AssetCollectionItem` fields ✅
- `export_collection_to_excel` uses `PositionPlatformPreset` columns → `_COLUMN_MAP` ✅

**Gap found:** Full drag-drop collection editor UI is deferred. This plan gives basic create/list/load functionality. The full editor (adding assets to collection via drag-drop, reordering, export button) is a separate plan — too much UI for this round.
