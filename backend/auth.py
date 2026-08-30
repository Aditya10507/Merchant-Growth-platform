"""
auth.py
-------
Everything related to authentication and authorization lives here:
password hashing, JWT issuance/verification, the signup/login endpoints,
and the `get_current_merchant` dependency used to protect routes.

Security notes:
  - Passwords are never stored or logged in plaintext (bcrypt hash only).
  - JWTs are short-lived (see config.JWT_EXPIRY_MINUTES).
  - Login failures return a generic error so we don't leak whether an
    email exists in the system (prevents user enumeration).
"""

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from config import settings
from db import Merchant, get_db
from schemas import LoginRequest, SignupRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=True)


# ---------------------------------------------------------------------------
# Password + token helpers
# ---------------------------------------------------------------------------


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def create_access_token(merchant_id: int, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRY_MINUTES)
    payload = {"sub": str(merchant_id), "role": role, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired, please log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token")


# ---------------------------------------------------------------------------
# FastAPI dependency: resolves the current authenticated merchant
# ---------------------------------------------------------------------------


def get_current_merchant(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> Merchant:
    payload = decode_access_token(token)
    merchant = db.query(Merchant).filter(Merchant.id == int(payload["sub"])).first()
    if merchant is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Merchant not found")
    return merchant


def require_role(*allowed_roles: str):
    """Dependency factory for role-gated endpoints (e.g. reviewer-only routes)."""

    def _check(merchant: Merchant = Depends(get_current_merchant)) -> Merchant:
        if merchant.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return merchant

    return _check


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, db: Session = Depends(get_db)) -> TokenResponse:
    existing = db.query(Merchant).filter(Merchant.email == payload.email).first()
    if existing is not None:
        # Deliberately generic message — avoids confirming which emails are registered.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Could not create account with these details")

    merchant = Merchant(
        business_name=payload.business_name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role="merchant",
        onboarding_status="pending",
    )
    db.add(merchant)
    db.commit()
    db.refresh(merchant)

    token = create_access_token(merchant.id, merchant.role)
    return TokenResponse(
        access_token=token,
        merchant_id=merchant.id,
        business_name=merchant.business_name,
        role=merchant.role,
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    merchant = db.query(Merchant).filter(Merchant.email == payload.email).first()

    generic_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password"
    )

    if merchant is None or not verify_password(payload.password, merchant.password_hash):
        raise generic_error

    token = create_access_token(merchant.id, merchant.role)
    return TokenResponse(
        access_token=token,
        merchant_id=merchant.id,
        business_name=merchant.business_name,
        role=merchant.role,
    )
