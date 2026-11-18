from __future__ import annotations
import datetime as dt
import sys
from types import SimpleNamespace
import pytest
from openpyxl import load_workbook
from stock_alert.client import StockRow
from stock_alert.inbound import aggregate
from stock_alert.notify import build_low_stock_messages, build_inbound_messages, notify_low_stock, notify_inbound, DINGTALK_MAX_BYTES
from stock_alert.scan import scan, apply_names, mark_new

_CARD_ENV_KEYS = (
    'DINGTALK_CLIENT_ID', 'DINGTALK_CLIENT_SECRET', 'DINGTALK_ROBOT_CODE',
    'DINGTALK_OPEN_CONVERSATION_ID', 'DINGTALK_LOW_STOCK_TEMPLATE_ID',
    'DINGTALK_INBOUND_TEMPLATE_ID', 'DINGTALK_OPERATOR_ID',
)


@pytest.fixture(autouse=True)
def _no_card_env(monkeypatch):
    """默认走文本 ActionCard；图片/互动卡片用例再显式设置。"""
    for key in _CARD_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('STOCK_ALERT_CARD_MODE', 'text')


def _set_card_env(monkeypatch, mode='interactive', tmp_path=None):
    monkeypatch.setenv('STOCK_ALERT_CARD_MODE', mode)
    if tmp_path is not None:
        import stock_alert.notify as mod
        monkeypatch.setattr(mod, '_OUT_DIR', tmp_path)
    for key, value in {
        'DINGTALK_CLIENT_ID': 'cid',
        'DINGTALK_CLIENT_SECRET': 'secret',
        'DINGTALK_ROBOT_CODE': 'robot',
        'DINGTALK_OPEN_CONVERSATION_ID': 'conv==',
        'DINGTALK_LOW_STOCK_TEMPLATE_ID': 'low-tpl',
        'DINGTALK_INBOUND_TEMPLATE_ID': 'in-tpl',
    }.items():
        monkeypatch.setenv(key, value)

def result(n=2):
    r = scan({'美中-FZH-DANEEY': [StockRow('美中-FZH-DANEEY', f'S{i}', 1, 3) for i in range(n)], '美东-CENTRADE': []})
    apply_names(r, {f'S{i}': '产品甲' for i in range(n)})
    mark_new(r, {'美中-FZH-DANEEY': {f'S{i}': 1 for i in range(1, n)}, '美东-CENTRADE': {}})
    return r

def test_large_low_stock_is_one_compact_warehouse_card():
    messages = build_low_stock_messages(result(411), when=dt.date(2026, 11, 17), new_count=1)
    assert len(messages) == 1
    body = messages[0]
    assert '共 **411** 个 SKU' in body
    assert '### 美中-FZH-DANEEY' in body
    assert '### 美东-CENTRADE' in body
    assert '低库存：**411**' in body
    assert '今日新增：**1**' in body
    assert '在途合计：**1233**' in body
    assert '\n\n###' in body
    assert '第1/' not in body and 'S410' not in body
    assert '底部' in body
    assert len(body.encode()) < DINGTALK_MAX_BYTES

def fake_senders(monkeypatch, *, upload_fails=False, image_upload_fails=False):
    import stock_alert.notify as mod
    monkeypatch.setattr(mod, '_robot_path', lambda: '')
    monkeypatch.setattr(mod, '_resolve_creds', lambda: ('hook', 'secret'))
    posts = []
    uploads = []

    def upload(path):
        uploads.append(path)
        if upload_fails or (image_upload_fails and str(path).lower().endswith('.png')):
            raise OSError('upload down')
        return 'https://files.example/' + path.name

    def card(title, text, buttons, **kwargs):
        posts.append(('card', text, buttons, kwargs))
        return {'errcode': 0}

    def markdown(text, **kwargs):
        posts.append(('markdown', text, []))
        return {'errcode': 0}
    monkeypatch.setitem(sys.modules, 'upload_to_erpnext', SimpleNamespace(upload_file_to_erpnext=upload))
    monkeypatch.setitem(sys.modules, 'send_dingtalk', SimpleNamespace(send_action_card=card, send_markdown=markdown))
    return (posts, uploads)

def test_low_stock_single_card_contains_both_downloads(monkeypatch, tmp_path):
    posts, uploads = fake_senders(monkeypatch)
    resp = notify_low_stock(result(), out_xlsx=tmp_path / 'new.xlsx')
    assert resp['errcode'] == 0
    assert len(posts) == 1 and posts[0][0] == 'card'
    assert [b['title'] for b in posts[0][2]] == ['下载今日新增（1）', '下载全部低库存（2）']
    assert len(uploads) == 2
    counts = []
    for p in uploads:
        wb = load_workbook(p, read_only=True)
        counts.append(sum((ws.max_row - 1 for ws in wb)))
        wb.close()
    assert counts == [1, 2]

