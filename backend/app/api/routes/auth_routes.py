from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from app.core.auth import verify_password, create_access_token, get_password_hash
from app.models.user import UserResponse
from app.core.database import get_db
from app.api.deps import get_current_active_user
import uuid
from datetime import datetime, timedelta
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

class ForgotPasswordRequest(BaseModel):
    email: str

class RequestAccessRequest(BaseModel):
    name: str
    email: str
    company: str
    role: str
    password: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

router = APIRouter()

@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    db = get_db()
    # Find user by email
    user = await db["users"].find_one({"email": form_data.username})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if not await verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if user.get("status") != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )
        
    access_token = create_access_token(
        data={"sub": str(user["id"]), "role": user["role"], "org_id": user.get("organization_id")}
    )
    
    # Fetch org name for UI
    org_name = None
    if user.get("organization_id"):
        org = await db["organizations"].find_one({"id": user["organization_id"]})
        if org:
            org_name = org.get("name")
            
    user_response = UserResponse(**user).dict()
    user_response["organization_name"] = org_name

    # We return the standard OAuth2 token response
    return {"access_token": access_token, "token_type": "bearer", "user": user_response}


@router.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest):
    db = get_db()
    user = await db["users"].find_one({"email": request.email})
    
    if not user:
        # Return generic success message to prevent email enumeration
        return {"message": "If that email is in our system, we have sent a password reset link."}
        
    reset_token = str(uuid.uuid4())
    expiry = datetime.utcnow() + timedelta(hours=1)
    
    await db["users"].update_one(
        {"_id": user["_id"]},
        {"$set": {"reset_token": reset_token, "reset_token_expiry": expiry}}
    )
    
    from app.services.email_service import EmailService
    reset_link = f"http://localhost:5173/reset-password?token={reset_token}"
    
    # We'll also log it so it's easy to test locally
    logger.info(f"Password reset link for {request.email}: {reset_link}")
    
    try:
        await EmailService.send_password_reset_email(request.email, reset_link)
    except Exception as e:
        logger.error(f"Failed to send password reset email: {str(e)}")
        # Don't fail the request if email fails, just log it
    
    return {"message": "If that email is in our system, we have sent a password reset link."}

@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest):
    db = get_db()
    
    # Find user by reset token
    user = await db["users"].find_one({"reset_token": request.token})
    
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
        
    # Check expiry
    expiry = user.get("reset_token_expiry")
    if not expiry or datetime.utcnow() > expiry:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
        
    # Hash new password
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hashed_password = pwd_context.hash(request.new_password)
    
    # Update password and clear token
    await db["users"].update_one(
        {"_id": user["_id"]},
        {"$set": {"hashed_password": hashed_password}, "$unset": {"reset_token": "", "reset_token_expiry": ""}}
    )
    
    return {"message": "Password successfully reset. You can now log in."}

@router.post("/request-access")
async def request_access(request: RequestAccessRequest):
    db = get_db()
    
    # Check if already requested or exists
    existing = await db["users"].find_one({"email": request.email})
    if existing:
        raise HTTPException(status_code=400, detail="Account already exists for this email.")
        
    existing_request = await db["access_requests"].find_one({"email": request.email})
    if existing_request:
        raise HTTPException(status_code=400, detail="You have already requested access. We will be in touch soon.")
        
    request_data = request.dict()
    request_data["status"] = "pending"
    request_data["created_at"] = datetime.utcnow()
    
    # Hash password before storing in request
    raw_password = request_data.pop("password")
    request_data["hashed_password"] = get_password_hash(raw_password)
    
    await db["access_requests"].insert_one(request_data)
    
    logger.info(f"New access request received from {request.name} ({request.email}) at {request.company}")
    
    return {"message": "Request received successfully. We will review and grant access soon."}

@router.get("/me", response_model=UserResponse)
async def read_users_me(current_user = Depends(get_current_active_user)):
    db = get_db()
    user_dict = dict(current_user)
    if user_dict.get("organization_id"):
        org = await db["organizations"].find_one({"id": user_dict["organization_id"]})
        if org:
            user_dict["organization_name"] = org.get("name")
    return user_dict
