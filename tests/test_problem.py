import httpx
from fastapi import FastAPI, HTTPException

from zk_age_verifier.problem import (
    Problem,
    _use_problem_for_validation,
    install_problem_handlers,
    problem_responses,
)


def client_for(target: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=target)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def handled_app() -> FastAPI:
    api = FastAPI()
    install_problem_handlers(api)
    return api


async def test_http_exception_renders_problem_json() -> None:
    async with client_for(handled_app()) as client:
        response = await client.get("/no-such-route")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "about:blank",
        "title": "Not Found",
        "status": 404,
        "detail": "Not Found",
    }


async def test_exception_headers_survive() -> None:
    gated = FastAPI()
    install_problem_handlers(gated)

    @gated.get("/locked")
    async def locked() -> None:
        raise HTTPException(401, headers={"WWW-Authenticate": "Bearer"})

    async with client_for(gated) as client:
        response = await client.get("/locked")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["title"] == "Unauthorized"


async def test_validation_error_renders_problem_json() -> None:
    items = FastAPI()
    install_problem_handlers(items)

    @items.get("/items/{item_id}")
    async def read_item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    async with client_for(items) as client:
        response = await client.get("/items/not-a-number")
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["title"]
    assert body["status"] == 422
    assert body["detail"] == "Request validation failed."
    assert body["errors"][0]["loc"] == ["path", "item_id"]


async def test_problem_model_round_trips_validation_error() -> None:
    items = FastAPI()
    install_problem_handlers(items)

    @items.get("/items/{item_id}")
    async def read_item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    async with client_for(items) as client:
        body = (await client.get("/items/not-a-number")).json()
    problem = Problem.model_validate(body)
    assert problem.status == 422
    assert problem.model_dump() == body


def test_problem_responses_mapping_shape() -> None:
    responses = problem_responses(404, 409)
    assert set(responses) == {404, 409}
    assert "model" not in responses[404]
    assert responses[404]["description"] == "Not Found"
    assert responses[409]["description"] == "Conflict"
    content = responses[404]["content"]["application/problem+json"]
    assert content["schema"] == {"$ref": "#/components/schemas/Problem"}
    assert content["example"] == {
        "type": "about:blank",
        "title": "Not Found",
        "status": 404,
        "detail": "unknown or expired session",
    }


def test_validation_openapi_uses_problem() -> None:
    api = FastAPI()
    install_problem_handlers(api)

    @api.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @api.get("/items/{item_id}")
    async def read_item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    spec = api.openapi()
    responses = spec["paths"]["/items/{item_id}"]["get"]["responses"]
    assert set(responses["422"]["content"]) == {"application/problem+json"}
    assert responses["422"]["content"]["application/problem+json"]["schema"] == {
        "$ref": "#/components/schemas/ValidationProblem"
    }
    assert "422" not in spec["paths"]["/health"]["get"]["responses"]
    schemas = spec["components"]["schemas"]
    assert "errors" in schemas["ValidationProblem"]["properties"]
    assert "HTTPValidationError" not in schemas
    assert "ValidationError" not in schemas


def test_use_problem_for_validation_ignores_non_operations() -> None:
    schema = {"paths": {"/x": {"parameters": [], "get": {"responses": {"200": {}}}}}}
    result = _use_problem_for_validation(schema)
    assert result["paths"]["/x"]["get"]["responses"] == {"200": {}}
    assert "Problem" in result["components"]["schemas"]
    assert "ValidationProblem" not in result["components"]["schemas"]
