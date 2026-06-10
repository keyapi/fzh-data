# Phase 4: Collection Version History — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Collection version history side panel + non-destructive restore

**Architecture:** Backend REST endpoint for version restore + Vue 3 CDN side panel UI (320px drawer matching Asset detail panel pattern)

**Tech Stack:** FastAPI, SQLAlchemy, Vue 3 CDN

---

## File Structure

| File | Change |
|------|--------|
| `dam-prototype/main.py` | Add POST restore endpoint |
| `dam-prototype/static/index.html` | Add History panel CSS, HTML, Vue state+methods |

---

### Task 1: Backend — Restore Endpoint

**Files:**

- Modify: `dam-prototype/main.py` (insert after GET /versions endpoint)

- [ ] **Step 1: Add POST /api/collections/{coll_id}/versions/{v}/restore**

Insert after line ~418 (after the GET versions endpoint), before the export endpoint:

```python
@app.post("/api/collections/{coll_id}/versions/{v}/restore")
def restore_version(coll_id: str, v: int):
    """Non-destructive restore: snapshots current state, then rebuilds from version snapshot."""
    c = session.query(AssetCollection).filter_by(id=coll_id).first()
    if not c:
        return JSONResponse({"error": "not found"}, 404)

    ver = session.query(AssetCollectionVersion)\
        .filter_by(collection_id=coll_id, version=v).first()
    if not ver:
        return JSONResponse({"error": "version not found"}, 404)

    # Non-destructive: snapshot current state first (Figma pattern)
    current_items = [{"asset_id": ci.asset_id, "position": ci.position, "role": ci.role}
                     for ci in sorted(c.items, key=lambda x: x.position)]
    if current_items:
        session.add(AssetCollectionVersion(
            collection_id=c.id, version=c.version,
            snapshot={"images": current_items},
        ))

    # Wipe current items and rebuild from snapshot
    for old in list(c.items):
        session.delete(old)
    session.flush()
    for img in ver.snapshot.get("images", []):
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

- [ ] **Step 2: Verify endpoint works**

```bash
cd dam-prototype && uv run python main.py --port 8098 --no-browser &
sleep 2