def test_no_new_stock_has_only_full_download(monkeypatch, tmp_path):
    posts, _ = fake_senders(monkeypatch)
    r = result()
    mark_new(r, {'美中-FZH-DANEEY': {'S0': 1, 'S1': 1}})
    assert notify_low_stock(r, out_xlsx=tmp_path / 'new.xlsx')['errcode'] == 0
    assert len(posts) == 1
    assert len(posts[0][2]) == 1
    assert '全部低库存' in posts[0][2][0]['title']

def test_upload_failure_still_sends_one_summary(monkeypatch, tmp_path):
    posts, _ = fake_senders(monkeypatch, upload_fails=True)
    resp = notify_low_stock(result(), out_xlsx=tmp_path / 'new.xlsx')
    assert resp['errcode'] != 0 and resp['file_errors']
    assert len(posts) == 1
    assert '失败' in posts[0][1]

def test_dry_run_makes_files_without_upload_or_post(monkeypatch, tmp_path):
    posts, uploads = fake_senders(monkeypatch)
    resp = notify_low_stock(result(), out_xlsx=tmp_path / 'new.xlsx', dry_run=True)
    assert resp['errcode'] == 0 and resp['dry_run']
    assert len(resp['messages']) == 1 and len(resp['files']) == 2
    assert not posts and (not uploads)

def test_file_write_failure_still_sends_exactly_one_summary(monkeypatch, tmp_path):
    import stock_alert.excel as excel
    posts, uploads = fake_senders(monkeypatch)

    def fail(*args, **kwargs):
        raise OSError('disk full')
    monkeypatch.setattr(excel, 'write_low_stock_workbook', fail)
    resp = notify_low_stock(result(), out_xlsx=tmp_path / 'new.xlsx')
    assert resp['errcode'] != 0 and resp['file_errors']
    assert len(posts) == 1 and (not uploads)
    assert '生成失败' in posts[0][1]

def test_zero_low_stock_sends_one_message_without_files(monkeypatch):
    posts, uploads = fake_senders(monkeypatch)
    r = scan({'W': [StockRow('W', 'A', 9, 0)]})
    assert notify_low_stock(r)['errcode'] == 0
    assert len(posts) == 1 and (not uploads)
    assert '无 SKU 可用库存低于阈值' in posts[0][1]

def inbound(n=1):
    return aggregate({'美中-FZH-DANEEY': [{'sku': f'A{i}', 'voucher_type': '02', 'available_increase': 45} for i in range(n)], '美东-CENTRADE': []}, names={f'A{i}': '产品甲' for i in range(n)}, day=dt.date(2026, 11, 16))

def test_inbound_has_real_paragraphs_for_name_sku_quantity_and_warehouses():
    messages = build_inbound_messages(inbound())
    assert len(messages) == 1
    text = messages[0]
    assert '\n\n### 美中-FZH-DANEEY' in text
    assert '**产品甲**\n\nSKU：A0\n\n入库：**45 个**' in text
    assert '\n\n### 美东-CENTRADE' in text and '无采购入库' in text

def test_large_inbound_is_one_card_with_full_download(monkeypatch, tmp_path):
    import stock_alert.notify as mod
    monkeypatch.setattr(mod, '_OUT_DIR', tmp_path)
    posts, uploads = fake_senders(monkeypatch)
    r = inbound(1000)
    messages = build_inbound_messages(r)
    assert len(messages) == 1 and len(messages[0].encode()) < DINGTALK_MAX_BYTES
    resp = notify_inbound(r)
    assert resp['errcode'] == 0
    assert len(posts) == 1 and posts[0][0] == 'card' and (len(posts[0][2]) == 1)
    wb = load_workbook(uploads[0], read_only=True)
    assert sum((ws.max_row - 1 for ws in wb)) == 1000
    wb.close()

def test_small_inbound_is_one_formatted_message(monkeypatch, tmp_path):
    import stock_alert.notify as mod
    monkeypatch.setattr(mod, '_OUT_DIR', tmp_path)
    posts, uploads = fake_senders(monkeypatch)
    assert notify_inbound(inbound())['errcode'] == 0
    assert len(posts) == 1 and posts[0][0] == 'card' and len(uploads) == 1
    wb = load_workbook(uploads[0], read_only=True)
    assert sum(ws.max_row - 1 for ws in wb) == 1
    wb.close()

def test_empty_inbound_still_one_clear_message():
    text = build_inbound_messages(aggregate({'W': []}, day=dt.date(2026, 11, 16)))
    assert len(text) == 1 and '昨日（2026-11-16）无采购入库' in text[0]


