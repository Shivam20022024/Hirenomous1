from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel
from app.core.database import get_db
from app.api.deps import get_context_organization_id
from app.models.job_ai_config import JobAIConfig, ScreeningQuestion
from app.services.prompt_engine import PromptEngine
import logging
import httpx
from app.core.config import settings

router = APIRouter(tags=["AI Recruiter"])
logger = logging.getLogger(__name__)

class AIConfigUpdateRequest(BaseModel):
    language: str
    tone: str
    voice: str
    screening_mode: str
    is_active: bool
    status: str
    screening_questions: List[dict]

@router.get("/ai-recruiter/{job_id}")
async def get_ai_config(job_id: str, org_id: str = Depends(get_context_organization_id)):
    db = get_db()
    config = await db.job_ai_config.find_one({"job_id": job_id, "organization_id": org_id})
    if not config:
        # Create default config if it doesn't exist
        default_config = JobAIConfig(job_id=job_id, organization_id=org_id)
        await db.job_ai_config.insert_one(default_config.model_dump())
        config = default_config.model_dump()
    
    config.pop('_id', None)
    return config

@router.put("/ai-recruiter/{job_id}")
async def update_ai_config(job_id: str, req: AIConfigUpdateRequest, org_id: str = Depends(get_context_organization_id)):
    db = get_db()
    
    questions = [ScreeningQuestion(**q).model_dump() for q in req.screening_questions]
    
    update_data = {
        "language": req.language,
        "tone": req.tone,
        "voice": req.voice,
        "screening_mode": req.screening_mode,
        "is_active": req.is_active,
        "status": req.status,
        "screening_questions": questions,
        "updated_at": datetime.utcnow().isoformat()
    }
    
    # Validation
    if req.status == "Active":
        db_job = await db.jobs_board.find_one({"id": job_id, "organization_id": org_id})
        missing = []
        if not db_job or not db_job.get("title"): missing.append("Job title")
        if not db_job or not db_job.get("description"): missing.append("Job description")
        if not questions: missing.append("Screening questions")
        if not req.language: missing.append("Language")
        if not req.tone: missing.append("Tone")
        if not req.voice: missing.append("Voice")
        
        if missing:
            raise HTTPException(status_code=400, detail=f"AI Recruiter setup incomplete. Missing: {', '.join(missing)}")

    result = await db.job_ai_config.update_one(
        {"job_id": job_id, "organization_id": org_id},
        {"$set": update_data},
        upsert=True
    )
    
    config = await db.job_ai_config.find_one({"job_id": job_id, "organization_id": org_id})
    if config:
        config.pop('_id', None)
    return config

@router.post("/ai-recruiter/{job_id}/generate-questions")
async def generate_ai_questions(job_id: str, org_id: str = Depends(get_context_organization_id)):
    db = get_db()
    job = await db.jobs_board.find_one({"id": job_id, "organization_id": org_id})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    questions = await PromptEngine.generate_screening_questions(
        job_title=job.get("title", ""),
        job_description=job.get("description", ""),
        skills=job.get("skills", []),
        experience=job.get("experience", "")
    )
    
    formatted_questions = [ScreeningQuestion(**q).model_dump() for q in questions]
    
    await db.job_ai_config.update_one(
        {"job_id": job_id, "organization_id": org_id},
        {"$set": {"screening_questions": formatted_questions, "updated_at": datetime.utcnow().isoformat()}},
        upsert=True
    )
    
    return {"questions": formatted_questions}

@router.get("/ai-recruiter/{job_id}/preview")
async def preview_ai_prompt(job_id: str, org_id: str = Depends(get_context_organization_id)):
    db = get_db()
    job = await db.jobs_board.find_one({"id": job_id, "organization_id": org_id})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    config = await db.job_ai_config.find_one({"job_id": job_id, "organization_id": org_id})
    if not config:
        config = JobAIConfig(job_id=job_id, organization_id=org_id).model_dump()
        
    prompt = PromptEngine.generate_prompt(job, config, company_name=settings.APP_NAME)
    return {"prompt": prompt}

class SimulateRequest(BaseModel):
    messages: List[dict]

@router.post("/ai-recruiter/{job_id}/simulate")
async def simulate_ai_recruiter(job_id: str, req: SimulateRequest, org_id: str = Depends(get_context_organization_id)):
    db = get_db()
    job = await db.jobs_board.find_one({"id": job_id, "organization_id": org_id})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    config = await db.job_ai_config.find_one({"job_id": job_id, "organization_id": org_id})
    if not config:
        config = JobAIConfig(job_id=job_id, organization_id=org_id).model_dump()
        
    system_prompt = PromptEngine.generate_prompt(job, config, candidate_name="Candidate", company_name=settings.APP_NAME)
    
    messages = [{"role": "system", "content": system_prompt}] + req.messages
    
    if not settings.OPENAI_API_KEY:
        return {"response": "[Simulation requires OPENAI_API_KEY] Hello, I am simulating the AI Recruiter."}
        
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "gpt-4o",
        "messages": messages,
        "temperature": 0.3
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            return {"response": content}
    except Exception as e:
        logger.error(f"Simulation failed: {e}")
        return {"response": "I'm sorry, I'm having trouble connecting to my simulator engine."}
