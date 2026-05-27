"""
Auth wire formats. `LoginResponse` matches the body the frontend expects
from the Server Action / route handler.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    access_expires_at: datetime
    refresh_expires_at: datetime


class AuthenticatedUser(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    first_name: str
    last_name: str
    second_last_name: str | None = None
    active: bool
    roles: list[str]
    permissions: list[str]


class LoginResponse(BaseModel):
    success: bool = True
    tokens: TokenPair
    user: AuthenticatedUser
