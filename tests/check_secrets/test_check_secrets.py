"""Tests for scripts/check_secrets.py — 明文凭证扫描。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location("fzh_check_secrets", ROOT / "scripts" / "check_secrets.py")
assert _SPEC and _SPEC.loader
check_secrets = importlib.util.module_from_spec(_SPEC)
# `from __future__ import annotations` + @dataclass 需要模块能在 sys.modules 里被解析
sys.modules[_SPEC.name] = check_secrets
_SPEC.loader.exec_module(check_secrets)

scan_text = check_secrets.scan_text


# 断言里不直接写完整字面量，避免扫描器扫到本文件自己（或用 --include-tests 时误报）
BAD_PASSWORD = "Fangzhou" + "hui@1023"


def test_flags_literal_password_assignment():
    findings = scan_text(f'PWD = "{BAD_PASSWORD}"\n', "app.py")
    assert len(findings) == 1
    assert findings[0].kind == "literal"
    assert BAD_PASSWORD not in str(findings[0])  # 输出要脱敏


def test_flags_literal_client_secret():
    findings = scan_text('CLIENT_SECRET = "aBcDeFgHiJkLmNoP"\n', "cfg.py")
    assert [f.kind for f in findings] == ["literal"]


def test_ignores_env_indirection():
    for line in (
        'password = os.getenv("NAS_SSH_PASSWORD", "")\n',
        'PASS = env["NAS_SSH_PASSWORD"]\n',
        'api_key = settings.get("api_key")\n',
        'token = load_env()["CF_API_TOKEN"]\n',
    ):
        assert scan_text(line, "cfg.py") == [], line


def test_ignores_placeholders_and_examples():
    for line in (
        'DINGTALK_CLIENT_SECRET=replace_me\n',
        'API_KEY = "your_api_key"\n',
        'TOKEN = "xxxxxxxx"\n',
        'SECRET = "<fill-me>"\n',
        'PASSWORD = "${NAS_SSH_PASSWORD}"\n',
    ):
        assert scan_text(line, "cfg.py") == [], line


def test_env_var_name_as_value_is_not_a_literal():
    findings = scan_text('DEFAULT_PASSWORD = NAS_SSH_PASSWORD\n', "cfg.py")
    assert findings == []


def test_non_secret_keys_are_ignored():
    assert scan_text('NAS_SSH_USER = "someuser"\n', "cfg.py") == []
    assert scan_text('HOST = "192.168.1.5"\n', "cfg.py") == []


def test_flags_private_key_block():
    findings = scan_text("-----BEGIN RSA PRIVATE KEY-----\n", "k.py")
    assert [f.kind for f in findings] == ["private-key"]


def test_flags_sshpass_literal():
    findings = scan_text("sshpass -p hunter2xyz ssh user@host\n", "deploy.sh")
    assert [f.kind for f in findings] == ["sshpass"]


def test_skips_test_paths_when_asked():
    line = 'SECRET = "aBcDeFgHiJkLmNoP"\n'
    assert scan_text(line, "tests/test_x.py", scan_tests=False) == []
    assert scan_text(line, "tests/test_x.py", scan_tests=True) != []


def test_flags_getenv_default_literal():
    """os.getenv("SPS_PASSWORD", "明文") —— 默认值本身就是漏洞。"""
    line = f"    'password': os.getenv('SPS_PASSWORD', '{BAD_PASSWORD}'),\n"
    findings = scan_text(line, "config.py")
    assert "env-default" in [f.kind for f in findings]


def test_non_secret_getenv_default_is_ignored():
    """非密钥类 key 的字面默认值（URL/路径/端口）不该报。"""
    for line in (
        'HOST = os.getenv("HOST", "https://api.example.com")\n',
        'DB_PATH = os.getenv("PROXY_DB_PATH", "/data/x/y.db")\n',
        'PORT = os.getenv("PORT", "8080")\n',
    ):
        assert scan_text(line, "cfg.py") == [], line


def test_flags_dict_style_literal():
    findings = scan_text(f"'password': '{BAD_PASSWORD}',\n", "cfg.py")
    assert [f.kind for f in findings] == ["literal"]


def test_flags_markdown_backtick_value():
    findings = scan_text(f"- Password: `{BAD_PASSWORD}` (见 .env)\n", "note.md", scan_tests=True)
    assert [f.kind for f in findings] == ["md-literal"]
    assert BAD_PASSWORD not in str(findings[0])


def test_protocol_constants_are_ignored():
    for line in ('token_type = "Bearer"\n', 'token_type = "Bearer",\n'):
        assert scan_text(line, "oidc.py") == [], line


def test_scans_real_tree_for_a_planted_file(tmp_path):
    bad = tmp_path / "planted.py"
    bad.write_text(f'PASSWORD = "{BAD_PASSWORD}"\n', encoding="utf-8")
    (tmp_path / "clean.py").write_text('PASSWORD = os.getenv("PASSWORD")\n', encoding="utf-8")

    found = []
    for p in check_secrets.iter_files(tmp_path, include_tests=False):
        found.extend(scan_text(p.read_text(encoding="utf-8"), str(p.name)))

    assert [f.path for f in found] == ["planted.py"]
