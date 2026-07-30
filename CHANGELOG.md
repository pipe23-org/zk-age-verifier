# Changelog

## Unreleased

- pylongfellow 0.4.0: both verifier backends ship in the default install; no extra or
  separate wheel.
- `[service]` gains `backend` (default `google-cpp`) — the pylongfellow registry name the
  service verifies with, overridable as `ZK_AGE_VERIFIER_SERVICE__BACKEND`. An unknown or
  unbuilt name fails startup. Per-backend verification scope is documented in
  `docs/backends.md`.
- `ZkDocument` gains `device_name_spaces_bytes: bytes | None`. The ZK response format
  defines no field that carries the value, so every expressible presentation parses to
  explicit absence; where it is absent the service substitutes the empty device-namespace
  map at one stated-assumption injection point before the verify call
  ([pipe23-org/pylongfellow#29](https://github.com/pipe23-org/pylongfellow/issues/29)).
  google-cpp ignores the parameter; isrg-rust requires and binds it.
- In-process integration tests run against both verifier backends; the presenter proves
  with one fixed backend throughout, since a wallet's proving implementation is outside
  the service's knowledge and does not co-vary with the configured verifier. A specimen test
  observes both backends verifying the upstream example proof — isrg-rust under the
  assumed empty map — over the vendored v6 circuit and verify inputs
  (`tests/data/README.md` records provenance).
- Ported to the pylongfellow 0.3 client API: one `Pylongfellow(backend="google-cpp")`
  binds the backend at startup, `load_circuit` returns a handle, and `prove`/`verify`
  are methods on the client. The module-level `mdoc.prove`/`mdoc.verify` calls and the
  `mdoc.ZkSpec` type are gone; the service imports no backend-specific symbols.
- The circuit ships as package data (`src/zk_age_verifier/circuits/v7-1attr.circuit`
  with a sidecar record) and is loaded at startup, replacing generate-on-first-run.
  The loader checks the blob against the sidecar `byte_sha256` and the sidecar spec
  against the pinned system, version, and attribute count; the backend re-validates the
  circuit hash at load.
- Removed `circuit_cache_dir` from `[service]` config, the `XDG_CACHE_HOME` default, the
  container cache directory and volume, and the Makefile cache-volume machinery. No
  writable cache directory is needed.

## 0.1.2 - 2026-07-24

- `scripts/generate_credentials.py` builds its constructed entries through
  `pylongfellow.mdoc.create_credential` and `create_certificate`, and validates the
  `DeviceAuthentication` encoding against the vendored credential through
  `verify_device_authentication`; the local COSE, certificate, and mdoc-assembly helpers
  moved to pylongfellow 0.2.3 and are deleted here
  ([#20](https://github.com/pipe23-org/zk-age-verifier/pull/20)).
- The presenter re-signs each session's transcript through
  `pylongfellow.mdoc.sign_device_authentication`
  ([#20](https://github.com/pipe23-org/zk-age-verifier/pull/20)).
- pylongfellow pin bumped to `>=0.2.3,<0.3`; credential fixtures regenerated
  ([#20](https://github.com/pipe23-org/zk-age-verifier/pull/20)).

## 0.1.1 - 2026-07-23

- The OpenAPI descriptions of `createSession` and `submitPresentation` now state the
  service contract only; wording that described the consumer's page was removed from the
  served schema, docstrings, README, and docs
  ([#18](https://github.com/pipe23-org/zk-age-verifier/pull/18)).
- A tagged release now creates a GitHub Release with this file's section as notes, after
  the published package is verified to install and import
  ([#19](https://github.com/pipe23-org/zk-age-verifier/pull/19)).

## 0.1.0 - 2026-07-23

Initial release. zk-age-verifier verifies Longfellow zero-knowledge proofs over mdoc,
presented through the W3C Digital Credentials API, and runs as a sidecar HTTP service
beside a consumer backend.

- **Fail-closed verification** — malformed presentation input produces a failed verdict,
  not an HTTP 500 ([#14](https://github.com/pipe23-org/zk-age-verifier/pull/14)).
- **Trust-source schemes** — ETSI trusted-list sources accept only https URLs or file
  paths ([#15](https://github.com/pipe23-org/zk-age-verifier/pull/15)).
- **Document Signer key usage** — the presented Document Signer certificate must carry
  keyUsage with digitalSignature; acceptance through a configured anchor requires
  keyCertSign on the anchor certificate
  ([#16](https://github.com/pipe23-org/zk-age-verifier/pull/16)).
- **Trust-source scope** — the README and configuration reference document that all
  configured trust sources merge into one anchor set, and that the source list must
  contain only anchors intended to vouch for age credentials
  ([#16](https://github.com/pipe23-org/zk-age-verifier/pull/16)).
