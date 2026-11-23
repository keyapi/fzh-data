# -*- coding: utf-8 -*-
"""导出生产环境「重量模板」重尺数据，供同事核对（三角靠枕等）。

输出 xlsx，含：
- Sheet「重量模板数据」：数据库原值（全部字段）+ 两组联动校验列
- Sheet「联动复算」：外包装/内数量为输入，单个包装按重量模板单据的联动规则用公式计算（可编辑）
- Sheet「说明」：联动规则说明

联动规则（源自 light_mes/public/js/item.js，Item 表单）：
  单个包装长 = 外包装长
  单个包装宽 = 外包装宽
  单个包装高 = 外包装高 ÷ 外包装内数量
  （体积 = 长×宽×高；仅当外箱三项>0 且 内数量>0 时才自动写入，其余情况单个包装字段可手填）
  半成品（sfg）同理，用各自字段组。
"""
import json
import os
import sys
import argparse
import datetime
import urllib.request
import urllib.parse
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

_DIR = Path(__file__).resolve().parent

_ENV_URLS = {
    "test": "https://ensh.vilavi.cn",
    "prod": "https://erpnext.vilavi.cn",
}
_ENV_KEY_MAP = {
    "test": ("TEST_ERP_API_KEY", "TEST_ERP_API_SECRET"),
    "prod": ("PROD_ERP_API_KEY", "PROD_ERP_API_SECRET"),
}

# 运行时由 set_env() 赋值；凭证一律从 .env 读取，不写进代码
BASE = ""
KEY = ""
SEC = ""

OUT_DIR = os.path.join(_DIR, "out")


def _load_dotenv(candidates):
    for p in candidates:
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                v = v[1:-1]
            os.environ.setdefault(k, v)


# 凭证来源：仓库根 .env（item_weight_size/.env 可选），兜底 EN_API/.env。.env 已被 .gitignore 排除。
_load_dotenv([_DIR / ".env", _DIR.parent / ".env", _DIR.parent / "EN_API" / ".env"])


def set_env(env):
    """按环境选择 URL + 凭证（从环境变量读取）。"""
    global BASE, KEY, SEC
    kname, sname = _ENV_KEY_MAP[env]
    key, sec = os.environ.get(kname), os.environ.get(sname)
    if not key or not sec:
        raise SystemExit(
            "缺少凭证 %s / %s —— 请放到仓库根 .env（勿提交）。" % (kname, sname)
        )
    BASE, KEY, SEC = _ENV_URLS[env], key, sec

FIELDS = [
    "name", "item_name", "item_group", "has_variants",
    "custom_cover_weight_per_unit", "custom_cover_weight_uom",
    "custom_fg_weight_per_unit", "custom_fg_weight_uom",
    "custom_sfg_weight_per_unit", "custom_sfg_weight_uom",
    "custom_outer_package_length", "custom_outer_package_width",
    "custom_outer_package_height", "custom_outer_package_volume", "custom_quantity_per_outer_package",
    "custom_package_length", "custom_package_width", "custom_package_height", "custom_package_volume",
    "custom_sfg_outer_package_length", "custom_sfg_outer_package_width",
    "custom_sfg_outer_package_height", "custom_sfg_outer_package_volume",
    "custom_sfg_quantity_per_outer_package",
    "custom_sfg_package_length", "custom_sfg_package_width",
    "custom_sfg_package_height", "custom_sfg_package_volume",
]

HEADERS = [
    "重量模板编号", "名称", "物料组",
    "皮壳单重(g)", "皮壳单重单位",
    "成品单重(g)", "成品单重单位",
    "半成品单重", "半成品单重单位",
    "外包装长(cm)", "外包装宽(cm)", "外包装高(cm)", "外包装体积(cm³)", "外包装内数量",
    "单个包装长(cm)", "单个包装宽(cm)", "单个包装高(cm)", "单个包装体积(cm³)",
    "半成品外包装长(cm)", "半成品外包装宽(cm)", "半成品外包装高(cm)", "半成品外包装体积(cm³)",
    "半成品外包装内数量",
    "半成品单个包装长(cm)", "半成品单个包装宽(cm)", "半成品单个包装高(cm)", "半成品单个包装体积(cm³)",
    "校验·单个包装", "校验·半成品单个包装",
]

KEYS = [
    "name", "item_name", "item_group",
    "custom_cover_weight_per_unit", "custom_cover_weight_uom",
    "custom_fg_weight_per_unit", "custom_fg_weight_uom",
    "custom_sfg_weight_per_unit", "custom_sfg_weight_uom",
    "custom_outer_package_length", "custom_outer_package_width",
    "custom_outer_package_height", "custom_outer_package_volume", "custom_quantity_per_outer_package",
    "custom_package_length", "custom_package_width", "custom_package_height", "custom_package_volume",
    "custom_sfg_outer_package_length", "custom_sfg_outer_package_width",
    "custom_sfg_outer_package_height", "custom_sfg_outer_package_volume",
    "custom_sfg_quantity_per_outer_package",
    "custom_sfg_package_length", "custom_sfg_package_width",
    "custom_sfg_package_height", "custom_sfg_package_volume",
]


