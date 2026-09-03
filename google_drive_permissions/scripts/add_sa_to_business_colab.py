# -*- coding: utf-8 -*-
"""给「已有同事 writer 权限的业务 Colab notebook」补服务账号 writer 权限。

默认 dry-run 只打印计划 + 每个文件的 SA canShare 状态；
加 --apply 才真正新增权限（sendNotificationEmail=false，不发邮件）。
用用户级凭证(属主)授权，避免 SA 自身因"仅属主可改共享"被 403。
"""
from __future__ import annotations

import sys
import time

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from paths import user_oauth_path

TOKEN_FILE = str(user_oauth_path())
SA_EMAIL = "colab-gsheets@gsheets-351101.iam.gserviceaccount.com"
BASE = "https://www.googleapis.com/drive/v3"

# 15 个已有同事 writer 权限的业务 notebook (name -> id)
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


def api(token: str, method: str, path: str, **kwargs) -> requests.Response:
    url = f"{BASE}{path}"
    for attempt in range(4):
        r = requests.request(method, url, headers={"Authorization": f"Bearer {token}"}, timeout=60, **kwargs)
        if r.status_code in (429, 500, 503) and attempt < 3:
            time.sleep(2 * (attempt + 1) + 1)
            continue
        return r
    raise RuntimeError(f"{method} {path} failed after retries")


def main() -> None:
    apply = "--apply" in sys.argv
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, scopes=["https://www.googleapis.com/auth/drive"])
    if creds.expired or not creds.token:
        creds.refresh(Request())
    token = creds.token

    to_add = []
    for name, fid in NOTEBOOKS.items():
        # 读取权限列表，判断 SA 是否已有
        r = api(token, "GET", f"/files/{fid}/permissions", params={"fields": "permissions(id,emailAddress,role,type)", "supportsAllDrives": "true"})
        if r.status_code != 200:
            print(f"  [ERR-READ] {name}: HTTP {r.status_code} {r.text[:100]}")
            continue
        perms = r.json().get("permissions", [])
        sa = next((p for p in perms if p.get("emailAddress") == SA_EMAIL), None)

        status = f"已有({sa['role']})" if sa else "缺"
        print(f"  {status:10s} {name}")
        if not sa:
            to_add.append((name, fid))

    print(f"\n[计划] 需补 SA writer 的 notebook: {len(to_add)} 个")
    if not apply:
        print(">>> dry-run，未修改。加 --apply 执行。")
        return

    for name, fid in to_add:
        r = api(token, "POST", f"/files/{fid}/permissions",
                json={"role": "writer", "type": "user", "emailAddress": SA_EMAIL},
                params={"supportsAllDrives": "true", "sendNotificationEmail": "false"})
        if r.status_code in (200, 201):
            print(f"  [OK] {name}")
        elif r.status_code == 403:
            print(f"  [403] {name}: {r.text[:120]}")
        else:
            print(f"  [ERR] {name}: HTTP {r.status_code} {r.text[:120]}")
        time.sleep(0.1)

    print("\n[验证] 补权后 SA 状态:")
    for name, fid in NOTEBOOKS.items():
        p = api(token, "GET", f"/files/{fid}", params={"fields": "permissions(id,emailAddress,role,type)", "supportsAllDrives": "true"}).json()
        sa_p = next((x for x in p.get("permissions", []) if x.get("emailAddress") == SA_EMAIL), None)
        print(f"  {sa_p['role'] if sa_p else '无':6s} {name}")


if __name__ == "__main__":
    main()
