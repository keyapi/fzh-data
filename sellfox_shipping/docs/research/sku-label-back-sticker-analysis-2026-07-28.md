---
okf: v0.1
type: Research
title: SKU 背贴 PDF 生成 — 代码级实现指南（给 Agent 用）
description: 从 Colab notebook 提取的可移植代码 + 回退策略 + ERPNext SKU 名称通用查询 + sellfox_shipping 集成步骤
timestamp: 2026-07-28
tags: [sellfox-shipping, sku-label, back-sticker, pdf, reportlab, gspread, erpnext, sku-name-lookup]
---

# SKU 背贴 PDF 生成 — Agent 实现指南

> **写给接手开发的 Agent：** 本文包含可直接移植的 Python 代码。阅读顺序：§1 理解背贴 → §3 PDF 生成代码 → §4 名称查询（通用工具，也为背贴服务）→ §5 集成步骤。

## 1. 背贴是什么 / 输入输出

一张 4×2 英寸（288×144 points）的小标签 PDF，每包裹一页。贴在包裹上供仓库识别内容物。

**输入**（来自 sellfox_shipping）：
```
package_sn:   "P2AKA9T726212"
items:        [{commodity_sku: "KS0002-DL-194", seller_sku: "...", quantity: 2}, ...]
warehouse:    "DANEEY"
sku_names:    {"KS0002-DL-194": {"cn": "靠枕内胆 194cm", "es": "Relleno cojín 194cm"}}
```

**输出**：多页 PDF，每页包含：包裹号 + Code128 条形码 + 表格（序号 | SKU | 数量 | 中文名称 | 西班牙语名称）+ 右上角日期/仓库/页码。

## 2. Notebook 回退策略（Colab 遗产逻辑）

Notebook Cell 7 和 Cell 27 的 `merge_excel_gsheet()` 函数揭示了回退策略：

```python
# Step 1: left join Google Sheet，按 SKU 匹配
df = pd.merge(df_excel, df_sku_name, on=col_name_sku, how='left')

# Step 2: 回退 — 中文名称在 Google Sheet 里找不到，就用通途 Excel 自带的品名列
df.loc[df['中文名称'].isna(), '中文名称'] = df[col_name_product_name]

# Step 3: 西班牙语名称无回退，找不到就留空
df['西班牙语名称'].fillna('', inplace=True)
```

**回退链：**

| 名称 | 第一来源 | 回退（Google Sheet 无数据时）|
|------|---------|---------------------------|
| 中文名称 | Google Sheet `中文名称` | 通途 Excel 品名列（Fedex: `Buyer Notes` / 蜴国际: `收件人公司名称`）|
| 西班牙语名称 | Google Sheet `西班牙语名称` | 留空 |

**对应到 sellfox_shipping：** 赛狐包裹 item 只有 `variation`（Amazon 颜色/尺寸变体），没有中文品名。回退源需要换成 ERPNext Item。

## 3. PDF 生成核心代码

### 3.1 依赖

```bash
uv add reportlab
# reportlab 内置 STSong-Light 中文字体，无需额外安装字体文件
```

### 3.2 中英混排辅助

```python
# ── 语言检测 ──────────────────────────────────────────
def is_chinese(char: str) -> bool:
    return '一' <= char <= '鿿'


def split_text_by_language(text: str) -> list[tuple[str, bool]]:
    """按语言拆分文本为 [(片段, is_chinese), ...]。连续中文/拉丁各自成组。"""
    parts = []
    current = ""
    current_is_cn = None
    for char in text:
        char_is_cn = is_chinese(char)
        if current_is_cn is None:
            current_is_cn = char_is_cn
        if char_is_cn == current_is_cn or not char_is_cn:
            current += char
        else:
            parts.append((current, current_is_cn))
            current = char
            current_is_cn = char_is_cn
    if current:
        parts.append((current, current_is_cn))
    return parts


def build_mixed_xml(text: str, cn_font="STSong-Light", latin_font="Helvetica") -> str:
    """将文本转为 reportlab Paragraph XML。中文用 cn_font，拉丁用 latin_font。"""
    result = []
    for part, is_cn in split_text_by_language(text):
        if is_cn:
            result.append(f"<font name='{cn_font}'>{part}</font>")
        else:
            result.append(part)
    return ''.join(result)
```

