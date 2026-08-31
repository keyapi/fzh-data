---
okf: v0.1
type: Research
title: Amazon 否定词 Bulksheet 格式研究
description: Amazon Ads Console Bulk Operations 的否定关键词 .xlsx 文件格式规范
tags: [amazon, advertising, negative-keywords, bulksheet, research]
created: 2026-07-02
updated: 2026-07-07
---
# Amazon Advertising: Negative Keyword Bulk Upload Format

> Research date: 2026-07-02
> Purpose: Define the exact file format and column schema for generating negative keyword bulk uploads that can be directly uploaded to Amazon Ads Console.

---

## Executive Summary

Amazon provides TWO ways to manage negative keywords at scale:

| Method | Vehicle | Capability | Recommendation |
|--------|---------|-----------|----------------|
| **Bulksheets** (no-code) | `.xlsx` file uploaded via Amazon Ads Console UI | Create/Update/Archive negative keywords and negative products | **Primary route** -- best for our use case |
| **Amazon Ads API** (programmatic) | REST API `POST /adsApi/v1/create/targets` | Create/manage negative keywords one-by-one (not truly "bulk") | Secondary -- useful for real-time adjustments, but volume-limited |

Sellfox API currently provides **query-only** (read) endpoints for negative keywords -- it does NOT offer create/update/delete operations for any ad keywords or targeting.

---

## 1. Bulksheet File Format (Primary Method)

### 1.1 Accepted File Types

| Format | Accepted? | Notes |
|--------|-----------|-------|
| `.xlsx` | YES | Recommended |
| `.xls` | YES | Legacy Excel format |
| `.csv` | NO | Amazon Ads bulksheets do NOT accept CSV |
| `.tsv` | NO | Not supported |

**Key**: Amazon Advertising bulksheets require Excel format (`.xlsx` or `.xls`). This is different from Seller Central inventory flat files which accept CSV.

### 1.2 Download / Upload Location

- **Download template**: Amazon Ads Console > Bulk Operations > "Download a bulk operations template"
- **Upload**: Same page > "Upload spreadsheet"

### 1.3 Bulksheet Structure (New Format, v2)

The new bulksheet format uses a **three-column header triplet** that appears in EVERY tab for every ad type:

| Column A | Column B | Column C |
|----------|----------|----------|
| **Product** | **Entity** | **Operation** |

**Column A (Product)** -- the ad product type:
- `Sponsored Products`
- `Sponsored Brands`
- `Sponsored Display` (or `Display`)

**Column B (Entity)** -- the entity hierarchy level. The full hierarchy for Sponsored Products:

```
Campaign
  ├── Ad Group
  │     ├── Product Ad
  │     ├── Keyword
  │     ├── Negative Keyword           <-- ad group-level negative keyword
  │     ├── Bidding Adjustment
  │     ├── Product Targeting
  │     └── Negative Product Targeting <-- ad group-level negative product/ASIN
  ├── Campaign Negative Keyword        <-- campaign-level negative keyword
  └── Campaign Negative Product        <-- campaign-level negative product/ASIN
```

**Column C (Operation)** -- what action to perform:
- `create` -- add a new record (leave Record ID blank)
- `update` -- modify an existing record (must include Record ID)
- `archive` -- delete/archive a record (must include Record ID)

> **IMPORTANT**: Legacy bulksheets used a single "Record Type" column and different column headers. These have been DEPRECATED. Always use the new bulksheet format with the Product/Entity/Operation triplet.

---

## 2. Negative Keyword Column Schema

### 2.1 Campaign-Level Negative Keywords

Entity value: `Campaign Negative Keyword`

| Column | Required | Value / Format | Notes |
|--------|----------|---------------|-------|
| Product | YES | `Sponsored Products` | |
| Entity | YES | `Campaign Negative Keyword` | Case-sensitive? Use exact casing from template |
| Operation | YES | `create` / `update` / `archive` | |
| Campaign ID | YES | e.g. `A1B2C3D4E5F6G7` | Amazon-assigned campaign identifier |
| Campaign Name | YES | e.g. `My Auto Campaign` | Must exactly match existing campaign (case-sensitive) |
| Ad Group ID | NO | Leave empty | Not applicable at campaign level |
| Ad Group Name | NO | Leave empty | Not applicable at campaign level |
| Keyword ID | For update/archive | e.g. `A1B2C3D4E5F6G7` | Amazon-assigned keyword identifier; leave empty for create |
| Keyword Text | YES | e.g. `cheap shoes` | The actual negative keyword phrase (max 100 chars) |
| Match Type | YES | `exact`, `phrase`, or `broad` | See match type details below |
| State | YES | `enabled` / `archived` | Campaign-level neg keywords CANNOT be paused. Use `archive` to remove. |

