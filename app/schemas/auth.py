from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    name: str
    balance: str  # string to preserve decimal precision
    api_key: str | None = None  # gateway API key, only returned on registration


class UserMeResponse(BaseModel):
    user_id: str
    name: str
    email: str | None
    balance: str
    is_admin: bool
