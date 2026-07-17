import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from zk_age_verifier.service.sessions import (
    SessionAlreadyAttempted,
    SessionStore,
    SessionUnknown,
    StoreAtCapacity,
    sweep_loop,
)

CLAIMS = ("age_over_18",)


def _expire(store: SessionStore, public_id: str) -> None:
    store._sessions[public_id].expires_at = datetime.now(UTC) - timedelta(seconds=1)


def test_create_take_round_trip(store: SessionStore) -> None:
    session, dc_request = store.create(CLAIMS)
    assert session.claims == CLAIMS
    assert session.expected_origin == "https://chat.example.org"
    assert "digital" in dc_request
    taken = store.take_for_attempt(session.public_id)
    assert taken is session
    assert taken.attempted is True


def test_create_origin_override(store: SessionStore) -> None:
    session, _ = store.create(CLAIMS, origin_override="https://other.example.org")
    assert session.expected_origin == "https://other.example.org"


def test_take_twice_raises_already_attempted(store: SessionStore) -> None:
    session, _ = store.create(CLAIMS)
    store.take_for_attempt(session.public_id)
    with pytest.raises(SessionAlreadyAttempted):
        store.take_for_attempt(session.public_id)


def test_take_unknown_raises_session_unknown(store: SessionStore) -> None:
    with pytest.raises(SessionUnknown):
        store.take_for_attempt("does-not-exist")


def test_take_expired_raises_session_unknown(store: SessionStore) -> None:
    session, _ = store.create(CLAIMS)
    _expire(store, session.public_id)
    with pytest.raises(SessionUnknown):
        store.take_for_attempt(session.public_id)
    assert session.public_id not in store._sessions


def test_cap_raises_store_at_capacity(make_store: Callable[..., SessionStore]) -> None:
    store = make_store(cap=1)
    store.create(CLAIMS)
    with pytest.raises(StoreAtCapacity):
        store.create(CLAIMS)


def test_cap_ignores_expired_sessions(make_store: Callable[..., SessionStore]) -> None:
    store = make_store(cap=1)
    stale, _ = store.create(CLAIMS)
    _expire(store, stale.public_id)
    session, _ = store.create(CLAIMS)
    assert stale.public_id not in store._sessions
    assert session.public_id in store._sessions


def test_sweep_evicts_only_expired(store: SessionStore) -> None:
    live, _ = store.create(CLAIMS)
    stale, _ = store.create(CLAIMS)
    _expire(store, stale.public_id)
    assert store.sweep() == 1
    assert stale.public_id not in store._sessions
    assert store.take_for_attempt(live.public_id) is live


def test_tombstone_survives_until_ttl(store: SessionStore) -> None:
    session, _ = store.create(CLAIMS)
    store.take_for_attempt(session.public_id)
    assert store.sweep() == 0
    with pytest.raises(SessionAlreadyAttempted):
        store.take_for_attempt(session.public_id)


def test_stored_encryption_info_matches_issued_request(store: SessionStore) -> None:
    session, dc_request = store.create(CLAIMS)
    digital = dc_request["digital"]
    assert isinstance(digital, dict)
    requests = digital["requests"]
    assert isinstance(requests, list)
    data = requests[0]["data"]
    assert isinstance(data, dict)
    assert session.dc.encryption_info_b64 == data["encryptionInfo"]


def test_get_returns_session_without_spending_attempt(store: SessionStore) -> None:
    session, _ = store.create(CLAIMS)
    assert store.get(session.public_id) is session
    assert session.attempted is False
    assert store.take_for_attempt(session.public_id) is session


def test_get_returns_attempted_session(store: SessionStore) -> None:
    session, _ = store.create(CLAIMS)
    store.take_for_attempt(session.public_id)
    got = store.get(session.public_id)
    assert got is session
    assert got.attempted is True


def test_get_unknown_raises_session_unknown(store: SessionStore) -> None:
    with pytest.raises(SessionUnknown):
        store.get("does-not-exist")


def test_get_expired_raises_and_evicts(store: SessionStore) -> None:
    session, _ = store.create(CLAIMS)
    _expire(store, session.public_id)
    with pytest.raises(SessionUnknown):
        store.get(session.public_id)
    assert session.public_id not in store._sessions


async def test_sweep_loop_evicts_then_cancels(store: SessionStore) -> None:
    session, _ = store.create(CLAIMS)
    _expire(store, session.public_id)
    task = asyncio.create_task(sweep_loop(store, 0))
    try:
        async with asyncio.timeout(1):
            while session.public_id in store._sessions:
                await asyncio.sleep(0)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
