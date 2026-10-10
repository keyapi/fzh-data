# -*- coding: utf-8 -*-
"""销售出库(DN) → 报关单据导出（4 个固定 sheet，严格对齐海关模板）。

用法:
  python customs_export.py --dn DN-26-00063          # 生产环境
  python customs_export.py --dn DN-26-00063 --test   # 测试环境

设计:
  用 openpyxl 打开 数据源/ZJ26DZJR0403-报关单据.xlsx 作为模板，
  仅覆盖「可变单元格」，保留合并单元格/边框/字体/列宽；并清除模板自带的图片(中基抬头/印章)。
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import Alignment
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.cell_range import CellRange

import requests

sys.stdout.reconfigure(encoding="utf-8")

_DIR = Path(__file__).resolve().parent
TEMPLATE = _DIR / "数据源" / "ZJ26DZJR0403-报关单据.xlsx"
OUT_DIR = _DIR / "out"

ENV_URLS = {"test": "https://ensh.vilavi.cn", "prod": "https://erpnext.vilavi.cn"}

# ──────────────────────────────────────────────────────────────
# 常量配置
# ──────────────────────────────────────────────────────────────
CONFIG = {
    "shipper_cn": "方州汇国际电子商务（北京）有限公司",
    "shipper_en": "FANGZHOUHUI INTERNATIONAL E-COMMERCE (BEIJING) CO., LTD.",
    "shipper_addr": "Room 1910, 16th Floor, Building 1, Cuijing Beili, Tongzhou District, Beijing, China",
    "currency": "USD",            # 报关币制
    "exchange_rate": 6.8,         # 人民币 → 美元（暂定，后续换汇率表）
    "price_markup": 1.45,         # 报关单价加成系数：报关单价 = BOM成本 ÷ 汇率 × 1.45
    "trade_term": "FOB",
    "trade_term_full": "FOB NINGBO,CHINA",
    "payment_term": "BY T/T 90 DAYS",
    "transport_route": "FROM NINGBO,CHINA TO LONG BEACH,UNITED STATES BY SEA",
    "transport_mode": "BY SEA",
    "port_loading": "NINGBO,CHINA",                # 出境关别/离境口岸
    "port_discharge": "LONG BEACH,UNITED STATES",  # 指运港
    "supervision_mode": "一般贸易",        # 监管方式
    "origin_place": "绍兴市（33069）",      # 境内货源地（常量）
    "declaration_unit": "宁波市鸿欣报关有限公司",   # 申报单位（弹窗可传，未传则保留模板原值）
    # 境内收货人(境内发货人 A4)与生产销售单位(A8)固定为同一主体（含统一社会信用代码+海关10位编码）。
    # 与模板 报关单NEW A4/A8 现填值逐字符一致，改动只改这一处。
    "domestic_party_cn": "（9111010856368328XF）（11149609R4）方州汇国际电子商务(北京)有限公司",
    # 单位映射：EN 的 uom → (英文单位, 中文单位)
    "uom_map": {
        "个": ("PIECES", "个"),
        "套": ("SETS", "套"),
        "件": ("PIECES", "件"),
        "只": ("PIECES", "只"),
        "条": ("PIECES", "条"),
    },
}

# 目的国（地区）映射：客户 → (英文, 中文)
DEST_COUNTRY = {
    "UNITED STATES(502)": "美国(502)",
    "PL(327)": "波兰(327)",
}
US_CUSTOMERS = {"DANEEY", "CENTRADE"}   # 美国客户（含美国FBA仓，具体客户名待补充）
PL_CUSTOMERS = set()                     # 波兰公司（具体客户名待补充）

# 境外收货人预设（与 EN 弹窗下拉同源；导出时填 C5 境外收货人：名称 + 地址）。
# 新增/修改收货人只改这一处。
CONSIGNEE_DATA = {
    "centrade": {"name": "Centrade Inc", "addr": "389 Route 10 Unit R, East Hanover, NJ 07936 U.S.A."},
    "daneey":   {"name": "Daneey LLC", "addr": "10812 Fallstone Rd, Suite 402, Houston TX 77099 U.S.A."},
    "poland":   {"name": "Pillow Palette Ltd", "addr": "ul. Krucza 68/9, 53-411 Wrocław, mail: kontakt@pillowpalette.pl, 786 603 993"},
}
DEFAULT_CONSIGNEE = "centrade"           # 兜底默认（未指定收货人时）

# 装箱组合（混装版）：key = DN 单号 → 组合列表。装箱信息完全由用户确认，不用外箱子表。
# 每个组合:
#   name          组合名
#   carton_qty    箱数（该组合几个箱子）
#   gross_kg      每箱毛重 kg
#   net_kg        每箱净重 kg
#   volume_cbm    每箱体积 m³
#   items         每箱内容: [{code: 去色后物料编码, qty_per_carton: 每箱数量}, ...]
CARTON_GROUPS_BY_DN = {
    "DN-26-00056": [
        {"name": "组合1 KS0001-153 皮壳+内胆", "carton_qty": 40, "gross_kg": 18.5, "net_kg": 17.8, "volume_cbm": 0.09024,
         "items": [
             {"code": "PK#KS0001-DM-153", "qty_per_carton": 2},
             {"code": "PK#KS0001-HLR-153", "qty_per_carton": 8},
             {"code": "ND#KS0001-153-CYF", "qty_per_carton": 9},
         ]},
        {"name": "组合2 KS0001-194 皮壳+内胆", "carton_qty": 32, "gross_kg": 17.0, "net_kg": 16.2, "volume_cbm": 0.09024,
         "items": [
             {"code": "PK#KS0001-DM-194", "qty_per_carton": 2},
             {"code": "PK#KS0001-HLR-194", "qty_per_carton": 1},
             {"code": "ND#KS0001-194-CYF", "qty_per_carton": 10},
         ]},
        {"name": "组合3 KS0001-100/140 内胆+皮壳", "carton_qty": 7, "gross_kg": 15.0, "net_kg": 14.2, "volume_cbm": 0.0768,
         "items": [
             {"code": "ND#KS0001-100-CYF", "qty_per_carton": 15},
             {"code": "ND#KS0001-140-CYF", "qty_per_carton": 3},
             {"code": "PK#KS0001-HLR-140", "qty_per_carton": 3},
         ]},
        {"name": "组合4 KS0003/KS0007 60/194", "carton_qty": 5, "gross_kg": 16.0, "net_kg": 15.2, "volume_cbm": 0.0768,
         "items": [
             {"code": "PK#KS0003-DM-60", "qty_per_carton": 4},
             {"code": "ND#KS0003-60-CYF", "qty_per_carton": 4},
             {"code": "PK#KS0007-DM-194", "qty_per_carton": 1},
             {"code": "ND#KS0007-194-CYF", "qty_per_carton": 1},
         ]},
        {"name": "组合5 KS0321+KS0383 床头靠枕", "carton_qty": 8, "gross_kg": 20.0, "net_kg": 19.1, "volume_cbm": 0.09024,
         "items": [
             {"code": "PK#KS0321-HLR-153", "qty_per_carton": 3},
             {"code": "ND#KS0321-153-CYF", "qty_per_carton": 3},
             {"code": "ND#KS0383-153x50x24-CYF", "qty_per_carton": 6},
             {"code": "ND#KS0383-194x50x24-CYF", "qty_per_carton": 2},
         ]},
        {"name": "组合6 KS0248+KS0401 大件", "carton_qty": 3, "gross_kg": 22.0, "net_kg": 21.0, "volume_cbm": 0.09024,
         "items": [
             {"code": "PK#KS0248-DM-194", "qty_per_carton": 2},
             {"code": "PK#KS0401-XRDR-100x100x80", "qty_per_carton": 3},
         ]},
    ],
}


def load_credentials(env: str) -> tuple[str, str]:
    vals: dict[str, str] = {}
    env_file = _DIR / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            vals[k.strip()] = v.strip()
    if env == "test":
        key, sec = vals.get("TEST_ERP_API_KEY", ""), vals.get("TEST_ERP_API_SECRET", "")
    else:
        key, sec = vals.get("PROD_ERP_API_KEY", ""), vals.get("PROD_ERP_API_SECRET", "")
    return key or vals.get("ERP_API_KEY", ""), sec or vals.get("ERP_API_SECRET", "")


def api_get(base: str, key: str, sec: str, path: str) -> dict:
    r = requests.get(f"{base}{path}", headers={"Authorization": f"token {key}:{sec}"}, timeout=60)
    r.raise_for_status()
    return r.json()


def get_doc(base: str, key: str, sec: str, doctype: str, name: str) -> dict:
    path = "/api/resource/{}/{}".format(
        urllib.parse.quote(doctype, safe=""), urllib.parse.quote(name, safe="")
    )
    return api_get(base, key, sec, path).get("data", {})


# ──────────────────────────────────────────────────────────────
# 简单翻译：中文品名 → 英文（复用 DeepSeek API，与 EN 的 AIContentGenerator 同源）
# ──────────────────────────────────────────────────────────────
DEEPSEEK_BASE_URL = "https://api.vilavi.cn/v1"   # 用户 AI 网关（部署到 EN 后改走 AIContentGenerator/PIM Settings）
DEEPSEEK_MODEL = "deepseek-v4-flash"

# 少数物料的固定英文品名（优先于 AI 翻译；键=去色后的 code_agg）
TRANSLATION_OVERRIDES = {
    "KZKP1010-5#-IRONBOTTOMSURFACE": "Button embryo 5# iron bottom surface",
}


def load_deepseek_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if key:
        return key
    env_file = _DIR / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.partition("=")[2].strip()
    return ""


def translate_zh_to_en(text: str, api_key: str) -> str:
    """中文 → 英文（海关报关品名），失败回退原文。"""
    if not text or not text.strip() or not api_key:
        return text
    url = f"{DEEPSEEK_BASE_URL}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "你是专业的海关报关品名翻译助手。把中文品名翻译成简洁、正式的英文品名，"
                           "用于出口报关单。只输出英文品名本身，不要任何解释、引号或前后缀。",
            },
            {"role": "user", "content": text},
        ],
        "temperature": 0.3,
    }
    try:
        for attempt in range(3):
            try:
                r = requests.post(url, json=payload, headers=headers, timeout=60)
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"].strip()
            except requests.RequestException as e:
                if attempt == 2:
                    raise
                print(f"  [翻译重试 {attempt+1}] {text!r}: {e}", file=sys.stderr)
                time.sleep(3)
    except Exception as e:
        print(f"  [翻译失败] {text!r}: {e}", file=sys.stderr)
        return text


# ──────────────────────────────────────────────────────────────
# 海绵（HM…）固定拼法：物料组翻译(海绵→Foam) + 型号(原样) + 尺寸
#   尺寸 = Foam Size 表 foam_size_translation（只存描述）+ 编码里的尺寸数字
#   与 EN 侧 delivery_plan/utils/customs_export.py 的 _translate_foam 逐字对齐
# ──────────────────────────────────────────────────────────────
FOAM_SIZE_DOCTYPE = "Item Attribute Value All Foam Size"
# 物料组「海绵」的 item_group_translation（等价 EN 的 _get_item_group_translation_by_ks("HM1510")）
FOAM_ITEM_GROUP_TRANSLATION = "Foam"

# 编码尺寸段末尾的内部后缀（QKL/LX/ZJ/KB…），展示时要剥掉
FOAM_SIZE_SUFFIX_RE = re.compile(r"[A-Z]{1,5}$")

_FOAM_SIZE_MAP: dict[str, str] | None = None


def _foam_size_display(size_abbr: str) -> str:
    """编码里的尺寸段 → 展示文本：剥掉内部后缀(QKL/LX/ZJ/KB)、分隔符统一 x、末尾补 cm。"""
    s = (size_abbr or "").strip()
    if not s:
        return ""
    s = FOAM_SIZE_SUFFIX_RE.sub("", s)
    s = re.sub(r"(?i)cm$", "", s)
    s = re.sub(r"[*×＊xX]", "x", s)
    s = re.sub(r"\s+", "", s)
    return s + "cm" if s else ""


def load_foam_size_map(base: str, key: str, sec: str) -> dict[str, str]:
    """abbr → foam_size_translation（一次拉全表，进程内缓存）。"""
    global _FOAM_SIZE_MAP
    if _FOAM_SIZE_MAP is None:
        path = f"/api/resource/{urllib.parse.quote(FOAM_SIZE_DOCTYPE, safe='')}?limit_page_length=0"
        rows = api_get(base, key, sec, path).get("data", [])
        _FOAM_SIZE_MAP = {r["abbr"]: (r.get("foam_size_translation") or "")
                          for r in rows if r.get("abbr")}
    return _FOAM_SIZE_MAP


def _translate_foam(code_agg: str, name_agg: str, foam_map: dict[str, str]) -> str:
    """海绵：Foam + 型号(原样，不翻译) + 尺寸（表中描述 + 编码尺寸）。"""
    parts = [p for p in (code_agg or "").split("-") if p]
    if not parts:
        return name_agg or code_agg
    model_attr = size_abbr = ""
    if len(parts) >= 3:
        model_attr, size_abbr = parts[1], "-".join(parts[2:])
    elif len(parts) == 2:
        # 只有两段：带 x / 以 cm 结尾 → 是尺寸；否则当型号
        if re.search(r"[xX×＊*]", parts[1]) or re.search(r"(?i)cm$", parts[1]):
            size_abbr = parts[1]
        else:
            model_attr = parts[1]
    desc = (foam_map or {}).get(size_abbr, "") if size_abbr else ""
    size_part = " ".join(x for x in (desc, _foam_size_display(size_abbr)) if x)
    out = [p for p in (FOAM_ITEM_GROUP_TRANSLATION, model_attr, size_part) if p]
    return " ".join(out) if out else (name_agg or code_agg)


# ──────────────────────────────────────────────────────────────
# 聚合：去掉 item_code / item_name 最后一个 "-" 段（颜色）
# ──────────────────────────────────────────────────────────────
def drop_color(s: str) -> str:
    s = (s or "").strip()
    return s.rsplit("-", 1)[0] if s else s


# ──────────────────────────────────────────────────────────────
# 靠枕固定宽高：系统只维护长度，导出时按物料族补出 长度x宽x高。
# 中文品名含关键词且尺寸为单段数字 → 尺寸段补 x宽x高；已有完整三围(x/*/cm)则不动。
# ──────────────────────────────────────────────────────────────
FIXED_DIM_CN = (("三角靠枕", 20, 50), ("平条靠枕", 15, 50))


def _sep_to_x(s: str) -> str:
    """把尺寸分隔符统一为 x：只替换「数字 分隔符 数字」处，其余 * 不动。

    194*20*50 → 194x20x50；153×60X10 → 153x60x10。中/英文品名共用（与 EN 侧同口径）。
    """
    return re.sub(r"(?<=\d)\s*[*×＊xX]\s*(?=\d)", "x", s or "")


def _enrich_dim_cn(name: str) -> str:
    """给单段长度尺寸补固定宽高：三角靠枕 x20x50、平条靠枕 x15x50。未命中必须返回原文。"""
    if not name:
        return name or ""
    for kw, w, h in FIXED_DIM_CN:
        if kw not in name:
            continue
        parts = name.split("-")
        for i in range(len(parts) - 1, -1, -1):
            m = re.fullmatch(r"(\d+)(cm|CM|厘米)?", parts[i])
            if m:
                parts[i] = f"{m.group(1)}x{w}x{h}{m.group(2) or ''}"
                return "-".join(parts)
    return name


def aggregate_items(dn: dict) -> list[dict]:
    groups: dict[str, dict] = {}
    for it in dn.get("items", []):
        code = it.get("item_code", "")
        key = drop_color(code)
        g = groups.setdefault(key, {
            "code_agg": key,
            "name_agg": drop_color(it.get("item_name", "")),
            "qty": 0.0,
            "amount": 0.0,      # 销售金额（发票/合同用）
            "bom_cost": 0.0,    # BOM 成本（报关单用）
            "uom": it.get("uom") or it.get("stock_uom") or "个",
            "code_display": code,
        })
        g["qty"] += float(it.get("qty") or 0)
        g["amount"] += float(it.get("amount") or 0)
        g["bom_cost"] += float(it.get("bom_cost") or 0)
    for g in groups.values():
        g["rate"] = g["amount"] / g["qty"] if g["qty"] else 0.0          # 销售单价
        g["bom_rate"] = g["bom_cost"] / g["qty"] if g["qty"] else 0.0    # BOM 单价
    return list(groups.values())


# ──────────────────────────────────────────────────────────────
# 扣胚（KZKP…）补价：DN 明细行常无价（rate/amount/bom_cost 全 0）→ 导出报关单时取 Item Price。
# 只对扣胚生效；DN 行本身有成本时以 DN 为准（不覆盖真实数据）；Item Price 查不到则保持 0。
# 与 EN 侧 delivery_plan/utils/customs_export.py 同口径。
# ──────────────────────────────────────────────────────────────
BUTTON_EMBRYO_PRICE_LIST = "标准采购"
_BUTTON_EMBRYO_PRICE_CACHE: dict[str, float] = {}


def _is_button_embryo(code_agg: str) -> bool:
    return (code_agg or "").upper().startswith("KZKP")


def load_button_embryo_price(base: str, key: str, sec: str, item_code: str) -> float:
    """扣胚单价（元/套）：取 Item Price「标准采购」里 valid_from 最新的一条；无则 0。"""
    if not item_code:
        return 0.0
    code = item_code.strip()
    if code not in _BUTTON_EMBRYO_PRICE_CACHE:
        path = (f"/api/resource/Item%20Price?filters={urllib.parse.quote(json.dumps([['item_code', '=', code], ['price_list', '=', BUTTON_EMBRYO_PRICE_LIST]]))}"
                f"&fields={urllib.parse.quote(json.dumps(['price_list_rate']))}&limit_page_length=1")
        rows = api_get(base, key, sec, path).get("data", [])
        _BUTTON_EMBRYO_PRICE_CACHE[code] = float((rows[0].get("price_list_rate") if rows else 0) or 0)
    return _BUTTON_EMBRYO_PRICE_CACHE[code]


def apply_button_embryo_price(base: str, key: str, sec: str, agg: list[dict]) -> None:
    """给聚合结果里的扣胚补价（就地修改）。"""
    for it in agg:
        if not _is_button_embryo(it.get("code_agg", "")) or it.get("bom_cost"):
            continue
        price = load_button_embryo_price(base, key, sec, it.get("code_display") or it.get("code_agg") or "")
        if price:
            it["bom_rate"] = price
            it["bom_cost"] = round(price * float(it.get("qty") or 0), 6)


def num_to_words(n: int) -> str:
    ones = ["", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN",
            "EIGHT", "NINE", "TEN", "ELEVEN", "TWELVE", "THIRTEEN",
            "FOURTEEN", "FIFTEEN", "SIXTEEN", "SEVENTEEN", "EIGHTEEN", "NINETEEN"]
    tens = ["", "", "TWENTY", "THIRTY", "FORTY", "FIFTY", "SIXTY",
            "SEVENTY", "EIGHTY", "NINETY"]
    n = int(n)
    if n < 20:
        return ones[n]
    if n < 100:
        return tens[n // 10] + (" " + ones[n % 10] if n % 10 else "")
    if n < 1000:
        return ones[n // 100] + " HUNDRED" + (" AND " + num_to_words(n % 100) if n % 100 else "")
    if n < 1000000:
        return num_to_words(n // 1000) + " THOUSAND" + (" " + num_to_words(n % 1000) if n % 1000 else "")
    return str(n)


def fmt_date_contract(d: str) -> str:
    dt = datetime.date.fromisoformat(d[:10])
    m = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
         "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][dt.month - 1]
    return f"{dt.day}/{m}/{dt.year}"


def uom_en(uom: str) -> str:
    return CONFIG["uom_map"].get(uom, (uom, uom))[0]


def uom_cn(uom: str) -> str:
    return CONFIG["uom_map"].get(uom, (uom, uom))[1]


def resolve_country(customer: str) -> tuple[str, str]:
    """客户 → (英文国别, 中文国别)"""
    if customer in US_CUSTOMERS:
        return "UNITED STATES(502)", "美国(502)"
    if customer in PL_CUSTOMERS:
        return "PL(327)", "波兰(327)"
    return "", ""


def resolve_consignee(args, customer: str) -> dict:
    """境外收货人：CLI --consignee 选择即导出（仅公司名写入 C5）；未指定则默认 Centrade Inc。

    2026-09-08 需求调整：不再无条件固定 Centrade，选择哪个预设/自定义名称就导出哪个。
    """
    choice = (args.consignee or "").strip().lower()
    name = args.consignee_name or ""
    addr = args.consignee_addr or ""
    if choice and choice != "custom" and choice in CONSIGNEE_DATA:
        name = name or CONSIGNEE_DATA[choice]["name"]
        addr = addr or CONSIGNEE_DATA[choice]["addr"]
    if not name and not addr:
        name = CONSIGNEE_DATA[DEFAULT_CONSIGNEE]["name"]
    return {"name": name, "addr": addr}


def usd_price(rmb: float) -> float:
    """RMB → USD 报关价：BOM成本 × 加成系数 ÷ 汇率（先涨价、后换汇），保留 3 位小数。"""
    return round(float(rmb) * CONFIG["price_markup"] / CONFIG["exchange_rate"], 3)


def _n3(ws, coord: str, value):
    """写入数值并强制保留 3 位小数（补零对齐）。"""
    ws[coord] = round(float(value), 3)
    ws[coord].number_format = "0.000"


def _n2(ws, coord: str, value):
    """写入金额/单价并强制保留 2 位小数（与 EN 侧报关单据一致）。"""
    ws[coord] = round(float(value), 2)
    ws[coord].number_format = "0.00"


def compute_packing(agg, groups):
    """根据装箱组合计算每个物料的 箱数/毛重/净重/体积（按数量占比分摊）。

    返回:
        {"qty","cartons","gross","net","volume": {code: 值}, "total_cartons","total_gross","total_net","total_volume"}
    """
    from collections import defaultdict
    c_qty = defaultdict(float)
    c_cartons = defaultdict(float)
    c_gross = defaultdict(float)
    c_net = defaultdict(float)
    c_volume = defaultdict(float)
    total_cartons = total_gross = total_net = total_volume = 0.0
    for g in groups:
        c = float(g.get("carton_qty", 0) or 0)
        g_net = float(g.get("net_kg", 0) or 0)
        g_gross = float(g.get("gross_kg", 0) or 0)
        g_vol = float(g.get("volume_cbm", 0) or 0)
        total_cartons += c
        total_gross += c * g_gross
        total_net += c * g_net
        total_volume += c * g_vol
        items = g.get("items", []) or []
        total_in = sum(float(i.get("qty_per_carton", 0) or 0) for i in items) or 1
        for i in items:
            code = i.get("code", "")
            qpc = float(i.get("qty_per_carton", 0) or 0)
            share = qpc / total_in
            c_qty[code] += c * qpc
            c_cartons[code] += c
            c_net[code] += c * g_net * share
            c_gross[code] += c * (g_net * share + (g_gross - g_net) * share)
            c_volume[code] += c * g_vol * share
    return {
        "qty": dict(c_qty),
        "cartons": dict(c_cartons),
        "gross": dict(c_gross),
        "net": dict(c_net),
        "volume": dict(c_volume),
        "total_cartons": round(total_cartons),
        "total_gross": round(total_gross, 3),
        "total_net": round(total_net, 3),
        "total_volume": round(total_volume, 3),
    }


def _copy_row_style(ws, from_row: int, to_row: int, max_col: int):
    """把 from_row 单元格样式（字体/边框/填充/对齐/数字格式）复制到 to_row（insert_rows 不继承样式）。"""
    import copy
    for col in range(1, max_col + 1):
        src = ws.cell(row=from_row, column=col)
        dst = ws.cell(row=to_row, column=col)
        if src.has_style:
            dst._style = copy.copy(src._style)


def _expand_rows(ws, at_row: int, k: int, extend_ranges: list[str], ref_rows: list[int] | None = None):
    """在 at_row 前插入 k 行，修复合并单元格，并复制样式。

    - at_row 及以下的合并整体下移 k 行
    - extend_ranges（如 marks 竖列）下边界 + k
    - 复制模板数据行样式到插入行（insert_rows 不继承样式，否则新行字体/边框缺失）
    - ref_rows：插入行对应的样式参考行（缺省取 at_row-1）；报关单NEW 每物料 2 行交替传 [item行, element行]
    """
    if k <= 0:
        return
    ws.insert_rows(at_row, k)
    to_move = []
    for rng in list(ws.merged_cells.ranges):
        if rng.min_row >= at_row:
            to_move.append(CellRange(str(rng)))
            ws.merged_cells.remove(rng)
    for r in to_move:
        ws.merged_cells.add(
            f"{get_column_letter(r.min_col)}{r.min_row + k}:{get_column_letter(r.max_col)}{r.max_row + k}"
        )
    for coord in extend_ranges:
        r = CellRange(coord)
        if str(r) in [str(x) for x in ws.merged_cells.ranges]:
            ws.merged_cells.remove(r)
        ws.merged_cells.add(
            f"{get_column_letter(r.min_col)}{r.min_row}:{get_column_letter(r.max_col)}{r.max_row + k}"
        )
    ref_rows = ref_rows or [at_row - 1]
    max_col = ws.max_column
    for j in range(k):
        _copy_row_style(ws, ref_rows[j % len(ref_rows)], at_row + j, max_col)


def expand_sheets(wb, n_items: int):
    """按聚合物料数扩展 4 个 sheet 的数据行（模板默认 16 行）。"""
    # (sheet名, 插入位置, marks列延长区间, 样式参考行)
    specs = [
        ("报关发票 ", 32, ["B15:B33"], [31]),
        ("装箱单", 33, ["B16:B34"], [32]),
        ("报关合同 ", 32, [], [31]),
    ]
    for name, at_row, ext, ref in specs:
        ws = wb[name]
        k = n_items - 16
        _expand_rows(ws, at_row, k, ext, ref)
    # 报关单NEW：每物料 2 行，插在第 50 行（分隔线）之前；item/element 交替参考 48/49
    ws = wb["报关单NEW "]
    k = 2 * (n_items - 16)
    _expand_rows(ws, 50, k, [], [48, 49])


def _delete_rows_safe(ws, start_row: int, count: int):
    """整行删除数据区末尾的多余行，并正确处理合并单元格。

    - 完全在删除区内 → 移除
    - 跨越删除区边界 → 收缩到边界（保留删除区外部分）
    - 完全在删除区下方 → 整体上移 count 行（openpyxl 的 delete_rows 不会平移合并区）
    - 完全在删除区上方 → 不动
    """
    if count <= 0:
        return
    end = start_row + count - 1
    for rng in list(ws.merged_cells.ranges):
        rmin, rmax = rng.min_row, rng.max_row
        if rmax < start_row:
            continue                       # 完全在上方，不动
        if rmin >= start_row and rmax <= end:
            ws.merged_cells.remove(rng)    # 完全在删除区内，移除
            continue
        keep_min, keep_max = rmin, rmax
        if rmin < start_row <= rmax:
            keep_max = start_row - 1       # 跨越上边界，保留上方部分
        elif rmin <= end < rmax:
            keep_min = end + 1             # 跨越下边界，保留下方部分
        new_min, new_max = keep_min, keep_max
        if keep_min > end:
            new_min, new_max = keep_min - count, keep_max - count   # 删除区下方整体上移
        if new_min > new_max:
            continue
        ws.merged_cells.remove(rng)
        ws.merged_cells.add(
            f"{get_column_letter(rng.min_col)}{new_min}:{get_column_letter(rng.max_col)}{new_max}"
        )
    ws.delete_rows(start_row, count)


def _remove_blank_header_rows(wb):
    """删除三张表「表头与数据之间」的空白行：报关发票 row15、装箱单 row16、报关合同 row15。

    删除后所有相关行坐标整体上移 1：数据起始 发票/合同 16→15、装箱单 17→16；表格下边界 -1。
    """
    _delete_rows_safe(wb["报关发票 "], 15, 1)
    _delete_rows_safe(wb["装箱单"], 16, 1)
    _delete_rows_safe(wb["报关合同 "], 15, 1)


def _merge_contract_name_cols(ws, n_items: int):
    """报关合同每个物料数据行把「货物名称及规格」名称区四列 B:E 合并为单格。

    注：表头下空白行（原 row15）已删除，数据行起始为 15。
    """
    if not n_items or n_items <= 0:
        return
    from openpyxl.utils.cell import range_boundaries
    start_row = 15
    data_rows = set(range(start_row, start_row + n_items))
    # 先拆掉数据行里与 B:E 重叠的旧合并（如模板默认 B16:C16 / 扩展复制来的 B:C）
    for rng in list(ws.merged_cells.ranges):
        min_col, min_row, max_col, max_row = range_boundaries(str(rng))
        if (min_row == max_row and min_row in data_rows
                and min_col <= 5 and max_col >= 2):
            ws.unmerge_cells(str(rng))
    for i in range(n_items):
        r = start_row + i
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=5)


def _plain_left_single_line(wb):
    """统一 4 张表所有「有内容」单元格：水平左对齐、不自动换行、不缩小字号、去除写入的换行符。

    模板数据区默认 wrap_text=True，长英文品名会换行把行高撑高、出现折叠/跨行；
    这里改成单行显示 + 全部左对齐，保证导出件行高一致、视觉统一。
    合并区非锚点的只读 MergedCell 跳过（锚点会被统一处理）。
    """
    for ws in wb.worksheets:
        start = DATA_START.get(ws.title, 1)
        for row in ws.iter_rows():
            for cell in row:
                if cell.row < start:
                    continue  # 表头/公司信息区：保持模板样式，不左对齐、不去换行
                if cell.value is None or (isinstance(cell.value, str) and cell.value == ""):
                    continue
                if isinstance(cell.value, str):
                    cell.value = re.sub(r"\s*\r?\n\s*", " ", cell.value)
                try:
                    a = cell.alignment
                    cell.alignment = Alignment(
                        horizontal="left",
                        vertical=a.vertical,
                        text_rotation=a.text_rotation,
                        wrap_text=False,
                        shrink_to_fit=False,
                        indent=a.indent,
                    )
                except Exception:
                    pass  # MergedCell 只读，跳过


def _autofit_columns(wb):
    """动态列宽：只加宽「单行内容会真正被截断」的列。

    不换行后长文本若右侧一路是空格，Excel 会直接溢出完整显示（无需拉宽）；
    只有右邻格也有内容、文字被挡在列边界内时才会视觉截断。这里逐格估算
    「文本宽度 vs 该格 + 右侧连续空格子的可用宽度」，不够才把本格所在列加宽
    （合并格按整段合并列宽 + 其后空格子计可用宽度）。列宽只增不减。
    个别静态长句「合并区已撑满整行仍放不下」时回退允许换行（完整显示，不影响数据行高）。
    """
    from openpyxl.utils import get_column_letter

    def vlen(s):
        return sum(2 if ord(ch) > 127 else 1 for ch in str(s))

    def cell_merge(ws, row, col):
        for rng in ws.merged_cells.ranges:
            if rng.min_row <= row <= rng.max_row and rng.min_col <= col <= rng.max_col:
                return rng
        return None

    def occupied(ws, row, col):
        c = ws.cell(row, col)
        if c.value not in (None, ""):
            return True
        return c.__class__.__name__ == "MergedCell"

    for ws in wb.worksheets:
        existing = {}
        for col in range(1, ws.max_column + 1):
            d = ws.column_dimensions.get(get_column_letter(col))
            existing[col] = (d.width if (d and d.width) else 8.43)
        need = {}
        for row in ws.iter_rows():
            for cell in row:
                v = cell.value
                if v is None or (isinstance(v, str) and not v.strip()):
                    continue
                if cell.__class__.__name__ == "MergedCell":
                    continue
                rng = cell_merge(ws, cell.row, cell.column)
                right_max = rng.max_col if rng else cell.column
                avail = sum(existing.get(cc, 8.43) for cc in range(cell.column, right_max + 1))
                cc = right_max + 1
                while cc <= ws.max_column and not occupied(ws, cell.row, cc):
                    avail += existing.get(cc, 8.43)
                    cc += 1
                need_w = vlen(v) + 1.2
                if need_w > avail:
                    deficit = need_w - avail
                    want = min(existing[cell.column] + deficit, 90.0)  # 封顶防病态拉宽
                    if want > need.get(cell.column, existing[cell.column]):
                        need[cell.column] = want
        for col, w in need.items():
            if w > existing[col]:
                ws.column_dimensions[get_column_letter(col)].width = w
        # 回退：仅对仍放不下的格允许换行（完整显示；静态固定行不影响数据行高）
        for row in ws.iter_rows():
            for cell in row:
                v = cell.value
                if v is None or (isinstance(v, str) and not v.strip()):
                    continue
                if cell.__class__.__name__ == "MergedCell":
                    continue
                rng = cell_merge(ws, cell.row, cell.column)
                right_max = rng.max_col if rng else cell.column
                avail = 0.0
                for cc in range(cell.column, right_max + 1):
                    d = ws.column_dimensions.get(get_column_letter(cc))
                    avail += (d.width if (d and d.width) else 8.43)
                cc = right_max + 1
                while cc <= ws.max_column and not occupied(ws, cell.row, cc):
                    d = ws.column_dimensions.get(get_column_letter(cc))
                    avail += (d.width if (d and d.width) else 8.43)
                    cc += 1
                if vlen(v) + 1.2 > avail:
                    try:
                        a = cell.alignment
                        cell.alignment = Alignment(
                            horizontal="left", vertical=a.vertical,
                            text_rotation=a.text_rotation,
                            wrap_text=True, shrink_to_fit=False, indent=a.indent)
                    except Exception:
                        pass
    return wb


# 各表「数据区起始行」：其上方为表头/公司信息区，**不做左对齐**（保留模板样式，如表头居中）
DATA_START = {"报关发票 ": 15, "装箱单": 16, "报关合同 ": 15, "报关单NEW ": 18}

# 统一行高的起止：各自顶部「公司信息/标题块」以下开始统一（报关单NEW 不动）
_UNIFORM_START = {"报关发票 ": 6, "装箱单": 6, "报关合同 ": 9}
_UNIFORM_H = 16.5


def _uniform_row_heights(wb):
    """三张表（发票/装箱单/合同）除顶部公司信息/标题块外，行高统一为 16.5。

    例外：含「回退允许换行」的长句所在行给足够高度（完整显示），其余严格统一。
    """
    for ws in wb.worksheets:
        start = _UNIFORM_START.get(ws.title)
        if not start:
            continue
        last = max(ws.max_row, start)
        for r in range(start, last + 1):
            ws.row_dimensions[r].height = _UNIFORM_H
        for row in ws.iter_rows():
            for cell in row:
                if cell.value not in (None, "") and cell.alignment and cell.alignment.wrap_text:
                    ws.row_dimensions[cell.row].height = 30


def _apply_table_borders(wb, n_items: int):
    """报关发票/装箱单/报关合同 表格区：内部全细线 + 外框 thick 粗线。

    区间随物料数 N 动态：发票 B14:G(17+N)、装箱单 B15:K(18+N)、报关合同 B13:J(17+N)。
    含表头行、数据行、合计行及其间空白行。

    ⚠️ 合并区边框关键点：Excel 按「每个子格」渲染边框，openpyxl 合并会把覆盖格替换为
    只读 MergedCell（赋值不落盘）→ 只画锚点会让合并区某条边缺线（线中断）。做法：给表格内
    每一个坐标（含合并覆盖格）放一个真实 Cell 写边框；合并关系保留。
    """
    from openpyxl.styles import Border, Side
    from openpyxl.cell.cell import Cell as _Cell
    thin = Side(style="thin")
    thick = Side(style="thick")
    spec = [
        ("报关发票 ", 2, 7, 14, 16 + n_items),
        ("装箱单", 2, 11, 15, 17 + n_items),
        ("报关合同 ", 2, 10, 13, 16 + n_items),
    ]
    for title, c1, c2, r1, r2 in spec:
        ws = wb[title]
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                border = Border(
                    left=(thick if c == c1 else thin),
                    right=(thick if c == c2 else thin),
                    top=(thick if r == r1 else thin),
                    bottom=(thick if r == r2 else thin),
                )
                cell = ws._cells.get((r, c))
                if cell is None or cell.__class__.__name__ == "MergedCell":
                    cell = _Cell(ws, row=r, column=c, value=None)
                    ws._cells[(r, c)] = cell
                cell.border = border


def delete_extra_rows(wb, n_items: int):
    """按实际导出的物料数 N 删除数据区末尾的多余整行。

    模板默认 16 行数据；当 N < 16 时删除 N 之后的多余行，合计行/页脚随之上移。
    发票/装箱单/报关合同/报关单NEW 都处理。N >= 16 时由 expand_sheets 扩展，无需删除。
    """
    if n_items >= 16:
        return
    # 报关发票：数据行 16..31（16 行），TOTAL 33
    _delete_rows_safe(wb["报关发票 "], 16 + n_items, 16 - n_items)
    # 装箱单：数据行 17..32，TOTAL 34
    _delete_rows_safe(wb["装箱单"], 17 + n_items, 16 - n_items)
    # 报关合同：数据行 16..31（16 行），TOTAL 33
    _delete_rows_safe(wb["报关合同 "], 16 + n_items, 16 - n_items)
    # 报关单NEW：每物料 2 行（项号+申报要素），数据 18..49，TOTAL 51
    _delete_rows_safe(wb["报关单NEW "], 18 + 2 * n_items, 2 * (16 - n_items))
    # 报关合同：不处理


# ──────────────────────────────────────────────────────────────
# 各 sheet 填充
# ──────────────────────────────────────────────────────────────
def fill_invoice(ws, dn, agg, totals):
    c = CONFIG
    k = max(0, len(agg) - 16)   # 扩展行偏移
    ws["B2"] = c["shipper_cn"]
    ws["B3"] = c["shipper_en"]
    ws["B4"] = c["shipper_addr"]
    ws["B8"] = None                        # 买方(To Messrs) 留空
    ws["G8"] = datetime.datetime.fromisoformat(dn["posting_date"][:10])
    ws["G9"] = None                        # 发票号 留空
    ws["G10"] = dn["name"]                 # 合同号
    ws["C13"] = c["transport_route"]
    ws["F13"] = c["payment_term"]
    for i in range(max(16, len(agg))):
        row = 16 + i
        if i < len(agg):
            it = agg[i]
            ws[f"C{row}"] = it["name_en"]                    # 品名(英文)
            ws[f"D{row}"] = it["qty"]
            ws[f"E{row}"] = uom_en(it["uom"])
            _n2(ws, f"F{row}", it["price_usd"])    # 单价(USD)
            _n2(ws, f"G{row}", it["amount_usd"])   # 总金额(USD)
        else:
            for col in "CDEFG":
                ws[f"{col}{row}"] = None
    tr = 33 + k
    ws[f"C{tr}"] = "TOTAL:"
    ws[f"D{tr}"] = totals["qty"]
    ws[f"F{tr}"] = c["currency"]
    _n2(ws, f"G{tr}", totals["amount_usd"])
    nr = 35 + k
    ws[f"C{nr}"] = f"TOTAL PACKED IN {num_to_words(totals['cartons'])} CTNS"


def fill_packing(ws, dn, agg, totals):
    c = CONFIG
    k = max(0, len(agg) - 16)   # 扩展行偏移
    ws["B2"] = c["shipper_cn"]
    ws["B3"] = c["shipper_en"]
    ws["B4"] = c["shipper_addr"]
    ws["B8"] = None
    ws["H8"] = datetime.datetime.fromisoformat(dn["posting_date"][:10])
    ws["H9"] = None                        # 发票号 留空
    ws["H10"] = dn["name"]
    ws["C13"] = c["transport_route"]
    for i in range(max(16, len(agg))):
        row = 17 + i
        if i < len(agg):
            it = agg[i]
            ws[f"C{row}"] = it["name_en"]
            ws[f"D{row}"] = f"{int(it['qty'])} {uom_en(it['uom'])}"
            ws[f"E{row}"] = f"{int(it.get('cartons', 0))}CTNS"
            _n3(ws, f"F{row}", it.get("gross", 0.0))
            _n3(ws, f"H{row}", it.get("net", 0.0))
            _n3(ws, f"J{row}", it.get("measrs", 0.0))
        else:
            for col in "CDEFGHIJK":
                ws[f"{col}{row}"] = None
    tr = 34 + k
    ws[f"C{tr}"] = "TOTAL："
    ws[f"E{tr}"] = f"{totals['cartons']}\n CTNS"
    _n3(ws, f"F{tr}", totals["gross"])
    ws[f"G{tr}"] = "KGS"
    _n3(ws, f"H{tr}", totals["net"])
    ws[f"I{tr}"] = "KGS"
    _n3(ws, f"J{tr}", totals["measrs"])
    ws[f"K{tr}"] = "CBM"
    n36 = 36 + k
    ws[f"D{n36}"] = f"TOTAL PACKED IN {num_to_words(totals['cartons'])} CTNS"
    ws[f"D{n36+1}"] = f"TOTAL GROSS WEIGHT {totals['gross']:.3f}KGS"
    ws[f"D{n36+2}"] = f"TOTAL NET WEIGHT {totals['net']:.3f}KGS"
    ws[f"D{n36+3}"] = f"TOTAL MEASUREMENTS {totals['measrs']:.3f}M³"


def fill_contract(ws, dn, agg, totals):
    c = CONFIG
    k = max(0, len(agg) - 16)   # 扩展行偏移
    ws["B2"] = c["shipper_cn"]
    ws["B3"] = c["shipper_en"]
    ws["B4"] = c["shipper_addr"]
    ws["I7"] = dn["name"]
    ws["I8"] = fmt_date_contract(dn["posting_date"])
    ws["B9"] = None                        # 买方 留空
    for i in range(max(16, len(agg))):
        row = 16 + i
        if i < len(agg):
            it = agg[i]
            ws[f"B{row}"] = it["name_en"]
            ws[f"F{row}"] = it["qty"]
            ws[f"G{row}"] = uom_en(it["uom"])
            _n2(ws, f"H{row}", it["price_usd"])
            ws[f"I{row}"] = f"/{uom_en(it['uom'])}"
            _n2(ws, f"J{row}", it["amount_usd"])
        else:
            for col in "BFGHIJ":
                ws[f"{col}{row}"] = None
    tr = 33 + k
    ws[f"B{tr}"] = "TOTAL:"
    ws[f"F{tr}"] = totals["qty"]
    _n2(ws, f"J{tr}", totals["amount_usd"])
    ws[f"E{39+k}"] = None                   # Time of Shipment(装运期) 留空
    ws[f"F{40+k}"] = None                   # 装运口岸/目的港（装运港及目的港）置空
    ws[f"E{43+k}"] = None                   # TERMS OF PAYMENT 留空
    ws[f"H{48+k}"] = None                   # 底部 BUYERS 留空


def fill_declaration(ws, dn, agg, totals, country,
                     consignee_name="", consignee_addr="", declaration_unit=""):
    c = CONFIG
    country_en, country_cn = country
    k = 2 * max(0, len(agg) - 16)   # 扩展行偏移（每物料 2 行）
    # 「数量单位」分列：拆开模板合并表头 E17:F17 → E=数量、F=单位（数据行分列写）
    from copy import copy as _copy
    if "E17:F17" in [str(x) for x in ws.merged_cells.ranges]:
        ws.unmerge_cells("E17:F17")
        for attr in ("font", "fill", "border", "alignment", "number_format", "protection"):
            setattr(ws["F17"], attr, _copy(getattr(ws["E17"], attr)))
    ws["E17"] = "数量"
    ws["F17"] = "单位"
    # 表头 E/F 之间补竖线
    from openpyxl.styles import Border as _Bd, Side as _Sd
    _b = ws["E17"].border
    ws["E17"].border = _Bd(left=_b.left, right=_Sd(style="thin"), top=_b.top, bottom=_b.bottom)
    _c = ws["F17"].border
    ws["F17"].border = _Bd(left=_Sd(style="thin"), right=_c.right, top=_c.top, bottom=_c.bottom)
    ws["I2"] = None                        # 发票号 留空
    ws["A4"] = c["domestic_party_cn"]      # 境内收货人(境内发货人)固定方州汇含编码
    ws["G4"] = None                        # 出境关别 留空
    # 境外收货人 C5：按选择写公司名（仅名称，2026-09-08；不带地址），未传兜底 Centrade Inc
    ws["C5"] = consignee_name or CONSIGNEE_DATA[DEFAULT_CONSIGNEE]["name"]
    ws["C5"].alignment = Alignment(wrap_text=True, vertical="center")
    ws["G6"] = None                        # 运输方式 留空
    ws["A8"] = c["domestic_party_cn"]      # 生产销售单位固定方州汇含编码
    ws["G8"] = c["supervision_mode"]       # 监管方式
    ws["A10"] = dn["name"]                 # 合同协议号
    ws["D10"] = None                       # 贸易国（地区） 留空
    ws["G10"] = None                       # 运抵国（地区） 留空
    ws["J10"] = None                       # 指运港 留空
    ws["L10"] = None                       # 离境口岸 留空
    ws["A12"] = "CTNS"
    ws["D12"] = totals["cartons"]          # 件数
    _n3(ws, "E12", totals["gross"])        # 毛重
    _n3(ws, "G12", totals["net"])          # 净重
    ws["H12"] = c["trade_term"]            # 成交方式
    for i in range(max(16, len(agg))):
        row = 18 + i * 2
        if i < len(agg):
            it = agg[i]
            ws[f"A{row}"] = i + 1
            ws[f"B{row}"] = None                        # 商品编号(HS) 留空
            ws[f"C{row}"] = it["name_agg"]              # 中文名称（保留）
            ws[f"D{row}"] = it["name_en"]               # 英文名称
            ws[f"E{row}"] = int(it["qty"])
            ws[f"F{row}"] = uom_cn(it["uom"])
            # 数量/单位之间补竖线（模板原 E:F 为合并列，内部无线）
            _eb = ws[f"E{row}"].border
            ws[f"E{row}"].border = _Bd(left=_eb.left, right=_Sd(style="thin"), top=_eb.top, bottom=_eb.bottom)
            _fb = ws[f"F{row}"].border
            ws[f"F{row}"].border = _Bd(left=_Sd(style="thin"),
                                       right=(_fb.right if (_fb.right and _fb.right.style) else _Sd(style="thin")),
                                       top=_eb.top, bottom=_eb.bottom)
            _n2(ws, f"G{row}", it["price_usd"])     # 单价 = BOM成本 ÷ 汇率 × 加成
            _n2(ws, f"H{row}", it["amount_usd"])    # 总价
            ws[f"I{row}"] = c["currency"]
            ws[f"J{row}"] = "中国"
            ws[f"K{row}"] = country_cn                  # 最终目的国（地区）
            ws[f"L{row}"] = c["origin_place"]           # 境内货源地
            ws[f"M{row}"] = None                        # 征免
            ws[f"C{row + 1}"] = None                    # 申报要素 留空
            # 申报要素行合并（A:B、C:N），超出模板 16 项时需新建
            for mg in (f"A{row+1}:B{row+1}", f"C{row+1}:N{row+1}"):
                if str(CellRange(mg)) not in [str(x) for x in ws.merged_cells.ranges]:
                    ws.merged_cells.add(mg)
        else:
            for col in "ABCDEFGHIJKLMN":
                ws[f"{col}{row}"] = None
            ws[f"C{row + 1}"] = None
    tr = 51 + k
    ws[f"A{tr}"] = f"TOTAL：{c['currency']} {totals['amount_usd']:.2f}"
    if declaration_unit:                    # 申报单位：仅当传入才写入，否则保留模板原值
        ws[f"A{54+k}"] = f"申报单位  {declaration_unit}"


# ══════════════════════════════════════════════════════════════
# 云驼版（出口报关单-云驼.xlsx，2026-10-09 需求）—— 与 EN 侧 delivery_plan/utils/customs_export.py 同口径
#   4 张表全部由代码写值（模板自带公式一律覆盖），仅「报关单」有表头固定字段。
#   版式：每物料 2 行（主行 + 申报要素行）；中文品名、不用英文；不涉及翻译。
#   注：本参考脚本不建模「申报要素」，故要素行留空（与本地智美通版一致）。
# ══════════════════════════════════════════════════════════════
YUNTUO_TEMPLATE = _DIR / "数据源" / "出口报关单-云驼.xlsx"
_YUNTUO_TMPL_ITEMS = 3      # 模板自带 3 个物料的合并区
_YUNTUO_STEP = 2            # 每物料占 2 行

# start=数据起始行；two=跨 2 行合并的列；one=主行/要素行各自单行合并的列；span=跨整个数据区合并的列
_YUNTUO_LAYOUT = {
    "报关单": {"start": 20,
               "two": ("A", "B:C", "G", "H", "I", "J", "K", "L:M", "N:P", "Q:S", "T", "U", "V", "W"),
               "one": ("D:F",), "span": ()},
    "发票":   {"start": 8,  "two": ("D", "E", "F", "G:H"), "one": ("C",), "span": ("A:B",)},
    "箱单":   {"start": 10, "two": ("C", "D", "E", "F", "G"), "one": ("B",), "span": ("A",)},
    "合同":   {"start": 18, "two": ("D", "E", "F", "G:H"), "one": ("B:C",), "span": ()},
}
_YUNTUO_PRINT_END = {"报关单": ("T", 25), "发票": ("H", 17), "箱单": ("G", 18), "合同": ("H", 48)}


def _split_cols(spec: str) -> tuple:
    """'B:C' → ('B','C')；'A' → ('A','A')。"""
    if ":" in spec:
        a, b = spec.split(":", 1)
        return a.strip(), b.strip()
    return spec, spec


def safe_write(ws, coord: str, value):
    """写入单元格；合并区非锚点（只读 MergedCell）自动跳过。"""
    cell = ws[coord]
    if cell.__class__.__name__ == "MergedCell":
        return
    cell.value = value


def _shift_merges_down(ws, at_row: int, k: int) -> None:
    """把 at_row 及以下的所有合并区整体下移 k 行（insert_rows 不会平移合并区）。"""
    if k <= 0:
        return
    to_remove, to_add = [], []
    for rng in [r for r in list(ws.merged_cells.ranges) if r.min_row >= at_row]:
        to_remove.append(rng)
        to_add.append(f"{get_column_letter(rng.min_col)}{rng.min_row + k}:"
                      f"{get_column_letter(rng.max_col)}{rng.max_row + k}")
    for rng in to_remove:
        ws.merged_cells.remove(rng)
    for coord in to_add:
        ws.merged_cells.add(coord)


def _shift_row_heights_down(ws, at_row: int, k: int) -> None:
    """行高不会随 insert_rows 平移，手动下移。"""
    if k <= 0:
        return
    heights = {r: d.height for r, d in ws.row_dimensions.items() if r >= at_row and d.height}
    for r, h in sorted(heights.items(), reverse=True):
        ws.row_dimensions[r].height = None
        ws.row_dimensions[r + k].height = h


def _yuntuo_block_refs(layout: dict, row: int) -> list:
    """一个物料块（2 行）的合并区引用。"""
    r2 = row + 1
    refs = []
    for spec in layout["two"]:
        c1, c2 = _split_cols(spec)
        refs.append(f"{c1}{row}:{c2}{r2}")
    for spec in layout["one"]:
        c1, c2 = _split_cols(spec)
        refs.append(f"{c1}{row}:{c2}{row}")
        refs.append(f"{c1}{r2}:{c2}{r2}")
    return refs


def _resize_yuntuo_data(ws, sheet: str, n_items: int) -> int:
    """把云驼某表的数据区调整为 n_items 个物料（每物料 2 行），并重建合并区；返回数据起始行。"""
    lay = _YUNTUO_LAYOUT[sheet]
    start, step = lay["start"], _YUNTUO_STEP
    tmpl_end = start + _YUNTUO_TMPL_ITEMS * step - 1
    for rng in [r for r in list(ws.merged_cells.ranges) if start <= r.min_row <= tmpl_end]:
        ws.merged_cells.remove(rng)
    if n_items < _YUNTUO_TMPL_ITEMS:
        _delete_rows_safe(ws, start + n_items * step, (_YUNTUO_TMPL_ITEMS - n_items) * step)
    elif n_items > _YUNTUO_TMPL_ITEMS:
        at = start + _YUNTUO_TMPL_ITEMS * step
        k = (n_items - _YUNTUO_TMPL_ITEMS) * step
        ws.insert_rows(at, k)
        _shift_merges_down(ws, at, k)
        _shift_row_heights_down(ws, at, k)
        for r in range(at, start + n_items * step):
            ref = start + (r - start) % (_YUNTUO_TMPL_ITEMS * step)
            _copy_row_style(ws, ref, r, ws.max_column)
            h = ws.row_dimensions.get(ref)
            if h and h.height:
                ws.row_dimensions[r].height = h.height
    for i in range(n_items):
        for ref in _yuntuo_block_refs(lay, start + i * step):
            ws.merged_cells.add(ref)
    last = start + n_items * step - 1
    for spec in lay["span"]:
        c1, c2 = _split_cols(spec)
        ws.merged_cells.add(f"{c1}{start}:{c2}{last}")
    return start


def _extend_yuntuo_print_area(wb, n_items: int) -> None:
    """打印区随物料数扩展（模板按 3 个物料写死）。"""
    d = (int(n_items) - _YUNTUO_TMPL_ITEMS) * _YUNTUO_STEP
    for sheet, (col, row) in _YUNTUO_PRINT_END.items():
        if sheet in wb.sheetnames:
            wb[sheet].print_area = f"A1:{col}{row + d}"


_UNIFORM_FONT_FAMILY = "微软雅黑"


def _set_font_family(ws, family: str = _UNIFORM_FONT_FAMILY) -> None:
    """把整张表所有单元格的字族统一为 family，保留字号/加粗/斜体/颜色等。

    - 跳过合并区覆盖格（MergedCell 只读；合并区显示样式取自锚点，无需处理）。
    - 跳过「无样式且无值」的空格，避免给上万个空单元格建样式。
    - scheme=None：防止主题字体（minor/major）覆盖显式字体名。
    """
    from openpyxl.styles import Font
    for row in ws.iter_rows():
        for cell in row:
            if cell.__class__.__name__ == "MergedCell":
                continue
            if not cell.has_style and cell.value in (None, ""):
                continue
            f = cell.font
            if f is not None and f.name == family and f.scheme is None:
                continue
            src = f or Font()
            cell.font = Font(
                name=family, size=src.size, bold=src.bold, italic=src.italic,
                underline=src.underline, color=src.color, vertAlign=src.vertAlign,
                strike=src.strike, charset=src.charset, outline=src.outline,
                shadow=src.shadow, condense=src.condense, extend=src.extend,
                family=src.family, scheme=None,
            )


def _finalize_yuntuo(wb) -> None:
    """云驼版收尾（与智美通同口径：内容显示完整 + 整册统一字体族微软雅黑）。"""
    for ws in wb.worksheets:
        _set_font_family(ws)
    _autofit_columns(wb)
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.value in (None, "") or not (cell.alignment and cell.alignment.wrap_text):
                    continue
                cur = ws.row_dimensions[cell.row].height or 0
                if cur < 30:
                    ws.row_dimensions[cell.row].height = 30


def fill_yuntuo_declaration(ws, dn, agg, totals, country_cn, consignee_name="", packing=None):
    """云驼「报关单」：表头固定字段（标签奇数行/值偶数行）+ 逐物料 2 行。"""
    c = CONFIG
    start = _resize_yuntuo_data(ws, "报关单", len(agg))
    ws["A4"] = c["domestic_party_cn"]                       # 境内发货人
    ws["A8"] = c["domestic_party_cn"]                       # 生产销售单位
    safe_write(ws, "A6", consignee_name or "")              # 境外收货人
    safe_write(ws, "A10", dn.get("name", ""))               # 合同协议号
    ws["E8"] = c["supervision_mode"]                        # 监管方式
    ws["E10"] = country_cn                                  # 贸易国（地区）
    for ref in ("E4", "F4", "G4", "L4", "P4", "E6", "F6", "G6", "L6",
                "G8", "H8", "L8", "G10", "H10", "L10", "M10", "P10", "Q10",
                "L12", "O12", "R12", "C13", "C15", "B16", "P17"):
        safe_write(ws, ref, None)
    ws["A12"] = "CTNS"
    ws["E12"] = int(totals["cartons"])
    _n2(ws, "F12", totals["gross"])
    _n2(ws, "G12", totals["net"])
    ws["I12"] = c["trade_term"]
    safe_write(ws, "K12", None)
    ws["U18"] = int(totals["cartons"])
    _n2(ws, "V18", totals["gross"])
    _n2(ws, "W18", totals["net"])
    pk = packing or {}
    for i, it in enumerate(agg):
        row = start + i * _YUNTUO_STEP
        safe_write(ws, f"A{row}", i + 1)
        safe_write(ws, f"B{row}", None)
        safe_write(ws, f"D{row}", it["name_agg"])
        ws[f"G{row}"] = int(it["qty"])
        ws[f"H{row}"] = uom_cn(it["uom"])
        _n2(ws, f"I{row}", it["price_usd"])
        _n2(ws, f"J{row}", it["amount_usd"])
        ws[f"K{row}"] = c["currency"]
        ws[f"L{row}"] = "中国"
        ws[f"N{row}"] = country_cn
        ws[f"Q{row}"] = c["origin_place"]
        safe_write(ws, f"T{row}", None)
        p = pk.get(it["code_agg"]) or {}
        ws[f"U{row}"] = float(p.get("net") or 0)
        ws[f"V{row}"] = float(p.get("gross") or 0)
        ws[f"W{row}"] = int(p.get("cartons") or 0)
        safe_write(ws, f"D{row + 1}", None)                 # 申报要素（本脚本不建模）


def fill_yuntuo_invoice(ws, dn, agg, totals, consignee_name=""):
    """云驼「发票」：中文品名 + 逐物料 2 行。"""
    c = CONFIG
    start = _resize_yuntuo_data(ws, "发票", len(agg))
    safe_write(ws, "G2", dn.get("name", ""))
    safe_write(ws, "C3", consignee_name or "")
    ws["G3"] = datetime.datetime.fromisoformat(_parse_date(dn.get("posting_date", "")))
    safe_write(ws, "G6", c["trade_term"])
    safe_write(ws, "H6", None)
    for i, it in enumerate(agg):
        row = start + i * _YUNTUO_STEP
        safe_write(ws, f"C{row}", it["name_agg"])
        ws[f"D{row}"] = int(it["qty"])
        ws[f"E{row}"] = uom_cn(it["uom"])
        _n2(ws, f"F{row}", it["price_usd"])
        _n2(ws, f"G{row}", it["amount_usd"])
        safe_write(ws, f"C{row + 1}", None)
    tr = start + len(agg) * _YUNTUO_STEP
    ws[f"A{tr}"] = f"总计{c['currency']}:"
    _n2(ws, f"C{tr}", totals["amount_usd"])
    ws[f"F{tr}"] = "TOTAL:"
    _n2(ws, f"G{tr}", totals["amount_usd"])
    safe_write(ws, f"F{tr + 1}", None)
    safe_write(ws, f"F{tr + 2}", None)
    safe_write(ws, f"D{tr + 3}", c["domestic_party_cn"])


def fill_yuntuo_packing(ws, dn, agg, totals, consignee_name="", packing=None, country_cn=""):
    """云驼「箱单」：中文品名 + 逐物料 2 行（箱数/数量/毛重/净重）。"""
    c = CONFIG
    start = _resize_yuntuo_data(ws, "箱单", len(agg))
    ws["G3"] = datetime.datetime.fromisoformat(_parse_date(dn.get("posting_date", "")))
    safe_write(ws, "G4", dn.get("name", ""))
    safe_write(ws, "B5", consignee_name or "")
    safe_write(ws, "G5", dn.get("name", ""))
    origin_city = re.sub(r"[（(][^（）()]*[）)]\s*$", "", c["origin_place"]).strip()
    safe_write(ws, "C7", f"由  {origin_city}  至")         # 由=报关单境内货源地(Q)，只取城市名
    safe_write(ws, "D7", country_cn or None)               # 至=报关单贸易国（地区）(E10)
    safe_write(ws, "G7", None)
    pk = packing or {}
    for i, it in enumerate(agg):
        row = start + i * _YUNTUO_STEP
        safe_write(ws, f"B{row}", it["name_agg"])
        p = pk.get(it["code_agg"]) or {}
        ws[f"C{row}"] = int(p.get("cartons") or 0)
        ws[f"D{row}"] = int(it["qty"])
        ws[f"E{row}"] = uom_cn(it["uom"])
        _n2(ws, f"F{row}", float(p.get("gross") or 0))
        _n2(ws, f"G{row}", float(p.get("net") or 0))
        safe_write(ws, f"B{row + 1}", None)
    tr = start + len(agg) * _YUNTUO_STEP
    ws[f"C{tr}"] = int(totals["cartons"])
    _n2(ws, f"F{tr}", totals["gross"])
    _n2(ws, f"G{tr}", totals["net"])
    safe_write(ws, f"A{start}", "N/M")
    safe_write(ws, f"B{tr + 1}", c["domestic_party_cn"])


def fill_yuntuo_contract(ws, dn, agg, totals, consignee_name="", consignee_addr=""):
    """云驼「合同」：中文品名 + 逐物料 2 行。"""
    c = CONFIG
    start = _resize_yuntuo_data(ws, "合同", len(agg))
    ws["C2"] = c["domestic_party_cn"]
    safe_write(ws, "C4", c["shipper_addr"])
    safe_write(ws, "C8", consignee_name or "")
    safe_write(ws, "C10", consignee_addr or "")
    safe_write(ws, "C12", None)
    safe_write(ws, "E12", None)
    safe_write(ws, "C6", None)
    safe_write(ws, "E6", None)
    safe_write(ws, "G6", dn.get("name", ""))
    safe_write(ws, "G8", fmt_date_contract(dn.get("posting_date", "")))
    safe_write(ws, "G10", None)
    safe_write(ws, "G11", c["trade_term"])
    safe_write(ws, "H11", None)
    for i, it in enumerate(agg):
        row = start + i * _YUNTUO_STEP
        safe_write(ws, f"B{row}", it["name_agg"])
        ws[f"D{row}"] = int(it["qty"])
        ws[f"E{row}"] = uom_cn(it["uom"])
        _n2(ws, f"F{row}", it["price_usd"])
        _n2(ws, f"G{row}", it["amount_usd"])
        safe_write(ws, f"B{row + 1}", None)
    tr = start + len(agg) * _YUNTUO_STEP
    _n2(ws, f"G{tr}", totals["amount_usd"])
    safe_write(ws, f"E{tr + 2}", None)
    amt = float(totals["amount_usd"] or 0)
    dollars, cents = int(amt), int(round((amt - int(amt)) * 100))
    words = num_to_words(dollars) or ""
    if cents:
        words = f"{words} AND CENTS {num_to_words(cents)}".strip()
    safe_write(ws, f"B{tr + 3}", f"Total Value in Word:  {words} ONLY" if words else None)
    for ref in (f"C{tr + 7}", f"C{tr + 8}", f"D{tr + 8}", f"C{tr + 12}"):
        safe_write(ws, ref, None)
    # 「(9)装运口岸和目的地」模板硬编码了港名（深圳 / Shenzhen-- To Hongkong）→ 只去港名、保留标签
    for ref, pat in ((f"B{tr + 8}", "深圳"), (f"B{tr + 9}", "From  Shenzhen-- To Hongkong")):
        cur = ws[ref].value
        if isinstance(cur, str):
            safe_write(ws, ref, cur.replace(pat, "").replace("Destination:  ", "Destination: "))


def _parse_date(val) -> str:
    """'2026-10-08' → 同值；带时间戳则取日期部分。"""
    return (str(val or "").strip() or "1970-01-01")[:10]


def main():
    ap = argparse.ArgumentParser(description="DN → 报关单据导出")
    ap.add_argument("--dn", required=True, help="DN 单号，如 DN-26-00063")
    ap.add_argument("--test", action="store_true", help="使用测试环境")
    ap.add_argument("--output", "-o", help="输出路径")
    ap.add_argument("--consignee", help="境外收货人预设: centrade/daneey/poland/custom（缺省默认 centrade，选择即导出）")
    ap.add_argument("--consignee-name", help="境外收货人名称（覆盖预设/自定义）")
    ap.add_argument("--consignee-addr", help="境外收货人地址（覆盖预设/自定义）")
    ap.add_argument("--declaration-unit", help="申报单位（缺省保留模板原值）")
    ap.add_argument("--no-enrich-flat-dim", action="store_true",
                    help="靠枕尺寸不补全（三角靠枕×20×50 / 平条靠枕×15×50），保持只有长度与已开票一致")
    ap.add_argument("--template", choices=["zhimaitong", "yuntuo"], default="zhimaitong",
                    help="报关单据版式：zhimaitong=智美通（默认）| yuntuo=云驼")
    args = ap.parse_args()

    env = "test" if args.test else "prod"
    key, sec = load_credentials(env)
    if not key or not sec or "your_" in key:
        print("✗ 凭证未配置（检查 .env）", file=sys.stderr)
        sys.exit(1)
    base = ENV_URLS[env]
    print(f"系统: {base}")

    dn = get_doc(base, key, sec, "Delivery Note", args.dn)
    if not dn:
        print(f"✗ 未找到 DN: {args.dn}", file=sys.stderr)
        sys.exit(1)

    agg = aggregate_items(dn)
    # 扣胚在 DN 行上常无价 → 用 Item Price（标准采购）补单件成本
    apply_button_embryo_price(base, key, sec, agg)
    # 靠枕尺寸补全开关（默认补全）：三角靠枕→长度*20*50 / 平条靠枕→长度*15*50。
    # 已开票且当时尺寸不完整的单，可加 --no-enrich-flat-dim 保持只有长度与开票一致。
    if not args.no_enrich_flat_dim:
        for it in agg:
            it["name_agg"] = _enrich_dim_cn(it["name_agg"])
    # 尺寸分隔符统一为 x（中/英文品名都统一；与 EN 侧同口径）
    for it in agg:
        it["name_agg"] = _sep_to_x(it["name_agg"])
    # 英文品名：海绵固定拼法 / 固定覆盖 / 其余并行 AI 翻译
    dskey = load_deepseek_key()
    foam_map = (load_foam_size_map(base, key, sec)
                if any(it["code_agg"].startswith("HM") for it in agg) else {})

    def _en_name(it):
        if it["code_agg"].startswith("HM"):
            return _sep_to_x(_translate_foam(it["code_agg"], it["name_agg"], foam_map))
        ov = TRANSLATION_OVERRIDES.get(it["code_agg"])
        if ov:
            return _sep_to_x(ov)
        return _sep_to_x(translate_zh_to_en(it["name_agg"], dskey)) if dskey else it["name_agg"]

    if dskey:
        def _do(it):
            return it, _en_name(it)
        with ThreadPoolExecutor(max_workers=5) as ex:
            futs = [ex.submit(_do, it) for it in agg]
            for i, f in enumerate(as_completed(futs), 1):
                it, en = f.result()
                it["name_en"] = en
                print(f"  [{i}/{len(agg)}] {it['code_agg']} -> {en}", flush=True)
    else:
        for it in agg:
            it["name_en"] = _en_name(it)
    print(f"聚合后物料 {len(agg)} 行:")
    for it in agg:
        print(f"  {it['code_agg']}  qty={it['qty']}  rate={it['rate']:.4f}  "
              f"amount={it['amount']:.2f}  bom_rate={it['bom_rate']:.4f}  bom_cost={it['bom_cost']:.2f}")
        print(f"    中文: {it['name_agg']}")
        print(f"    英文: {it['name_en']}")

    # 目的国
    country = resolve_country(dn.get("customer", ""))
    print(f"客户: {dn.get('customer')} ({dn.get('customer_name')}) → 目的国: {country}")

    # 境外收货人：固定 Centrade Inc（全部导出强制）
    consignee = resolve_consignee(args, dn.get("customer", ""))
    print(f"境外收货人: {consignee['name']}")

    # 装箱数据：仅用用户确认的装箱组合(CARTON_GROUPS_BY_DN)，不用外箱子表(outer_box_summary/item_weight_cats)
    groups = CARTON_GROUPS_BY_DN.get(args.dn, []) or []
    if groups:
        pk = compute_packing(agg, groups)
        for it in agg:
            code = it["code_agg"]
            it["cartons"] = int(pk["cartons"].get(code, 0))
            it["gross"] = pk["gross"].get(code, 0.0)
            it["net"] = pk["net"].get(code, 0.0)
            it["measrs"] = pk["volume"].get(code, 0.0)
        total_cartons = pk["total_cartons"]
        total_gross = pk["total_gross"]
        total_net = pk["total_net"]
        total_volume = pk["total_volume"]
    else:
        for it in agg:
            it["cartons"] = it["gross"] = it["net"] = it["measrs"] = 0
        total_cartons = total_gross = total_net = total_volume = 0

    # 报关金额（USD）：单价 = RMB 单件成本换算后取整；
    # 金额 —— 扣胚按「单价 × 数量」（保证该行「单价×数量=金额」自洽，2026-09-28 要求）；
    # 其余物料沿用「对 RMB 总额换算」。与 EN 侧同口径。
    for it in agg:
        it["price_usd"] = round(usd_price(it["bom_rate"]), 2)
        it["amount_usd"] = (
            round(it["price_usd"] * float(it.get("qty") or 0), 2)
            if _is_button_embryo(it.get("code_agg", ""))
            else round(usd_price(it["bom_cost"]), 2)
        )

    totals = {
        "qty": round(sum(float(i.get("qty") or 0) for i in dn.get("items", [])), 2),
        "amount": round(sum(float(i.get("amount") or 0) for i in dn.get("items", [])), 2),
        "bom_cost": round(sum(float(i.get("bom_cost") or 0) for i in dn.get("items", [])), 2),
        # 单据 TOTAL = 逐行 USD 金额之和（与打印的逐行金额严格对账）
        "amount_usd": round(sum(float(i["amount_usd"]) for i in agg), 2),
        "cartons": total_cartons,
        "gross": total_gross,
        "net": total_net,
        "measrs": total_volume,
    }
    print(f"合计: qty={totals['qty']}  amount={totals['amount']}  bom_cost={totals['bom_cost']}  "
          f"cartons={total_cartons}  gross={total_gross}kg  net={total_net}kg  vol={total_volume}m³")

    if args.template == "yuntuo":
        # ── 云驼版：4 张表全部写值（模板公式一律覆盖）；与 EN 侧 delivery_plan 同口径 ──
        packing = {it["code_agg"]: {"cartons": it["cartons"], "gross": it["gross"], "net": it["net"]}
                   for it in agg}
        cname = (consignee or {}).get("name", "")
        caddr = (consignee or {}).get("addr", "")
        cty = country[1] if isinstance(country, tuple) else (country or "")
        wb = load_workbook(YUNTUO_TEMPLATE)
        for ws in wb.worksheets:
            ws._images = []
        fill_yuntuo_declaration(wb["报关单"], dn, agg, totals, cty, consignee_name=cname, packing=packing)
        fill_yuntuo_invoice(wb["发票"], dn, agg, totals, consignee_name=cname)
        fill_yuntuo_packing(wb["箱单"], dn, agg, totals, consignee_name=cname, packing=packing, country_cn=cty)
        fill_yuntuo_contract(wb["合同"], dn, agg, totals, consignee_name=cname, consignee_addr=caddr)
        _extend_yuntuo_print_area(wb, len(agg))
        _finalize_yuntuo(wb)
        out_path = Path(args.output) if args.output else OUT_DIR / f"报关单据_{args.dn}_云驼.xlsx"
        wb.save(out_path)
        print(f"OK: {out_path}")
        return 0

    wb = load_workbook(TEMPLATE)
    for ws in wb.worksheets:      # 清除模板自带图片（中基抬头/印章/签名）
        ws._images = []
    expand_sheets(wb, len(agg))
    fill_invoice(wb["报关发票 "], dn, agg, totals)
    fill_packing(wb["装箱单"], dn, agg, totals)
    fill_contract(wb["报关合同 "], dn, agg, totals)
    fill_declaration(wb["报关单NEW "], dn, agg, totals, country,
                     consignee_name=(consignee or {}).get("name", ""),
                     consignee_addr=(consignee or {}).get("addr", ""),
                     declaration_unit=args.declaration_unit or "")

    # 按实际物料数删除数据区多余整行（发票/装箱单/报关单NEW，报关合同不动）
    delete_extra_rows(wb, len(agg))
    # 删除三张表「表头与数据之间」的空白行（发票15/装箱单16/合同15），其后行坐标整体上移 1
    _remove_blank_header_rows(wb)

    # 报关合同：名称区每物料行合并 B:E；统一 4 张表内容格为左对齐 + 单行（不换行/不缩小/去换行）
    _merge_contract_name_cols(wb["报关合同 "], len(agg))
    _plain_left_single_line(wb)
    # 动态列宽：仅加宽「单行内容会被右邻格截断」的列，保证完整显示
    _autofit_columns(wb)
    # 行高统一（三张表除顶部公司信息块外 16.5）+ 表格区全框线/粗外框
    _uniform_row_heights(wb)
    _apply_table_borders(wb, len(agg))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(args.output) if args.output else OUT_DIR / f"报关单据_{args.dn}.xlsx"
    wb.save(str(out))
    print(f"OK: {out}")


# ──────────────────────────────────────────────────────────────
# BOM 成本参照实现（与 EN delivery_plan/doc_event.py 的 _get_nd_cost 逻辑一致）
# 用于内胆(ND#) bom_rate 取 BOM内胆成本 cost_nd 列；皮壳(PK#) 取 cost_pk 列。
# ──────────────────────────────────────────────────────────────
BOM_COST_FILE = _DIR / "数据源" / "bom_cost_list_v2_2026-57-25-15-8.json.gz"


def _load_bom_cost_report() -> list[dict]:
    """读取 BOM 成本报表(gzip JSON)，返回 result 行列表（键=item_fg 成品编码）。"""
    import gzip
    import json as _json
    if not BOM_COST_FILE.is_file():
        print(f"✗ 未找到 BOM 成本报表: {BOM_COST_FILE}", file=sys.stderr)
        return []
    with gzip.open(BOM_COST_FILE, "rt", encoding="utf-8") as f:
        return _json.load(f).get("result", [])


def _get_nd_cost_ref(item_nd: str, bom_rows: list[dict]) -> tuple[float | None, dict | None]:
    """按内胆物料编码反向查找 BOM 内胆成本 cost_nd（参照实现）。

    匹配逻辑（membership-based，不依赖颜色词表）：
      1. 去掉 ND# 前缀，按 '-' 切分：段[0]=KS号，段[1]=尺寸；
      2. 遍历 BOM 成品行，item_fg 不去色直接按 '-' 切分，
         匹配条件 = 首段==KS号 且 尺寸出现在任一字段段
         （不用「最后一段=尺寸」，因成品可能带颜色/不带颜色，段位不固定）；
      3. 命中取该行 cost_nd；cost_nd 为 0/缺失则继续找有值的行。
    返回 (cost_nd, matched_row)；未命中返回 (None, None)。
    """
    if not item_nd or not item_nd.startswith("ND#"):
        return None, None
    parts = item_nd[3:].split("-")
    if len(parts) < 2:
        return None, None
    ks, size = parts[0], parts[1]
    for row in bom_rows:
        item_fg = (row.get("item_fg") or "").strip()
        if not item_fg:
            continue
        fg_parts = item_fg.split("-")
        if len(fg_parts) < 2:
            continue
        if fg_parts[0] == ks and size in fg_parts:
            cost_nd = row.get("cost_nd")
            if cost_nd is not None and cost_nd != 0:
                return cost_nd, row
    return None, None


if __name__ == "__main__":
    main()
