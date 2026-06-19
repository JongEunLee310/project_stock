from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.response import ApiResponse, success
from app.db.session import get_db
from app.domains.users.model import User
from app.domains.users.schema import Token, UserCreate, UserLogin, UserResponse
from app.domains.users.service import UserService

router = APIRouter()


@router.post(
    "/register",
    response_model=ApiResponse[UserResponse],
    status_code=201,
    summary="Register user",
    description="Create a user account with email and password.",
)
def register(data: UserCreate, db: Session = Depends(get_db)) -> ApiResponse[UserResponse]:
    return success(UserResponse.model_validate(UserService(db).register(data)))


@router.post(
    "/login",
    response_model=ApiResponse[Token],
    summary="Login user",
    description="Validate credentials and return a bearer access token.",
)
def login(data: UserLogin, db: Session = Depends(get_db)) -> ApiResponse[Token]:
    return success(UserService(db).login(data))


@router.get(
    "/me",
    response_model=ApiResponse[UserResponse],
    summary="Get current user",
    description="Return the authenticated user's profile.",
)
def get_me(current_user: User = Depends(get_current_user)) -> ApiResponse[UserResponse]:
    return success(UserResponse.model_validate(current_user))
