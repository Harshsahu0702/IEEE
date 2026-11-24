from datetime import datetime, timedelta
from typing import Optional
import jwt
import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database.connection import get_db
from backend.database import crud
from backend.database.models import User
from backend.api.limiter import rate_limit_auth


router = APIRouter(prefix="/auth", tags=["Authentication"])
security = HTTPBearer(auto_error=False)


# ==========================================
# Schemas
# ==========================================

class UserRegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: Optional[str] = "operator"


class UserLoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


# ==========================================
# Helpers
# ==========================================

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    # Strip any accidental redundant 'Bearer ' prefix entered in Swagger UI
    if token.startswith("Bearer "):
        token = token.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

    user = crud.get_user_by_username(db, username=username)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


# ==========================================
# Endpoints
# ==========================================

@router.post("/register", response_model=TokenResponse)
def register(req: UserRegisterRequest, db: Session = Depends(get_db)):
    if crud.get_user_by_username(db, req.username):
        raise HTTPException(status_code=400, detail="Username already registered")
    if crud.get_user_by_email(db, req.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_pw = hash_password(req.password)
    user = crud.create_user(db, req.username, req.email, hashed_pw, req.role or "operator")

    access_token = create_access_token({"sub": user.username, "role": user.role, "id": user.id})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role
        }
    }


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(rate_limit_auth)])
def login(req: UserLoginRequest, db: Session = Depends(get_db)):
    user = crud.get_user_by_username(db, req.username)
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    is_default_pw = (user.username == "admin" and verify_password("admin123", user.hashed_password))

    access_token = create_access_token({"sub": user.username, "role": user.role, "id": user.id})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "is_default_password": is_default_pw
        }
    }


@router.get("/me")
def get_profile(current_user: User = Depends(get_current_user)):
    is_default_pw = (current_user.username == "admin" and verify_password("admin123", current_user.hashed_password))
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "role": current_user.role,
        "is_active": current_user.is_active,
        "is_default_password": is_default_pw,
        "created_at": current_user.created_at
    }


@router.post("/change-password")
def change_password(
    req: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Allow operator to update password and clear default credentials warning."""
    if not verify_password(req.old_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password incorrect")
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")

    current_user.hashed_password = hash_password(req.new_password)
    db.commit()
    return {"message": "Password updated successfully."}

