"""JWT authentication and password hashing."""

from __future__ import annotations


import logging

logger = logging.getLogger(__name__)
import asyncio
import hmac
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.database import DbAdapter
from app.audit import log_audit
from app.db.adapter import get_db
from app.repository import current_tenant_id

pwd_context = CryptContext(schemes=["argon2"], argon2__type="ID", deprecated="auto")
security = HTTPBearer()

# Admin usernames: built-in "admin" plus optional ADMIN_USERS env (comma-separated).
_admin_env = os.environ.get("ADMIN_USERS", "")
ADMIN_USERNAMES: set[str] = {"admin"} | {u.strip() for u in _admin_env.split(",") if u.strip()}
_LOGIN_FAILURE_LIMIT = 5
_LOGIN_LOCK_SECONDS = 15 * 60
_LOGIN_IP_FAILURE_LIMIT = 30
_LOGIN_FAILURES_BY_KEY: dict[str, tuple[int, float]] = {}
_ADMIN_BOOTSTRAP_LOCK = asyncio.Lock()


def _monotonic() -> float:
    return time.monotonic()


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
    to_encode.setdefault("jti", str(uuid.uuid4()))
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token."""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录凭证无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def is_access_token_revoked(db: DbAdapter, payload: dict) -> bool:
    """Check the append-only revocation marker for tokens carrying a JTI."""
    jti = payload.get("jti")
    family_id = payload.get("family_id")
    if not jti or not family_id:
        return False  # compatibility with tokens issued before JTI support
    return bool(await db.query_one(
        "SELECT id FROM audit_log WHERE tenant_id = ? AND entity_type = ? AND entity_id = ? LIMIT 1",
        (family_id, "token_revocation", jti),
    ))


async def _register_user_without_bootstrap(
    db: DbAdapter,
    username: str,
    password: str,
    display_name: str | None = None,
    *,
    consent_privacy: bool = False,
    consent_health_data: bool = False,
    birth_year: int | None = None,
) -> dict:
    """Register a new user. Returns user dict with token.

    Stores PIPL consent records (隐私同意 / 健康数据同意 / 同意日期) in
    ``users.settings`` JSON so the consent timeline is auditable.
    """
    # Check duplicate
    existing = await db.query_one(
        "SELECT id FROM users WHERE username = ?", (username,)
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户名已存在",
        )

    if not password or len(password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码至少8个字符",
        )

    user_id = str(uuid.uuid4())
    family_id = str(uuid.uuid4())
    password_hash = hash_password(password)

    # Build PIPL consent record stored in settings JSON (spec §12.2)
    settings_json = json.dumps(
        {
            "consent_privacy": consent_privacy,
            "consent_health_data": consent_health_data,
            "consent_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "birth_year": birth_year,
        },
        ensure_ascii=False,
    )

    # Create family
    await db.execute(
        "INSERT INTO families (id, name, owner_id) VALUES (?, ?, ?)",
        (family_id, f"{display_name or username}的家庭", user_id),
    )

    # Create user
    await db.execute(
        """INSERT INTO users (id, username, password_hash, display_name, family_id, settings)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, username, password_hash, display_name or username, family_id, settings_json),
    )

    # Create token — role must match what login would issue for the same
    # username (ADMIN_USERNAMES check), otherwise register-then-use tokens
    # and login tokens grant different privileges for the same account.
    token = create_access_token({
        "sub": user_id,
        "username": username,
        "family_id": family_id,
        "role": "admin" if username in ADMIN_USERNAMES else "user",
    })

    return {
        "id": user_id,
        "username": username,
        "display_name": display_name or username,
        "family_id": family_id,
        "role": "admin" if username in ADMIN_USERNAMES else "user",
        "access_token": token,
    }


async def register_user(
    db: DbAdapter,
    username: str,
    password: str,
    display_name: str | None = None,
    *,
    consent_privacy: bool = False,
    consent_health_data: bool = False,
    birth_year: int | None = None,
    admin_bootstrap_token: str | None = None,
) -> dict:
    """Register a user; privileged usernames require a one-time bootstrap token."""
    if username not in ADMIN_USERNAMES or os.environ.get("HOMEDOCTOR_TESTING") == "1":
        return await _register_user_without_bootstrap(
            db, username, password, display_name,
            consent_privacy=consent_privacy,
            consent_health_data=consent_health_data,
            birth_year=birth_year,
        )

    expected = settings.ADMIN_BOOTSTRAP_TOKEN
    if not expected or not admin_bootstrap_token or not hmac.compare_digest(
        expected, admin_bootstrap_token
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="管理员账号注册需要有效的引导令牌",
        )

    async with _ADMIN_BOOTSTRAP_LOCK:
        async with db.transaction():
            placeholders = ",".join("?" for _ in ADMIN_USERNAMES)
            existing_admin = await db.query_one(
                f"SELECT id FROM users WHERE username IN ({placeholders}) LIMIT 1",
                tuple(sorted(ADMIN_USERNAMES)),
            )
            bootstrap_used = await db.query_one(
                "SELECT id FROM audit_log WHERE tenant_id = ? AND entity_type = ? LIMIT 1",
                ("system", "admin_bootstrap"),
            )
            if existing_admin or bootstrap_used:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="管理员账号已初始化，不能再次使用引导令牌",
                )
            result = await _register_user_without_bootstrap(
                db, username, password, display_name,
                consent_privacy=consent_privacy,
                consent_health_data=consent_health_data,
                birth_year=birth_year,
            )
            await log_audit(
                db,
                tenant_id="system",
                action="bootstrap",
                entity_type="admin_bootstrap",
                entity_id=result["id"],
                changes={"username": username},
            )
            return result


