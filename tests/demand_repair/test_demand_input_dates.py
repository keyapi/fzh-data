import pandas as pd

from supply_netting.demand_input import canonical_order_dates


def test_source_sheet_month_is_not_the_sales_event_month():
    source = pd.DataFrame({'month':['202301','202610'],
                           'sale_date':['2022-12-29','2026-10-02']})
    fixed, report = canonical_order_dates(source)
    assert fixed['source_month'].tolist() == ['202301','202610']
    assert fixed['month'].tolist() == ['202212','202610']
    assert report['month_mismatch_rows'] == 1
    pd.testing.assert_frame_equal(source,pd.DataFrame({'month':['202301','202610'],
                                                       'sale_date':['2022-12-29','2026-10-02']}))


def test_invalid_sale_date_remains_unknown_not_source_month_fallback():
    fixed, report = canonical_order_dates(pd.DataFrame({'month':['202601'], 'sale_date':['bad']}))
    assert pd.isna(fixed['month'].iloc[0])
    assert report['unknown_event_dates'] == 1
