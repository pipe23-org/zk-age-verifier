# Verifying site

An example site that gates entry on zk-age-verifier's answer: a gate page and a forwarding
backend for a real-phone age check. The backend is the consumer backend of the default DC-path topology — it
serves the page and forwards two routes to the verifier, which stays on a private network
beside it. The backend never parses credential material.

This is a standalone uv project with its own `pyproject.toml`, `uv.lock`, and `.venv`, separate
from the verifier project.

## Routes

- `POST /av/session` forwards to the verifier's `POST /sessions`.
- `POST /av/response?session=<public_id>` forwards to the verifier's
  `POST /sessions/{public_id}/presentation`.
- `GET /` serves the gate page; `/static/` serves its assets.

Each forward copies the request body through unchanged and returns the verifier's status code,
content type, and body untouched. Verifier problem+json errors reach the page as issued.

## The page

`verifying_site/static/index.html` drives state swaps idle → checking → verified / failed / rejected.
The Digital Credentials call is `verifying_site/static/dc.js`: it opens a session, passes
`transports.dc` to `navigator.credentials.get()` unchanged, forwards the wallet's response, and
returns the verdict. A rejected promise — no wallet, user cancel, unsupported browser — becomes
the `rejected` state. `dc.js` carries no page coupling and lifts unchanged into another
consumer. The page is plain JS; there is no build step.

## Run the backend alone

    DEMO_VERIFIER_URL=http://127.0.0.1:8000 uv run verifying-site

Serves the page and forwards to a verifier at `DEMO_VERIFIER_URL`.

Backend environment:

- `DEMO_VERIFIER_URL` — verifier base URL. Default `http://127.0.0.1:8000`.
- `DEMO_HOST` — listen address. Default `0.0.0.0`.
- `DEMO_PORT` — listen port. Default `8080`.

## Run the full demo with compose

`compose.yaml` runs traefik terminating TLS, the backend, and the verifier. traefik and the
backend share the `edge` network; the backend and verifier share the `internal` network, which
is marked `internal: true`. The verifier publishes no ports and carries no traefik labels, so it
is reachable only from the backend by the service name `verifier`.

Set these before `docker compose up`:

- `DEMO_DOMAIN` — the page origin host, e.g. `age.example.org`. It becomes the traefik router
  `Host` rule and the verifier's `expected_origin` (`https://${DEMO_DOMAIN}`, injected as an
  env override).
- `DEMO_CERT_DIR` — directory holding `cert.pem` and `key.pem` for `DEMO_DOMAIN`, mounted into
  traefik and served via its file provider.

The verifier config is committed (`verifier-config.toml`); it trusts whatever `anchors/`
holds — by default the captured Commission test IACA (provenance in `anchors/README.md`), so
credentials from the Commission's dev issuer verify out of the box. To trust a different
issuer, set `DEMO_VERIFIER_ANCHOR` to a PEM file or a directory of them.

The verifier image builds from the repository root (`build: ../..`); the backend image builds
from this directory. The circuit cache is a named volume, so first-boot circuit generation is
paid once.

## Tests

    uv run pytest

The forwarding routes are tested with the verifier stubbed by a mock transport: forwarding targets,
body pass-through, and error pass-through. The page is not tested here — `navigator.credentials.get`
is exercised manually against a real wallet, not a headless shim.
