# site-dc-mdoc

site-dc-mdoc is a Docker Compose age-gate demonstration built on zk-age-verifier, wiring
a browser page, a site backend, the verifier, and a TLS-terminating traefik. The page calls
the backend to open a verifier session and to relay the wallet response. Only the backend
calls the verifier, which publishes no ports and is reachable only from the backend on an
internal network. The backend relays the verifier's verdict to the page and does not itself
gate site access.

## Usage

The demo needs a DNS name resolving to the host and a TLS certificate and key for it.

```
export DEMO_DOMAIN=age.example.org
export DEMO_CERT_DIR=/path/to/certs   # holds cert.pem and key.pem
docker compose up --build
```

First start generates the ZK circuit once and caches it in the `circuits` named volume. Visit
`https://${DEMO_DOMAIN}` from a browser that supports the Digital Credentials API.

## Routes

- `GET /` serves the page; `/static/` serves its assets.
- `POST /av/session` opens a verifier session with the backend's fixed body,
  `{"checks": ["age_over_18"]}`. The client request body is ignored.
- `POST /av/response?session=<session_id>` forwards the request body unchanged to the
  verifier's `POST /sessions/{session_id}/presentation`.

The verifier's status code, content type, and body pass back untouched.

## Configuration

- `DEMO_DOMAIN` — page origin host; no default. Becomes the traefik `Host` rule and the
  verifier `expected_origin` `https://${DEMO_DOMAIN}`.
- `DEMO_CERT_DIR` — directory holding `cert.pem` and `key.pem` for `DEMO_DOMAIN`; no default.
  Mounted into traefik.
- `DEMO_VERIFIER_ANCHOR` — PEM file or directory of trust anchors; default `./anchors`, the
  committed Commission test IACA. Set to trust a different issuer.
- `DEMO_VERIFIER_URL` — verifier base URL the backend calls; compose sets `http://verifier:8000`,
  default `http://127.0.0.1:8000`.
- `DEMO_HOST`, `DEMO_PORT` — backend listen address; default `0.0.0.0:8080`.

The verifier configuration is committed as `verifier-config.toml` and trusts whatever the
mounted anchors directory holds.

## Documentation

Verifier endpoints, verdict format, and configuration: https://zk-age-verifier.readthedocs.io/

## Development

```
uv run pytest
```

The suite drives the backend against a mocked verifier transport.

## License

Apache-2.0.
