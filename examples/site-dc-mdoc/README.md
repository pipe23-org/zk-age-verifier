# dc-mdoc-example-site


## Routes

- `GET /` serves the page; `/static/` serves its assets.
- `POST /av/session` opens a session at the verifier's `POST /sessions` with the backend's
  own body, `{"checks": ["age_over_18"]}`. The client request body is ignored.
- `POST /av/response?session=<session_id>` forwards the request body unchanged to the
  verifier's `POST /sessions/{session_id}/presentation`.

The verifier's status code, content type, and body pass back untouched, so problem+json
errors reach the page as issued. 

A production backend would go further: reject non-empty `/av/session` bodies, log at verdict time, and 
allow/deny site access server-side from the verdict.

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

