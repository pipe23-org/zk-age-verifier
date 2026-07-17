"""Run the site backend with uvicorn, reading the listen address from the environment."""

import os

import uvicorn

from verifying_site.app import create_app


def main() -> None:
    """Serve the backend on ``DEMO_HOST``/``DEMO_PORT`` (default ``0.0.0.0:8080``)."""
    uvicorn.run(
        create_app(),
        host=os.environ.get("DEMO_HOST", "0.0.0.0"),
        port=int(os.environ.get("DEMO_PORT", "8080")),
    )


if __name__ == "__main__":
    main()
