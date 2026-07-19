"""The consumer-facing HTTP surface: open a session, relay a presentation, debug a transcript.

Three routes over ``SessionStore`` and the verify pipeline. ``POST /sessions`` creates a
session and returns the closed, schema-pinned DC transport offer under ``transports.dc``.
``POST /sessions/{session_id}/presentation`` claims the session's one attempt before any
verification work and returns the terminal verdict synchronously.
``GET /debug/transcript/{session_id}`` reconstructs the transcript bytes for post-mortem.
"""

from typing import Literal

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from zk_age_verifier.config import validate_origin
from zk_age_verifier.core.transport.dc import build_handover_hash, build_session_transcript
from zk_age_verifier.problem import problem_responses
from zk_age_verifier.service.sessions import (
    SessionAlreadyAttempted,
    SessionUnknown,
    StoreAtCapacity,
)
from zk_age_verifier.service.verify import Verdict, verify_response

log = structlog.get_logger(__name__)

SUPPORTED_CHECKS = ["age_over_18"]
"""The only accepted ``checks`` vocabulary; other well-formed lists are rejected 400."""

_B64URL = r"^[A-Za-z0-9_-]+$"


class CreateSessionRequest(BaseModel):
    """The ``POST /sessions`` body: a strict check list and an optional origin override."""

    model_config = ConfigDict(extra="forbid")

    checks: list[str] = Field(
        description='The checks to request. Exactly `["age_over_18"]`.',
        json_schema_extra={
            "items": {"type": "string", "const": SUPPORTED_CHECKS[0]},
            "minItems": 1,
            "maxItems": 1,
        },
    )
    expected_origin: str | None = None

    @field_validator("expected_origin")
    @classmethod
    def _validate_origin(cls, value: str | None) -> str | None:
        """Validate the override against the config field's rules when present."""
        return None if value is None else validate_origin(value)


class DcRequestData(BaseModel):
    """The ``data`` object: the two payloads as unpadded base64url strings."""

    model_config = ConfigDict(extra="forbid")

    deviceRequest: str = Field(pattern=_B64URL)  # noqa: N815 - wire field name
    encryptionInfo: str = Field(pattern=_B64URL)  # noqa: N815 - wire field name


class DcRequestEntry(BaseModel):
    """One ``requests`` entry: the ``org-iso-mdoc`` protocol and its data."""

    model_config = ConfigDict(extra="forbid")

    protocol: Literal["org-iso-mdoc"]
    data: DcRequestData


class DcRequestDigital(BaseModel):
    """The ``digital`` member: a single-entry ``requests`` array."""

    model_config = ConfigDict(extra="forbid")

    requests: list[DcRequestEntry] = Field(min_length=1, max_length=1)


class DcRequest(BaseModel):
    """The ``navigator.credentials.get`` argument, closed and fully pinned."""

    model_config = ConfigDict(extra="forbid")

    digital: DcRequestDigital
    mediation: Literal["required"]


class Transports(BaseModel):
    """The per-transport offers for a session; ``dc`` is the only one in v0.1."""

    model_config = ConfigDict(extra="forbid")

    dc: DcRequest


class SessionCreated(BaseModel):
    """The ``POST /sessions`` 201 body."""

    session_id: str
    transports: Transports
    expires_at: str


class DigitalCredentialData(BaseModel):
    """The DigitalCredential ``data`` member, as the browser returned it."""

    model_config = ConfigDict(extra="forbid")

    response: str = Field(description="The encrypted wallet response, base64url.")


class TranscriptDebug(BaseModel):
    """The ``GET /debug/transcript`` 200 body."""

    origin: str
    encryption_info_b64: str
    handover_hash_hex: str
    transcript_hex: str


router = APIRouter()


_VERDICT_EXAMPLES = {
    "verified": {
        "summary": "Proof verified",
        "value": {
            "state": "verified",
            "result": {"age_over_18": True},
            "verified_at": "2026-07-09T12:00:00Z",
        },
    },
    "failed": {
        "summary": "Verification failed",
        "value": {"state": "failed", "reason": "decrypt-failed"},
    },
}


