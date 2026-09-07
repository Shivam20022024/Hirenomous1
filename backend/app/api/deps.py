from fastapi import Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer
from typing import Optional
from app.core.auth import decode_access_token
from app.models.user import UserInDB
from app.core.database import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
        
    user_id: str = payload.get("sub")
    if user_id is None:
        raise credentials_exception
        
    db = get_db()
    user_data = await db["users"].find_one({"id": user_id})
    if user_data is None:
        raise credentials_exception
        
    return UserInDB(**user_data)

async def get_current_active_user(current_user: UserInDB = Depends(get_current_user)):
    if current_user.status != "active":
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

async def require_super_admin(current_user: UserInDB = Depends(get_current_active_user)):
    if current_user.role != "SUPER_ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation requires Super Admin privileges",
        )
    return current_user

# Dependency to handle Super Admin "View As Organization" capability
async def get_context_organization_id(
    current_user: UserInDB = Depends(get_current_active_user),
    x_view_as_org: Optional[str] = Header(None)
) -> str:
    if current_user.role == "SUPER_ADMIN" and x_view_as_org:
        return x_view_as_org
    
    if not current_user.organization_id and current_user.role != "SUPER_ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not belong to any organization",
        )
        
    return current_user.organization_id
