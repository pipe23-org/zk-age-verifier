"""In-process session store: one open check per record, TTL, and a sweeper."""

import asyncio
import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog

from zk_age_verifier.config import Config
from zk_age_verifier.core.transport.dc import DcSessionState, DcTransport

log = structlog.get_logger(__name__)

_SESSION_ID_BYTES = 16


class SessionUnknown(Exception):
    """Raised for a session id that is unknown or has expired."""


class SessionAlreadyAttempted(Exception):
    """Raised when a session has already spent its one response attempt."""


class StoreAtCapacity(Exception):
    """Raised when the live-session cap leaves no room for a new session."""


@dataclass
class Session:
    """One open age check.

    Attributes:
        session_id: The opaque handle returned to the consumer.
        dc: The DC transport's per-session state (recipient key, encryption info).
        expected_origin: The origin the consumer page's browser will assert.
        claims: The validated check list.
        created_at: When the session was created.
        expires_at: When the session stops being usable.
        attempted: Whether the one response attempt has been spent.
    """

    session_id: str
    dc: DcSessionState
    expected_origin: str
    claims: tuple[str, ...]
    created_at: datetime
    expires_at: datetime
    attempted: bool = False


class SessionStore:
    """A dict of live sessions, sized by the configured cap and swept on TTL."""

    def __init__(self, config: Config, transport: DcTransport) -> None:
        """Bind the store to its configuration and DC transport.

        Args:
            config: The service configuration (cap, TTL, default origin).
            transport: The DC transport that builds each session's offer.
        """
        self._config = config
        self._transport = transport
        self._sessions: dict[str, Session] = {}

    def create(
        self, claims: Sequence[str], origin_override: str | None = None
    ) -> tuple[Session, dict[str, object]]:
        """Create a session and its DC-API request.

        Args:
            claims: The validated check list.
            origin_override: A per-session origin replacing the service default.

        Returns:
            The stored session and the ``navigator.credentials.get`` argument.

        Raises:
            StoreAtCapacity: The live-session cap is reached.
        """
        # Expired sessions shouldn't count against the cap, so sweep before rejecting.
        cap = self._config.service.session_cap
        if len(self._sessions) >= cap:
            self.sweep()
        if len(self._sessions) >= cap:
            log.warning("store_at_capacity", cap=cap)
            raise StoreAtCapacity(f"session cap {cap} reached")

        session_id = secrets.token_urlsafe(_SESSION_ID_BYTES)
        dc_state, dc_request = self._transport.build_offer(claims)

        created_at = datetime.now(UTC)
        session = Session(
            session_id=session_id,
            dc=dc_state,
            expected_origin=origin_override or self._config.service.expected_origin,
            claims=tuple(claims),
            created_at=created_at,
            expires_at=created_at + timedelta(seconds=self._config.service.session_ttl_seconds),
        )
        self._sessions[session_id] = session
        log.info("session_created", session_id=session_id, expires_at=session.expires_at.isoformat())
        return session, dc_request

    def take_for_attempt(self, session_id: str) -> Session:
        """Claim a session's one response attempt.

        Args:
            session_id: The session handle.

        Returns:
            The session, now marked attempted.

        Raises:
            SessionUnknown: No such session, or it has expired.
            SessionAlreadyAttempted: The attempt was already spent.
        """
        session = self._live(session_id)
        if session.attempted:
            raise SessionAlreadyAttempted(session_id)
        session.attempted = True
        return session

    def get(self, session_id: str) -> Session:
        """Look up a session without spending its attempt.

        Args:
            session_id: The session handle.

        Returns:
            The session, whether or not its attempt is spent.

        Raises:
            SessionUnknown: No such session, or it has expired.
        """
        return self._live(session_id)

    def _live(self, session_id: str) -> Session:
        """Return the session if unexpired, evicting it on expiry.

        Args:
            session_id: The session handle.

        Returns:
            The live session.

        Raises:
            SessionUnknown: No such session, or it has expired.
        """
        session = self._sessions.get(session_id)
        if session is None:
            raise SessionUnknown(session_id)
        if datetime.now(UTC) >= session.expires_at:
            del self._sessions[session_id]
            log.info("session_expired", session_id=session_id)
            raise SessionUnknown(session_id)
        return session

    def sweep(self) -> int:
        """Evict expired sessions.

        Returns:
            The number of sessions evicted.
        """
        now = datetime.now(UTC)
        expired = [pid for pid, session in self._sessions.items() if now >= session.expires_at]
        for pid in expired:
            del self._sessions[pid]
        if expired:
            log.info("sessions_swept", count=len(expired))
        return len(expired)


async def sweep_loop(store: SessionStore, interval: float) -> None:
    """Sweep the store every ``interval`` seconds until cancelled.

    Args:
        store: The store to sweep.
        interval: Seconds between sweeps.
    """
    while True:
        await asyncio.sleep(interval)
        store.sweep()