# Get a collection and its versions
COLL_ID=$(curl -s http://127.0.0.1:8098/api/collections | python -c "import sys,json;d=json.load(sys.stdin);print(d['collections'][0]['id'])")
curl -s http://127.0.0.1:8098/api/collections/$COLL_ID/versions | python -m json.tool

# Test restore to v1 (if it exists)
curl -s -X POST http://127.0.0.1:8098/api/collections/$COLL_ID/versions/1/restore | python -c "import sys,json;d=json.load(sys.stdin);print('restored to v'+str(d.get('version','?'))+' with '+str(len(d.get('items',[])))+' items')"

kill %1
```

- [ ] **Step 3: Commit**

```bash
git add dam-prototype/main.py
git commit -m "feat(dam): POST /api/collections/{id}/versions/{v}/restore — non-destructive rollback"
```

---

### Task 2: Frontend — Version History Panel

**Files:**

- Modify: `dam-prototype/static/index.html` (CSS + HTML + Vue)

- [ ] **Step 1: Add History panel CSS**

Insert after the editor-picker CSS block (before `</style>`):

```css
/* ── Version History Panel ── */
.history-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.2); z-index: 22; opacity: 0; pointer-events: none; transition: opacity 0.2s; }
.history-overlay.visible { opacity: 1; pointer-events: auto; }
.history-panel { position: fixed; top: 0; right: 0; width: 320px; height: 100vh; background: var(--surface); border-left: 1px solid var(--border); z-index: 23; transform: translateX(100%); transition: transform 0.25s cubic-bezier(0.16,1,0.3,1); display: flex; flex-direction: column; box-shadow: var(--shadow-lg); }
.history-panel.open { transform: translateX(0); }
.history-header { display: flex; align-items: center; gap: 8px; padding: 12px 16px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.history-header h3 { font-size: 14px; font-weight: 600; }
.history-body { flex: 1; overflow-y: auto; padding: 10px; }
.history-card { padding: 10px 12px; border-radius: 6px; margin-bottom: 6px; cursor: pointer; transition: all 0.15s; border-left: 3px solid transparent; background: var(--surface-hover); }
.history-card:hover { background: var(--bg); }
.history-card.current { border-left-color: var(--primary); background: var(--primary-light); }
.history-card.selected { border: 1px solid var(--warning); }
.history-card .ver-header { display: flex; align-items: center; gap: 6px; margin-bottom: 3px; }
.history-card .ver-header strong { font-size: 13px; }
.history-card .ver-header .badge { font-size: 9px; padding: 1px 5px; border-radius: 8px; font-weight: 500; }
.history-card .ver-header .badge.current { background: var(--primary); color: #FFF; }
.history-card .ver-meta { font-size: 10px; color: var(--text-muted); margin-bottom: 4px; }
.history-card .ver-thumbs { display: flex; gap: 3px; }
.history-card .ver-thumb { width: 26px; height: 26px; border-radius: 3px; overflow: hidden; background: var(--border); }
.history-card .ver-thumb img { width: 100%; height: 100%; object-fit: cover; }
.history-card .restore-btn { margin-top: 6px; width: 100%; padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; cursor: pointer; background: var(--warning); color: #000; border: none; display: none; }
.history-card.selected .restore-btn { display: block; }
```

- [ ] **Step 2: Add History button to editor toolbar**

In the editor-toolbar, add after Export Excel button (line ~213):

old_string:
```html
<button class="btn btn-secondary" @click="exportEditor" style="font-size:12px;padding:4px 12px">Export Excel</button>
```

new_string:
```html
<button class="btn btn-secondary" @click="exportEditor" style="font-size:12px;padding:4px 12px">Export Excel</button>
<button class="btn btn-secondary" @click="openHistory" style="font-size:12px;padding:4px 12px">History</button>
```

- [ ] **Step 3: Add History panel HTML**

Insert before the closing `</div>` of editor-main area (before the asset picker overlay div), at the same level as detail-overlay:

old_string:
```html
</div><!-- end .editor-view -->
<div v-if="editorPick" class="editor-picker-overlay"
```

new_string:
```html
</div><!-- end .editor-view -->
<div class="history-overlay" :class="{visible: showHistory}" @click="showHistory=false"></div>
<div class="history-panel" :class="{open: showHistory}">
  <div class="history-header"><h3>History</h3><button class="close-btn" @click="showHistory=false">×</button></div>
  <div class="history-body">
    <div v-for="ver in editorVersions" :key="ver.version" class="history-card"
         :class="{current: ver.version===editorColl.version, selected: selectedVer===ver.version}"
         @click="selectedVer = selectedVer===ver.version ? null : ver.version">
      <div class="ver-header">
        <strong>v{{ ver.version }}</strong>
        <span v-if="ver.version===editorColl.version" class="badge current">current</span>
      </div>
      <div class="ver-meta">{{ fmtDate(ver.created_at) }} · {{ (ver.snapshot.images||[]).length }} images</div>
      <div class="ver-thumbs">
        <div v-for="img in (ver.snapshot.images||[]).slice(0,4)" :key="img.asset_id" class="ver-thumb">
          <img :src="getThumbByAssetId(img.asset_id)" loading="lazy">
        </div>
      </div>
      <button v-if="selectedVer===ver.version && ver.version!==editorColl.version" class="restore-btn"
              @click.stop="restoreVersion(ver.version)">Restore to v{{ ver.version }}</button>
    </div>
  </div>
</div>
<div v-if="editorPick" class="editor-picker-overlay"
```

- [ ] **Step 4: Add Vue state and methods**

Add state after `editorDirty`:

old_string:
```javascript
const editorColl=ref(null),editorSku=ref(null),editorPick=ref(false),editorPicked=ref([]),editorDirty=ref(false);
```

new_string:
```javascript
const editorColl=ref(null),editorSku=ref(null),editorPick=ref(false),editorPicked=ref([]),editorDirty=ref(false);
const showHistory=ref(false),editorVersions=ref([]),selectedVer=ref(null);
```

Add methods before `openCollectionEditor`:

```javascript
async function openHistory(){if(!editorColl.value)return;try{const r=await fetch('/api/collections/'+editorColl.value.id+'/versions');const d=await r.json();editorVersions.value=d.versions||[];showHistory.value=true;selectedVer.value=null}catch(e){toast('Failed to load history','error')}}
async function restoreVersion(v){if(!editorColl.value)return;if(!confirm('Restore to v'+v+'? Current v'+editorColl.value.version+' will be saved as a checkpoint.'))return;try{const r=await fetch('/api/collections/'+editorColl.value.id+'/versions/'+v+'/restore',{method:'POST'});if(!r.ok)throw new Error('Restore failed');editorColl.value=await r.json();editorDirty.value=false;showHistory.value=false;toast('Restored to v'+v)}catch(e){toast('Restore failed','error')}}
function getThumbByAssetId(aid){const a=assets.value.find(x=>x.id===aid);return a?(a.thumb_url||a.file_url):''}
```

- [ ] **Step 5: Update return statement**

Add new symbols to return:

```
showHistory,editorVersions,selectedVer,openHistory,restoreVersion,getThumbByAssetId
```

- [ ] **Step 6: Commit**

```bash
git add dam-prototype/static/index.html
git commit -m "feat(dam): version history side panel with non-destructive restore"
```

---

### Task 3: Integration Test

- [ ] **Step 1: Start server and verify**

```bash
cd dam-prototype
uv run python main.py --port 8098 --no-browser
```

Manual test in browser at `http://localhost:8098`:
1. Open a collection → editor shows
2. Click "History" → right panel slides in showing version list
3. Verify current version has blue border + "current" badge
4. Click an older version → yellow border + "Restore to v{N}" button
5. Click Restore → confirm dialog appears → confirm → panel closes, editor refreshes
6. Open History again → verify a checkpoint of pre-restore state was created

- [ ] **Step 2: Commit any fixes**

---

## Self-Review

1. **Spec coverage**: All spec requirements mapped. Restore endpoint (spec §3) → Task 1. Panel UI (spec §4) → Task 2. Non-destructive flow (spec §2.3) → both tasks.
2. **No placeholders**: Every step has actual code.
3. **Type consistency**: `editorVersions` array of `{version, created_at, snapshot: {images: [...]}}` — matches `GET /versions` response format. `getThumbByAssetId` uses `a.thumb_url` from `_asset_to_dict`. Consistent throughout.
