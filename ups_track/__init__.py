"""ups_track — UPS 跟踪码批量查询工具（通用、可复用）。

用法：``python -m ups_track.cli query --input tracking.txt --out result``
"""

from .client import (
    DEFAULT_CIE_BASE,
    DEFAULT_PROD_BASE,
    UpsTrackClient,
    UpsTrackError,
)
from .models import UpsEvent, UpsTrackInfo, parse_event_dt, parse_track_payload

__all__ = [
    "DEFAULT_CIE_BASE",
    "DEFAULT_PROD_BASE",
    "UpsTrackClient",
    "UpsTrackError",
    "UpsEvent",
    "UpsTrackInfo",
    "parse_event_dt",
    "parse_track_payload",
]

__version__ = "0.1.0"
