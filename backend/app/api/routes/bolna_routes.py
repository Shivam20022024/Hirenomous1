from fastapi import APIRouter, HTTPException, Request, Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.services.bolna_service import BolnaService
from app.core.database import get_db
from app.core.config import settings
from app.api.deps import get_context_organization_id
import logging
from datetime import datetime
from pydantic import BaseModel
from typing import Optional, List
class CallShortlistedRequest(BaseModel):
    job_ids: Optional[List[str]] = []
class BolnaCallbackRequest(BaseModel):
    candidate_id: str
    callback_date: str
    callback_time: str
    callback_notes: Optional[str] = ""

security = HTTPBearer()

def verify_callback_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verifies that the provided Bearer token matches BOLNA_CALLBACK_API_TOKEN."""
    expected_token = settings.BOLNA_CALLBACK_API_TOKEN
    
    if not expected_token:
        # If no token is configured in environment, fail secure
        logger.error("BOLNA_CALLBACK_API_TOKEN is not configured in the environment.")
        raise HTTPException(status_code=401, detail="Callback API token not configured")
        
    if credentials.credentials != expected_token:
        raise HTTPException(status_code=401, detail="Invalid callback API token")
        
    return credentials.credentials

router = APIRouter(prefix="/bolna", tags=["Bolna Integration"])
logger = logging.getLogger(__name__)

@router.post("/call-candidate/{candidate_id}")
async def call_candidate(candidate_id: str, org_id: str = Depends(get_context_organization_id)):
    """Initiates a Bolna.ai call for a specific candidate."""
    db = get_db()
    
    candidate = await db.candidates.find_one({"id": candidate_id, "organization_id": org_id})
    if not candidate:
        candidate = await db.candidates.find_one({"name": {"$regex": candidate_id.replace("-", " "), "$options": "i"}, "organization_id": org_id})

    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    phone_number = candidate.get("phone")
    if not phone_number:
        raise HTTPException(status_code=400, detail="Candidate missing phone number")

    try:
        call_result = await BolnaService.initiate_bolna_call(
            candidate_id=candidate_id, 
            phone_number=phone_number,
            candidate_name=candidate.get("name", ""),
            job_title=candidate.get("role", "Candidate")
        )
        
        if call_result["status"] != "success":
            raise Exception(call_result.get("message", "Bolna API failure"))

        data = call_result.get("data", {})
        bolna_call_id = data.get("call_id") or data.get("execution_id") or data.get("id") or data.get("executionId")
        
        await db.candidates.update_one(
            {"id": candidate_id},
            {"$set": {
                "status": "calling",
                "shortlisted": True,
                "bolna_call_id": bolna_call_id,
                "bolna_integrated": True,
                "call_started_at": datetime.utcnow(),
                "startedAt": datetime.utcnow().isoformat(),
                "last_interaction": datetime.utcnow(),
                "job_role": candidate.get("role") or "Candidate"
            }}
        )

        
        return {"status": "success", "call_id": bolna_call_id, "candidate": candidate["name"]}
    except Exception as e:
        logger.error(f"Failed to initiate Bolna call: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Bolna error: {str(e)}")

@router.post("/stop-call/{candidate_id}")
async def stop_candidate_call(candidate_id: str):
    """Marks a candidate's active call as cancelled."""
    db = get_db()
    candidate = await db.candidates.find_one({"id": candidate_id})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
        
    await db.candidates.update_one(
        {"id": candidate_id},
        {"$set": {
            "status": "cancelled",
            "last_interaction": datetime.utcnow()
        }}
    )
    return {"status": "success", "message": "Call stopped/cancelled"}

