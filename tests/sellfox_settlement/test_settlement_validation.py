import importlib

import pytest


def module():
    return importlib.import_module('sellfox_settlement.settlement_validation')


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)

    def signed_post(self, path, body):
        return next(self.responses)


def test_pagination_keeps_every_row():
    client = FakeClient([{'totalSize':3,'rows':[{'id':1},{'id':2}]},
                         {'totalSize':3,'rows':[{'id':3}]}])
    assert len(module().fetch_complete(client, '/read', {'pageSize':'2'})) == 3


def test_real_group_response_schema_is_supported():
    client = FakeClient([{'totalSize':'1','groupVoList':[{'id':1}]}])
    assert module().fetch_complete(client, '/read', {}) == [{'id':1}]


def test_incomplete_page_is_rejected():
    client = FakeClient([{'totalSize':3,'rows':[{'id':1},{'id':2}]},
                         {'totalSize':3,'rows':[]}])
    with pytest.raises(ValueError, match='incomplete'):
        module().fetch_complete(client, '/read', {'pageSize':'2'})


def test_missing_response_rows_are_not_silent_zero():
    with pytest.raises(ValueError):
        module().fetch_complete(FakeClient([{'message':'unexpected'}]), '/read', {})


def test_real_explicit_zero_detail_response_allows_null_list():
    response = {'detailPageVoList': None, 'pageNo': 0, 'pageSize': 0,
                'totalPage': 0, 'totalSize': 0}
    assert module().fetch_complete(FakeClient([response]), '/read', {}) == []


def test_null_detail_list_without_explicit_zero_total_is_rejected():
    with pytest.raises(ValueError, match='missing response rows'):
        module().fetch_complete(FakeClient([{'detailPageVoList': None}]), '/read', {})


def test_scope_uses_seller_and_marketplace_together():
    scopes=[{'sellerId':'SYNTHETIC','marketplaceId':'SYNTHETIC-US'}]
    rows=[{'sellerId':'SYNTHETIC','marketplaceId':'SYNTHETIC-US'},
          {'sellerId':'SYNTHETIC','marketplaceId':'SYNTHETIC-DE'}]
    matched, outside = module().scope_rows(rows, scopes)
    assert len(matched) == 1
    assert len(outside) == 1


def test_bridge_keeps_beginning_and_ending_signed_balances():
    row = dict(beginningBalance='10',endingBalance='-6',accountIncome='2',
               accountRefund='-1',accountExpenditure='-3',accountNetIncome='2')
    assert module().bridge_residual(row) == 0


def test_repeated_pages_cannot_count_as_complete():
    client = FakeClient([{'totalSize':4,'rows':[{'id':1},{'id':2}]},
                         {'totalSize':4,'rows':[{'id':1},{'id':2}]}])
    with pytest.raises(ValueError, match='repeated'):
        module().fetch_complete(client, '/read', {'pageSize':'2'})


def test_overlapping_pages_are_rejected():
    client = FakeClient([{'totalSize':4,'rows':[{'id':1},{'id':2}]},
                         {'totalSize':4,'rows':[{'id':2},{'id':3}]}])
    with pytest.raises(ValueError, match='overlap'):
        module().fetch_complete(client, '/read', {'pageSize':'2'})


def test_empty_scope_is_rejected():
    with pytest.raises(ValueError, match='empty'):
        module().validate_scope([])


def test_currency_map_basename_matches_absolute_windows_source():
    scope = [{'id': 'us-shop', 'sellerId': 'seller', 'marketplaceId': 'us-site',
              'file': r'D:\private\bills\account.csv'}]
    result = module().native_currency_scopes(scope, {'account.csv': {'currency': 'USD', 'kind': 'csv'}})
    assert result == {'USD': scope}


def test_conflicting_full_path_and_basename_currency_is_rejected():
    scope = [{'id': 'us-shop', 'sellerId': 'seller', 'marketplaceId': 'us-site',
              'file': r'D:\private\bills\account.csv'}]
    with pytest.raises(ValueError, match='conflicting currency'):
        module().native_currency_scopes(scope, {
            scope[0]['file']: {'currency': 'USD'}, 'account.csv': {'currency': 'EUR'}})


def test_missing_currency_map_blocks_before_api_client_creation(tmp_path, monkeypatch):
    import sys
    monkeypatch.setattr(sys, 'argv', ['probe', '--scope', str(tmp_path/'not-opened.json'),
        '--data-root', str(tmp_path), '--out', str(tmp_path/'out'), '--include-details'])
    with pytest.raises(SystemExit) as error:
        module().main()
    assert error.value.code == 2


def test_native_details_limits_request_and_filters_returned_site(tmp_path):
    scope = [{'id': 'us-shop', 'sellerId': 'seller', 'marketplaceId': 'us-site', 'file': 'us.csv'},
             {'id': 'de-shop', 'sellerId': 'seller', 'marketplaceId': 'de-site', 'file': 'de.csv'}]
    class Recorder:
        def __init__(self):
            self.calls = []

        def signed_post(self, path, body):
            self.calls.append(body)
            return {'totalSize': 2, 'rows': [
                {'id': 'us-row', 'sellerId': 'seller', 'marketplaceId': 'us-site', 'currency': body['currency'], 'amount': '0'},
                {'id': 'de-row', 'sellerId': 'seller', 'marketplaceId': 'de-site', 'currency': body['currency'], 'amount': '0'}]}
    client = Recorder()
    details, errors = module().fetch_native_details(client, module().native_currency_scopes(scope,
        {'us.csv': {'currency': 'USD'}, 'de.csv': {'currency': 'EUR'}}), '2026-08-01', '2026-08-31', tmp_path/'out')
    assert not errors
    assert all(result['scoped_rows'] == 1 and result['outside_scope'] == 1 for result in details)
    by_currency = {call['currency']: call for call in client.calls}
    assert by_currency['USD']['shopIds'] == ['us-shop']
    assert by_currency['EUR']['shopIds'] == ['de-shop']
