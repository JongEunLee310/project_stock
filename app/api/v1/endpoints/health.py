from fastapi import APIRouter

router = APIRouter()


@router.get(
    "",
    summary="Health check",
    description="Return service health status without the common API envelope for monitoring compatibility.",
)
def health_check() -> dict[str, str]:
    return {"status": "ok"}
