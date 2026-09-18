from datetime import UTC, datetime, timedelta

from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import ApiError

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def create_access_token(user_id: int, ttl: timedelta | None = None) -> str:
    return _issue_token(user_id, "access", ttl or timedelta(days=settings.JWT_EXPIRE_DAYS))


def create_refresh_token(user_id: int, ttl: timedelta | None = None) -> str:
    return _issue_token(user_id, "refresh", ttl or timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS))


def _issue_token(user_id: int, token_type: str, ttl: timedelta) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": token_type,
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except ExpiredSignatureError:
        raise ApiError(ErrorCode.TOKEN_EXPIRED, "token 过期", 401) from None
    except JWTError:
        raise ApiError(ErrorCode.TOKEN_INVALID, "token 无效", 401) from None
