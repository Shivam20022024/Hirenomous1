from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict
from app.core.database import get_db
from app.models.user import UserInDB, Organization, OrganizationCreate, UserCreate
from app.api.deps import require_super_admin
from app.core.auth import get_password_hash
from pydantic import BaseModel
from bson import ObjectId

class CreateCompanyRequest(BaseModel):
    company_name: str
    admin_name: str
    admin_email: str
    admin_password: str

router = APIRouter()

@router.get("/stats")
async def get_global_stats(current_user: UserInDB = Depends(require_super_admin)):
    db = get_db()
    
    total_companies = await db["organizations"].count_documents({})
    active_companies = await db["organizations"].count_documents({"status": "active"})
    suspended_companies = await db["organizations"].count_documents({"status": "suspended"})
    
    total_users = await db["users"].count_documents({})
    total_jobs = await db["jobs_board"].count_documents({})
    total_candidates = await db["candidates"].count_documents({})
    total_calls = await db["calls"].count_documents({})
    
    # Calculate call minutes (if duration_seconds exists)
    pipeline = [
        {"$group": {"_id": None, "total_seconds": {"$sum": "$duration_seconds"}}}
    ]
    cursor = db["calls"].aggregate(pipeline)
    call_duration_result = await cursor.to_list(length=1)
    
    total_call_minutes = 0
    if call_duration_result and call_duration_result[0].get("total_seconds"):
        total_call_minutes = round(call_duration_result[0]["total_seconds"] / 60)
        
    return {
        "total_companies": total_companies,
        "active_companies": active_companies,
        "suspended_companies": suspended_companies,
        "total_users": total_users,
        "total_jobs": total_jobs,
        "total_candidates": total_candidates,
        "total_calls": total_calls,
        "total_call_minutes": total_call_minutes
    }

@router.get("/requests")
async def get_access_requests(current_user: UserInDB = Depends(require_super_admin)):
    db = get_db()
    requests = []
    
    cursor = db["access_requests"].find().sort("created_at", -1)
    async for req in cursor:
        req["_id"] = str(req["_id"])
        # Do not expose hashed password
        req.pop("hashed_password", None)
        requests.append(req)
        
    return requests

@router.post("/requests/{req_id}/approve")
async def approve_access_request(req_id: str, current_user: UserInDB = Depends(require_super_admin)):
    db = get_db()
    
    req = await db["access_requests"].find_one({"_id": ObjectId(req_id)})
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
        
    if req.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Request is already processed")
        
    # Create Organization
    org_data = Organization(name=req["company"], status="active").dict()
    await db["organizations"].insert_one(org_data)
    org_id = org_data["id"]
    
    # Create Admin User using stored hashed password
    user_data = UserInDB(
        name=req["name"],
        email=req["email"],
        hashed_password=req["hashed_password"],
        role="COMPANY_ADMIN",
        organization_id=org_id,
        status="active"
    ).dict()
    await db["users"].insert_one(user_data)
    
    # Update request status
    await db["access_requests"].update_one(
        {"_id": ObjectId(req_id)},
        {"$set": {"status": "approved"}}
    )
    
    return {"message": "Request approved and account created successfully"}

@router.post("/requests/{req_id}/reject")
async def reject_access_request(req_id: str, current_user: UserInDB = Depends(require_super_admin)):
    db = get_db()
    
    req = await db["access_requests"].find_one({"_id": ObjectId(req_id)})
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
        
    # Update request status
    await db["access_requests"].update_one(
        {"_id": ObjectId(req_id)},
        {"$set": {"status": "rejected"}}
    )
    
    return {"message": "Request rejected"}

@router.get("/companies")
async def get_all_companies(current_user: UserInDB = Depends(require_super_admin)):
    db = get_db()
    companies = []
    
    # Find all organizations
    cursor = db["organizations"].find().sort("created_at", -1)
    async for org in cursor:
        org_id = org["id"]
        
        # Get usage stats for this organization
        users_count = await db["users"].count_documents({"organization_id": org_id})
        jobs_count = await db["jobs_board"].count_documents({"organization_id": org_id})
        candidates_count = await db["candidates"].count_documents({"organization_id": org_id})
        
        companies.append({
            "id": org_id,
            "name": org.get("name"),
            "status": org.get("status"),
            "created_at": org.get("created_at"),
            "stats": {
                "users": users_count,
                "jobs": jobs_count,
                "candidates": candidates_count
            }
        })
        
    return companies

@router.post("/companies")
async def create_company(request: CreateCompanyRequest, current_user: UserInDB = Depends(require_super_admin)):
    db = get_db()
    
    # Check if user already exists
    existing_user = await db["users"].find_one({"email": request.admin_email})
    if existing_user:
        raise HTTPException(status_code=400, detail="User with this email already exists")
        
    # Create Organization
    org_data = Organization(name=request.company_name, status="active").dict()
    await db["organizations"].insert_one(org_data)
    org_id = org_data["id"]
    
    # Create Admin User
    hashed_password = get_password_hash(request.admin_password)
    user_data = UserInDB(
        name=request.admin_name,
        email=request.admin_email,
        role="ORGANIZATION_ADMIN",
        organization_id=org_id,
        hashed_password=hashed_password
    ).dict()
    
    await db["users"].insert_one(user_data)
    
    # Remove ObjectId for JSON serialization
    org_data.pop("_id", None)
    
    return {
        "success": True,
        "organization": org_data,
        "admin_user": {
            "email": request.admin_email,
            "name": request.admin_name
        }
    }

@router.get("/users")
async def get_all_users(current_user: UserInDB = Depends(require_super_admin)):
    db = get_db()
    users = []
    
    # Pre-fetch organizations to map org_id to org_name
    orgs_cursor = db["organizations"].find()
    orgs_map = {}
    async for org in orgs_cursor:
        orgs_map[org["id"]] = org["name"]
        
    cursor = db["users"].find().sort("created_at", -1)
    async for user in cursor:
        org_id = user.get("organization_id")
        org_name = orgs_map.get(org_id, "N/A") if org_id else "N/A"
        
        users.append({
            "id": user.get("id"),
            "name": user.get("name"),
            "email": user.get("email"),
            "role": user.get("role"),
            "organization_name": org_name,
            "created_at": user.get("created_at")
        })
        
    return users
