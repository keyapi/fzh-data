from channel_account_sync.plan import build_plan


def test_skip_null_and_split_illios():
    sheet = {
        "header": ["渠道", "渠道账号", "渠道账号别名", "运营人员202511", "运营人员202608"],
        "rows": [
            ["渠道", "渠道账号", "渠道账号别名", "运营人员202511", "运营人员202608"],
            ["其它渠道", "null", "", "", ""],
            ["Illiosenergy", "Illiosenergy", "Illiosenergy", "波兰", "波兰"],
        ],
    }
    en = {"accounts": []}
    plan = build_plan(sheet, en)
    assert plan["skip"] == [{"sheet": "null", "reason": "skip_create"}]
    assert plan["new_accounts"][0]["en_name"] == "ILLIOSPL"
    assert plan["new_accounts"][0]["owners"][0]["owner"] == "波兰"


def test_amazon_eur_is_forbidden():
    sheet = {
        "header": ["渠道", "渠道账号", "渠道账号别名", "运营人员202608"],
        "rows": [
            ["渠道", "渠道账号", "渠道账号别名", "运营人员202608"],
            ["Amazon", "AMZFZHSXEUR", "FZHSX欧洲", "陈立彬"],
        ],
    }
    plan = build_plan(sheet, {"accounts": []})
    assert plan["forbidden"]
    assert plan["n_new_accounts"] == 0


def test_change_only_insert_against_existing_en():
    sheet = {
        "header": ["渠道", "渠道账号", "渠道账号别名", "运营人员202511", "运营人员202607", "运营人员202608"],
        "rows": [
            ["渠道", "渠道账号", "渠道账号别名", "运营人员202511", "运营人员202607", "运营人员202608"],
            ["Amazon", "AMZFZHSXUS", "FZHSXUS", "于彬", "林俊彪", "林俊彪"],
        ],
    }
    en = {
        "accounts": [
            {
                "name": "AMZFZHSXUS",
                "aliases": [{"account_alias": "AMZFZHSXUS"}],
                "owners": [{"user": "于彬", "from_date": "2025-11-01"}],
            }
        ]
    }
    plan = build_plan(sheet, en)
    assert plan["insert_existing"][0]["needed"] == [
        {"from_ym": "202607", "from_date": "2026-07-01", "owner": "林俊彪"}
    ]
    assert plan["alias_gaps"][0]["add"] == ["FZHSXUS"]
