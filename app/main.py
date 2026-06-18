from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.exceptions import AppException, app_exception_handler

app = FastAPI(title="Project Stock API")

app.add_exception_handler(AppException, app_exception_handler)
app.include_router(api_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
