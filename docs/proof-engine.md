# Proof engine

The `pylongfellow.backend` key under `[service]` selects the proof engine the service
verifies with (default `google-cpp`; environment override
`ZK_AGE_VERIFIER_SERVICE__PYLONGFELLOW__BACKEND`). Registry names: `google-cpp`
(google/longfellow-zk), `isrg-rust` (abetterinternet/zk-cred-longfellow). Both ship in the
default pylongfellow install. An unknown or unbuilt name fails startup.

## Verification scope

The engines disagree over whether `DeviceNameSpacesBytes` is a verifier input, and the ZK
response format has no field for it; the record is
[pipe23-org/pylongfellow#29](https://github.com/pipe23-org/pylongfellow/issues/29).
google-cpp fixes the value to the empty map internally; isrg-rust takes it as input and
receives the empty map from this service (`core/engine/mdoc_zk.py`). A verified verdict
under either engine means the proof holds for a device that signed an empty namespace map.

## Operations

pylongfellow upstream is not benchmarked as of 2026-07-30.