### 2.2 Ad Group-Level Negative Keywords

Entity value: `Negative Keyword`

| Column | Required | Value / Format | Notes |
|--------|----------|---------------|-------|
| Product | YES | `Sponsored Products` | |
| Entity | YES | `Negative Keyword` | |
| Operation | YES | `create` / `update` / `archive` | |
| Campaign ID | YES | e.g. `A1B2C3D4E5F6G7` | |
| Campaign Name | YES | e.g. `My Auto Campaign` | Must exactly match (case-sensitive) |
| Ad Group ID | YES | e.g. `A1B2C3D4E5F6G7` | Must match an existing ad group within the campaign |
| Ad Group Name | YES | e.g. `Ad Group 1` | Must exactly match (case-sensitive) |
| Keyword ID | For update/archive | e.g. `A1B2C3D4E5F6G7` | Leave empty for create |
| Keyword Text | YES | e.g. `cheap shoes` | Actual negative keyword phrase (max 100 chars) |
| Match Type | YES | `exact`, `phrase`, or `broad` | |
| State | YES | `enabled` / `paused` / `archived` | Ad group-level negatives CAN be paused |

### 2.3 Match Type Values

For **negative keywords**, Amazon uses different match type vocabulary than positive keywords:

| Bulksheet Value | API Value | Description | Example |
|----------------|-----------|-------------|---------|
| `exact` | `EXACT` | Block only exact match queries | Negate "running shoes" -- only blocks searches for exactly "running shoes" |
| `phrase` | `PHRASE` | Block queries containing the phrase in order | Negate "running shoes" -- blocks "cheap running shoes", "running shoes men" |
| `broad` | `BROAD` | Block queries with any word from the phrase | Negate "running shoes" -- blocks "shoes for running", "athletic running", "feet shoes" |

> **Legacy naming**: In older (deprecated) bulksheets, campaign-level negatives used `Campaign Negative Exact` / `Campaign Negative Phrase` while ad-group level used `Negative Exact` / `Negative Phrase`. The NEW format simply uses `exact` / `phrase` / `broad`.

### 2.4 Campaign vs Ad Group Level: Behavioral Differences

| Property | Campaign Negative Keyword | Negative Keyword (Ad Group) |
|----------|--------------------------|-----------------------------|
| Scope | Blocks terms in ALL ad groups within the campaign | Blocks terms only in the specified ad group |
| Can pause? | NO -- must use `archive` to remove | YES -- can set State to `paused` |
| Archive behavior | Deletes the negative keyword from all records permanently | Removes only for that ad group |
| Typical use case | Brand-level exclusions, competitor names | Ad-group-specific waste terms discovered from search term reports |

---

## 3. Negative Product Targeting (ASIN / Brand)

### 3.1 Campaign-Level Negative Products

Entity value: `Campaign Negative Product`

| Column | Required | Value / Format | Notes |
|--------|----------|---------------|-------|
| Product | YES | `Sponsored Products` | |
| Entity | YES | `Campaign Negative Product` | |
| Operation | YES | `create` / `update` / `archive` | |
| Campaign ID | YES | e.g. `A1B2C3D4E5F6G7` | |
| Campaign Name | YES | Must exactly match | |
| Target ID | For update/archive | Amazon-assigned ID | Leave empty for create |
| Targeting Expression | YES | See below | e.g. `asinSameAs="B0XXXXXXX"` |
| State | YES | `enabled` / `archived` | |

### 3.2 Ad Group-Level Negative Products

Entity value: `Negative Product` (or `Negative Product Targeting`)

