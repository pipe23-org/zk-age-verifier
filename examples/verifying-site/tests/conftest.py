from collections.abc import Iterator
from dataclasses import dataclass, field

import httpx
import pytest
from fastapi.testclient import TestClient

from verifying_site.app import create_app

VERIFIER_URL = "http://verifier:8000"


@pytest.fixture(autouse=True)
def _verifier_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_VERIFIER_URL", VERIFIER_URL)


@dataclass
class Verifier:
    """A stub verifier: records forwarded requests, returns a settable canned response."""

    requests: list[httpx.Request] = field(default_factory=list)
    response: httpx.Response = field(default_factory=lambda: httpx.Response(201, json={"ok": True}))

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.response


@pytest.fixture
def verifier() -> Verifier:
    return Verifier()


@pytest.fixture
def client(verifier: Verifier) -> Iterator[TestClient]:
    mock = httpx.AsyncClient(transport=httpx.MockTransport(verifier.handler))
    with TestClient(create_app(client=mock)) as test_client:
        yield test_client
