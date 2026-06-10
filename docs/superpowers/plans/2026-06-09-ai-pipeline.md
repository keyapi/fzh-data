# AI Auto-Tagging Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace mock AI tagging with real Deepseek V4 Vision API calls — upload triggers auto-tagging + compliance check, stored as `ai_metadata` on Asset, confirmed by user via frontend.

**Architecture:** New module `dam-prototype/ai_pipeline.py` handles Deepseek API calls. Upload endpoint triggers async background processing. Existing `models.py` already has `ai_metadata` (JSON) and `ai_tags_confirmed` fields. Frontend already displays AI tags as yellow pills with confirm button.

**Tech Stack:** Deepseek V4 Vision API (OpenAI-compatible format), Pillow (image→base64), FastAPI BackgroundTasks, existing SQLAlchemy models.

**Prerequisites:** `DEEPSEEK_API_KEY` in `.env`, `DEEPSEEK_BASE_URL` (default `https://api.deepseek.com/v1`).

---

### Task 1: AI Pipeline Module

**Files:**
- Create: `dam-prototype/ai_pipeline.py`
- Modify: `dam-prototype/.env.example`

- [ ] **Step 1: Create ai_pipeline.py with Deepseek client**

```python
# ai_pipeline.py
"""AI auto-tagging pipeline — Deepseek V4 Vision API."""
from __future__ import annotations
import base64, json, os
from pathlib import Path
import httpx

DEEPSEEK_BASE = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

TAG_PROMPT = """Analyze this ecommerce product image for home textiles (pillow, cushion, sofa cover category).
Return ONLY valid JSON, no other text:
{
  "color": "white|black|red|blue|gray|beige|navy|green|brown|multi|other",
  "angle": "front|back|side|top|detail|45degree|lifestyle|other",
  "category": "pillow|cushion|sofa_cover|floor_pillow|other",
  "view_type": "studio|bedroom|living_room|outdoor|packaging|other",
  "background": "pure_white|off_white|colored|scene",
  "has_text_overlay": false,
  "has_logo_watermark": false,
  "has_human": false,
  "product_fill_pct": 85,
  "alt_text": "concise SEO alt text in English",
  "tags": ["tag1","tag2","tag3"]
}"""

COMPLIANCE_PROMPT = """Check if this image meets Amazon main image requirements:
- Pure white background (RGB 255,255,255)
- Product fills >=85% of frame
- No text, logos, or watermarks
- sRGB color profile preferred
Return ONLY valid JSON:
{
  "amazon_main_pass": true,
  "amazon_issues": [],
  "wayfair_main_pass": true,
  "wayfair_issues": []
}"""


def image_to_base64(path: str) -> str:
    """Read image file, return data:image/jpeg;base64,... string."""
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    ext = Path(path).suffix.lower().replace("jpeg", "jpg").replace(".", "")
    if ext not in ("jpg", "jpeg", "png", "gif", "webp"):
        ext = "jpeg"
    return f"data:image/{ext};base64,{b64}"


async def call_deepseek_vision(image_path: str, prompt: str) -> dict:
    """Send image + prompt to Deepseek, return parsed JSON response."""
    data_url = image_to_base64(image_path)
    body = {
        "model": DEEPSEEK_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }],
        "max_tokens": 500,
        "temperature": 0.1,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{DEEPSEEK_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_KEY}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        # Extract JSON from possible markdown code fence
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        return json.loads(content.strip())


async def run_ai_pipeline(asset_id: str, image_path: str) -> dict:
    """Run full AI pipeline on an image: tags + compliance. Returns dict to store in ai_metadata."""
    try:
        tags = await call_deepseek_vision(image_path, TAG_PROMPT)
        compliance = await call_deepseek_vision(image_path, COMPLIANCE_PROMPT)
        return {"tags": tags.get("tags", []), "color": tags.get("color"),
                "angle": tags.get("angle"), "category": tags.get("category"),
                "alt_text": tags.get("alt_text"), "compliance": compliance}
    except Exception as e:
        return {"error": str(e), "tags": [], "compliance": {}}
```

- [ ] **Step 2: Update .env.example to document new vars**

Append to `dam-prototype/.env.example`:
```
# Deepseek Vision API (for AI auto-tagging)
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
```

- [ ] **Step 3: Commit**

```bash
git add dam-prototype/ai_pipeline.py dam-prototype/.env.example
git commit -m "feat(dam): add AI pipeline module with Deepseek Vision integration"
```

---

### Task 2: Wire AI Pipeline into Upload Flow

**Files:**
- Modify: `dam-prototype/main.py:120-150` (upload endpoint)

- [ ] **Step 1: Add import at top of main.py**

```python
from ai_pipeline import run_ai_pipeline
from fastapi import BackgroundTasks
```

- [ ] **Step 2: Add AI processing after file save in upload endpoint**

In `main.py`, inside the `upload_files` function, after `session.add(asset)` and `session.commit()`, add background task:

In the upload loop, after `session.commit()`:
```python
# Trigger AI pipeline in background
import asyncio
asyncio.create_task(_process_ai(asset.id, asset.stored_path))
```

And add this function before the upload endpoint:
```python
async def _process_ai(asset_id: str, image_path: str):
    """Background AI processing — called after upload."""
    from models import Asset as AssetModel
    # Need fresh session for background task
    from models import init_db as _init_db
    from sqlalchemy.orm import Session as _Session
    bg_session = _init_db(f"sqlite:///{DB_PATH}")
    try:
        result = await run_ai_pipeline(asset_id, image_path)
        asset = bg_session.query(AssetModel).filter_by(id=asset_id).first()
        if asset:
            asset.ai_metadata = result
            asset.ai_tags_confirmed = False
            bg_session.commit()
    except Exception as e:
        print(f"AI pipeline failed for {asset_id}: {e}")
```

