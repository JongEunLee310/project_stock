from typing import Any

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.db.session import get_db
from app.domains.users.model import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    if token is None:
        raise AppException(
            status_code=401,
            detail="유효하지 않은 토큰입니다.",
            error_code=ErrorCode.AUTH_INVALID_TOKEN,
        )
    try:
        payload: dict[str, Any] = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        sub = payload.get("sub")
        if not isinstance(sub, str):
            raise AppException(
                status_code=401,
                detail="유효하지 않은 토큰입니다.",
                error_code=ErrorCode.AUTH_INVALID_TOKEN,
            )
        user_id = int(sub)
    except (JWTError, ValueError):
        raise AppException(
            status_code=401,
            detail="유효하지 않은 토큰입니다.",
            error_code=ErrorCode.AUTH_INVALID_TOKEN,
        )

    user = db.scalars(select(User).where(User.id == user_id)).first()
    if not user:
        raise AppException(
            status_code=401,
            detail="사용자를 찾을 수 없습니다.",
            error_code=ErrorCode.AUTH_USER_NOT_FOUND,
        )
    return user
