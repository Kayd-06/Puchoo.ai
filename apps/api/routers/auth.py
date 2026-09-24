"""Authentication router."""

from fastapi import APIRouter, Request, Response, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Dict, Any
from apps.api.session import session_manager
from apps.api.security import create_jwt_token, get_current_user
import random
from apps.api.email_service import send_otp_email

router = APIRouter(prefix="/auth", tags=["auth"])

class LoginRequest(BaseModel):
    identifier: str  # email or phone
    password: str

class SignupRequest(BaseModel):
    name: str
    identifier: str
    password: str
    account_type: str = "personal" # personal, business, institutional
    otp: str

class OTPRequest(BaseModel):
    identifier: str

class OTPVerifyRequest(BaseModel):
    identifier: str
    otp: str

def set_auth_cookie(response: Response, email: str):
    token = create_jwt_token({"sub": email})
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=False, # True in prod
        max_age=60 * 24 * 7 * 60 # 1 week
    )

@router.get("/me")
def get_current_user_endpoint(current_user: Dict[str, Any] = Depends(get_current_user)):
    return current_user

@router.post("/login")
def login(request: LoginRequest, response: Response):
    if not request.identifier or not request.password:
        raise HTTPException(status_code=400, detail="Identifier and password required")
    
    # Verify user exists in mock DB
    user = session_manager.get_user(request.identifier)
    if not user:
        # Mock auto-creation for ease of dev testing
        session_manager.add_user(request.identifier, request.identifier.split('@')[0], "personal")
        user = session_manager.get_user(request.identifier)
        
    set_auth_cookie(response, request.identifier)
    return {"message": "Logged in successfully", "profile": user}

@router.post("/signup")
def signup(request: SignupRequest, response: Response):
    if not request.identifier or not request.password or not request.name or not request.otp:
        raise HTTPException(status_code=400, detail="Name, identifier, password, and OTP required")
    
    if not session_manager.verify_otp(request.identifier, request.otp):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    if request.account_type not in ["personal", "business", "institutional"]:
        raise HTTPException(status_code=400, detail="Invalid account type")
        
    session_manager.add_user(request.identifier, request.name, request.account_type)
    user = session_manager.get_user(request.identifier)
    
    set_auth_cookie(response, request.identifier)
    return {"message": "Signed up successfully", "profile": user}

@router.post("/send-otp")
def send_otp(request: OTPRequest):
    if not request.identifier:
        raise HTTPException(status_code=400, detail="Identifier required")
    
    otp_code = f"{random.randint(100000, 999999)}"
    session_manager.set_otp(request.identifier, otp_code)
    
    if '@' in request.identifier:
        send_otp_email(request.identifier, otp_code)
    
    print(f"DEBUG: Generated OTP for {request.identifier}: {otp_code}")
    return {"message": "OTP sent successfully"}

@router.post("/verify-otp")
def verify_otp(request: OTPVerifyRequest, response: Response):
    if not request.identifier or not request.otp:
        raise HTTPException(status_code=400, detail="Identifier and OTP required")
    
    if not session_manager.verify_otp(request.identifier, request.otp):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    
    user = session_manager.get_user(request.identifier)
    if not user:
        session_manager.add_user(request.identifier, request.identifier.split('@')[0], "personal")
        user = session_manager.get_user(request.identifier)
        
    set_auth_cookie(response, request.identifier)
    return {"message": "OTP verified successfully", "profile": user}

@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("access_token")
    return {"message": "Logged out successfully"}
