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
