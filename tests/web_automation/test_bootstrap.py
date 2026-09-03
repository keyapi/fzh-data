import sys
from pathlib import Path

from web_automation.scripts.bootstrap import plan_bootstrap, probe_modules


def test_default_bootstrap_never_installs_ocr():
    facts = {"env_ready": False, "chromium_ready": False, "ocr_ready": False}
    commands = plan_bootstrap(facts, with_ocr=False)
    flat = " ".join(" ".join(cmd) for cmd in commands)
    assert "--group ocr" not in flat
    assert "ddddocr" not in flat
    assert "onnxruntime" not in flat


def test_env_sync_happens_first_then_chromium():
    facts = {"env_ready": False, "chromium_ready": False, "ocr_ready": False}
    commands = plan_bootstrap(facts, with_ocr=False)
    assert commands[0] == ["uv", "sync", "--project", "web_automation"]
    assert commands[-1] == [
        "uv", "run", "--project", "web_automation",
        "python", "-m", "playwright", "install", "chromium",
    ]


def test_ready_env_returns_no_commands():
    facts = {"env_ready": True, "chromium_ready": True, "ocr_ready": True}
    commands = plan_bootstrap(facts, with_ocr=False)
    assert commands == []


def test_ocr_is_explicit_second_sync():
    facts = {"env_ready": True, "chromium_ready": True, "ocr_ready": False}
    commands = plan_bootstrap(facts, with_ocr=True)
    assert commands == [["uv", "sync", "--project", "web_automation", "--group", "ocr"]]


def test_probe_modules_asks_the_given_interpreter():
    py = Path(sys.executable)
    assert probe_modules(py, ("sys", "json")) is True
    assert probe_modules(py, ("definitely_not_installed_ddddocr_zzz",)) is False


def test_ocr_ready_assignment_does_not_use_parent_find_spec():
    text = Path(__file__).resolve().parents[2].joinpath(
        "web_automation", "scripts", "bootstrap.py"
    ).read_text(encoding="utf-8")
    assert 'facts["ocr_ready"] = _find_spec("ddddocr")' not in text
    assert "probe_modules" in text