### 3.3 核心 PDF 生成函数

```python
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.graphics.barcode import code128

# ── 常量（4×2 英寸标签）──────────────────────────────
PAGE_W, PAGE_H = 288, 144
MARGIN_L, MARGIN_R, MARGIN_TOP = 5, 5, 10
FONT_START, FONT_MIN, FONT_SHRINK, LEADING_SHRINK = 10, 5, 0.9, 0.9
COL_WIDTHS = [0.4*cm, 2.55*cm, 0.5*cm, 3.25*cm, 3.35*cm]
HEADERS = ['#', 'SKU', 'QTY', 'Name Chinese', 'Nombres en español']


def _build_table(items, font_size=10, leading=8):
    """构建 reportlab Table 数据。items: [{sku, qty, cn_name, es_name}, ...]"""
    styles = getSampleStyleSheet()
    ps = ParagraphStyle('cell', parent=styles['BodyText'], fontSize=font_size, leading=leading)
    data = [HEADERS]
    for i, it in enumerate(items, 1):
        data.append([
            str(i),
            Paragraph(it["sku"], ps),
            str(it.get("qty", 1)),
            Paragraph(build_mixed_xml(it.get("cn_name", "")), ps),
            Paragraph(build_mixed_xml(it.get("es_name", "")), ps),
        ])
    return data


def _table_style():
    return TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 1),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 1),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('TOPPADDING', (0, 1), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 2),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ])


def generate_sku_label_pdf(packages: list[dict], output_path: str, *,
                           timestamp: str = "", warehouse_class: str = "") -> str:
    """生成背贴 PDF。packages: [{package_sn, items: [{sku, qty, cn_name, es_name}]}]"""
    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    c = canvas.Canvas(output_path, pagesize=(PAGE_W, PAGE_H))
    total = len(packages)

    for page, pkg in enumerate(packages, 1):
        sn = pkg["package_sn"]
        items = pkg.get("items", [])
        y = PAGE_H - MARGIN_TOP

        c.setFont('Helvetica', 8)
        c.drawString(MARGIN_L, y, f"Package Number: {sn}")
        y -= 9
        code128.Code128(sn, barHeight=10, fontSize=8, barWidth=1.2).drawOn(c, MARGIN_L + 100, y + 5)

        c.setFont('STSong-Light', 5)
        label = f"{timestamp}{warehouse_class}仓" if warehouse_class else timestamp
        c.drawRightString(PAGE_W - MARGIN_R - 10, PAGE_H - MARGIN_TOP + 3, label)
        c.drawRightString(PAGE_W - MARGIN_R - 10, PAGE_H - MARGIN_TOP - 3, f"{page} / {total}")

        font_size, leading = FONT_START, 9.5
        while True:
            t = Table(_build_table(items, font_size, leading), colWidths=COL_WIDTHS)
            t.setStyle(_table_style())
            t.wrapOn(c, PAGE_W - MARGIN_L - MARGIN_R, y)
            if y - t._height >= 0 or font_size <= FONT_MIN:
                break
            font_size *= FONT_SHRINK
            leading *= LEADING_SHRINK
        t.drawOn(c, MARGIN_L - 3, y - t._height)
        c.showPage()
    c.save()
    return output_path
```

### 3.4 已知问题

长西班牙语名称偶尔超出单元格。用了 2 年仓库可以接受。如需修复，调大 `COL_WIDTHS[4]`（西语列宽）。

## 4. SKU 名称通用查询（新工具，也为背贴服务）

**不只是背贴需要。** 系统中多处需要根据 `commodity_sku` 查品名。新建一个通用 lookup 类，各处复用。

### 4.1 数据来源优先级

