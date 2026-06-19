from app.core.error_codes import ErrorCode
from app.core.response import error_response, paginated, success


def test_success_builds_api_response() -> None:
    response = success({"id": 1}, message="created")

    assert response.data == {"id": 1}
    assert response.message == "created"
    assert response.error is None
    assert response.meta is None


def test_paginated_builds_api_response_with_page_meta() -> None:
    response = paginated([{"id": 1}], page=2, size=10, total=25)

    assert response.data == [{"id": 1}]
    assert response.message is None
    assert response.error is None
    assert response.meta is not None
    assert response.meta.page == 2
    assert response.meta.size == 10
    assert response.meta.total == 25


def test_error_response_builds_api_response_with_code_and_fields() -> None:
    response = error_response(
        ErrorCode.VALIDATION_ERROR,
        message="요청 값이 올바르지 않습니다.",
        fields=[{"loc": ["body", "email"], "msg": "value is not a valid email"}],
    )

    assert response.data is None
    assert response.message == "요청 값이 올바르지 않습니다."
    assert response.error == {
        "code": "VALIDATION_ERROR",
        "fields": [{"loc": ["body", "email"], "msg": "value is not a valid email"}],
    }
    assert response.meta is None
