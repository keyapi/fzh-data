import base64
import hashlib
import json

from demand_collaboration.local_static import build

BASE = (
    "<!doctype html><html lang='zh-CN'><head><title>需求协同 · 运营工作台</title></head>"
    "<body><div id='identity'></div><script>'use strict';async function load(){};load();</script>"
    "</body></html>"
)


def _hash(text):
    return base64.b64encode(hashlib.sha256(text.encode()).digest()).decode()


def test_build_injects_banner_state_transport_and_csp():
    state = {"actor": "x", "role": "operator", "baseline": {"rows": []},
             "proposals": [], "publications": [], "recommendation": None}
    doc = build(BASE, state)
    assert 'id="demo-bar"' in doc
    assert 'id="demo-state"' in doc
    assert 'DEMAND_TRANSPORT' in doc
    assert 'Content-Security-Policy' in doc
    assert "connect-src 'none'" in doc
    assert 'src=' not in doc.split('<body>', 1)[1].split('<script', 1)[0]
    payload = doc.split('id="demo-state">', 1)[1].split('</script>', 1)[0]
    assert json.loads(payload)["role"] == "operator"


def test_build_escapes_closing_script_in_state():
    state = {"x": "</script><script>alert(1)</script>"}
    doc = build(BASE, state)
    payload = doc.split('id="demo-state">', 1)[1].split('</script>', 1)[0]
    assert '</script>' not in payload
    assert '</script>' in doc  # the real closing tag still exists


def test_csp_hashes_match_inline_scripts():
    state = {"x": 1}
    doc = build(BASE, state)
    csp = doc.split('Content-Security-Policy" content="', 1)[1].split('"', 1)[0]
    scripts = []
    rest = doc.split('<body>', 1)[1]
    while '<script>' in rest:
        rest = rest.split('<script>', 1)[1]
        body, rest = rest.split('</script>', 1)
        scripts.append(body)
    assert len(scripts) == 2
    for body in scripts:
        assert f"'sha256-{_hash(body)}'" in csp


def test_no_external_script_or_link():
    doc = build(BASE, {"x": 1})
    assert '<script src=' not in doc
    assert '<link' not in doc
    assert 'fetch(' not in doc.split('<script>')[-2]