| Column | Required | Value / Format | Notes |
|--------|----------|---------------|-------|
| Product | YES | `Sponsored Products` | |
| Entity | YES | `Negative Product` | |
| Operation | YES | `create` / `update` / `archive` | |
| Campaign ID | YES | | |
| Ad Group ID | YES | | |
| Target ID | For update/archive | | Leave empty for create |
| Targeting Expression | YES | See below | |
| State | YES | `enabled` / `paused` / `archived` | |

### 3.3 Targeting Expression Format

Negative product/ASIN/brand targeting uses the `expression` field with specific format strings:

| Expression | Meaning | Example |
|-----------|---------|---------|
| `asinSameAs="B0XXXXXXX"` | Negate a specific ASIN | `asinSameAs="B09XYZ1234"` |
| `asinBrandSameAs="BrandName"` | Negate all products from a brand | `asinBrandSameAs="Nike"` |

---

## 4. API Route: Amazon Ads API

### 4.1 Endpoint (Unified Targets API v1)

The Amazon Ads API uses a **unified targets API** where you set `negative: true` to create negative keywords.

**Create endpoint**: `POST https://advertising-api.amazon.com/adsApi/v1/create/targets`

**Required headers**:
```
Amazon-Advertising-API-ClientId: <your-client-id>
Amazon-Advertising-API-Scope: <profile-id>
Authorization: Bearer <access-token>
Content-Type: application/json
```

**Request body -- Campaign-level negative keyword**:
```json
{
  "targets": [
    {
      "adProduct": "SPONSORED_PRODUCTS",
      "campaignId": "987654321",
      "negative": true,
      "state": "ENABLED",
      "targetDetails": {
        "keywordTarget": {
          "keyword": "toy",
          "matchType": "EXACT"
        }
      },
      "targetType": "KEYWORD"
    }
  ]
}
```

**Request body -- Ad group-level negative keyword**:
```json
{
  "targets": [
    {
      "adProduct": "SPONSORED_PRODUCTS",
      "adGroupId": "123456789",
      "negative": true,
      "state": "ENABLED",
      "targetDetails": {
        "keywordTarget": {
          "keyword": "toy",
          "matchType": "EXACT"
        }
      },
      "targetType": "KEYWORD"
    }
  ]
}
```

**Response**: HTTP `207 Multi-Status` with `success` and `error` arrays. The success entry includes the new `targetId` and `targetLevel` (`CAMPAIGN` or `AD_GROUP`).

**API Match Type Values**: `EXACT`, `PHRASE`, `BROAD`

### 4.2 API vs Bulksheets: Volume Considerations

The API endpoint creates targets **one at a time** (though you can batch multiple in one request body). For bulk operations with hundreds or thousands of negatives, **bulksheets are the recommended approach**. The API is better suited for programmatic, real-time adjustments (e.g., auto-adding a negative after a click threshold is hit).

### 4.3 API List/Query Endpoints

| Entity | List Endpoint |
|--------|--------------|
| Campaign negative keywords | `GET /v2/sp/campaignNegativeKeywords` |
| Campaign negative keywords (extended) | `GET /v2/sp/campaignNegativeKeywords/extended` |
| Ad group negative keywords | `GET /v2/sp/adGroupNegativeKeywords` |
| Ad group negative keywords (extended) | `GET /v2/sp/adGroupNegativeKeywords/extended` |

---

## 5. Sellfox API: Available Endpoints

### 5.1 What Exists (Query-Only)

Sellfox API has **read-only** (query) endpoints for all negative keyword types:

| Sellfox Endpoint | Ad Type | Entity | HTTP Method | Capability |
|-----------------|---------|--------|-------------|------------|
| `/api/cpc/manageData/spNeKeyword.json` | SP | Negative Keyword | POST | **Query only** (paginated listing) |
| `/api/cpc/manageData/spNeTarget.json` | SP | Negative Product | POST | **Query only** |
| `/api/cpc/manageData/sbNeKeyword.json` | SB | Negative Keyword | POST | **Query only** |
| `/api/cpc/manageData/sbNeTarget.json` | SB | Negative Product | POST | **Query only** |
| `/api/cpc/manageData/sdNeTarget.json` | SD | Negative Product | POST | **Query only** |

All these endpoints accept the same request structure:
```json
{
  "shopId": "string (required)",
  "state": "enabled | paused | archived",
  "campaignId": "string",
  "pageSize": "string (100~1000, default 100)",
  "groupId": "string",
  "nextToken": "string (for pagination)"
}
```