def api_items():
    rows = []
    start = 0
    page = 200
    while True:
        params = {
            "fields": json.dumps(FIELDS, ensure_ascii=False),
            "filters": json.dumps([["item_group", "like", "重量模板#%"]], ensure_ascii=False),
            "limit_start": start,
            "limit_page_length": page,
            "order_by": "item_group asc, name asc",
        }
        url = BASE + "/api/resource/Item?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"Authorization": "token %s:%s" % (KEY, SEC)})
        with urllib.request.urlopen(req, timeout=300) as r:
            data = json.loads(r.read().decode("utf-8")).get("data", [])
        rows.extend(data)
        if len(data) < page:
            break
        start += page
    return rows


def build(rows):
    wb = Workbook()

    # ---------- Sheet1 重量模板数据 ----------
    ws = wb.active
    ws.title = "重量模板数据"
    hdr_fill = PatternFill("solid", fgColor="D9E1F2")
    for c, h in enumerate(HEADERS, 1):
        cell = ws.cell(row=1, column=c, value=h)
        cell.font = Font(bold=True)
        cell.fill = hdr_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for i, raw in enumerate(rows):
        r = i + 2
        for c, k in enumerate(KEYS, 1):
            v = raw.get(k)
            if v == "":
                v = None
            ws.cell(row=r, column=c, value=v)
        # 校验·单个包装 (J..Q = 10..17)
        ws.cell(row=r, column=28, value=(
            '=IF(AND(J{r}>0,K{r}>0,L{r}>0,N{r}>0),'
            'IF(AND(O{r}=J{r},P{r}=K{r},ROUND(Q{r},6)=ROUND(L{r}/N{r},6)),"OK","不符"),"不适用")'
        ).format(r=r))
        # 校验·半成品单个包装 (S..Z = 19..26)
        ws.cell(row=r, column=29, value=(
            '=IF(AND(S{r}>0,T{r}>0,U{r}>0,W{r}>0),'
            'IF(AND(X{r}=S{r},Y{r}=T{r},ROUND(Z{r},6)=ROUND(U{r}/W{r},6)),"OK","不符"),"不适用")'
        ).format(r=r))

    ws.freeze_panes = "J2"   # 冻结 A~I 列 + 首行，横向滚动时编号/名称/物料组/单重列固定
    ws.auto_filter.ref = "A1:%s%d" % (get_column_letter(len(HEADERS)), len(rows) + 1)
    widths = [22, 34, 24] + [13] * (len(HEADERS) - 3)
    for c, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(c)].width = w
    ws.row_dimensions[1].height = 30

    # ---------- Sheet2 重尺联动（可编辑） ----------
    ws2 = wb.create_sheet("重尺联动（可编辑）")
    h2 = ["重量模板编号", "物料名称",
          "外包装长(cm)", "外包装宽(cm)", "外包装高(cm)", "外包装体积(cm³)", "外包装内数量",
          "单个包装长(cm)", "单个包装宽(cm)", "单个包装高(cm)", "单个包装体积(cm³)",
          "半成品外包装长(cm)", "半成品外包装宽(cm)", "半成品外包装高(cm)", "半成品外包装体积(cm³)",
          "半成品外包装内数量",
          "半成品单个包装长(cm)", "半成品单个包装宽(cm)", "半成品单个包装高(cm)", "半成品单个包装体积(cm³)"]
    for c, h in enumerate(h2, 1):
        cell = ws2.cell(row=1, column=c, value=h)
        cell.font = Font(bold=True)
        cell.fill = hdr_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    inp_fill = PatternFill("solid", fgColor="FFF2CC")   # 输入格底色
    for i, raw in enumerate(rows):
        r = i + 2
        # 标识
        ws2.cell(row=r, column=1, value=raw.get("name"))
        ws2.cell(row=r, column=2, value=raw.get("item_name"))
        # 输入（初值取自数据库）
        ws2.cell(row=r, column=3, value=raw.get("custom_outer_package_length"))
        ws2.cell(row=r, column=4, value=raw.get("custom_outer_package_width"))
        ws2.cell(row=r, column=5, value=raw.get("custom_outer_package_height"))
        ws2.cell(row=r, column=7, value=raw.get("custom_quantity_per_outer_package"))
        ws2.cell(row=r, column=12, value=raw.get("custom_sfg_outer_package_length"))
        ws2.cell(row=r, column=13, value=raw.get("custom_sfg_outer_package_width"))
        ws2.cell(row=r, column=14, value=raw.get("custom_sfg_outer_package_height"))
        ws2.cell(row=r, column=16, value=raw.get("custom_sfg_quantity_per_outer_package"))
        for c in (3, 4, 5, 7, 12, 13, 14, 16):
            ws2.cell(row=r, column=c).fill = inp_fill
        # 公式：体积 + 单个包装
        ws2.cell(row=r, column=6, value="=C{r}*D{r}*E{r}".format(r=r))
        ws2.cell(row=r, column=8, value="=C{r}".format(r=r))
        ws2.cell(row=r, column=9, value="=D{r}".format(r=r))
        ws2.cell(row=r, column=10, value='=IF(G{r}>0,E{r}/G{r},"")'.format(r=r))
        ws2.cell(row=r, column=11, value='=IF(J{r}="","",H{r}*I{r}*J{r})'.format(r=r))
        ws2.cell(row=r, column=15, value="=L{r}*M{r}*N{r}".format(r=r))
        ws2.cell(row=r, column=17, value="=L{r}".format(r=r))
        ws2.cell(row=r, column=18, value="=M{r}".format(r=r))
        ws2.cell(row=r, column=19, value='=IF(P{r}>0,N{r}/P{r},"")'.format(r=r))
        ws2.cell(row=r, column=20, value='=IF(S{r}="","",Q{r}*R{r}*S{r})'.format(r=r))
    ws2.freeze_panes = "C2"   # 冻结 编号+物料名称 两列 + 首行
    ws2.auto_filter.ref = "A1:%s%d" % (get_column_letter(len(h2)), len(rows) + 1)
    for c in range(1, len(h2) + 1):
        ws2.column_dimensions[get_column_letter(c)].width = 16
    ws2.column_dimensions["A"].width = 22
    ws2.column_dimensions["B"].width = 34
    ws2.row_dimensions[1].height = 30

    # ---------- Sheet3 说明 ----------
    ws3 = wb.create_sheet("说明")
    notes = [
        "重量模板重尺数据导出 — 供核对",
        "",
        "数据来源：生产 erpnext.vilavi.cn，物料组 like 重量模板#%%，共 %d 条。" % len(rows),
        "导出时间：%s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "",
        "【联动规则】（源自 light_mes/public/js/item.js — Item 表单）",
        "  单个包装长 = 外包装长",
        "  单个包装宽 = 外包装宽",
        "  单个包装高 = 外包装高 ÷ 外包装内数量",
        "  体积 = 长 × 宽 × 高",
        "  仅当 外箱长/宽/高 均 > 0 且 内数量 > 0 时，单个包装字段才自动写入并置为只读；否则可手工填写。",
        "  半成品（sfg）同理，使用各自字段组。",
        "",
        "【Sheet 说明】",
        "  重量模板数据：数据库原值。末尾两列『校验·单个包装 / 校验·半成品单个包装』比对库值与联动规则，取值：",
        "      OK      = 库里的单个包装与联动规则一致",
        "      不符    = 库值与规则不一致（可能被手工改过，或改了外箱但没重算）",
        "      不适用  = 外箱长/宽/高 或 内数量 有缺失（为 0），联动规则不触发；",
        "                此时『单个包装』是手工填写的，无法用规则校验（产品物料库的箱规仍会取用它）。",
        "  重尺联动（可编辑）：黄色格为输入（初值取自库），单个包装各列与体积为公式，改动外包装/内数量即自动重算。",
        "      （编辑『外包装内数量』或『外包装高』→『单个包装高』= 外包装高 ÷ 外包装内数量，会自动更新）",
        "",
        "【产品物料库 箱规取值口径】",
        "  FBA：一律用『单个包装长/宽/高』。",
        "  FBM：皮壳、成品 → 『单个包装长/宽/高』；半成品 → 『半成品单个包装长/宽/高』。",
    ]
    for i, t in enumerate(notes, 1):
        ws3.cell(row=i, column=1, value=t)
    ws3.column_dimensions["A"].width = 110

    wb.calculation.fullCalcOnLoad = True   # 打开时强制重算（openpyxl 不写缓存值）
    return wb


def main():
    ap = argparse.ArgumentParser(description="导出重量模板重尺数据（凭证从 .env 读取，勿提交）")
    ap.add_argument("--env", choices=("prod", "test"), default="prod",
                    help="数据来源环境，默认 prod")
    args = ap.parse_args()
    set_env(args.env)
    print("环境: %s (%s)" % (args.env, BASE))
    print("拉取重量模板 ...")
    rows = api_items()
    print("共 %d 条" % len(rows))
    if not rows:
        print("无数据，退出"); sys.exit(1)
    os.makedirs(OUT_DIR, exist_ok=True)
    wb = build(rows)
    fn = os.path.join(OUT_DIR, "重量模板_重尺数据_%s.xlsx" % datetime.datetime.now().strftime("%Y%m%d"))
    wb.save(fn)
    print("已写出:", fn)


if __name__ == "__main__":
    main()
