"""离线单测：模型解析（真实 rstt028 响应形状）。"""

from gls_track.models import parse_detail, parse_summary

DETAIL_10 = {
    "postalCode": "21706",
    "signature": {"validate": True, "name": "Signature:", "value": "true"},
    "infos": [
        {"type": "WEIGHT", "name": "Weight:", "value": "2 kg"},
        {"type": "PRODUCT", "name": "Product:", "value": "EuroBusinessSmallParcel"},
        {"type": "SERVICES", "name": "Services:", "value": "FlexDeliveryService,"},
    ],
    "progressBar": {"level": 100, "statusInfo": "DELIVERED", "statusText": "Delivered"},
    "references": [
        {"type": "UNITNO", "name": "Parcel number:", "value": "29626585597"},
        {"type": "GLSREF", "name": "Origin National Reference in Unicode", "value": "29006842"},
        {"type": "NOTECARDID", "name": "Track ID", "value": "29626585597"},
        {"type": "CUSTREF", "name": "Customer's own reference number", "value": "P81921805"},
    ],
    "arrivalTime": {"name": "Delivered on:", "value": "03-Sep-2026 at 12:39 o`clock"},
    "history": [
        {"time": "12:39:09", "date": "2026-09-03", "evtDscr": "The parcel has been delivered.", "address": {"city": "Geestland", "countryCode": "DE", "countryName": "Germany"}},
        {"time": "06:33:39", "date": "2026-09-03", "evtDscr": "The parcel is expected to be delivered during the day.", "address": {"city": "Geestland", "countryCode": "DE"}},
        {"time": "06:30:52", "date": "2026-09-03", "evtDscr": "The parcel has reached the parcel center.", "address": {"city": "Geestland", "countryCode": "DE"}},
        {"time": "21:36:59", "date": "2026-09-01", "evtDscr": "The parcel has left the parcel center.", "address": {"city": "Neuenstein", "countryCode": "DE"}},
        {"time": "21:34:39", "date": "2026-09-01", "evtDscr": "The parcel has reached the parcel center.", "address": {"city": "Neuenstein", "countryCode": "DE"}},
        {"time": "20:20:10", "date": "2026-08-31", "evtDscr": "The parcel has reached the parcel center.", "address": {"city": "Strykow", "countryCode": "PL"}},
        {"time": "20:20:10", "date": "2026-08-31", "evtDscr": "The parcel was handed over to GLS.", "address": {"city": "Strykow", "countryCode": "PL"}},
        {"time": "07:06:44", "date": "2026-08-31", "evtDscr": "The parcel data was entered into the GLS IT system; the parcel was not yet handed over to GLS.", "address": {"city": "Strykow", "countryCode": "PL"}},
    ],
}


def test_detail_parses_full_real_shape():
    p = parse_detail("29626585597", DETAIL_10)
    assert p.parcel_no == "29626585597"
    assert p.current_status == "DELIVERED"
    assert p.delivered is True
    assert p.cust_ref == "P81921805"
    assert len(p.events) == 8
    # events 时间升序：第一条=数据录入(07:06)；交接事件存在且为 08-31 20:20
    assert p.events[0].dt.isoformat().startswith("2026-08-31T07:06:44")
    assert any(e.description == "The parcel was handed over to GLS." for e in p.events)
    # 关键时点
    assert p.data_entered_dt.hour == 7
    assert p.handed_dt.hour == 20 and p.handed_dt.day == 31
    assert p.delivered_dt.isoformat().startswith("2026-09-03T12:39:09")
    assert p.last_event_dt == p.delivered_dt
    # 交付城市兜底
    assert p.events[-1].city == "Geestland"


def test_detail_no_history_not_delivered():
    payload = {"progressBar": {"statusInfo": "INTRANSIT", "statusText": "In transit"}, "history": []}
    p = parse_detail("29626585597", payload)
    assert p.current_status == "INTRANSIT"
    assert p.delivered is False
    assert p.events == [] and p.last_event_dt is None


def test_summary_delivered_arrival():
    payload = {"tuStatus": [{"arrivalTime": {"value": "03-Sep-2026 at 12:39 o`clock"},
                            "progressBar": {"statusInfo": "DELIVERED", "statusText": "Delivered"}}]}
    p = parse_summary("29626585597", payload)
    assert p.delivered and p.delivered_dt.hour == 12
