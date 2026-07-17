import json
import logging

import pytest
import structlog

from zk_age_verifier.log import configure_logging


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


def test_stdlib_logs_join_the_stream(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    configure_logging()
    logging.getLogger("uvicorn.error").info("server started")
    record = json.loads(capsys.readouterr().err)
    assert record["event"] == "server started"
    assert record["level"] == "info"
