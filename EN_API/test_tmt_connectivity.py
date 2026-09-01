# -*- coding: utf-8 -*-
"""Quick TMT connectivity check. Reads EN_API/.env only."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent


def _load_dotenv() -> None:
    for p in (_DIR / ".env", _DIR.parent / ".env"):
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


def main() -> int:
    _load_dotenv()
    sid = os.getenv("TENCENT_SECRET_ID", "")
    sk = os.getenv("TENCENT_SECRET_KEY", "")
    region = os.getenv("TENCENT_TMT_REGION", "ap-guangzhou")
    if not sid or not sk:
        print("FAIL: missing TENCENT_SECRET_ID / TENCENT_SECRET_KEY in EN_API/.env")
        return 1
    print(f"SecretId prefix: {sid[:8]}... region: {region}")

    from tencentcloud.common import credential
    from tencentcloud.common.profile.client_profile import ClientProfile
    from tencentcloud.common.profile.http_profile import HttpProfile
    from tencentcloud.tmt.v20180321 import tmt_client

    cred = credential.Credential(sid, sk)
    hp = HttpProfile()
    hp.endpoint = "tmt.tencentcloudapi.com"
    cp = ClientProfile()
    cp.httpProfile = hp
    client = tmt_client.TmtClient(cred, region, cp)

    samples = ["三角靠枕", "BetterRest靠卧枕", "BBL坐趴两用枕"]
    for zh in samples:
        body = client.call(
            "TextTranslate",
            {"SourceText": zh, "Source": "zh", "Target": "en", "ProjectId": 0},
        )
        resp = json.loads(body)["Response"]
        if "Error" in resp:
            err = resp["Error"]
            print(f"FAIL: {err.get('Code')}: {err.get('Message')}")
            return 1
        print(f"  {zh} -> {resp.get('TargetText')}")

    print("TMT_OK: credentials work for TextTranslate")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