### 5.2 What Does NOT Exist (Write Operations)

Sellfox API currently has **NO create/update/delete endpoints** for:
- Negative keywords (SP, SB, SD)
- Negative products/ASINs (SP, SB, SD)
- Regular positive keywords (SP, SB)
- Any keyword-level write operations

All advertising endpoints under `/api/cpc/manageData/` use the same read/paginate pattern with `nextToken` cursors -- they are purely for data retrieval, not mutation.

### 5.3 Conclusion on Sellfox API

**Sellfox API cannot be used to create or manage negative keywords.** The only routes available for negative keyword management are:
1. Amazon Ads Console Bulk Operations (bulksheet upload) -- **recommended**
2. Amazon Ads API (`/adsApi/v1/create/targets`) -- programmatic alternative

---

## 6. Bulksheet Upload Process (Step by Step)

### Step 1: Download Template
1. Go to Amazon Ads Console
2. Navigate to "Bulk Operations" (left sidebar, under "Sponsored ads")
3. Click "Download a bulk operations template"
4. Select ad type: "Sponsored Products"
5. Download as `.xlsx`

### Step 2: Fill in Negative Keywords
Open the spreadsheet, find the tab for "Sponsored Products" and add rows:
- For campaign-level negatives: set Entity = `Campaign Negative Keyword`
- For ad group-level negatives: set Entity = `Negative Keyword`
- Populate Campaign ID/Name, Ad Group ID/Name (if applicable), Keyword Text, Match Type, State

### Step 3: Save and Upload
1. Save as `.xlsx` (NOT `.csv`)
2. Return to Bulk Operations page
3. Click "Upload spreadsheet"
4. Select your file
5. Wait for processing (few minutes for small files, up to hours for very large files)

### Step 4: Review Results
- Green: Success
- Yellow: Warnings (optional fixes)
- Red: Errors (must resolve and re-upload)
- Download error report if any rows failed

---

## 7. Important Formatting Rules

### 7.1 Case Sensitivity
- `Campaign Name` and `Ad Group Name` must match EXACTLY (case-sensitive) the names in your account
- `Entity` values may be case-sensitive -- match the template exactly
- `Operation` values are lowercase: `create`, `update`, `archive`
- `Match Type` values are lowercase: `exact`, `phrase`, `broad`
- `State` values are lowercase: `enabled`, `paused`, `archived`

### 7.2 Numeric Fields
- Do NOT use commas or currency symbols in numeric fields
- Use `1500` not `1,500`; use `50` not `50%`

