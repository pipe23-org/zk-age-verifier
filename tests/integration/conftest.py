from collections.abc import Iterator
from typing import Any, cast

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.conftest import ORIGIN, render_config
from zk_age_verifier.app import create_app
from zk_age_verifier.config import _default_circuit_cache_dir, load_config


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--transport") != "live":
        return
    skip_live = pytest.mark.skip(reason="in-process-only: cannot cross a socket")
    for item in items:
        if item.get_closest_marker("inprocess_only"):
            item.add_marker(skip_live)


@pytest.fixture(scope="session")
def origin() -> str:
    return ORIGIN


@pytest.fixture(scope="session")
def client(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[httpx.Client]:
    if request.config.getoption("--transport") == "live":
        base_url = request.config.getoption("--base-url")
        if not base_url:
            raise pytest.UsageError("--transport=live requires --base-url=<url>")
        with httpx.Client(base_url=str(base_url)) as live_client:
            yield live_client
        return
    config_file = tmp_path_factory.mktemp("config") / "config.toml"
    config_file.write_text(render_config(circuit_cache_dir=str(_default_circuit_cache_dir())))
    with TestClient(create_app(load_config(config_file))) as test_client:
        yield test_client


@pytest.fixture
def created_session(client: httpx.Client) -> dict[str, Any]:
    created = client.post("/sessions", json={"checks": ["age_over_18"]})
    assert created.status_code == 201
    return cast(dict[str, Any], created.json())
