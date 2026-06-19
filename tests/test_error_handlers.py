from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from app.core.exceptions import (
    AppException,
    app_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.error_codes import ErrorCode


def test_app_exception_handler_returns_error_envelope() -> None:
    test_app = FastAPI()
    test_app.add_exception_handler(AppException, app_exception_handler)

    @test_app.get("/duplicate")
    def duplicate() -> None:
        raise AppException(
            status_code=400,
            detail="이미 등록된 종목입니다.",
            error_code=ErrorCode.ASSET_DUPLICATE,
        )

    response = TestClient(test_app).get("/duplicate")

    assert response.status_code == 400
    assert response.json() == {
        "data": None,
        "message": "이미 등록된 종목입니다.",
        "error": {"code": "ASSET_DUPLICATE"},
        "meta": None,
    }


def test_validation_exception_handler_returns_fields() -> None:
    test_app = FastAPI()
    test_app.add_exception_handler(RequestValidationError, validation_exception_handler)

    @test_app.get("/items/{item_id}")
    def read_item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    response = TestClient(test_app).get("/items/not-an-int")

    assert response.status_code == 422
    body = response.json()
    assert body["data"] is None
    assert body["message"] == "요청 값이 올바르지 않습니다."
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert {"loc": ["path", "item_id"], "msg": "Input should be a valid integer, unable to parse string as an integer"} in body[
        "error"
    ]["fields"]
    assert body["meta"] is None


def test_unhandled_exception_handler_hides_internal_detail() -> None:
    test_app = FastAPI()
    test_app.add_exception_handler(Exception, unhandled_exception_handler)

    @test_app.get("/boom")
    def boom() -> None:
        raise RuntimeError("database password leaked")

    response = TestClient(test_app, raise_server_exceptions=False).get("/boom")

    assert response.status_code == 500
    assert response.json() == {
        "data": None,
        "message": "서버 오류가 발생했습니다.",
        "error": {"code": "INTERNAL_ERROR"},
        "meta": None,
    }
