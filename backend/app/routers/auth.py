"""Auth router — register, login, me, consent-status."""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import authenticate_user, get_current_user, register_user
from app.database import DbAdapter, get_db


import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: dict, db: DbAdapter = Depends(get_db)):
    """Register a new user with PIPL consent (spec §12.2)."""
    username = body.get("username")
    password = body.get("password")
    display_name = body.get("display_name")
    consent_privacy = body.get("consent_privacy", False)
    consent_health_data = body.get("consent_health_data", False)
    birth_year = body.get("birth_year")

    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="用户名和密码不能为空",
        )

    if not consent_privacy:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="请同意隐私政策",
        )

    if birth_year is not None:
        current_year = datetime.now(timezone.utc).year
        age = current_year - int(birth_year)
        if age < 14:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="未成年人需监护人确认",
            )

    result = await register_user(
        db,
        username,
        password,
        display_name,
        consent_privacy=consent_privacy,
        consent_health_data=consent_health_data,
        birth_year=birth_year,
    )
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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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


@router.get("/consent-status")
async def consent_status(
    current_user: dict = Depends(get_current_user),
    db: DbAdapter = Depends(get_db),
):
    """Get the PIPL consent record for the current user (spec §12.2)."""
    user = await db.query_one(
        "SELECT settings FROM users WHERE id = ?", (current_user["id"],)
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    settings_raw = user.get("settings") or "{}"
    try:
        settings = json.loads(settings_raw) if isinstance(settings_raw, str) else settings_raw
    except (json.JSONDecodeError, TypeError):
        settings = {}

    return {
        "consent_privacy": settings.get("consent_privacy", False),
        "consent_health_data": settings.get("consent_health_data", False),
        "consent_date": settings.get("consent_date"),
        "birth_year": settings.get("birth_year"),
    }
