from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.domains.users.model import User
from app.domains.users.repository import UserRepository
from app.domains.users.schema import Token, UserCreate, UserLogin

_INVALID_TOKEN_EXC = AppException(
    status_code=401,
    detail="유효하지 않은 토큰입니다.",
    error_code=ErrorCode.AUTH_INVALID_TOKEN,
)


class UserService:
    def __init__(self, db: Session) -> None:
        self.repo = UserRepository(db)

    def register(self, data: UserCreate) -> User:
        if self.repo.get_by_email(data.email):
            raise AppException(
                status_code=400,
                detail="이미 등록된 이메일입니다.",
                error_code=ErrorCode.USER_EMAIL_DUPLICATE,
            )
        return self.repo.create(
            email=data.email,
            hashed_password=hash_password(data.password),
        )

    def login(self, data: UserLogin) -> Token:
        user = self.repo.get_by_email(data.email)
        if not user or not verify_password(data.password, user.hashed_password):
            raise AppException(
                status_code=401,
                detail="이메일 또는 비밀번호가 올바르지 않습니다.",
                error_code=ErrorCode.AUTH_INVALID_CREDENTIALS,
            )
        expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        return Token(
            access_token=create_access_token(subject=user.id),
            refresh_token=create_refresh_token(subject=user.id),
            expires_in=expires_in,
        )

    def refresh(self, refresh_token: str) -> Token:
        from jose import JWTError

        try:
            payload = decode_token(refresh_token)
        except JWTError:
            raise _INVALID_TOKEN_EXC

        if payload.get("type") != "refresh":
            raise _INVALID_TOKEN_EXC

        sub = payload.get("sub")
        if not isinstance(sub, str):
            raise _INVALID_TOKEN_EXC

        try:
            user_id = int(sub)
        except ValueError:
            raise _INVALID_TOKEN_EXC

        user = self.repo.get_by_id(user_id)
        if not user:
            raise _INVALID_TOKEN_EXC

        expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        return Token(
            access_token=create_access_token(subject=user.id),
            expires_in=expires_in,
        )
