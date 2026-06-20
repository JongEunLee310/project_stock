import pytest
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from app.core.pagination import PaginationParams, parse_sort
from tests.conftest import api_error


def test_pagination_params_defaults_and_offset_limit() -> None:
    pagination = PaginationParams()

    assert pagination.page == 1
    assert pagination.size == 20
    assert pagination.offset == 0
    assert pagination.limit == 20


def test_pagination_params_calculates_offset_from_page_and_size() -> None:
    pagination = PaginationParams(page=3, size=100)

    assert pagination.offset == 200
    assert pagination.limit == 100


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0, "size": 20},
        {"page": 1, "size": 101},
    ],
)
def test_pagination_params_reject_invalid_query_bounds(
    client: TestClient,
    params: dict[str, int],
) -> None:
    response = client.get("/api/v1/assets", params=params)

    assert response.status_code == 422
    assert api_error(response)["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize(
    ("raw_sort", "field", "direction", "value"),
    [
        ("priority", "priority", "asc", "priority"),
        ("-priority", "priority", "desc", "-priority"),
        (None, "created_at", "desc", "-created_at"),
    ],
)
def test_parse_sort_accepts_allowed_fields(
    raw_sort: str | None,
    field: str,
    direction: str,
    value: str,
) -> None:
    sort = parse_sort(
        raw_sort,
        allowed_fields={"priority", "created_at"},
        default="-created_at",
    )

    assert sort.field == field
    assert sort.direction == direction
    assert sort.value == value


def test_parse_sort_rejects_disallowed_field() -> None:
    with pytest.raises(RequestValidationError) as exc_info:
        parse_sort(
            "asset_id",
            allowed_fields={"priority", "created_at"},
            default="priority",
        )

    assert exc_info.value.errors() == [
        {
            "loc": ("query", "sort"),
            "msg": (
                "Input should be one of: "
                "-created_at, -priority, created_at, priority"
            ),
        }
    ]