```
commodity_sku (如 KS0002-DL-194)
    │
    ├── 1. ERPNext Item.item_name   ← 权威来源（中文名）
    │      已有 EN API 集成（erpnext_dims_v2.py），复用同一套认证
    │
    ├── 2. Google Sheets "US SKU Name"  ← 西班牙语名（ERPNext 暂无此字段）
    │
    └── 3. 兜底：显示 commodity_sku 本身
```

### 4.2 实现代码

放在 `sellfox_shipping/sku_label/name_lookup.py`：

```python
"""SKU 名称查询 — 通用工具，从 ERPNext / Google Sheets 获取中/西语品名。

用途：背贴 PDF、包裹详情页、面单品名填充等。
"""

import os
from typing import Optional
from urllib.parse import quote

import httpx


class SkuNameLookup:
    """按 commodity_sku 查询中文名称和西班牙语名称。

    查询链: ERPNext Item → Google Sheets → SKU 编码兜底

    用法:
        lookup = SkuNameLookup(
            erpnext_base="https://erpnext.vilavi.cn",
            erpnext_api_key=os.getenv("ERP_API_KEY"),
            erpnext_api_secret=os.getenv("ERP_API_SECRET"),
        )
        name = lookup.get("KS0002-DL-194")
        # → {"cn": "靠枕内胆 194cm", "es": "Relleno cojín 194cm"}
    """

    def __init__(
        self,
        *,
        erpnext_base: str,
        erpnext_api_key: str,
        erpnext_api_secret: str,
        http_client: Optional[httpx.Client] = None,
    ):
        self._base = erpnext_base.rstrip("/")
        self._headers = {"Authorization": f"token {erpnext_api_key}:{erpnext_api_secret}"}
        self._client = http_client or httpx.Client(timeout=30)
        self._cache: dict[str, dict[str, str] | None] = {}  # None = 已查过但无数据

    def get(self, commodity_sku: str) -> dict[str, str]:
        """返回 {"cn": str, "es": str}。未找到时 cn = commodity_sku, es = ""."""
        sku = (commodity_sku or "").strip()
        if not sku:
            return {"cn": "", "es": ""}
        if sku not in self._cache:
            self._cache[sku] = self._resolve(sku)
        result = self._cache[sku]
        return result if result else {"cn": sku, "es": ""}

    def prefetch(self, skus: list[str]) -> None:
        """批量预热缓存。"""
        for sku in skus:
            self.get(sku)

    def _resolve(self, commodity_sku: str) -> dict[str, str] | None:
        """查询 ERPNext Item。"""
        item = self._fetch_erpnext_item(commodity_sku)
        if item is None:
            return None  # cache miss, will fallback to sku in get()

        cn = (item.get("item_name") or item.get("description") or "").strip()
        es = (item.get("custom_spanish_name") or "").strip()

        # TODO: 如果 ERPNext 没有 custom_spanish_name，可选接入 Google Sheets
        # es = self._fetch_gsheet_es_name(commodity_sku) or es

        if not cn:
            return None
        return {"cn": cn, "es": es}

    def _fetch_erpnext_item(self, commodity_sku: str) -> dict | None:
        """通过 EN API 获取 ERPNext Item 文档。

        与 erpnext_dims_v2.py._fetch_item() 同一接口，但只取名称相关字段。
        """
        try:
            path = quote(commodity_sku, safe="")
            url = f"{self._base}/api/resource/Item/{path}"
            resp = self._client.get(
                url,
                headers=self._headers,
                params={"fields": '["item_name","description","custom_spanish_name"]'},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data") if data.get("data") else None
        except Exception:
            # EN 不可用时返回 None，上层兜底为 SKU 编码
            return None
```

> **注意**：`custom_spanish_name` 是假设的 ERPNext 自定义字段名。如果 ERPNext 中没有西语名字段，需要先建字段，或者接 Google Sheets。详见 §4.3。

### 4.3 Google Sheets 凭证（西语名兜底，单独发给同事）

**⚠️ 私钥绝对不能放入 git。** 通过钉钉/微信单独发给同事。

当前 service account:
- Email: `colab-gsheets@gsheets-351101.iam.gserviceaccount.com`
- Google Sheet: "US SKU Name" → worksheet "SKUName"
- 权限：将上述 email 添加为 Sheet 的 Viewer

