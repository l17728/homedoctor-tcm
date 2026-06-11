"""Auth router — register, login, me."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import authenticate_user, get_current_user, register_user
from app.database import DbAdapter, get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: dict, db: DbAdapter = Depends(get_db)):
    """Register a new user."""
    username = body.get("username")
    password = body.get("password")
    display_name = body.get("display_name")

    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="用户名和密码不能为空",
        )

    result = await register_user(db, username, password, display_name)
    token = result.pop("access_token")
    return {
        "user": result,
        "access_token": token,
        "token_type": "bearer",
    }


@router.post("/login")
async def login(body: dict, db: DbAdapter = Depends(get_db)):
    """Login with username and password."""
    username = body.get("username")
    password = body.get("password")

    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="用户名和密码不能为空",
        )

    result = await authenticate_user(db, username, password)
    token = result.pop("access_token")
    return {
        "user": result,
        "access_token": token,
        "token_type": "bearer",
    }


@router.get("/me")
async def me(current_user: dict = Depends(get_current_user)):
    """Get current user info."""
    return current_user
