# zk-age-verifier

zk-age-verifier is a verifier service for EU age verification, accepting Longfellow
zero-knowledge proofs over mdoc through the W3C Digital Credentials API. It
runs as a sidecar HTTP service beside a consumer backend. A verdict contains one boolean
per requested check and no name, birthdate, identifier, or wallet information. The service
has no authentication and is intended to be reachable only from the consumer backend, not
the browser or internet. It is experimental and unstable.

[![CI](https://github.com/pipe23-org/zk-age-verifier/actions/workflows/ci.yml/badge.svg)](https://github.com/pipe23-org/zk-age-verifier/actions/workflows/ci.yml)
[![Docs](https://app.readthedocs.org/projects/zk-age-verifier/badge/?version=latest)](https://zk-age-verifier.readthedocs.io/en/latest/)
[![PyPI](https://img.shields.io/pypi/v/zk-age-verifier)](https://pypi.org/project/zk-age-verifier/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

## Installation

```
pip install zk-age-verifier
uv add zk-age-verifier
docker pull ghcr.io/pipe23-org/zk-age-verifier:latest
```

## Usage

The verifier needs a configured page origin and at least one trust source.

```toml
[service]
expected_origin = "https://av.example"

[[trust.sources]]
pem = "/etc/zk-age-verifier/anchors"
```

First start generates the ZK circuit and caches it on disk.

```
python -m zk_age_verifier --config config.toml
```

`POST /sessions` opens a session and returns the `navigator.credentials.get()` argument
under `transports.dc`.

```
$ curl -X POST http://127.0.0.1:8000/sessions \
    -H 'content-type: application/json' -d '{"checks": ["age_over_18"]}'
{"session_id": "tmcdOPmo7oCgd4AmmMFyYg",
 "transports": {"dc": {"digital": {"requests": [{"protocol": "org-iso-mdoc",
   "data": {"deviceRequest": "omd2ZXJzaW9u…", "encryptionInfo": "gmVkY2FwaaJ…"}}]},
   "mediation": "required"}},
 "expires_at": "2026-07-20T09:34:22.089682Z"}
```

The consumer backend relays the wallet response to `POST /sessions/{session_id}/presentation`. A
verified and a failed verification both return 200.

```
POST /sessions/{session_id}/presentation
{"response": "<wallet response, base64url>"}

{"state": "verified", "result": {"age_over_18": true}, "verified_at": "<iso8601>"}
{"state": "failed", "reason": "decrypt-failed"}
```

`GET /health` returns `{"status": "ok"}` while the process is up.

`GET /debug/transcript/{session_id}` returns the transcript inputs stored for a session — the
origin and the `encryptionInfo` string — with the handover hash and session-transcript bytes
reconstructed from them, hex-encoded. It is a development route, unauthenticated like the rest
of the service.

## Configuration

Two TOML tables, `[service]` and `[trust]`, passed with `--config`.

- `expected_origin` (required) — the exact `scheme://host[:port]` origin of the page that runs the credential call.
- `session_ttl_seconds` (default 300) — session lifetime.
- `session_cap` (default 1000) — live-session limit; `POST /sessions` returns 503 at the cap.
- `timestamp_skew_seconds` (default 300) — proofs with a timestamp older than this fail `stale-proof`.
- `cors_allowed_origins` (default `[]`) — origins for which CORS headers are emitted.
- `circuit_cache_dir` (default `$XDG_CACHE_HOME/zk-age-verifier/circuits`) — where the generated circuit is cached.
- `trust.sources` (required) — non-empty list; each entry sets one of `pem` (a PEM file or directory of issuer CA certs) or `etsi_xml` (an ETSI trusted-list URL).

A presented document-signer certificate must carry the keyUsage extension asserting digitalSignature; an anchor accepted as the issuer of a chained leaf must assert keyCertSign.

Configured trust sources merge into one anchor set. Any anchor in that set can vouch for a certificate that signs age credentials. The certificate layer carries no required marker restricting what an anchor's certificates may sign. ETSI TS 119 412-6 clause 6 places no type indicator on EAA signing certificates. The `trust.sources` list must name only anchors intended to vouch for age credentials. A mixed-purpose or broad list authorizes every CA on it as an age-credential issuer.

Environment variables `ZK_AGE_VERIFIER_<SECTION>__<KEY>` override scalar values; lists and
nested tables come from the TOML file only. Environment variables take precedence over the
TOML file, which takes precedence over the defaults.

## Documentation

Full documentation: https://zk-age-verifier.readthedocs.io/

## Development

```
uv sync
uv run pytest
```

`make test-live` runs the suite against a running server over HTTP. `make test-container`
runs it against the built container image.

## Status

You should not rely on this code.

- End-to-end testing covers Chrome on one Android 16 device.
- No rate limiting.
- The session store is in-process.

## License

Apache-2.0.