### 7.3 ID Fields
- Leave `Keyword ID` / `Target ID` empty when creating new records (Amazon auto-assigns)
- NEVER modify existing Record IDs in the template unless you intend to update/archive those specific records
- If deleting rows from a downloaded template, delete entire rows (don't just clear cells)

### 7.4 Date Format
- If included, dates use `YYYYMMDD` format (e.g., `20260702`)

### 7.5 Encoding
- Save as standard Excel `.xlsx` format (handles encoding automatically)

---

## 8. Example Bulksheet Rows

### For generating Sponsored Products campaign-level negative keywords:

| Product | Entity | Operation | Campaign ID | Campaign Name | Keyword Text | Match Type | State |
|--------|--------|-----------|-------------|---------------|-------------|------------|-------|
| Sponsored Products | Campaign Negative Keyword | create | A1B2C3D4E5F6G7 | My Auto Campaign | cheap shoes | exact | enabled |
| Sponsored Products | Campaign Negative Keyword | create | A1B2C3D4E5F6G7 | My Auto Campaign | free trial | phrase | enabled |
| Sponsored Products | Campaign Negative Keyword | create | A1B2C3D4E5F6G7 | My Auto Campaign | buy now | broad | enabled |

### For generating Sponsored Products ad group-level negative keywords:

| Product | Entity | Operation | Campaign ID | Campaign Name | Ad Group ID | Ad Group Name | Keyword Text | Match Type | State |
|--------|--------|-----------|-------------|---------------|-------------|---------------|-------------|------------|-------|
| Sponsored Products | Negative Keyword | create | A1B2C3D4E5F6G7 | My Manual Campaign | G1H2I3J4K5L6M7 | Ad Group 1 | cheap shoes | exact | enabled |
| Sponsored Products | Negative Keyword | create | A1B2C3D4E5F6G7 | My Manual Campaign | G1H2I3J4K5L6M7 | Ad Group 1 | free trial | phrase | paused |

---

## 9. Recommendations For Our `generate_negatives.py`

Based on the master plan (`2026-07-02-ad-analysis-master-plan.md`, Step 4.2), we need to output a bulksheet `.xlsx` file. Here is the recommended approach:

1. **Use `openpyxl`** library to generate `.xlsx` files (Python standard for Excel)
2. **Output separate tabs** for campaign-level and ad-group-level negatives
3. **Column order** must match Amazon's template exactly:
   - Product, Entity, Operation, Campaign ID, Campaign Name, Ad Group ID, Ad Group Name, Keyword ID, Keyword Text, Match Type, State
4. **Match type mapping** for our analysis output:
   - High-spend zero-conversion terms from broad/phrase match -> add as `exact` negative to the originating campaign
   - Generic waste terms appearing across multiple campaigns -> add as `exact` or `phrase` negative at campaign level
5. **State defaults** to `enabled` for ad group-level, `enabled` for campaign-level (campaign-level cannot be paused)
6. **Always leave Keyword ID empty** since we are always creating new negatives

---

## 10. Source References

- [Amazon Ads Bulksheets v2 Migration Guide](https://advertising.amazon.com/API/docs/en-us/no-code-tools/bulksheets/2-0/migration-guide)
- [Amazon Ads Bulksheets: Get Started Part 1](https://advertising.amazon.com/API/docs/en-us/no-code-tools/bulksheets/2-0/get-started-with-bulksheets-part1)
- [Amazon Ads Bulksheets: Create SP Campaign](https://advertising.amazon.com/API/docs/en-us/no-code-tools/bulksheets/2-0/create-sp-campaign)
- [Amazon Ads Help: Manage Sponsored Ads with Bulksheets](https://advertising.amazon.ca/help/GPVTCZRJ7G9HXHWB)
- [Amazon Ads Help: Add Negative Keywords or Products](https://advertising.amazon.com/help/GTEHPEG5BXY9UX5W)
- [Amazon Ads API: Negative Keyword Targeting Guide](https://advertising.amazon.com/API/docs/en-us/guides/sponsored-products/negative-targeting/keywords)
- [Amazon Ads API: Campaign Structure Overview](https://advertising.amazon.com/API/docs/en-us/guides/sponsored-products/get-started/campaign-structure)
- [Amazon Bulk Operations User Guide (PDF)](https://m.media-amazon.com/images/G/01/api/guides/Bulk_operations_user_guide.pdf)
- [Amazon Sponsored Products Uploading (PDF)](https://m.media-amazon.com/images/G/28/AS/AGS/PDF/SP/9.sponsored-products-uploading._V507163357_.pdf)
- [BellaVix: How to Use Amazon Bulksheets](https://www.bellavix.com/how-to-use-amazon-bulksheets-to-manage-ppc-campaigns-at-scale/)
- [AdBadger: Amazon Advertising Bulk Operations](https://www.adbadger.com/blog/amazon-advertising-bulk-operations/)
- [AdBadger Help: Understanding Bulk Operations](https://help.adbadger.com/en/article/253-understanding-bulk-operations-in-amazon-ppc-campaign-management)
- [Feedvisor: How to Use Amazon Advertising Bulk Operations](https://feedvisor.com/resources/amazon-marketing-advertising-strategies/how-to-use-amazon-advertising-bulk-operations/)
- Sellfox API docs: `SELLFOX_API/docs/api-reference/广告/基础数据/SP否定关键词.md`
- Sellfox API docs: `SELLFOX_API/docs/api-reference/广告/基础数据/SP否定商品.md`
- Sellfox API docs: `SELLFOX_API/docs/api-reference/广告/基础数据/SB否定关键词.md`
- Sellfox API docs: `SELLFOX_API/docs/api-reference/广告/基础数据/SB否定商品.md`
- Sellfox API docs: `SELLFOX_API/docs/api-reference/广告/基础数据/SD否定商品.md`
