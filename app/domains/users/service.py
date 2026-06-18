from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.core.security import create_access_token, hash_password, verify_password
from app.domains.users.model import User
from app.domains.users.repository import UserRepository
from app.domains.users.schema import Token, UserCreate, UserLogin


class UserService:
    def __init__(self, db: Session) -> None:
        self.repo = UserRepository(db)

    def register(self, data: UserCreate) -> User:
        if self.repo.get_by_email(data.email):
            raise AppException(status_code=400, detail="이미 등록된 이메일입니다.")
        return self.repo.create(
            email=data.email,
            hashed_password=hash_password(data.password),
        )

    def login(self, data: UserLogin) -> Token:
        user = self.repo.get_by_email(data.email)
        if not user or not verify_password(data.password, user.hashed_password):
            raise AppException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")
        return Token(access_token=create_access_token(subject=user.id))
