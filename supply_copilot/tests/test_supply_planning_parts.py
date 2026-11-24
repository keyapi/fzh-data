"""Native Page extraction uses generated synthetic content only."""
import json
from pathlib import Path

import pytest

from supply_copilot.en_page.supply_planning_static import split_parts


def test_split_parts_preserves_data_and_separates_executable_script():
    parts = split_parts("<html><head><style>:root{color:red}</style></head><body>"
                        "<main>测试</main><script type='application/json' id='supply-workbench-data'>{}</script>"
                        "<script>document.getElementById('test');</script></body></html>")
    assert parts['css'] == ':root{color:red}'
    assert parts['js'] == "document.getElementById('test');"
    assert "application/json" in parts['html']
    assert "<script>" not in parts['html']


def test_split_parts_rejects_missing_or_multiple_script_blocks():
    with pytest.raises(ValueError):
        split_parts('<html><body>not a workbench</body></html>')


def test_get_parts_propagates_existing_authorization_failure(monkeypatch):
    from supply_copilot.en_page import supply_planning_static

    def denied():
        raise PermissionError('System Manager required')

    monkeypatch.setattr(supply_planning_static, 'get_html', denied)
    with pytest.raises(PermissionError):
        supply_planning_static.get_parts()


def test_native_page_has_canonical_route_and_shadow_boundary():
    root = Path(__file__).parents[1] / 'en_page/supply_planning'
    fixture = json.loads((root / 'supply_planning.json').read_text(encoding='utf-8'))
    assert fixture['name'] == fixture['page_name'] == 'supply-planning'
    assert fixture['title'] == '供应链计划工作台'
    assert fixture['standard'] == 'Yes' and fixture['module'] == 'key_test'
    js = (root / 'supply_planning.js').read_text(encoding='utf-8')
    assert 'attachShadow' in js and 'documentProxy' in js
    assert "createElement('iframe')" not in js
    assert '.get_parts' in js
