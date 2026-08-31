# -*- coding: utf-8 -*-
"""Channel Account naming: Sheet → EN, aliases, Amazon country sites."""
from __future__ import annotations

import re

SHEET_TO_EN = {"Illiosenergy": "ILLIOSPL"}
SKIP_CREATE = {"null"}
ILLIOS_CHANNEL = "Illiosenergy"
ILLIOS_CODE = "ILLIOS"
AMAZON_FORBIDDEN_REGIONS = frozenset({"EUR", "EU"})
AMAZON_EU_COUNTRY_SITES = ("DE", "ES", "FR", "IT", "UK", "PL", "NL", "BE", "SE")
KNOWN_REGIONS = frozenset(
    {
        "AE",
        "AT",
        "AU",
        "BE",
        "BG",
        "BR",
        "CA",
        "CZ",
        "DE",
        "DY",
        "EG",
        "ES",
        "EU",
        "FR",
        "HU",
        "IE",
        "IN",
        "IT",
        "JP",
        "MX",
        "NL",
        "PL",
        "PT",
        "RO",
        "SA",
        "SE",
        "SG",
        "SK",
        "TR",
        "UK",
        "US",
    }
)


def sheet_to_en_name(sheet_name: str) -> str:
    name = (sheet_name or "").strip()
    return SHEET_TO_EN.get(name, name)


def parse_aliases(canonical: str, alias_cell: str) -> list[str]:
    raw = (alias_cell or "").replace("，", ",")
    parts = [re.sub(r"\s+", " ", x).strip() for x in raw.split(",")]
    out, seen = [], set()
    for a in [canonical] + parts:
        if not a or a in seen:
            continue
        seen.add(a)
        out.append(a)
    return out


def reject_amazon_euro(en_name: str, channel: str, region: str) -> str | None:
    """Return an error string if this would create an Amazon EUR/EU account."""
    ch = (channel or "").strip()
    rg = (region or "").strip().upper()
    name = (en_name or "").strip()
    if ch == "Amazon" and rg in AMAZON_FORBIDDEN_REGIONS:
        return f"Amazon must be country-level; refuse {name} region={rg}"
    if name.upper().endswith("EUR") and ch == "Amazon":
        return f"Amazon must be country-level; refuse {name}"
    return None


def split_account(en_name: str, channel: str, channel_code: str) -> tuple[str | None, str, int]:
    code = (channel_code or "").strip()
    if not code or not en_name.startswith(code):
        raise ValueError(f"cannot split {en_name} with channel {channel} code {code}")
    rest = en_name[len(code) :]
    if channel == "Amazon" and rest.upper().endswith(("EUR", "EU")):
        region_guess = "EUR" if rest.upper().endswith("EUR") else "EU"
        raise ValueError(reject_amazon_euro(en_name, channel, region_guess))
    region = rest[-2:]
    if region not in KNOWN_REGIONS:
        raise ValueError(f"unknown region in {en_name}: {region}")
    err = reject_amazon_euro(en_name, channel, region)
    if err:
        raise ValueError(err)
    account_code = rest[:-2] or None
    return account_code, region, 0 if account_code else 1
