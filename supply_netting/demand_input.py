"""Normalize demand event time without treating source worksheet labels as dates."""
from __future__ import annotations

import pandas as pd


def canonical_order_dates(frame, date_column='sale_date'):
    if date_column not in frame or 'month' not in frame:
        raise ValueError('order input requires event date and source month columns')
    result = frame.copy()
    result['source_month'] = result['month'].astype('string')
    event_date = pd.to_datetime(result[date_column], errors='coerce')
    result['month'] = event_date.dt.strftime('%Y%m').astype('string')
    result['demand_event_date'] = event_date.dt.date
    mismatch = result['month'].notna() & result['month'].ne(result['source_month']).fillna(False)
    return result, dict(event_date_column=date_column, source_month_role='worksheet_partition_only',
                        rows=len(result), month_mismatch_rows=int(mismatch.sum()),
                        unknown_event_dates=int(event_date.isna().sum()))
