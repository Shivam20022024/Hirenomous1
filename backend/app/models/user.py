from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import uuid

class OrganizationBase(BaseModel):
    name: str
    status: str = "active"  # active, suspended

class OrganizationCreate(OrganizationBase):
    pass

class Organization(OrganizationBase):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True

class UserBase(BaseModel):
    name: str
    email: str
    role: str  # SUPER_ADMIN, ORGANIZATION_ADMIN, RECRUITER, HIRING_MANAGER
    organization_id: Optional[str] = None
    status: str = "active"

class UserCreate(UserBase):
    password: str

class UserInDB(UserBase):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    hashed_password: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class UserResponse(UserBase):
    id: str
    created_at: datetime
    updated_at: datetime
    organization_name: Optional[str] = None

    class Config:
        from_attributes = True
