# zk-age-verifier

[![CI](https://github.com/pipe23-org/zk-age-verifier/actions/workflows/ci.yml/badge.svg)](https://github.com/pipe23-org/zk-age-verifier/actions/workflows/ci.yml)
[![Docs](https://app.readthedocs.org/projects/zk-age-verifier/badge/?version=latest)](https://zk-age-verifier.readthedocs.io/en/latest/)
[![PyPI](https://img.shields.io/pypi/v/zk-age-verifier)](https://pypi.org/project/zk-age-verifier/)
[![Python](https://img.shields.io/pypi/pyversions/zk-age-verifier)](https://pypi.org/project/zk-age-verifier/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

## Overview

A verifier service for zero-knowledge age proofs, following the EU age-verification
profile: Longfellow ZK over mdoc credentials, presented through the W3C Digital
Credentials API. Your backend opens a session, your page hands the returned request to
`navigator.credentials.get()`, your backend relays the wallet's response, and the answer
comes back on the same call: `{"age_over_18": true}`, or a named failure. The service
stores no identifier for the person the verdict describes — one boolean is the product.

An age presentation varies along four axes:

**Invocation**: how the request reaches the wallet — DC API
(`navigator.credentials.get()`, same- or cross-device), custom-URI/QR + `direct_post`,
or ISO 18013-5 proximity.

**Presentation protocol**: the request/response framing — `org-iso-mdoc`
(DeviceRequest/DeviceResponse CBOR, HPKE) or OpenID4VP (DCQL).

**Credential format**: the issuer-signed object — mdoc (ISO/IEC 18013-5) or SD-JWT-VC.

**Disclosed vs ZK**: what the verifier receives — the credential itself with claim
values disclosed, or a zero-knowledge proof of a predicate over it
(`longfellow-libzk-v1`), never the credential.

| # | Invocation | Protocol | Format | Disclosed/ZK | Status |
|---|------------|----------|--------|--------------|--------|
| 1 | DC API | `org-iso-mdoc` | mdoc | ZK | implemented |
| 2 | DC API | `org-iso-mdoc` | mdoc | disclosed | not implemented |
| 3 | custom-URI/QR + `direct_post` | OpenID4VP | mdoc | disclosed | not implemented |
| 4 | custom-URI/QR + `direct_post` | OpenID4VP | mdoc | ZK | planned |
| 5 | DC API | OpenID4VP | mdoc | disclosed or ZK | not implemented |
| 6 | custom-URI/QR + `direct_post` | OpenID4VP | SD-JWT-VC | disclosed | not implemented |
| 7 | custom-URI/QR + `direct_post` | OpenID4VP | SD-JWT-VC | ZK | out of scope |
| 8 | DC API | `org-iso-mdoc` | SD-JWT-VC | — | out of scope |
| 9 | Proximity (BLE/NFC) | ISO 18013-5 device retrieval | mdoc | disclosed or ZK | out of scope |

The disclosed rows stay "not implemented" as a matter of principle, not sequencing: this
service verifies zero-knowledge proofs only. A standard mdoc presentation discloses a
correlatable credential to the verifier; accepting one would quietly convert an age check
into an identification event, so the service refuses them by construction
(`standard-mdoc-not-accepted`).

## Usage

```
pip install zk-age-verifier
```

or the container:

```
docker pull ghcr.io/pipe23-org/zk-age-verifier
```

Configuration is one TOML file — who runs the page, and which issuers to believe:

```toml
[service]
expected_origin = "https://example.org"   # exact origin of the page that runs the credential call

[trust]
sources = [
  { pem = "/etc/zk-age-verifier/anchors/" },   # PEM file or directory of issuer CAs
  # { etsi_xml = "https://.../trusted-list.xml" },
]
```

The package ships no trust material — the store is empty until you configure it. For the
Commission test environment, the repo carries a captured copy of the test issuer CA
(`examples/verifying-site/anchors/eu-av-test.pem`, provenance in its README). First start
generates the proof circuit and caches it on disk.

The integration is two HTTP calls from your backend and one browser call from your page:

1. `POST /sessions` with `{"checks": ["age_over_18"]}` → `201` with a `public_id` and
   `transports.dc`, the ready-made argument for the browser call.
2. Your page runs `navigator.credentials.get(dcRequest)`; the browser handles picker,
   wallet, and consent. (`examples/verifying-site/static/dc.js` is a lift-out-able
   reference for this step.)
3. `POST /sessions/{public_id}/presentation` with the wallet's response, untouched.
   Verification is synchronous; the verdict returns on the same call —
   `{"state": "verified", "result": {"age_over_18": true}}` or
   `{"state": "failed", "reason": "..."}` with a short machine reason
   (`proof-invalid`, `untrusted-issuer`, `unsupported-circuit`, `stale-proof`, …).

One attempt per session; a second post gets `409` and the fix is always a fresh session.
Sessions expire on their own. The verifier needs no inbound connectivity from the
internet — only your backend talks to it.

The [documentation](https://zk-age-verifier.readthedocs.io/) covers the operator manual
and the generated HTTP API reference. `examples/verifying-site/` is a complete consumer:
gate page, forwarding backend, compose topology.

## Gaps

Deliberate limitations, stated rather than discovered:

- **A verified verdict assures the operator and no one else.** Trust is local
  configuration; cryptographically, an issuer is any P-256 key an anchor vouches for.
  Nothing compares the anchor set against an official list, and the verdict cannot serve
  as compliance evidence to a third party. The properties that protect the holder — no
  issuer phone-home, no third party in the loop, no identity in logs or verdicts — are
  the properties that make verification unprovable to anyone but the operator.
- **The proof does not bind the claim's namespace.** The underlying proof system matches
  disclosed elements by identifier and value; the namespace string is unbound (doctype is
  bound). No concrete bypass is known under the age-verification doctype. Namespace
  binding belongs upstream; watch item.
- **The platform sees the event.** On the DC API path the browser/OS mediate consent and
  learn that an age check happened; HPKE blinds them to the response contents, not the
  fact. The OpenID4VP path (planned) is the no-platform-intermediary alternative — with,
  today, no shipped wallet able to present ZK over it.
- **Cross-device consent-relay is unmitigated.** An adult can consent for a minor on
  another screen. This verifier proves "an adult consented to this session," not "the
  human at the keyboard is an adult."
- **Requests are unsigned.** The profile scopes reader authentication out; nothing
  controls who may ask. Shipped wallets carry the enforcement machinery with the policy
  switched off; the day a deployed wallet turns it on, unsigned requests — ours
  included — will be rejected.
- **Browser support is two of three engines.** Chrome 141+ and Safari 26 ship the DC API;
  Firefox's position is negative. Firefox users get the OpenID4VP path when it exists.
- **The proof system is pre-1.0.** Longfellow is not peer-reviewed, and the profile that
  recommends it says so itself. We report this; we cannot resolve it.
- **Single-worker deployment is required.** Sessions are in-memory and process-lifetime;
  a second worker is a second, disjoint store. `--workers 1` is pinned in the container
  entrypoint, and a bare-metal run must not raise it.
- **It's in Python.** Orchestration glue around a C++ verify call, chosen for legibility
  to the people deciding whether to trust it.

<!-- HELD, do not forget: the hostile-input posture statement (crafted bytes on the
     verify path can abort the process; the hostile-input-safe claim is deliberately
     not made until the upstream guard+fuzz pass lands). Vehicle undecided —
     SECURITY.md vs a bullet here vs both. Tracked in workspace#29. -->

## Vendoring and pinning

Upstream reaches this service only through deliberate bumps, at two links:

- zk-age-verifier hard-pins pylongfellow (`>=0.2.2,<0.3`).
- pylongfellow hard-pins google/longfellow-zk at a submodule SHA.

This repository never vendors directly from google/longfellow-zk. pylongfellow's
submodule pin is the SHA of record for that upstream; every longfellow-zk-derived byte
here cites it. The point is a firewall: upstream churn lands on our schedule, maintained
and tested at each link, never implicitly.

Vendored test inputs — upstream credential bytes, protocol example strings, the reference
verifier-service example — are frozen snapshots with per-input provenance (manifests
beside the bytes, `tests/data/README.md`). They never track upstream; staleness is a
property to surface, not silently repair.

Bumps happen on criteria, not cadence: a pylongfellow release, a circuit version change
in the ecosystem, wallet wire-format movement. Last verified against pylongfellow 0.2.2
(2026-07-18). If upstream moves and we haven't, file an issue.

## Development

```
uv sync            # env from the lockfile
uv run pytest      # tests; the coverage gate is on by default
uv run ruff check && uv run mypy    # lint + types
uv run mkdocs serve                 # docs preview
```

Two make targets exercise the service beyond the in-process suite: `make test-live` runs
it against a real server over HTTP; `make test-container` runs it against the built
container image.

## License

Apache-2.0.
