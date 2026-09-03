"""离线测试用 UPS track/details mock payload（结构参考 UPS 官方 API + CIE 样例）。"""

from __future__ import annotations

from typing import Any


def delivered_payload(number: str = "1Z999AA10123456784") -> dict[str, Any]:
    """一条"已交付"样例：建标 07/06 → 实际发货 07/20 → 交付 07/23（对应 2026-08 PB 核查样例）。"""
    return {
        "trackResponse": {
            "shipment": [{
                "inquiryNumber": number,
                "currentStatus": {"type": "D", "code": "FS", "description": "Delivered"},
                "package": [{
                    "trackingNumber": number,
                    "activity": [
                        {"location": {"address": {"city": "Stafford", "stateProvince": "TX", "postalCode": "77477"}},
                         "status": {"type": "M", "code": "MP",
                                   "description": "Shipper created a label, UPS has not received the package"},
                         "date": "20260706", "time": "091500"},
                        {"location": {"address": {"city": "Stafford", "stateProvince": "TX", "postalCode": "77477"}},
                         "status": {"type": "MV", "code": "OR", "description": "We Have Your Package"},
                         "date": "20260720", "time": "183000"},
                        {"location": {"address": {"city": "Houston", "stateProvince": "TX", "postalCode": "77001"}},
                         "status": {"type": "I", "code": "DP", "description": "Departed from Facility"},
                         "date": "20260721", "time": "021500"},
                        {"location": {"address": {"city": "West Roxbury", "stateProvince": "MA", "postalCode": "02132"}},
                         "status": {"type": "D", "code": "FS", "description": "Delivered"},
                         "date": "20260723", "time": "141200"},
                    ],
                }],
                "deliveryInformation": {"signedBy": "A.ROOM", "location": "Front Door"},
            }]
        }
    }


def empty_payload(number: str = "1Z999AA10123456784") -> dict[str, Any]:
    """查无此号 / 空数据样例（HTTP 200 但无 shipment）。"""
    return {"trackResponse": {"shipment": []}}