Wait — FastAPI background tasks with SQLAlchemy sessions are tricky. Let me think about this differently.

**Correction — Use FastAPI BackgroundTasks properly:**

Step 2 revised:
```python
# In the upload for-loop, after session.commit():
# Don't use asyncio.create_task — use a sync background task
# that creates its own session

def _process_ai_sync(asset_id: str, image_path: str, db_url: str):
    """Sync wrapper for AI pipeline — runs in thread pool."""
    import asyncio as aio
    sess = init_db(db_url)
    try:
        result = aio.run(run_ai_pipeline(asset_id, image_path))
        asset = sess.query(Asset).filter_by(id=asset_id).first()
        if asset:
            asset.ai_metadata = result
            asset.ai_tags_confirmed = False
            sess.commit()
    except Exception as e:
        print(f"AI pipeline failed for {asset_id}: {e}")
    finally:
        sess.close()
```

And in the upload endpoint, replace the manual asyncio with:
```python
# After session.commit() for the new asset:
from fastapi.concurrency import run_in_threadpool
# Actually, BackgroundTasks is cleaner:
background_tasks.add_task(_process_ai_sync, asset.id, asset.stored_path, f"sqlite:///{DB_PATH}")
```

And add `background_tasks: BackgroundTasks` parameter to `upload_files`.

- [ ] **Step 3: Restart server and test upload of one image**

```bash
# Upload a test image, then check the DB:
uv run python -c "
from models import init_db, Asset
s = init_db('sqlite:///dam.db')
a = s.query(Asset).first()
print(a.ai_metadata)
"
```

Expected: `ai_metadata` contains tags, color, compliance results.

- [ ] **Step 4: Commit**

```bash
git add dam-prototype/main.py
git commit -m "feat(dam): wire AI pipeline into upload flow via BackgroundTasks"
```

---

### Task 3: Frontend AI Result Display (already partially done)

**Files:**
- Verify: `dam-prototype/static/index.html` (AI pill display + confirm button)

**Status: No changes needed.** The frontend already:
- Shows `ai_tags` as yellow pills (line: `<span v-for="(t,i) in (detailAsset.ai_tags||[])">`)
- Shows "Confirm AI Tags" button when `!ai_tags_confirmed`
- `confirmAi()` calls `API.update(id, {ai_tags_confirmed: true})` and merges tags

**One fix needed**: The frontend reads `a.ai_tags` from the API response, but `_asset_to_dict` maps `ai_metadata.get("tags")` to `ai_tags`. This is already correct in the current code.

- [ ] **Step 1: Verify the frontend display logic**

Check `_asset_to_dict` in `main.py`:
```python
"ai_tags": a.ai_metadata.get("tags") if a.ai_metadata else None,
"ai_tags_confirmed": a.ai_tags_confirmed,
```

This is correct. No changes needed.

- [ ] **Step 2: Commit (if any verification fixes)**

```bash
git add dam-prototype/static/index.html
git commit -m "fix(dam): verify AI tag display pipeline from backend to frontend"
```

---

### Task 4: End-to-End Test

**Files:**
- Create: `dam-prototype/test_ai_pipeline.py`

- [ ] **Step 1: Write a manual test script**

```python
"""Manual test: upload image → verify AI pipeline runs."""
import sys
sys.path.insert(0, ".")
from ai_pipeline import image_to_base64, call_deepseek_vision, TAG_PROMPT

if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else input("Image path: ")
    import asyncio
    result = asyncio.run(call_deepseek_vision(path, TAG_PROMPT))
    import json
    print(json.dumps(result, indent=2))
```

- [ ] **Step 2: Run test with a local product image**

```bash
uv run python test_ai_pipeline.py D:/path/to/test-pillow-image.jpg
```

Expected: JSON output with `color`, `angle`, `category`, `tags`, `alt_text`.

- [ ] **Step 3: Upload same image via browser, verify AI pills appear**

Open `http://127.0.0.1:8098`, upload the test image. After upload completes:
- Asset appears in grid
- Click it → detail panel shows yellow AI tag pills
- Click "Confirm AI Tags" → tags turn blue (manual style) and button disappears

- [ ] **Step 4: Commit test script**

```bash
git add dam-prototype/test_ai_pipeline.py
git commit -m "test(dam): add manual test script for AI pipeline"
```

---

## Self-Review

**1. Spec coverage:**
- Upload triggers AI pipeline → Task 2 ✅
- Deepseek V4 Vision API calls → Task 1 ✅
- Tags + compliance stored as ai_metadata → Task 1, Task 2 ✅
- Frontend shows yellow pills → Task 3 ✅
- Confirm AI Tags merges into tags → Task 3 ✅
- Compliance result visible → Partial (stored in ai_metadata, but not yet shown in detail panel UI — defer to Phase 2b)

**2. Placeholder scan:** No TBD/TODO found. All code is concrete.

**3. Type consistency:** `ai_metadata` field is JSON in models.py, `call_deepseek_vision` returns dict, `run_ai_pipeline` returns dict. Consistent.

**Gap found:** Compliance result is stored but not displayed in detail panel. This is a separate UI task (add compliance section to detail panel). Deferred to Phase 2b — not blocking the core AI tagging flow.