def test_low_stock_uses_interactive_card_when_configured(monkeypatch, tmp_path):
    _set_card_env(monkeypatch, tmp_path=tmp_path)
    posts, uploads = fake_senders(monkeypatch)
    import stock_alert.card as card_mod
    calls = []
    monkeypatch.setattr(card_mod, 'send_low_stock',
                        lambda *a, **k: calls.append(k) or {'errcode': 0, 'mode': 'interactive'})
    resp = notify_low_stock(result(), out_xlsx=tmp_path / 'new.xlsx')
    assert resp['mode'] == 'interactive'
    assert calls and not posts
    assert len(uploads) == 2  # 两个 Excel 仍照常上传


def test_low_stock_falls_back_to_actioncard_when_interactive_fails(monkeypatch, tmp_path):
    _set_card_env(monkeypatch, tmp_path=tmp_path)
    posts, _ = fake_senders(monkeypatch)
    import stock_alert.card as card_mod
    monkeypatch.setattr(card_mod, 'send_low_stock',
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError('boom')))
    resp = notify_low_stock(result(), out_xlsx=tmp_path / 'new.xlsx')
    assert resp['errcode'] == 0
    assert len(posts) == 1 and posts[0][0] == 'card'


def test_dry_run_includes_card_preview_when_configured(monkeypatch, tmp_path):
    _set_card_env(monkeypatch, tmp_path=tmp_path)
    resp = notify_low_stock(result(), out_xlsx=tmp_path / 'new.xlsx', dry_run=True)
    assert resp['card_preview']['title'] == '通途低库存提醒'
    assert resp['card_preview']['btn1Title']


def test_inbound_uses_interactive_card_when_configured(monkeypatch, tmp_path):
    _set_card_env(monkeypatch, tmp_path=tmp_path)
    import stock_alert.notify as mod
    import stock_alert.card as card_mod
    monkeypatch.setattr(mod, '_OUT_DIR', tmp_path)
    posts, _ = fake_senders(monkeypatch)
    monkeypatch.setattr(card_mod, 'send_inbound',
                        lambda *a, **k: {'errcode': 0, 'mode': 'interactive'})
    resp = notify_inbound(inbound())
    assert resp['mode'] == 'interactive' and not posts


def test_image_mode_sends_actioncard_with_image(monkeypatch, tmp_path):
    _set_card_env(monkeypatch, mode='image', tmp_path=tmp_path)
    posts, uploads = fake_senders(monkeypatch)
    resp = notify_low_stock(result(), out_xlsx=tmp_path / 'new.xlsx')
    assert resp['mode'] == 'image'
    assert len(posts) == 1 and posts[0][0] == 'card'
    assert '![卡片]' in posts[0][1]
    assert posts[0][3].get('single_jump') is False  # 防止点图片直接下载
    assert any(str(p).lower().endswith('.png') for p in uploads)


def test_image_upload_failure_falls_back_to_text(monkeypatch, tmp_path):
    _set_card_env(monkeypatch, mode='image', tmp_path=tmp_path)
    posts, uploads = fake_senders(monkeypatch, image_upload_fails=True)
    resp = notify_low_stock(result(), out_xlsx=tmp_path / 'new.xlsx')
    assert resp['errcode'] == 0
    assert len(posts) == 1 and posts[0][0] == 'card'
    assert '![卡片]' not in posts[0][1]


def test_image_mode_inbound(monkeypatch, tmp_path):
    _set_card_env(monkeypatch, mode='image', tmp_path=tmp_path)
    posts, uploads = fake_senders(monkeypatch)
    resp = notify_inbound(inbound())
    assert resp['mode'] == 'image'
    assert '![卡片]' in posts[0][1]
    assert posts[0][3].get('single_jump') is False  # 单按钮也不让整卡可点
    assert any(str(p).lower().endswith('.png') for p in uploads)


def test_inbound_label_and_empty_message():
    r = aggregate({'W': []}, day=dt.date(2026, 11, 18),
                  label='10:00–14:00 新增', as_of='14:00')
    text = build_inbound_messages(r)[0]
    assert '10:00–14:00 新增' in text
    assert '本次无采购入库' in text


def test_inbound_filename_includes_window_time(monkeypatch, tmp_path):
    import stock_alert.notify as mod
    monkeypatch.setattr(mod, '_OUT_DIR', tmp_path)
    posts, uploads = fake_senders(monkeypatch)
    r = aggregate({'美中-FZH-DANEEY': [{'sku': 'A', 'voucher_type': '02', 'available_increase': 45}]},
                  names={'A': '产品甲'}, day=dt.date(2026, 11, 18),
                  label='10:00–14:00 新增', as_of='14:00')
    assert notify_inbound(r)['errcode'] == 0
    assert any('_1400' in str(p) for p in uploads)

def test_failure_diagnostic_kept():
    from stock_alert.notify import failure_body
    assert '1.2.3.4' in failure_body('524', egress_ip='1.2.3.4')
    assert failure_body('boom') == 'boom'
