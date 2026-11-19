# -*- coding: utf-8 -*-
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for _p in (_REPO, _REPO / "amazon_period_tax", _REPO / "dingtalk" / "dingtalk_oa_approval"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
