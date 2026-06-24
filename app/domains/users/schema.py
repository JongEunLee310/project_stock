from pydantic import BaseModel, EmailStr


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


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: str = ""
    expires_in: int = 0


class RefreshRequest(BaseModel):
    refresh_token: str
