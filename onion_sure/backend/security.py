"""
Security, Password Hashing, JWT Authentication, and RBAC
Smart India Hackathon 2026 - Problem Statement PS26031

Rules:
- Never commit secrets; all keys loaded from environment/settings.
- Bcrypt password hashing with secure salt.
- Short-lived JWT access tokens and verifiable refresh tokens.
- Role-Based Access Control (RBAC) dependency injection.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
import jwt
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models.entities import User, Role

ROLE_ALIASES = {
    "SUPER_ADMIN": {"SUPER_ADMIN", "ADMIN"},
    "ADMIN": {"ADMIN", "SUPER_ADMIN"},
    "CENTRE_ADMIN": {"CENTRE_ADMIN", "OFFICER"},
    "OPERATOR": {"OPERATOR"},
    "AUDITOR": {"AUDITOR", "REVIEWER"},
    "INSPECTOR": {"INSPECTOR"},
}

security_scheme = HTTPBearer(auto_error=False)


def normalize_role_name(role_name: Optional[str]) -> str:
    if role_name is None:
        return ""
    return role_name.strip().upper().replace("-", "_").replace(" ", "_")


def expand_role_aliases(role_names: List[str]) -> set[str]:
    expanded: set[str] = set()
    for raw_name in role_names:
        normalized = normalize_role_name(raw_name)
        if not normalized:
            continue
        expanded.add(normalized)
        for alias_group in ROLE_ALIASES.values():
            if normalized in alias_group:
                expanded.update(alias_group)
    return expanded


# ==============================================================================
# PASSWORD HASHING
# ==============================================================================

def hash_password(password: str) -> str:
    """Hashes plain password using bcrypt with random salt."""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies plain password against stored bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


# ==============================================================================
# JWT TOKEN GENERATION & DECODING
# ==============================================================================

def create_access_token(
    subject: str,
    roles: List[str],
    expires_delta: Optional[timedelta] = None,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """Generates a cryptographically signed JWT access token."""
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: Dict[str, Any] = {
        "sub": subject,
        "roles": roles,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(subject: str, expires_delta: Optional[timedelta] = None) -> str:
    """Generates a long-lived JWT refresh token."""
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )
    payload = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    """Decodes and validates JWT token signature and expiration."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ==============================================================================
# DEPENDENCIES: CURRENT USER & RBAC
# ==============================================================================

def get_current_user(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency to extract and verify authenticated user from Bearer token."""
    if not auth or not auth.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(auth.credentials)
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type for API access",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token claims",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User associated with token not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account",
        )

    return user


def get_current_active_user(user: User = Depends(get_current_user)) -> User:
    return user


class RequireRoles:
    """RBAC Guard dependency enforcing permitted roles."""

    def __init__(self, *allowed_roles: str):
        self.allowed_roles = [r.upper() for r in allowed_roles]

    def __call__(self, user: User = Depends(get_current_user)) -> User:
        if user.is_superuser:
            return user

        normalized_allowed = expand_role_aliases(self.allowed_roles)
        user_role_names = expand_role_aliases([r.name for r in user.roles])
        if not user_role_names & normalized_allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation requires one of permissions: {', '.join(self.allowed_roles)}",
            )
        return user
