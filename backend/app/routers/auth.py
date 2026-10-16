"""Auth router — register, login, me, consent-status."""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.auth import authenticate_user, get_current_user, register_user, security
from app.audit import log_audit
from app.database import DbAdapter, get_db
from app.models import LoginRequest, RegisterRequest
from app.middleware.rate_limit import RateLimitMiddleware


import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


def _coerce_birth_year(raw: int | str | None) -> int | None:
    """birth_year 必须是数字（int 或纯数字字符串），否则 400 中文报错。"""
    if raw is None:
        return None
    if isinstance(raw, int) and not isinstance(raw, bool):
        return raw
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip())
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="出生年份必须是数字（如 1958）",
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: DbAdapter = Depends(get_db)):
    """Register a new user with PIPL consent (spec §12.2)."""
    username = body.username
    password = body.password

    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="用户名和密码不能为空",
        )

    if not body.consent_privacy:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="请同意隐私政策",
        )

    birth_year = _coerce_birth_year(body.birth_year)
    if birth_year is not None:
        current_year = datetime.now(timezone.utc).year
        age = current_year - birth_year
        if age < 14:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="未成年人需监护人确认",
            )

    result = await register_user(
        db,
        username,
        password,
        body.display_name,
        consent_privacy=body.consent_privacy,
        consent_health_data=body.consent_health_data,
        birth_year=birth_year,
        admin_bootstrap_token=body.admin_bootstrap_token,
    )
    token = result.pop("access_token")
    return {
        "user": result,
        "access_token": token,
        "token_type": "bearer",
    }


@router.post("/login")
async def login(body: LoginRequest, request: Request, db: DbAdapter = Depends(get_db)):
    """Login with username and password."""
    if not body.username or not body.password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="用户名和密码不能为空",
        )

    result = await authenticate_user(
        db, body.username, body.password,
        RateLimitMiddleware._get_client_ip(request),
    )
    token = result.pop("access_token")
    return {
        "user": result,
        "access_token": token,
        "token_type": "bearer",
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    current_user: dict = Depends(get_current_user),
    credentials=Depends(security),
    db: DbAdapter = Depends(get_db),
):
    """Revoke the presented bearer token immediately."""
    from app.auth import decode_access_token

    payload = decode_access_token(credentials.credentials)
    jti = payload.get("jti")
    if jti:
        exists = await db.query_one(
            "SELECT id FROM audit_log WHERE tenant_id = ? AND entity_type = ? AND entity_id = ? LIMIT 1",
            (current_user["family_id"], "token_revocation", jti),
        )
        if not exists:
            await log_audit(
                db, tenant_id=current_user["family_id"], user_id=current_user["id"],
                action="revoke", entity_type="token_revocation", entity_id=jti,
            )


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
