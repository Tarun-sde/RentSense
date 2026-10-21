import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, get_current_user, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, UserResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Auth"])

# Cookie name used for the session
COOKIE_NAME = "access_token"


@router.post("/login", response_model=UserResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """
    Authenticate with email + password.
    On success sets an HttpOnly session cookie and returns user info.
    """
    user = db.query(User).filter(User.email == payload.email, User.is_active.is_(True)).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        # ponytail: single generic message prevents email enumeration
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token(
        {"sub": user.id, "email": user.email, "role": user.role},
        expires_delta=timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    )

    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",          # lax allows GET redirects to carry cookie
        secure=settings.AUTH_COOKIE_SECURE if settings.AUTH_COOKIE_SECURE is not None else settings.ENVIRONMENT.lower() == "production",
        max_age=settings.JWT_EXPIRE_MINUTES * 60,
        path="/",
    )

    logger.info(f"Successful login for {user.email}")
    return UserResponse.model_validate(user)


@router.post("/logout")
def logout(response: Response):
    """Clear the session cookie."""
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"status": "logged_out"}


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    """Return the currently authenticated user."""
    return UserResponse.model_validate(current_user)
