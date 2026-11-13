import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from api.db import get_db
from api.settings import get_settings
from api.tables import User

_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(user: User) -> str:
    s = get_settings()
    exp = datetime.now(UTC) + timedelta(minutes=s.jwt_minutes)
    return jwt.encode({"sub": str(user.id), "exp": exp}, s.jwt_secret, algorithm="HS256")


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
                 db: Session = Depends(get_db)) -> User:
    if creds is None:
        raise HTTPException(401, "not logged in", headers={"WWW-Authenticate": "Bearer"})
    try:
        claims = jwt.decode(creds.credentials, get_settings().jwt_secret, algorithms=["HS256"])
        user = db.get(User, uuid.UUID(claims["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        user = None
    if user is None:
        raise HTTPException(401, "invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
    return user
