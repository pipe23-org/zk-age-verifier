import json
import logging
from collections.abc import Iterator

import pytest
import structlog

from zk_age_verifier.config import ConfigError
from zk_age_verifier.log import configure_logging


@pytest.fixture(autouse=True)
def _unset_log_level(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    yield


def test_json_by_default(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    configure_logging()
    structlog.get_logger().info("something-happened", answer=42)
    record = json.loads(capsys.readouterr().err)
    assert record["event"] == "something-happened"
    assert record["answer"] == 42
    assert record["level"] == "info"


def test_console_renderer_in_dev(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOG_FORMAT", "console")
    configure_logging()
    structlog.get_logger().info("something-happened", answer=42)
    err = capsys.readouterr().err
    assert "something-happened" in err
    with pytest.raises(json.JSONDecodeError):
        json.loads(err)


def test_json_carries_the_logged_exception_traceback(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    configure_logging()
    try:
        raise ValueError("boom")
    except ValueError:
        structlog.get_logger().exception("engine-error")
    record = json.loads(capsys.readouterr().err)
    assert record["event"] == "engine-error"
    assert "ValueError: boom" in record["exception"]
    assert "exc_info" not in record


def test_stdlib_logs_join_the_stream(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    configure_logging()
    logging.getLogger("uvicorn.error").info("server started")
    record = json.loads(capsys.readouterr().err)
    assert record["event"] == "server started"
    assert record["level"] == "info"


def test_debug_dropped_by_default(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    configure_logging()
    structlog.get_logger().debug("something-happened")
    assert capsys.readouterr().err == ""


def test_debug_emitted_at_log_level_debug(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    monkeypatch.setenv("LOG_LEVEL", "debug")
    configure_logging()
    structlog.get_logger().debug("something-happened", answer=42)
    record = json.loads(capsys.readouterr().err)
    assert record["event"] == "something-happened"
    assert record["level"] == "debug"


def test_info_dropped_at_log_level_warning(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    monkeypatch.setenv("LOG_LEVEL", "warning")
    configure_logging()
    structlog.get_logger().info("something-happened")
    assert capsys.readouterr().err == ""


def test_log_level_is_case_insensitive(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    monkeypatch.setenv("LOG_LEVEL", "DeBuG")
    configure_logging()
    structlog.get_logger().debug("something-happened")
    record = json.loads(capsys.readouterr().err)
    assert record["level"] == "debug"


def test_unknown_log_level_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "verbose")
    with pytest.raises(ConfigError, match="LOG_LEVEL is 'verbose'; accepted values are "):
        configure_logging()
