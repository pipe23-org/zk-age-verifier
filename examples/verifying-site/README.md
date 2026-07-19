# Verifying site

An example site that gates entry on zk-age-verifier's answer: a page and a backend for a
real-phone age check. The backend is the consumer backend of the default DC-path topology: it
serves the page, opens verifier sessions, and forwards wallet responses to a verifier on a
private network beside it. It never parses credential material.

This is a standalone uv project with its own `pyproject.toml`, `uv.lock`, and `.venv`, separate
from the verifier project.

## Routes

- `POST /av/session` opens a session at the verifier's `POST /sessions` with the backend's
  own body, `{"checks": ["age_over_18"]}`. The client request body is ignored: `checks` is
  the consumer's policy, and a client that could write the session body could downgrade the
  check (once more vocabulary exists) or set `expected_origin` and defeat the origin binding.
- `POST /av/response?session=<session_id>` forwards the request body unchanged to the
  verifier's `POST /sessions/{session_id}/presentation`.
- `GET /` serves the page; `/static/` serves its assets.

The verifier's status code, content type, and body pass back untouched, so problem+json
errors reach the page as issued. A production backend would go further: reject non-empty
`/av/session` bodies, log at verdict time, and decide access server-side from the verdict
rather than in page state.

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

The routes are tested with the verifier stubbed by a mock transport: session opening with the
backend's own `checks` (client body ignored), body pass-through on the response route, and
error pass-through. The page is not tested here — `navigator.credentials.get`
is exercised manually against a real wallet, not a headless shim.
