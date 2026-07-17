"""RFC 9457 problem+json rendering for HTTP and validation errors."""

from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException


class Problem(BaseModel):
    """An RFC 9457 problem+json error body.

    Extension members are permitted; the 422 body carries its offending fields under
    ``errors``.
    """

    model_config = ConfigDict(extra="allow")

    type: str = "about:blank"
    title: str
    status: int
    detail: str


class ValidationProblem(Problem):
    """The 422 body: a Problem with the offending fields under an ``errors`` member."""

    errors: list[dict[str, Any]]


def _problem(
    status: int, detail: Any, headers: Mapping[str, str] | None = None, **extensions: Any
) -> JSONResponse:
    """Build an application/problem+json response ("type" defaults to about:blank)."""
    body = {"type": "about:blank", "title": HTTPStatus(status).phrase, "status": status}
    return JSONResponse(
        body | {"detail": detail} | extensions,
        status_code=status,
        headers=headers,
        media_type="application/problem+json",
    )


_PROBLEM_DETAILS: dict[int, str] = {
    400: "checks must be exactly ['age_over_18']; no other vocabulary is supported",
    404: "unknown or expired session",
    409: "session already attempted",
    503: "session store at capacity",
}


def problem_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    """Return `responses=` entries declaring Problem under application/problem+json.

    Each code's description is its HTTP reason phrase, and each carries an example body so
    Swagger renders a realistic Problem instead of a synthesized one. A route passes the
    result to its decorator to document the errors it raises without hand-writing the mapping.
    """
    schema = {"$ref": "#/components/schemas/Problem"}
    return {
        code: {
            "description": HTTPStatus(code).phrase,
            "content": {
                "application/problem+json": {
                    "schema": schema,
                    "example": {
                        "type": "about:blank",
                        "title": HTTPStatus(code).phrase,
                        "status": code,
                        "detail": _PROBLEM_DETAILS.get(code, HTTPStatus(code).phrase),
                    },
                }
            },
        }
        for code in codes
    }


def _use_problem_for_validation(schema: dict[str, Any]) -> dict[str, Any]:
    """Register the Problem schema and rewrite every 422 response to problem+json.

    The routes reference Problem only through ``$ref``, so it is registered unconditionally.
    Each 422 replaces FastAPI's stock HTTPValidationError entry, in place, with
    ValidationProblem under application/problem+json plus an example body, and drops the
    now-unreferenced stock schemas.
    """
    schemas = schema.setdefault("components", {}).setdefault("schemas", {})
    schemas["Problem"] = Problem.model_json_schema(ref_template="#/components/schemas/{model}")
    touched = False
    for item in schema["paths"].values():
        for operation in item.values():
            if not isinstance(operation, dict):
                continue
            responses = operation.get("responses", {})
            if "422" in responses:
                responses["422"] = {
                    "description": HTTPStatus(422).phrase,
                    "content": {
                        "application/problem+json": {
                            "schema": {"$ref": "#/components/schemas/ValidationProblem"},
                            "example": {
                                "type": "about:blank",
                                "title": HTTPStatus(422).phrase,
                                "status": 422,
                                "detail": "Request validation failed.",
                                "errors": [
                                    {
                                        "type": "missing",
                                        "loc": ["body", "checks"],
                                        "msg": "Field required",
                                    }
                                ],
                            },
                        }
                    },
                }
                touched = True
    if touched:
        schemas["ValidationProblem"] = ValidationProblem.model_json_schema(
            ref_template="#/components/schemas/{model}"
        )
        schemas.pop("HTTPValidationError", None)
        schemas.pop("ValidationError", None)
    return schema


def install_problem_handlers(app: FastAPI) -> None:
    """Register handlers that render errors per RFC 9457, and document 422 accordingly."""

    @app.exception_handler(HTTPException)
    async def _http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        """Render HTTPException (FastAPI's subclasses Starlette's)."""
        return _problem(exc.status_code, exc.detail, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Render request-validation failures, with the offending fields as an extension."""
        return _problem(422, "Request validation failed.", errors=jsonable_encoder(exc.errors()))

    generate = app.openapi

    def openapi() -> dict[str, Any]:
        """Return the app's OpenAPI schema with 422 rendered as problem+json."""
        return _use_problem_for_validation(generate())

    app.openapi = openapi  # type: ignore[method-assign]
