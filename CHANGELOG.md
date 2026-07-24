# Changelog

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
