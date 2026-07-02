from pydantic import BaseModel, EmailStr, computed_field

from app.core.schema import UtcDatetime


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    email: str
    is_active: bool
    created_at: UtcDatetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def username(self) -> str:
        return self.email.split("@", maxsplit=1)[0]


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: str = ""
    expires_in: int = 0


class RefreshRequest(BaseModel):
    refresh_token: str
