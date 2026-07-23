# zk-age-verifier

Verifier service for EU age-verification proofs: Longfellow ZK over mdoc, presented through
the W3C Digital Credentials API.

The consumer's backend opens a session (`POST /sessions`) and receives the `transports.dc`
offer, the parameter object for `navigator.credentials.get()`. The wallet's response is
submitted (`POST /sessions/{session_id}/presentation`) and the verdict returns on the same
call: `{"age_over_18": true}` or a failure reason. The service stores no identifier for the
person the verdict describes.

The [HTTP API](api.md) page documents the full surface, generated from the service's OpenAPI
schema.
