# Backends

The proof check runs on one of pylongfellow's verifier implementations, selected by the
`backend` key of the `[service]` table (default `google-cpp`; environment override
`ZK_AGE_VERIFIER_SERVICE__BACKEND`). Registry names:

- `google-cpp` — google/longfellow-zk, google's C++ implementation.
- `isrg-rust` — abetterinternet/zk-cred-longfellow, ISRG's independent Rust implementation.

Both ship in the default pylongfellow install. An unknown or unbuilt name fails startup.

## Verification scope

The two implementations disagree about whether `DeviceNameSpacesBytes` is a verifier
input, and the ZK response format defines no field that could carry it. The record of the
gap is [pipe23-org/pylongfellow#29](https://github.com/pipe23-org/pylongfellow/issues/29).

- `google-cpp` fixes the value to the tag-24-wrapped empty map inside its public-input
  assembly. Acceptance means the proof holds for a device that signed an empty namespace
  map; the restriction is upstream's constant.
- `isrg-rust` requires the value as a verify parameter and binds it into the transcript
  hash. This service supplies the empty map wherever the wire carries nothing — a stated
  assumption about deployed wallets, applied at one injection point in
  `core/engine/mdoc_zk.py`. Acceptance means the same statement, with the restriction
  stated in this repository instead of hardwired upstream.

Over today's wire format the two backends therefore check the same statement. The
assumption is never defaulted inside pylongfellow.

## Operations

pylongfellow upstream is not benchmarked as of 2026-07-30; backend choice has no measured
performance characterization.
