"""Request and response models for account routes."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from backend.security import password_is_valid


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SignupRequest(RequestModel):
    full_name: str
    email: EmailStr
    password: str = Field(max_length=1_024)
    confirm_password: str = Field(max_length=1_024)
    workspace_type: Literal["personal", "business", "institution", "institute"]
    workspace_name: str | None = None
    invite_code: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_workspace_payload(cls, value: object) -> object:
        """Accept pre-role rollout signup clients without weakening new rules."""
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        if "workspace_name" not in payload and "institute_name" in payload:
            payload["workspace_name"] = payload.pop("institute_name")
        if "invite_code" not in payload and "institute_code" in payload:
            payload["invite_code"] = payload.pop("institute_code")
        return payload

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

    @field_validator("workspace_name")
    @classmethod
    def clean_workspace_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if len(cleaned) > 200:
            raise ValueError("Workspace name must be at most 200 characters.")
        return cleaned or None

    @model_validator(mode="after")
    def check_account(self):
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        if not password_is_valid(self.password):
            raise ValueError(
                "Password must be at least 10 characters and include a letter and a number."
            )
        if self.invite_code:
            self.invite_code = self.invite_code.strip()
            if len(self.invite_code) > 128:
                raise ValueError("Invite code is too long.")
        if self.workspace_type in {"business", "institution", "institute"} and not self.invite_code and not self.workspace_name:
            raise ValueError("Workspace name is required.")
        if self.workspace_type == "personal":
            self.workspace_name = None
        return self


class VerifyLoginRequest(RequestModel):
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
    def verification_code(cls, value: str) -> str:
        cleaned = value.strip()
        if cleaned.isdigit() and len(cleaned) == 6:
            return cleaned
        raise ValueError("Enter the 6-digit email code.")


class ResendOtpRequest(RequestModel):
    """Email is ignored. Resend is authorized by the login-challenge cookie."""

    email: EmailStr | None = None

    @field_validator("email", mode="before")
    @classmethod
    def lowercase_email(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value


class PasswordForgotRequest(RequestModel):
    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def lowercase_email(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value


class PasswordResetRequest(VerifyLoginRequest):
    password: str = Field(max_length=1_024)
    confirm_password: str = Field(max_length=1_024)

    @model_validator(mode="after")
    def valid_password(self):
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        if not password_is_valid(self.password):
            raise ValueError("Password must be at least 10 characters and include a letter and a number.")
        return self


class EmailChangeRequest(RequestModel):
    new_email: EmailStr
    current_password: str = Field(max_length=1_024)

    @field_validator("new_email", mode="before")
    @classmethod
    def lowercase_email(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("current_password")
    @classmethod
    def require_current_password(cls, value: str) -> str:
        if not value:
            raise ValueError("Enter your current password.")
        return value


class EmailChangeVerifyRequest(RequestModel):
    new_email: EmailStr
    code: str

    @field_validator("new_email", mode="before")
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


class OtpChallengeResponse(BaseModel):
    otp_required: bool = True
    email: str


class LoginRequest(RequestModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1_024)

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
    workspace_name: str | None = None
    workspace_owner_id: str | None = None
    workspace_role: str = "owner"


class InstituteInviteResponse(BaseModel):
    code: str
    workspace_name: str
    workspace_type: str
    role: str


class WorkspaceInviteRequest(RequestModel):
    role: Literal["admin", "editor", "viewer"] = "editor"


class WorkspaceMemberRoleRequest(RequestModel):
    role: Literal["admin", "editor", "viewer"]


class WorkspaceMemberResponse(BaseModel):
    id: str
    full_name: str
    email: str
    role: Literal["owner", "admin", "editor", "viewer"]


class AuthResponse(BaseModel):
    user: UserResponse