@router.post("/call-shortlisted")
async def call_shortlisted(request: Optional[CallShortlistedRequest] = None, org_id: str = Depends(get_context_organization_id)):
    """Initiates Bolna.ai calls for all shortlisted candidates."""
    db = get_db()
    query = {"resume_score": {"$gte": 70}, "status": "shortlisted", "organization_id": org_id}
    
    if request and request.job_ids:
        query["job_id"] = {"$in": request.job_ids}
        
    shortlisted = await db.candidates.find(query).to_list(length=100)
    
    called_ids = []
    called_phones = {} # Maps phone number to bolna_call_id
    results_by_job = {}
    
    for candidate in shortlisted:
        job_id = candidate.get("job_id", "unknown")
        job_title = candidate.get("role", "Candidate")
        
        if job_id not in results_by_job:
            results_by_job[job_id] = {
                "job_title": job_title,
                "shortlisted_found": 0,
                "calls_queued": 0,
                "failed": 0
            }
            
        results_by_job[job_id]["shortlisted_found"] += 1
        
        try:
            phone = candidate.get("phone")
            if not phone:
                continue
                
            if phone in called_phones:
                # Share the call ID with duplicate profiles to prevent simultaneous duplicate calls
                called_ids.append(candidate["id"])
                await db.candidates.update_one(
                    {"id": candidate["id"]},
                    {"$set": {
                        "status": "calling", 
                        "shortlisted": True,
                        "bolna_call_id": called_phones[phone],
                        "call_started_at": datetime.utcnow(),
                        "startedAt": datetime.utcnow().isoformat(),
                        "last_interaction": datetime.utcnow(),
                        "job_role": job_title
                    }}
                )
                results_by_job[job_id]["calls_queued"] += 1
                continue

            res = await BolnaService.initiate_bolna_call(
                candidate_id=candidate["id"], 
                phone_number=phone,
                candidate_name=candidate.get("name", ""),
                job_title=job_title
            )
            
            if res["status"] == "success":
                called_ids.append(candidate["id"])
                bolna_call_id = res["data"].get("call_id") or res["data"].get("execution_id") or res["data"].get("id")
                called_phones[phone] = bolna_call_id
                await db.candidates.update_one(
                    {"id": candidate["id"]},
                    {"$set": {
                        "status": "calling", 
                        "shortlisted": True,
                        "bolna_call_id": bolna_call_id,
                        "call_started_at": datetime.utcnow(),
                        "startedAt": datetime.utcnow().isoformat(),
                        "last_interaction": datetime.utcnow(),
                        "job_role": job_title
                    }}
                )
                results_by_job[job_id]["calls_queued"] += 1
            else:
                results_by_job[job_id]["failed"] += 1

        except Exception as e:
            logger.error(f"Failed to call {candidate['id']}: {str(e)}")
            results_by_job[job_id]["failed"] += 1

    return {
        "status": "success", 
        "called_count": len(called_ids), 
        "called_ids": called_ids,
        "results": [
            {"job_id": k, **v} for k, v in results_by_job.items()
        ]
    }

@router.post("/webhook")
async def bolna_webhook(request: Request):
    """Receives results from Bolna.ai."""
    try:
        payload = await request.json()
        logger.info("Received Bolna Webhook")
        result = await BolnaService.process_webhook_payload(payload)
        return result
    except Exception as e:
        logger.error(f"Bolna Webhook Error: {str(e)}")
        return {"status": "error", "message": str(e)}

@router.post("/callback")
async def bolna_callback_request(payload: BolnaCallbackRequest, token: str = Depends(verify_callback_token)):
    """Handles mid-conversation callback requests from Bolna Custom Functions."""
    try:
        if not payload.candidate_id or not payload.callback_date or not payload.callback_time:
            raise HTTPException(status_code=400, detail="Missing required callback fields")
            
        result = await BolnaService.handle_callback_request(payload)
        if not result.get("success"):
            raise HTTPException(status_code=404, detail="Candidate not found")
            
        return {"success": True, "status": "callback_required"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bolna Callback Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sync-call/{candidate_id}")
async def sync_candidate_call(candidate_id: str):
    """Manually syncs call data for a specific candidate from Bolna API."""
    return await BolnaService.fetch_bolna_call_details(candidate_id)

@router.post("/save-call-result/{candidate_id}")
async def save_call_result(candidate_id: str):
    """Manually triggers Excel storage for a candidate's call results."""
    db = get_db()
    candidate = await db.candidates.find_one({"id": candidate_id})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    from app.services.excel_service import ExcelService
    success = ExcelService.save_call_result_to_excel(candidate)
    
    return {"status": "success" if success else "error", "message": "Result saved to Excel" if success else "Failed to save to Excel"}

