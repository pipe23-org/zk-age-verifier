"""The site backend: serve the page, open verifier sessions, forward wallet responses.

The consumer backend of the default DC-path topology. ``POST /av/session`` opens a session
at the verifier's ``POST /sessions`` with the backend's own ``checks``; the client request
body is ignored, so the browser cannot choose the check vocabulary or set
``expected_origin``. ``POST /av/response`` forwards the request body unchanged to
``POST /sessions/{session_id}/presentation``; the body is ciphertext the backend cannot
read, and ``session_id`` arrives as a query parameter and is used only to build the
verifier URL. The verifier's status, content type, and body pass back untouched, so
problem+json errors reach the page as issued.
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).parent / "static"

DEFAULT_VERIFIER_URL = "http://127.0.0.1:8000"
"""Verifier base URL used when ``DEMO_VERIFIER_URL`` is unset (loopback beside the backend)."""

SESSION_REQUEST = {"checks": ["age_over_18"]}
"""The session-open body. ``checks`` is the consumer's policy and is chosen here, server-side;
client input never reaches ``POST /sessions``."""


def verifier_base_url() -> str:
    """Return the verifier base URL from ``DEMO_VERIFIER_URL``, trailing slash stripped."""
    return os.environ.get("DEMO_VERIFIER_URL", DEFAULT_VERIFIER_URL).rstrip("/")


def create_app(client: httpx.AsyncClient | None = None) -> FastAPI:
    """Build the application.

    Args:
        client: An httpx client to forward with. When omitted, the app opens and closes
            its own for the process lifetime; tests pass one backed by a mock transport.

    Returns:
        The configured application.
    """
    base = verifier_base_url()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Open a forwarding client for the process lifetime unless one was injected."""
        owns = client is None
        app.state.client = client or httpx.AsyncClient()
        try:
            yield
        finally:
            if owns:
                await app.state.client.aclose()

    app = FastAPI(title="zk-age-verifier demo", lifespan=lifespan)

    def reply(upstream: httpx.Response) -> Response:
        """Return the verifier's reply untouched."""
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type"),
        )

    async def forward(request: Request, url: str) -> Response:
        """Forward the request body to ``url`` and return the verifier's reply untouched."""
        upstream = await request.app.state.client.post(
            url,
            content=await request.body(),
            headers={"content-type": request.headers.get("content-type", "application/json")},
        )
        return reply(upstream)

    @app.post("/av/session")
    async def open_session(request: Request) -> Response:
        """Open a verifier session with ``SESSION_REQUEST``. The client body is ignored."""
        upstream = await request.app.state.client.post(f"{base}/sessions", json=SESSION_REQUEST)
        return reply(upstream)

    @app.post("/av/response")
    async def forward_response(request: Request, session: str) -> Response:
        """Forward a wallet response to the verifier's presentation route for ``session``."""
        return await forward(request, f"{base}/sessions/{session}/presentation")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        """Serve the gate page."""
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    return app
