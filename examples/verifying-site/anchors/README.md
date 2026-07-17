# Captured trust material for the demo

The demo compose mounts this directory as the verifier's `pem` trust source by default
(override with `DEMO_VERIFIER_ANCHOR`). Nothing here ships in the wheel; each capture carries
its provenance and upstream location, so a deployment can fetch fresh instead of trusting the
copy.

These are test-environment certificates, never production trust. Trusting `eu-av-test.pem`
accepts credentials from the Commission's dev issuer, where anyone can enroll.

## eu-av-test.pem

The European Commission Age Verification test IACA, "Age Verification Issuer CA 01", valid to
2034.

- Source: eu-digital-identity-wallet/av-srv-web-issuing-avw-py,
  `api_docs/test_tokens/IACA-token/AgeVerificationIssuer.IACA.01.EU.pem` (Apache-2.0).
- Captured: 2026-07-08.
- The test environment's DS-001 certificate expires 2026-09-24.
