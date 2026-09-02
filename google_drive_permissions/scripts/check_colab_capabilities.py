# -*- coding: utf-8 -*-
"""检查 15 个业务 Colab 的 sharing 能力（capabilities），确认 SA 能否改共享。

capabilities.canShare 是调用者视角：必须用服务账号 token 查，用属主 OAuth 会永远 True。
"""
from __future__ import annotations

import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account

from tongtool_order_cost.tongtool_order_cost.gsheets import service_account_path

BASE = "https://www.googleapis.com/drive/v3"

NOTEBOOKS = {
    "通途DHL DPD GLS 导出订单地址文件处理 202302": "1OY0HHKfh4SI-6oDlnW8EHbZ-Gawoircf",
    "订单处理 Overstock. 炸开SKU别名,不处理MyToys": "1nnpuKfOjfF0rixqNGWnkRrL-QvY_UzP0",
    "Fedex 通途导出包裹文件处理/海外仓文件表头改名 202308 美东": "1aGL55Z8g36k5wNhenuRYnTckCgs4q6HD",
    "李娜 美中 通途 Fedex excel 生成 SKU PDF 分割 202409": "1q_FzbxozoeSTRLJFNEuSlCWdLTrijOk7",
    "Wayfair PDF 添加 SKU，李娜提取FBAPlan 20230802": "17E5LEO8Cd5zAO1KPlu3Oje-ImLUo7c4H",
    "PotteryBarn/SPS 合并装箱单+UPS PDF 添加 SKU 1拆2 20230721": "1SjFXUYbQf0XwKl5H8B2lRhFBaYbF9d_5",
    "赛狐手工订单导入测试": "1ddzcWyPE2s_t7YvDSkCBIOLqcnkvaNSS",
    "ERPNext EN 新建物料模板 REST API": "14KhniG536IaRPvH5hV8_RncxdB-6_z1P",
    "测试Home24 XXXL订单 Requests for Humans Python HTTP": "1rEW5Abu8mYS4TyuPRNSt2-U0jmLMmbXV",
    "老 透视表订单-区分清仓 美国分公司 to USNJ_USTX 加拿大 20250516": "1WBX66YgnKToGhpgfSLKWWySHrKAcdIrU",
    "成本核算20230904 尺寸提取 产品名称-品类 海外仓成本": "1O2K65veBeP5tjXFxpxfz8FStHFSJQzQ7",
    "裁切PDF 202407": "1OBoBWOlgnxWwSqBiihU1Sg-T7lxbr0po",
    "账期文件分析-读通途新FBA文件 20240523": "1vhrAf4leTmsEBv4oZjV2IAPmoEWUwbNZ",
    "税账期TXT 挂载Gdrive": "1YkIZtFElA8DD8K02nghgT2UQOTY_xjWy",
    "钉钉OA收款费用Amazon多平台&附加费&Tax 20250704": "1tyBOhVCG5uEQ90RMUyV4rN_JRURW_aeh",
}


def main():
    creds = service_account.Credentials.from_service_account_file(
        service_account_path(), scopes=["https://www.googleapis.com/auth/drive"]
    )
    creds.refresh(Request())
    token = creds.token

    print("using service-account token (canShare is caller-specific)")
    failed = 0
    for name, fid in NOTEBOOKS.items():
        r = requests.get(
            f"{BASE}/files/{fid}",
            params={"fields": "capabilities(canShare,canEdit)", "supportsAllDrives": "true"},
            headers={"Authorization": f"Bearer {token}"}, timeout=60,
        )
        if r.status_code != 200:
            print(f"  [ERR] {name}: HTTP {r.status_code} {r.text[:80]}")
            failed += 1
            continue
        cap = r.json().get("capabilities", {})
        can_share = cap.get("canShare")
        if can_share is not True:
            failed += 1
        print(f"  canShare={can_share!s:5s} canEdit={cap.get('canEdit')!s:5s} {name}")
    if failed:
        raise SystemExit(f"{failed} notebook(s) SA cannot share or read")


if __name__ == "__main__":
    main()
