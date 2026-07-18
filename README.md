# zk-age-verifier

[![CI](https://github.com/pipe23-org/zk-age-verifier/actions/workflows/ci.yml/badge.svg)](https://github.com/pipe23-org/zk-age-verifier/actions/workflows/ci.yml)
[![Docs](https://app.readthedocs.org/projects/zk-age-verifier/badge/?version=latest)](https://zk-age-verifier.readthedocs.io/en/latest/)
[![PyPI](https://img.shields.io/pypi/v/zk-age-verifier)](https://pypi.org/project/zk-age-verifier/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

## Overview

An experimental verifier (relying party) for EUDI-AV wallet presentations. Implements
DC-API / mdoc / longfellow-zk verification. End-to-end tested against the
[AV reference wallet](https://github.com/eu-digital-identity-wallet/av-app-android-wallet-ui).
Unstable, not to be used in production. Depends on
[pipe23-org/pylongfellow](https://github.com/pipe23-org/pylongfellow), also unstable.

An independent implementation; not affiliated with the EU Digital Identity Wallet project.

## Usage

Read the [documentation](https://zk-age-verifier.readthedocs.io/), install the
[package](https://pypi.org/project/zk-age-verifier/), or pull the
[container image](https://github.com/pipe23-org/zk-age-verifier/pkgs/container/zk-age-verifier).
See `examples/` for an end-to-end test environment.

## Development

```
uv sync            # env from the lockfile
uv run pytest      # tests; the coverage gate is on by default
```

`make test-live` runs the suite against a real server over HTTP; `make test-container`
runs it against the built container image.

<!-- HELD, do not forget (workspace#29): the hostile-input posture statement — crafted
     bytes on the verify path can abort the process; the hostile-input-safe claim is
     deliberately not made until the upstream guard+fuzz pass lands. Vehicle undecided:
     SECURITY.md vs a README section vs both. -->

## License

Apache-2.0.
