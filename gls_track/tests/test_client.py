"""离线单测：client URL 构造 + 错误分类（httpx.MockTransport）。"""

import httpx
import pytest

from gls_track.client import DEFAULT_BASE, GlsTrackClient, GlsTrackError

SUMMARY_PAYLOAD = {
    "tuStatus": [
        {
            "arrivalTime": {"name": "Delivered on:", "value": "03-Sep-2026 at 12:39 o`clock"},
            "progressBar": {
                "level": 100,
                "statusInfo": "DELIVERED",
                "statusText": "Delivered",
                "statusBar": [{"status": "PREADVICE", "imageStatus": "COMPLETE"}],
            },
            "tuNo": "29626585597",
        }
    ]
}

DETAIL_PAYLOAD = {
    "progressBar": {"statusInfo": "DELIVERED", "statusText": "Delivered", "level": 100},
    "arrivalTime": {"name": "Delivered on:", "value": "03-Sep-2026 at 12:39 o`clock"},
    "references": [
        {"type": "UNITNO", "value": "29626585597"},
        {"type": "CUSTREF", "value": "P81921805"},
        {"type": "NOTECARDID", "value": "29626585597"},
    ],
    "history": [
        {"date": "2026-09-03", "time": "12:39:09", "evtDscr": "The parcel has been delivered.",
         "address": {"city": "Geestland", "countryCode": "DE", "countryName": "Germany"}},
        {"date": "2026-08-31", "time": "20:20:10", "evtDscr": "The parcel was handed over to GLS.",
         "address": {"city": "Strykow", "countryCode": "PL", "countryName": "Poland"}},
        {"date": "2026-08-31", "time": "07:06:44", "evtDscr": "The parcel data was entered into the GLS IT system; the parcel was not yet handed over to GLS.",
         "address": {"city": "Strykow", "countryCode": "PL", "countryName": "Poland"}},
    ],
}


def _client(handler):
    transport = httpx.MockTransport(handler)
    return GlsTrackClient(transport=transport)


def test_summary_url_and_parse():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        return httpx.Response(200, json=SUMMARY_PAYLOAD)

    with _client(handler) as c:
        p = c.summary("29626585597")
    assert "rstt029" in seen["url"] and "match=29626585597" in seen["url"]
    assert p.current_status == "DELIVERED" and p.delivered is True
    assert p.delivered_dt.year == 2026 and p.delivered_dt.month == 9


def test_detail_url_requires_postal_and_parses():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        return httpx.Response(200, json=DETAIL_PAYLOAD)

    with _client(handler) as c:
        p = c.detail("29626585597", "21706")
    assert "rstt028/29626585597" in seen["url"] and "postalCode=21706" in seen["url"]
    assert p.delivered and p.cust_ref == "P81921805"
    assert len(p.events) == 3
    # events 时间升序 → 最早=数据录入(建标)，中间=交接，最晚=交付
    assert p.events[0].dt.hour == 7
    assert p.handed_dt.hour == 20
    assert p.delivered_dt.isoformat().startswith("2026-09-03T12:39:09")


def test_track_chooses_detail_when_postal_present():
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        return httpx.Response(200, json=DETAIL_PAYLOAD)

    with _client(handler) as c:
        p = c.track("29626585597", "21706")
    assert len(calls) == 1 and "rstt028" in calls[0]
    assert p.delivered
    # 无邮编 → 摘要（单次，避免双调用）
    calls.clear()
    with _client(lambda req: calls.append(str(req.url)) or httpx.Response(200, json=SUMMARY_PAYLOAD)) as c2:
        p2 = c2.track("29626585597")
    assert len(calls) == 1 and "rstt029" in calls[0]


def test_error_404_raises_not_found():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"exceptionText": "boom"})

    with _client(handler) as c:
        with pytest.raises(GlsTrackError) as ei:
            c.summary("29626585597")
    assert ei.value.category == "not_found"


def test_429_retriable():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={})

    with _client(handler) as c:
        with pytest.raises(GlsTrackError) as ei:
            c.summary("29626585597")
    assert ei.value.retriable is True
