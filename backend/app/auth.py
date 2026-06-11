"""JWT authentication and password hashing."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.database import DbAdapter

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
security = HTTPBearer()


def hash_password(password: str) -> str:
    """Hash a password using Argon2id."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭据",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def register_user(
    db: DbAdapter, username: str, password: str, display_name: str | None = None
) -> dict:
    """Register a new user. Returns user dict with token."""
    # Check duplicate
    existing = await db.query_one(
        "SELECT id FROM users WHERE username = ?", (username,)
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户名已存在",
        )

    user_id = str(uuid.uuid4())
    family_id = str(uuid.uuid4())
    password_hash = hash_password(password)

    # Create family
    await db.execute(
        "INSERT INTO families (id, name, owner_id) VALUES (?, ?, ?)",
        (family_id, f"{display_name or username}的家庭", user_id),
    )

    # Create user
    await db.execute(
        """INSERT INTO users (id, username, password_hash, display_name, family_id)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, username, password_hash, display_name or username, family_id),
    )

    # Create token
    token = create_access_token({
        "sub": user_id,
        "username": username,
        "family_id": family_id,
    })

    return {
        "id": user_id,
        "username": username,
        "display_name": display_name or username,
        "family_id": family_id,
        "access_token": token,
    }


async def authenticate_user(
    db: DbAdapter, username: str, password: str
) -> dict:
    """Authenticate a user and return token."""
    user = await db.query_one(
        "SELECT * FROM users WHERE username = ?", (username,)
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    if not verify_password(password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    token = create_access_token({
        "sub": user["id"],
        "username": user["username"],
        "family_id": user["family_id"],
    })

    return {
        "id": user["id"],
        "username": user["username"],
        "display_name": user["display_name"],
        "family_id": user["family_id"],
        "access_token": token,
    }


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """FastAPI dependency: extract and validate current user from JWT."""
    payload = decode_access_token(credentials.credentials)
    return {
        "id": payload.get("sub"),
        "username": payload.get("username"),
        "family_id": payload.get("family_id"),
    }
