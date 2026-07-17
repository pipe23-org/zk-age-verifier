#!/bin/sh
set -e
# Sessions are in-memory and per-process; a second worker cannot see the
# first worker's sessions.
exec granian --interface asgi --factory --workers 1 --host 0.0.0.0 --port 8000 zk_age_verifier.app:app_factory