@router.post(
    "/sessions",
    status_code=201,
    tags=["sessions"],
    operation_id="createSession",
    summary="Open a session",
    description=(
        "Opens an age-verification session. The response carries the session handle "
        "(`session_id`), the transport offers keyed by transport (`transports`), and the expiry "
        "(`expires_at`). The DC transport offer is at `transports.dc`.\n\n"
        "The page passes `transports.dc` to `navigator.credentials.get()` unchanged and relays "
        "the wallet's response to `POST /sessions/{session_id}/presentation`. `checks` must be "
        'exactly `["age_over_18"]`; a well-formed list with any other vocabulary gets 400. '
        "`expected_origin`, when present, replaces the configured origin for this session and "
        "must be the exact origin of the page that runs the credential call. The session "
        "expires at `expires_at` whether or not a response arrives."
    ),
    response_description="Session created",
    responses=problem_responses(400, 503),
)
async def create_session(request: Request, body: CreateSessionRequest) -> SessionCreated:
    """Open a session and return its transport offers.

    Args:
        request: The incoming request, carrying the app state.
        body: The validated session-open body.

    Returns:
        The session handle, transport offers, and expiry.

    Raises:
        HTTPException: 400 for an unknown check vocabulary; 503 at the session cap.
    """
    if body.checks != SUPPORTED_CHECKS:
        raise HTTPException(
            400, f"checks must be exactly {SUPPORTED_CHECKS}; no other vocabulary is supported"
        )
    store = request.app.state.store
    try:
        session, dc_request = store.create(body.checks, body.expected_origin)
    except StoreAtCapacity as exc:
        raise HTTPException(503, "session store at capacity") from exc
    return SessionCreated(
        session_id=session.session_id,
        transports=Transports(dc=dc_request),
        expires_at=session.expires_at.isoformat().replace("+00:00", "Z"),
    )


@router.post(
    "/sessions/{session_id}/presentation",
    tags=["sessions"],
    operation_id="submitPresentation",
    summary="Submit the wallet's response, get the verdict",
    description=(
        "Submits the wallet's response for a session and returns the verdict in the same "
        "call. The request body is the DigitalCredential `data` object exactly as the browser "
        "returned it.\n\n"
        "Verification is synchronous. The 200 body is the session's terminal state, "
        "`verified` or `failed`; a failed verification is a 200, not an HTTP error. A session "
        "accepts one response; later submissions get 409.\n\n"
        "An `expected_origin` mismatch surfaces as `decrypt-failed`: the origin is an input "
        "to the response encryption, so a wrong origin makes the response undecryptable "
        "rather than producing a distinct reason. `unsupported-circuit` means the wallet "
        "proved with a circuit version this verifier does not hold; the log line names both "
        "versions."
    ),
    response_description="Terminal verdict, verified or failed",
    responses={
        **problem_responses(404, 409),
        200: {"content": {"application/json": {"examples": _VERDICT_EXAMPLES}}},
    },
)
async def submit_response(
    session_id: str, request: Request, body: DigitalCredentialData
) -> Verdict:
    """Relay a wallet presentation and return the terminal verdict synchronously.

    Args:
        session_id: The session handle.
        request: The incoming request, carrying the app state.
        body: The DigitalCredential ``data`` object.

    Returns:
        The terminal verdict, verified or failed, as a 200 body.

    Raises:
        HTTPException: 404 for an unknown or expired session; 409 once its attempt is spent.
    """
    state = request.app.state
    try:
        session = state.store.take_for_attempt(session_id)
    except SessionUnknown as exc:
        raise HTTPException(404, "unknown or expired session") from exc
    except SessionAlreadyAttempted as exc:
        raise HTTPException(409, "session already attempted") from exc
    log.info("response_received", session_id=session_id)
    return await verify_response(
        session, state.held, state.anchors, body.model_dump(), state.config
    )


@router.get(
    "/debug/transcript/{session_id}",
    tags=["debug"],
    operation_id="debugTranscript",
    summary="Reconstruct a session's transcript inputs",
    description=(
        "Returns the transcript inputs stored for a session — the origin and the "
        "`encryptionInfo` string as issued — with the handover hash and session-transcript "
        "bytes reconstructed from them, hex-encoded. A transcript mismatch between wallet and "
        "verifier is located by comparing these inputs, not the final bytes."
    ),
    response_description="Transcript inputs and reconstructed bytes",
    responses=problem_responses(404),
)
async def debug_transcript(session_id: str, request: Request) -> TranscriptDebug:
    """Return a session's transcript inputs and reconstructed bytes.

    Args:
        session_id: The session handle.
        request: The incoming request, carrying the app state.

    Returns:
        The origin, the stored ``encryptionInfo`` string, and the resulting
        handover hash and transcript bytes, hex-encoded where they're bytes.

    Raises:
        HTTPException: 404 for an unknown or expired session.
    """
    try:
        session = request.app.state.store.get(session_id)
    except SessionUnknown as exc:
        raise HTTPException(404, "unknown or expired session") from exc
    handover_hash = build_handover_hash(session.dc.encryption_info_b64, session.expected_origin)
    transcript = build_session_transcript(session.dc.encryption_info_b64, session.expected_origin)
    return TranscriptDebug(
        origin=session.expected_origin,
        encryption_info_b64=session.dc.encryption_info_b64,
        handover_hash_hex=handover_hash.hex(),
        transcript_hex=transcript.hex(),
    )