async def authenticate_user(
    db: DbAdapter, username: str, password: str, client_ip: str = "unknown"
) -> dict:
    """Authenticate using per-source/account and per-source failure budgets.

    A username alone is never locked, so an attacker cannot deny service to a
    victim by deliberately failing that victim's login from another address.
    """
    now = _monotonic()
    pair_key = f"pair:{client_ip}:{username.casefold()}"
    ip_key = f"ip:{client_ip}"
    pair_count, pair_marker = _LOGIN_FAILURES_BY_KEY.get(pair_key, (0, 0.0))
    ip_count, ip_marker = _LOGIN_FAILURES_BY_KEY.get(ip_key, (0, 0.0))
    pair_locked_until = pair_marker if pair_count >= _LOGIN_FAILURE_LIMIT else 0.0
    ip_locked_until = ip_marker if ip_count >= _LOGIN_IP_FAILURE_LIMIT else 0.0
    if pair_locked_until > now or ip_locked_until > now:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="登录失败次数过多，请15分钟后重试；同一来源15分钟内累计失败30次也会锁定15分钟",
        )
    if pair_count and pair_marker <= now and (
        pair_count >= _LOGIN_FAILURE_LIMIT or pair_marker + _LOGIN_LOCK_SECONDS <= now
    ):
        _LOGIN_FAILURES_BY_KEY.pop(pair_key, None)
        pair_count = 0
    if ip_count and ip_marker <= now and (
        ip_count >= _LOGIN_IP_FAILURE_LIMIT or ip_marker + _LOGIN_LOCK_SECONDS <= now
    ):
        _LOGIN_FAILURES_BY_KEY.pop(ip_key, None)
        ip_count = 0

    def record_failure() -> None:
        current_pair_count, _ = _LOGIN_FAILURES_BY_KEY.get(pair_key, (0, 0.0))
        current_pair_count += 1
        _LOGIN_FAILURES_BY_KEY[pair_key] = (
            current_pair_count,
            now + _LOGIN_LOCK_SECONDS if current_pair_count >= _LOGIN_FAILURE_LIMIT else now,
        )
        current_ip_count, _ = _LOGIN_FAILURES_BY_KEY.get(ip_key, (0, 0.0))
        current_ip_count += 1
        _LOGIN_FAILURES_BY_KEY[ip_key] = (
            current_ip_count,
            now + _LOGIN_LOCK_SECONDS if current_ip_count >= _LOGIN_IP_FAILURE_LIMIT else now,
        )
        if len(_LOGIN_FAILURES_BY_KEY) > 10_000:
            for key, (_, expiry) in list(_LOGIN_FAILURES_BY_KEY.items()):
                if expiry and expiry <= now:
                    _LOGIN_FAILURES_BY_KEY.pop(key, None)
            while len(_LOGIN_FAILURES_BY_KEY) > 10_000:
                _LOGIN_FAILURES_BY_KEY.pop(next(iter(_LOGIN_FAILURES_BY_KEY)))

    user = await db.query_one("SELECT * FROM users WHERE username = ?", (username,))
    if not user or not verify_password(password, user["password_hash"]):
        record_failure()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    _LOGIN_FAILURES_BY_KEY.pop(pair_key, None)
    token = create_access_token({
        "sub": user["id"], "username": user["username"],
        "family_id": user["family_id"],
        "role": "admin" if user["username"] in ADMIN_USERNAMES else "user",
    })
    return {
        "id": user["id"], "username": user["username"],
        "display_name": user["display_name"], "family_id": user["family_id"],
        "role": "admin" if user["username"] in ADMIN_USERNAMES else "user",
        "access_token": token,
    }


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: DbAdapter = Depends(get_db),
) -> dict:
    """FastAPI dependency: extract and validate current user from JWT."""
    payload = decode_access_token(credentials.credentials)
    if (
        not getattr(request.state, "token_revocation_checked", False)
        and await is_access_token_revoked(db, payload)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录凭证已注销")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的认证凭据")
    middleware_checked = getattr(request.state, "token_revocation_checked", False)
    user = getattr(request.state, "user", None) if middleware_checked else None
    if user is not None and user.get("id") != user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token subject mismatch")
    if user is None:
        user = await db.query_one(
            "SELECT id, username, family_id FROM users WHERE id = ?", (user_id,)
        )
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号不存在或已注销")
    if payload.get("family_id") != user["family_id"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="stale token family claim; please sign in again",
        )
    # The database is authoritative even when this dependency is used without
    # the auth middleware's pre-validation path.
    current_tenant_id.set(user["family_id"])
    return {
        "id": user["id"],
        "username": user["username"],
        "family_id": user["family_id"],
        "role": payload.get("role", "user"),
    }


async def require_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """FastAPI dependency: require admin role."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return current_user
