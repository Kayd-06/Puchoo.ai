"""Request and response models for account routes."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator, model_validator

from backend.security import password_is_valid


class SignupRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    confirm_password: str
    workspace_type: Literal["personal", "institute"]
    institute_name: str | None = None
    institute_code: str | None = None

    @field_validator("email", mode="before")
    @classmethod
    def lowercase_email(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("full_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Enter your full name.")
        if len(cleaned) > 120:
            raise ValueError("Name must be at most 120 characters.")
        return cleaned

    @field_validator("institute_name")
    @classmethod
    def clean_institute(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if len(cleaned) > 200:
            raise ValueError("Institute name must be at most 200 characters.")
        return cleaned or None

    @model_validator(mode="after")
    def check_account(self):
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        if not password_is_valid(self.password):
            raise ValueError(
                "Password must be at least 10 characters and include a letter and a number."
            )
        if self.institute_code:
            self.institute_code = self.institute_code.strip()
        if self.workspace_type == "institute" and not self.institute_code:
            if not self.institute_name:
                raise ValueError("Institute name is required.")
        else:
            self.institute_name = None
        return self


class VerifyLoginRequest(BaseModel):
    email: EmailStr
    code: str

    @field_validator("email", mode="before")
    @classmethod
    def lowercase_email(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("code")
    @classmethod
    def six_digits(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) != 6 or not cleaned.isdigit():
            raise ValueError("Enter the 6-digit code from your email.")
        return cleaned


class ResendOtpRequest(BaseModel):
    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def lowercase_email(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value


class PasswordForgotRequest(ResendOtpRequest):
    pass


class PasswordResetRequest(VerifyLoginRequest):
    password: str
    confirm_password: str

    @model_validator(mode="after")
    def valid_password(self):
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        if not password_is_valid(self.password):
            raise ValueError("Password must be at least 10 characters and include a letter and a number.")
        return self


class OtpChallengeResponse(BaseModel):
    otp_required: bool = True
    email: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email", mode="before")
    @classmethod
    def lowercase_email(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    full_name: str
    email: str
    workspace_type: str
    institute_name: str | None = None
    institute_owner_id: str | None = None


class InstituteInviteResponse(BaseModel):
    code: str
    institute_name: str


class AuthResponse(BaseModel):
    user: UserResponse
