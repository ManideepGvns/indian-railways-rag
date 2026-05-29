from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from ..models import get_db, User
from ..core.security import verify_password, create_access_token, get_current_user_id, COOKIE_NAME
from ..core.config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    user_id: int
    is_admin: bool


class MeResponse(BaseModel):
    id: int
    username: str
    is_admin: bool


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username, User.is_active == True).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
    token = create_access_token({"sub": str(user.id)})

    settings = get_settings()
    # Set httpOnly cookie — not readable by JS (XSS-safe)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,          # Set to True behind HTTPS in production
        max_age=settings.jwt_expire_minutes * 60,
        path="/",
    )
    # Also return the token in the body so API clients / local dev can use Bearer
    return TokenResponse(access_token=token, username=user.username, user_id=user.id, is_admin=user.is_admin)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"message": "Logged out"}


@router.get("/me", response_model=MeResponse)
def me(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return MeResponse(id=user.id, username=user.username, is_admin=user.is_admin)