环境变量（`.env`，gitignore）：
```bash
ERP_API_KEY=xxx          # 已有，erpnext_dims_v2.py 在用
ERP_API_SECRET=xxx       # 已有
# 以下仅在需要 Google Sheets 西语名兜底时需要：
GOOGLE_SERVICE_ACCOUNT_FILE=data/service-account.json
```

## 5. 集成到 sellfox_shipping 的步骤

### Step 1：新增模块

```
sellfox_shipping/sku_label/
├── __init__.py          # 导出 generate_sku_label_pdf, SkuNameLookup
├── pdf_generator.py     # §3 代码
└── name_lookup.py       # §4 代码
```

### Step 2：在 app.py 中初始化 SkuNameLookup（全局复用）

```python
# app.py 或依赖注入
from sellfox_shipping.sku_label.name_lookup import SkuNameLookup

sku_name_lookup = SkuNameLookup(
    erpnext_base=os.getenv("ERP_API_BASE_URL", "https://erpnext.vilavi.cn"),
    erpnext_api_key=os.getenv("ERP_API_KEY", ""),
    erpnext_api_secret=os.getenv("ERP_API_SECRET", ""),
)
```

### Step 3：CLI 命令

在 `cli.py` 新增：

```python
@cli.command("sku-label")
def sku_label(
    package_sn: str = typer.Option(..., help="包裹号"),
    output: str = typer.Option("sku_label.pdf", help="输出路径"),
):
    """为一个包裹生成 SKU 背贴 PDF"""
    # ... 获取包裹 items → SkuNameLookup.prefetch(skus) → generate_sku_label_pdf(...)
```

### Step 4：Web 按钮

`templates/package_detail.html` 加 `<a href="/packages/{{ sn }}/sku-label">下载背贴</a>`，对应 `app.py` 路由返回 `FileResponse`。

### Step 5：测试

```bash
uv run python -m sellfox_shipping.cli sku-label --package-sn P2AKA9T726212 -o test.pdf
# 打开 PDF 验证：中文/西语/条形码/页码
uv run pytest tests/sellfox_shipping -q
```

## 6. Colab notebook 速查（148 cells）

| 区块 | Cells | 做什么 | 要不要 |
|------|-------|--------|--------|
| 0 | 0 | pip install + gspread 认证（**含硬编码私钥**）| 参考 gsheet2df() |
| 0.1 | 1 | VITE-FedEx PDF 奇偶页拆分 | 不要 |
| 2.x | 2-16 | 通途 FedEx 背贴 PDF + Excel 合并 | **§3 代码出处** |
| 3.x | 17-34 | 蜴国际 PDF+Excel 配对 → 背贴 | 列名映射参考 |
| 4.x | 35-39 | 七条承运人多仓 zip | 不要 |
| 后半 | 40-147 | UPS OCR、SPS、邮件、Prophet 演示 | 都不要 |

## 7. 给同事 Agent 的说明

> **Agent，任务：**
>
> 1. 在 `sellfox_shipping/sku_label/` 下新建模块（`pdf_generator.py` + `name_lookup.py`）
> 2. `pdf_generator.py`：复制本文 §3 代码
> 3. `name_lookup.py`：复制本文 §4 代码 — **注意这是一个通用工具**，不仅背贴用，之后包裹详情页、面单品名填充也可以复用
> 4. 加 CLI `sku-label` 命令 + Web 下载按钮
> 5. 先在 `SkuNameLookup._resolve()` 里确认 ERPNext Item 是否有 `custom_spanish_name` 字段。如果没有，西语名暂时留空（或后续接 Google Sheets）
> 6. **Service account JSON** 私钥单独从 keyapi 获取（钉钉发），放在 `data/service-account.json`，gitignore
> 7. 验证：对测试包裹生成背贴 PDF，打开确认
>
> **不要做的：**
> - 不要重写 PDF 核心逻辑（已跑 2 年，只改数据适配层）
> - 不要把凭证写入代码或文档
