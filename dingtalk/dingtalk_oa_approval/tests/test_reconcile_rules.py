from nas_upload_api21 import dest_bucket
from july_amz_txt_vs_sellfox import shop_key
from person_folders import nas_person_folder
from sellfox_amz_settlements import norm_brand


JUL = "账期20260704-20260803"
AUG = "账期20260804-20260903"


def test_brand_aliases_rucener_and_novelledo():
    assert norm_brand("北京如森-Rucener-US") == "ROSOON"
    assert norm_brand("AMZRosoonIT") == "ROSOON"
    assert norm_brand("云途汇德-Novelledo-US") == "YTHD"
    assert norm_brand("AMZYTHDUS") == "YTHD"


def test_shop_key_chinese_storefront():
    assert shop_key("北京如森-Rucener-IT", "IT")[0] == "ROSOON"
    assert shop_key("云途汇德-Novelledo-US", "US")[0] == "YTHD"


def test_dest_bucket_closed_june_window():
    rec = {"createTime": "2026-07-03 10:00:00", "period_months": ["2026-07"]}
    assert dest_bucket(rec, "AMZDANEEYES-2026-07-01.txt") == ""


def test_dest_bucket_july_period():
    rec = {"createTime": "2026-08-06 17:17:00", "period_months": ["2026-07"]}
    assert dest_bucket(rec, "AMZJohnaUS-7.13.txt") == JUL


def test_dest_bucket_september_stays_out():
    rec = {"createTime": "2026-09-05 09:00:00", "period_months": ["2026-09"]}
    assert dest_bucket(rec, "AMZFooUS-2026-09-01.txt") == ""


def test_unknown_originator_is_identity():
    assert nas_person_folder("UnknownOriginator") == "UnknownOriginator"
    assert nas_person_folder("") == ""
