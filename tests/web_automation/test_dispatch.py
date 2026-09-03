from web_automation.scripts.dispatch import DispatchResult, RunResult, dispatch


class FakeRunner:
    def __init__(self, results=None):
        self.calls = []
        self.results = list(results or [RunResult(0, None)])

    def __call__(self, command, with_ocr=False):
        self.calls.append(command)
        return self.results.pop(0)


def test_write_task_blocks_without_scope():
    fake_runner = FakeRunner()
    result = dispatch(
        "sellfox.other-outbound.import",
        check=False,
        with_ocr=False,
        confirm_scope=None,
        passthrough=[],
        runner=fake_runner,
    )
    assert result.status == "NEED_USER_CONFIRMATION"
    assert fake_runner.calls == []


def test_write_task_runs_with_explicit_scope():
    fake_runner = FakeRunner()
    result = dispatch(
        "sellfox.other-outbound.import",
        check=False,
        with_ocr=False,
        confirm_scope="test001-white only",
        passthrough=["input.xlsx"],
        runner=fake_runner,
    )
    assert result.status == "READY"
    assert "sellfox_import_other_outbound.py" in " ".join(fake_runner.calls[-1])


def test_generic_web_returns_agent_instruction():
    fake_runner = FakeRunner()
    result = dispatch(
        "web.generic.explore",
        check=False,
        with_ocr=False,
        confirm_scope=None,
        passthrough=[],
        runner=fake_runner,
    )
    assert result.status == "READY"
    assert result.channel == "mcp"
    assert fake_runner.calls == []


def test_blocked_api_error_does_not_execute_browser():
    fake_runner = FakeRunner([RunResult(1, "AUTH_FAILED")])
    result = dispatch(
        "sellfox.stock.export",
        check=False,
        with_ocr=False,
        confirm_scope=None,
        passthrough=[],
        runner=fake_runner,
    )
    assert result.status == "BLOCKED"
    assert len(fake_runner.calls) == 1


def test_api_unclassified_failure_does_not_fall_back():
    fake_runner = FakeRunner([RunResult(1, None)])
    result = dispatch(
        "sellfox.stock.export",
        check=False,
        with_ocr=False,
        confirm_scope=None,
        passthrough=[],
        runner=fake_runner,
    )
    assert result.status == "BLOCKED"
    assert result.channel == "api"
    assert len(fake_runner.calls) == 1


def test_api_unclassified_named_code_does_not_fall_back():
    fake_runner = FakeRunner([RunResult(1, "UNCLASSIFIED_FAILURE")])
    result = dispatch(
        "sellfox.stock.export",
        check=False,
        with_ocr=False,
        confirm_scope=None,
        passthrough=[],
        runner=fake_runner,
    )
    assert result.status == "BLOCKED"
    assert len(fake_runner.calls) == 1


def test_api_endpoint_missing_falls_back_to_browser():
    fake_runner = FakeRunner([RunResult(1, "ENDPOINT_MISSING"), RunResult(0, None)])
    result = dispatch(
        "sellfox.stock.export",
        check=False,
        with_ocr=False,
        confirm_scope=None,
        passthrough=[],
        runner=fake_runner,
    )
    assert result.status == "READY"
    assert result.channel == "browser"
    assert len(fake_runner.calls) == 2


_ENV_READY = {
    "uv_present": True,
    "env_ready": True,
    "chromium_ready": True,
    "ocr_ready": False,
}


def test_check_reports_need_browser_when_child_env_missing():
    fake_runner = FakeRunner()
    result = dispatch(
        "tongtu.stock.export",
        check=True,
        with_ocr=False,
        confirm_scope=None,
        passthrough=[],
        runner=fake_runner,
        env_facts={"uv_present": True, "env_ready": False, "chromium_ready": False, "ocr_ready": False},
        profile_present=True,
    )
    assert result.status == "NEED_BROWSER"
    assert fake_runner.calls == []


def test_check_reports_need_ocr_when_requested_and_missing():
    fake_runner = FakeRunner()
    result = dispatch(
        "tongtu.stock.export",
        check=True,
        with_ocr=True,
        confirm_scope=None,
        passthrough=[],
        runner=fake_runner,
        env_facts=_ENV_READY,
        profile_present=True,
    )
    assert result.status == "NEED_OCR"
    assert fake_runner.calls == []


def test_check_reports_need_login_when_profile_missing():
    fake_runner = FakeRunner()
    result = dispatch(
        "sellfox.stock.export",
        check=True,
        with_ocr=False,
        confirm_scope=None,
        passthrough=[],
        runner=fake_runner,
        env_facts=_ENV_READY,
        profile_present=False,
    )
    assert result.status == "NEED_LOGIN"
    assert fake_runner.calls == []


def test_check_ready_when_env_and_profile_ok():
    fake_runner = FakeRunner()
    result = dispatch(
        "tongtu.stock.export",
        check=True,
        with_ocr=False,
        confirm_scope=None,
        passthrough=[],
        runner=fake_runner,
        env_facts=_ENV_READY,
        profile_present=True,
    )
    assert result.status == "READY"
    assert fake_runner.calls == []
    assert "tongtu_auto_export.py" in " ".join(result.command)
