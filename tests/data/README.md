# Test data

Bytes the tests read but did not produce.

- `upstream-verifier-service-request.json` — the example request body for google/longfellow-zk's
  reference verifier service. A JSON object with two base64 fields: `Transcript` (an
  OpenID4VP DC-API handover) and `ZKDeviceResponseCBOR` (a CBOR DeviceResponse carrying one
  `zkDocuments` entry). The ZK document is an `org.iso.18013.5.1.mDL` proof at circuit v6; its
  `zkSystemId` is a bare circuit hash, and its `documentData` has no `deviceSigned` key.
  Source: google/longfellow-zk `reference/verifier-service/server/examples/post1.json` at
  `fe83ec6c4efa5f98bc2439c8b06e5eccd153aca0` — pylongfellow's pinned submodule SHA, the SHA of
  record for all longfellow-zk-derived material here (byte-identical at upstream `90bb3c9`,
  the clone HEAD it was physically copied from). Captured 2026-07-14. Copied verbatim.
  google/longfellow-zk is Apache-2.0, the same licence as this repository.
