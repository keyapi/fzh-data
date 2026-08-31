# -*- coding: utf-8 -*-
from channel_account_sync.apply import already_has_owner, append_owners


def test_append_owners_is_idempotent():
    doc = {"owners": [{"user": "于彬", "from_date": "2025-11-01"}]}
    owners, added = append_owners(doc, [{"owner": "于彬", "from_date": "2025-11-01"}])
    assert added == []
    assert len(owners) == 1
    owners, added = append_owners(doc, [{"owner": "林俊彪", "from_date": "2026-07-01"}])
    assert already_has_owner(owners, "林俊彪", "2026-07-01")
    assert added[0]["owner"] == "林俊彪"
